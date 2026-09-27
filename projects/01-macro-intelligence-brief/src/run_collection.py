"""Manual entry point: collect, validate, calculate, report.

    export FRED_API_KEY="$(awk -F= '/^FRED_API_KEY=/{print $2}' ../../.env)"
    python3 -m src.run_collection

Run it from the project directory. It performs the only network access in this
project, and it is never invoked by the test suite.

Sequence, in order:

    official source -> raw snapshot -> boundary parsing -> normalised
    observations -> validation -> existing economic engine -> derived snapshot
    -> cross-check -> publication gate

The collector retrieves and normalises. It never calculates an economic
statistic: every figure comes from ``src.indicators``, which is unchanged.

Exit status is non-zero when the gate reports ``publication_ready = false``.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import pathlib
import subprocess
import sys
import uuid
from typing import Dict, Optional

from .errors import CollectionError
from .fred_client import (
    OBSERVATIONS_ENDPOINT,
    SERIES_ENDPOINT,
    SOURCE_NAME,
    FredClient,
    read_api_key,
)
from .indicators import SPECS, compute
from .brief_input import PublicationBlockedError, build_brief_input
from .normalisation import normalise_observations
from .provenance import RunProvenance, series_provenance_from
from .snapshot import write_json
from .validation import (
    FRED_COMPUTATIONAL_TOLERANCE_PP,
    Finding,
    ValidationReport,
    validate_derived,
    validate_metadata,
    validate_period_semantics,
    validate_series,
)

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "reference" / "phase2-first-real-run"

#: Observations requested per series. Comfortably above the engine's minimum so
#: that missing-value filtering cannot leave the series short.
FETCH_LIMITS: Dict[str, int] = {
    "CPIAUCNS": 24,   # engine needs 14
    "UNRATE": 12,     # engine needs 2
    "DFF": 40,        # engine needs 2; enough to observe the real calendar
    "GDPC1": 8,       # engine needs 3
    "RSAFS": 12,      # engine needs 3
}

#: Secondary cross-checks against FRED's own server-side transformations.
#: These are never the primary calculation. ``pc1`` is percent change from a
#: year ago; ``pca`` is the compounded annual rate of change, which for a
#: quarterly series is the annualised quarter-over-quarter growth rate.
CROSS_CHECK_UNITS: Dict[str, str] = {
    "CPIAUCNS": "pc1",
    "GDPC1": "pca",
}

#: Tolerance for the same-source computational cross-check, in percentage
#: points. Defined in src/validation.py alongside the reasoning, and
#: deliberately tight: both sides compute the same statistic from the same
#: observations. A disagreement beyond it is a HARD FAILURE.
CROSS_CHECK_TOLERANCE = FRED_COMPUTATIONAL_TOLERANCE_PP


def _git_commit(root: pathlib.Path) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def run(output_dir: pathlib.Path = DEFAULT_OUTPUT, *, client: Optional[FredClient] = None) -> int:
    api_key = None
    if client is None:
        api_key = read_api_key()
        client = FredClient(api_key)

    run_id = f"phase2-{_dt.datetime.now(_dt.timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    retrieved_at = _dt.datetime.now(_dt.timezone.utc)
    today = retrieved_at.date()

    report = ValidationReport(run_id=run_id, generated_at=retrieved_at)
    raw_dir = output_dir / "raw"
    derived_dir = output_dir / "derived"

    print(f"run_id         {run_id}")
    print(f"retrieved_at   {retrieved_at.isoformat()}")
    print(f"output         {output_dir}")
    print(f"source         {SOURCE_NAME}")
    print()

    requests_made = []
    derived_records = []
    series_provenance = {}

    for spec in SPECS.values():
        sid = spec.source_series
        limit = FETCH_LIMITS[sid]
        print(f"[{sid}] metadata + {limit} observations (units=lin) ...", end=" ")

        try:
            metadata = client.series_metadata(sid)
            raw_observations = client.observations(sid, limit=limit, units="lin")
        except CollectionError as exc:
            print("FAILED")
            report.add(Finding(
                code="collection.failed", severity="hard_failure", series_id=sid,
                message=f"{sid}: retrieval failed: {exc}",
            ))
            continue

        write_json(raw_dir / f"{sid}.metadata.json", metadata, secret=api_key)
        write_json(raw_dir / f"{sid}.observations.json", raw_observations, secret=api_key)
        requests_made.append(client.describe_request(SERIES_ENDPOINT, {"series_id": sid}))
        requests_made.append(client.describe_request(
            OBSERVATIONS_ENDPOINT,
            {"series_id": sid, "limit": str(limit), "sort_order": "desc", "units": "lin"},
        ))

        for finding in validate_period_semantics(spec):
            report.add(finding)
        for finding in validate_metadata(spec, metadata):
            report.add(finding)

        try:
            normalised = normalise_observations(raw_observations, sid)
        except CollectionError as exc:
            print("PARSE FAILED")
            report.add(Finding(
                code="normalisation.failed", severity="hard_failure", series_id=sid,
                message=f"{sid}: normalisation failed: {exc}",
            ))
            continue

        for finding in validate_series(spec, normalised, now=today, metadata=metadata):
            report.add(finding)
        report.series_results[sid] = normalised.summary()
        series_provenance[sid] = series_provenance_from(
            sid, metadata=metadata, normalised=normalised, source_name=SOURCE_NAME,
            raw_metadata_file=f"raw/{sid}.metadata.json",
            raw_observations_file=f"raw/{sid}.observations.json",
        )

        if normalised.valid_count < spec.minimum_history_required:
            print(f"INSUFFICIENT ({normalised.valid_count} valid)")
            continue

        try:
            observation = compute(spec.indicator_id, normalised.observations,
                                  retrieved_at=retrieved_at)
        except Exception as exc:
            print("TRANSFORM FAILED")
            report.add(Finding(
                code="transformation.failed", severity="hard_failure", series_id=sid,
                message=f"{sid}: transformation raised {type(exc).__name__}: {exc}",
            ))
            continue

        for finding in validate_derived(spec, observation):
            report.add(finding)
        derived_records.append(observation)

        print(f"ok  {normalised.valid_count} valid, "
              f"{normalised.missing_count} missing, "
              f"latest {normalised.latest_period}")

    # -- secondary cross-checks -------------------------------------------
    print()
    by_series = {o.source_series: o for o in derived_records}
    for sid, units in CROSS_CHECK_UNITS.items():
        entry = {
            "series_id": sid,
            "our_indicator_id": SPECS[[k for k, v in SPECS.items()
                                       if v.source_series == sid][0]].indicator_id,
            "fred_transformation": units,
            "fred_transformation_meaning": (
                "percent change from year ago" if units == "pc1"
                else "compounded annual rate of change"
            ),
            "role": "secondary cross-check only; never the primary calculation",
        }
        ours = by_series.get(sid)
        if ours is None:
            entry.update(status="unavailable", reason="no derived result for this series")
            report.cross_checks.append(entry)
            report.add(Finding(
                code="crosscheck.unavailable", severity="warning", series_id=sid,
                message=f"{sid}: cross-check skipped, no derived result",
            ))
            continue
        try:
            payload = client.observations(sid, limit=FETCH_LIMITS[sid], units=units)
            write_json(raw_dir / f"{sid}.crosscheck.{units}.observations.json",
                       payload, secret=api_key)
            requests_made.append(client.describe_request(
                OBSERVATIONS_ENDPOINT,
                {"series_id": sid, "limit": str(FETCH_LIMITS[sid]),
                 "sort_order": "desc", "units": units},
            ))
            transformed = normalise_observations(payload, sid)
            match = [o for o in transformed.observations if o.period == ours.period]
            if not match:
                entry.update(status="unavailable",
                             reason=f"no transformed observation for {ours.period}")
                report.add(Finding(
                    code="crosscheck.unavailable", severity="warning", series_id=sid,
                    message=(f"{sid}: FRED {units} has no observation for "
                             f"{ours.period}"),
                ))
            else:
                theirs = match[-1].value
                difference = ours.value - theirs
                agrees = abs(difference) <= CROSS_CHECK_TOLERANCE
                entry.update(
                    period=ours.period.isoformat(),
                    our_value=ours.value,
                    fred_value=theirs,
                    difference=difference,
                    tolerance=CROSS_CHECK_TOLERANCE,
                    status="agrees" if agrees else "disagrees",
                )
                report.add(Finding(
                    code="crosscheck.agrees" if agrees else "crosscheck.disagrees",
                    severity="pass" if agrees else "hard_failure",
                    series_id=sid,
                    message=(f"{sid} {ours.period}: ours {ours.value:.6f} vs FRED "
                             f"{units} {theirs:.6f}, difference "
                             f"{difference:+.6f} (tolerance "
                             f"{CROSS_CHECK_TOLERANCE})"),
                    detail={"our_value": ours.value, "fred_value": theirs,
                            "difference": difference},
                ))
                print(f"[{sid}] cross-check {units}: ours {ours.value:.4f} vs FRED "
                      f"{theirs:.4f} -> {entry['status']}")
        except CollectionError as exc:
            entry.update(status="unavailable", reason=str(exc))
            report.add(Finding(
                code="crosscheck.unavailable", severity="warning", series_id=sid,
                message=f"{sid}: cross-check could not be performed: {exc}",
            ))
        report.cross_checks.append(entry)

    # -- artefacts ---------------------------------------------------------
    manifest = {
        "run_id": run_id,
        "retrieved_at_utc": retrieved_at.isoformat(),
        "phase": "Phase 2 — first real data collection",
        "source_name": SOURCE_NAME,
        "source_base": "https://api.stlouisfed.org/fred",
        "endpoints_used": [SERIES_ENDPOINT, OBSERVATIONS_ENDPOINT],
        "series": sorted(spec.source_series for spec in SPECS.values()),
        "fetch_limits": FETCH_LIMITS,
        "primary_units": "lin (raw source values; no source-side transformation)",
        "cross_check_units": CROSS_CHECK_UNITS,
        "git_commit_before_run": _git_commit(PROJECT_ROOT),
        "requests": requests_made,
        "credential_policy": (
            "FRED_API_KEY is read from the process environment, is never written "
            "to disk, and is excluded from every stored request description. No "
            "URL is persisted."
        ),
        "notes": (
            "Raw payloads are stored exactly as received, including any "
            "missing-value sentinels, so every derived figure is traceable to "
            "what the source said at retrieval time."
        ),
    }
    write_json(output_dir / "manifest.json", manifest, secret=api_key)

    snapshot = {
        "run_id": run_id,
        "retrieved_at_utc": retrieved_at.isoformat(),
        "economy": "US",
        "source_name": SOURCE_NAME,
        "content": "derived macroeconomic statistics",
        "disclaimer": (
            "Data snapshot only. No forecast, no interpretation, no investment "
            "advice. Figures are computed by this project from the source series "
            "named in each record and must be verified against the primary "
            "release before any use."
        ),
        "observations": [o.to_display(value_dp=4, change_dp=4) for o in derived_records],
        "observations_full_precision": [
            {
                "indicator_id": o.indicator_id,
                "value": o.value,
                "previous_value": o.previous_value,
                "change": o.change,
            }
            for o in derived_records
        ],
    }
    write_json(derived_dir / "macro_snapshot.json", snapshot, secret=api_key)
    write_json(derived_dir / "validation_report.json", report.to_dict(), secret=api_key)

    # The brief input is produced only behind the publication gate.
    provenance = RunProvenance(
        run_id=run_id,
        retrieved_at=retrieved_at,
        source_name=SOURCE_NAME,
        snapshot_directory=str(output_dir.relative_to(PROJECT_ROOT)),
        git_commit=manifest["git_commit_before_run"],
        series=series_provenance,
    )
    try:
        brief = build_brief_input(derived_records, report, provenance,
                                 generated_at=retrieved_at)
        write_json(derived_dir / "brief_input.json", brief, secret=api_key)
        print()
        print(f"brief input written: {len(brief['indicators'])} indicators, "
              f"{len(brief['warnings'])} warning(s)")
    except PublicationBlockedError as exc:
        print()
        print(f"brief input NOT produced: {exc}")

    # -- summary -----------------------------------------------------------
    print()
    print("=" * 72)
    print(f"status            {report.status}")
    print(f"publication_ready {report.publication_ready}")
    print(f"hard failures     {len(report.hard_failures)}")
    print(f"warnings          {len(report.warnings)}")
    print(f"checks passed     {len(report.checks_passed)}")
    print(f"derived records   {len(derived_records)} of {len(SPECS)}")
    print("=" * 72)
    for finding in report.hard_failures:
        print(f"  HARD FAILURE  {finding.code}: {finding.message}")
    for finding in report.warnings:
        print(f"  WARNING       {finding.code}: {finding.message}")

    return 0 if report.publication_ready else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Collect, validate and compute the V1 macro indicators. "
                    "Performs live network access to the FRED API."
    )
    parser.add_argument(
        "--output-dir", type=pathlib.Path, default=DEFAULT_OUTPUT,
        help="directory for the run artefacts (default: %(default)s)",
    )
    args = parser.parse_args(argv)
    try:
        return run(args.output_dir)
    except CollectionError as exc:
        print(f"collection aborted: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
