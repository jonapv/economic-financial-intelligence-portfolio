"""Rebuild the brief input from a stored run, offline.

    python3 -m src.build_brief_input [--run-dir data/reference/phase2-first-real-run]
                                     [--derived-dir derived]

Reads the raw payloads a previous run preserved, re-runs normalisation,
validation and the transformations, and writes ``derived/brief_input.json``.

**No network access.** This is deliberate, and it does two jobs at once:

* it produces the brief input for a run that predates the contract, and
* it demonstrates the reproducibility claim, because every figure is recomputed
  from the stored payloads rather than copied from the stored results.

Whenever ``derived/macro_snapshot.json`` is present, each recomputed figure is
compared against the recorded one at full precision and any mismatch aborts the
rebuild. A stored snapshot that cannot be reproduced from its own raw payloads
would mean the artefact is not what it claims to be.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys
from typing import Dict, List

from .brief_input import PublicationBlockedError, build_brief_input
from .errors import CollectionError
from .fred_client import SOURCE_NAME
from .indicators import SPECS, compute
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
DEFAULT_RUN_DIR = PROJECT_ROOT / "data" / "reference" / "phase2-first-real-run"
DEFAULT_DERIVED_DIR = PROJECT_ROOT / "derived"

#: Recomputed figures must match the stored ones to this absolute tolerance.
#: Not a tolerance for economic agreement — a guard against a stored artefact
#: that does not follow from its own raw payloads.
REPRODUCIBILITY_TOLERANCE = 1e-12


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def rebuild(run_dir: pathlib.Path, *,
            derived_dir: pathlib.Path = None, verbose: bool = True) -> int:
    manifest = _load(run_dir / "manifest.json")
    raw_dir = run_dir / "raw"
    derived_dir = derived_dir if derived_dir is not None else DEFAULT_DERIVED_DIR

    run_id = manifest["run_id"]
    retrieved_at = _dt.datetime.fromisoformat(manifest["retrieved_at_utc"])
    as_of = retrieved_at.date()

    if verbose:
        print(f"run_dir      {run_dir}")
        print(f"run_id       {run_id}")
        print(f"retrieved_at {retrieved_at.isoformat()}  (replayed, not refetched)")
        print()

    report = ValidationReport(run_id=run_id, generated_at=retrieved_at)
    provenance_series: Dict[str, object] = {}
    derived: List = []

    for spec in SPECS.values():
        sid = spec.source_series
        metadata = _load(raw_dir / f"{sid}.metadata.json")
        observations = _load(raw_dir / f"{sid}.observations.json")

        for finding in validate_period_semantics(spec):
            report.add(finding)
        for finding in validate_metadata(spec, metadata):
            report.add(finding)

        normalised = normalise_observations(observations, sid)
        for finding in validate_series(spec, normalised, now=as_of, metadata=metadata):
            report.add(finding)
        report.series_results[sid] = normalised.summary()
        provenance_series[sid] = series_provenance_from(
            sid, metadata=metadata, normalised=normalised, source_name=SOURCE_NAME,
            raw_metadata_file=f"raw/{sid}.metadata.json",
            raw_observations_file=f"raw/{sid}.observations.json",
        )

        observation = compute(spec.indicator_id, normalised.observations,
                              retrieved_at=retrieved_at)
        for finding in validate_derived(spec, observation):
            report.add(finding)
        derived.append(observation)
        if verbose:
            print(f"  {sid:<10} {observation.period}  value={observation.value!r}")

    # -- replay the stored cross-checks, offline --------------------------
    for path in sorted(raw_dir.glob("*.crosscheck.*.observations.json")):
        sid, _, units, _, _ = path.name.split(".")
        payload = _load(path)
        theirs_series = normalise_observations(payload, sid)
        ours = next((o for o in derived if o.source_series == sid), None)
        match = [o for o in theirs_series.observations if ours and o.period == ours.period]
        if ours is None or not match:
            report.add(Finding(
                code="crosscheck.unavailable", severity="warning", series_id=sid,
                message=f"{sid}: stored {units} cross-check has no matching period",
            ))
            continue
        theirs = match[-1].value
        difference = ours.value - theirs
        agrees = abs(difference) <= FRED_COMPUTATIONAL_TOLERANCE_PP
        report.add(Finding(
            code="crosscheck.agrees" if agrees else "crosscheck.disagrees",
            severity="pass" if agrees else "hard_failure", series_id=sid,
            message=(f"{sid} {ours.period}: ours {ours.value:.9f} vs source {units} "
                     f"{theirs:.9f}, difference {difference:+.3e} "
                     f"(tolerance {FRED_COMPUTATIONAL_TOLERANCE_PP})"),
            detail={"our_value": ours.value, "source_value": theirs,
                    "difference": difference, "units": units},
        ))
        report.cross_checks.append({
            "series_id": sid, "fred_transformation": units,
            "period": ours.period.isoformat(), "our_value": ours.value,
            "fred_value": theirs, "difference": difference,
            "tolerance": FRED_COMPUTATIONAL_TOLERANCE_PP,
            "tolerance_category": "same-source computational cross-check",
            "status": "agrees" if agrees else "disagrees",
            "role": "secondary cross-check only; never the primary calculation",
        })
        if verbose:
            print(f"  {sid:<10} cross-check {units}: diff {difference:+.3e} -> "
                  f"{'agrees' if agrees else 'DISAGREES'}")

    # -- reproducibility guard against the stored snapshot ----------------
    stored_path = derived_dir / "macro_snapshot.json"
    if stored_path.exists():
        stored = {r["indicator_id"]: r
                  for r in _load(stored_path)["observations_full_precision"]}
        mismatches = []
        for observation in derived:
            recorded = stored.get(observation.indicator_id)
            if recorded is None:
                mismatches.append(f"{observation.indicator_id}: absent from stored snapshot")
                continue
            for field in ("value", "previous_value", "change"):
                delta = abs(getattr(observation, field) - recorded[field])
                if delta > REPRODUCIBILITY_TOLERANCE:
                    mismatches.append(
                        f"{observation.indicator_id}.{field}: recomputed "
                        f"{getattr(observation, field)!r} vs stored "
                        f"{recorded[field]!r} (delta {delta:.3e})")
        if mismatches:
            print("\nREPRODUCIBILITY FAILURE — stored snapshot does not follow from "
                  "its own raw payloads:", file=sys.stderr)
            for m in mismatches:
                print(f"  {m}", file=sys.stderr)
            return 3
        if verbose:
            print(f"\n  reproducibility: all {len(derived)} figures recomputed from raw "
                  f"payloads match the stored snapshot exactly")

    # -- build the contract ----------------------------------------------
    provenance = RunProvenance(
        run_id=run_id, retrieved_at=retrieved_at, source_name=SOURCE_NAME,
        snapshot_directory=str(run_dir.relative_to(PROJECT_ROOT)),
        git_commit=manifest.get("git_commit_before_run"),
        series=provenance_series,
    )

    if verbose:
        print()
        print(f"status            {report.status}")
        print(f"publication_ready {report.publication_ready}")
        print(f"hard failures     {len(report.hard_failures)}")
        print(f"warnings          {len(report.warnings)}")
        for f in report.hard_failures:
            print(f"  HARD FAILURE  {f.code}: {f.message}")
        for f in report.warnings:
            print(f"  WARNING       {f.code}: {f.message}")

    try:
        brief = build_brief_input(
            derived, report, provenance,
            generated_at=_dt.datetime.now(_dt.timezone.utc),
        )
    except PublicationBlockedError as exc:
        print(f"\nbrief input NOT produced: {exc}", file=sys.stderr)
        return 1

    write_json(derived_dir / "brief_input.json", brief)
    write_json(derived_dir / "validation_report.json", report.to_dict())
    if verbose:
        print()
        print(f"written: {derived_dir / 'brief_input.json'}")
        print(f"         {len(brief['indicators'])} indicators, "
              f"{len(brief['warnings'])} warning(s), "
              f"schema {brief['schema_version']}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild brief_input.json from a stored run. No network access."
    )
    parser.add_argument("--run-dir", type=pathlib.Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--derived-dir", type=pathlib.Path, default=DEFAULT_DERIVED_DIR)
    args = parser.parse_args(argv)
    try:
        return rebuild(args.run_dir, derived_dir=args.derived_dir)
    except (CollectionError, OSError, KeyError, ValueError) as exc:
        print(f"rebuild failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
