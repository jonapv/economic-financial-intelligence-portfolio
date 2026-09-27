"""Validation gate.

Decides whether a collected dataset may be published. Two severities, kept
strictly apart:

**Hard failures** mean the data is not what the specification says it is, or a
calculation did not produce a usable number. Any hard failure sets
``publication_ready = false`` and the pipeline must refuse to publish.

**Warnings** mean the data is usable but something is worth a human's attention
— most often that the latest observation is older than a generous tolerance.
Warnings never block publication and never remove an observation.

No economic forecasts and no anomaly thresholds are applied. This module checks
that data matches its declared specification; it does not judge whether an
economic figure is plausible.

Pure: ``now`` is passed in, no clock is read and no I/O is performed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Mapping, Optional

from .indicators import IndicatorSpec
from .models import Frequency, MacroObservation
from .normalisation import NormalisedSeries, observation_gaps

# ---------------------------------------------------------------------------
# Freshness tolerances
# ---------------------------------------------------------------------------
#: Deliberately generous, in calendar days. These are NOT release calendars:
#: the intent is only to notice a series that has plainly stopped updating, so
#: they are set well beyond any normal publication delay. Crossing one is a
#: warning, never a failure, and never removes an observation.
#:
#: The critical subtlety is that a period is labelled by its FIRST day. A
#: monthly observation for August is dated 1 August, so it is already ~31 days
#: "old" the moment the month ends and ~45-60 days old when published. A
#: quarterly observation for Q2 is dated 1 April and is ~120 days old at its
#: first (advance) estimate, reaching ~210 days just before the next quarter's
#: advance estimate appears. Tolerances must clear that whole cycle or they fire
#: on every healthy series.
#:
#: An earlier setting of 160 days for quarterly data did exactly that: it warned
#: on GDPC1 at 179 days when the series was perfectly current.
STALENESS_TOLERANCE_DAYS: Dict[Frequency, int] = {
    Frequency.DAILY: 10,        # DFF publishes every calendar day; 10 clears any holiday
    Frequency.MONTHLY: 95,      # label + month length (31) + publication lag (~45) + buffer
    Frequency.QUARTERLY: 220,   # label + quarter length (92) + lag to next advance (~120)
}

#: A gap between consecutive observations larger than this is described in the
#: report as unusual. For daily series a long weekend plus holidays is normal,
#: so the bar is set above that.
GAP_WARNING_DAYS: Dict[Frequency, int] = {
    Frequency.DAILY: 5,
    Frequency.MONTHLY: 40,
    Frequency.QUARTERLY: 100,
}

#: FRED's ``frequency_short`` codes, mapped to our enum.
FRED_FREQUENCY_CODES: Dict[str, Frequency] = {
    "D": Frequency.DAILY,
    "M": Frequency.MONTHLY,
    "Q": Frequency.QUARTERLY,
}

#: Our free-text ``seasonal_adjustment`` mapped to FRED's short code. A spec
#: that says "not applicable" is not checked against the source, because the
#: concept does not apply to the series.
_SA_EXPECTATIONS = {
    "not seasonally adjusted": "NSA",
    "seasonally adjusted": "SA",
    "seasonally adjusted annual rate": "SAAR",
}


def expected_sa_code(spec: IndicatorSpec) -> Optional[str]:
    """Derive the expected FRED seasonal-adjustment code from our spec text.

    Returns ``None`` when the spec declares the concept inapplicable, so that
    no hard check is imposed where none is meaningful.
    """
    return _SA_EXPECTATIONS.get(spec.seasonal_adjustment.strip().lower())


@dataclass
class Finding:
    """One validation result."""

    code: str
    severity: str  # "hard_failure" | "warning" | "pass"
    message: str
    series_id: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        out = {"code": self.code, "severity": self.severity, "message": self.message}
        if self.series_id:
            out["series_id"] = self.series_id
        if self.detail:
            out["detail"] = self.detail
        return out


@dataclass
class ValidationReport:
    """Structured outcome of the gate."""

    run_id: str
    generated_at: datetime
    findings: List[Finding] = field(default_factory=list)
    series_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    cross_checks: List[Dict[str, Any]] = field(default_factory=list)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    @property
    def hard_failures(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "hard_failure"]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def checks_passed(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "pass"]

    @property
    def publication_ready(self) -> bool:
        return not self.hard_failures

    @property
    def status(self) -> str:
        if self.hard_failures:
            return "failed"
        if self.warnings:
            return "passed_with_warnings"
        return "passed"

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at.isoformat(),
            "status": self.status,
            "publication_ready": self.publication_ready,
            "counts": {
                "hard_failures": len(self.hard_failures),
                "warnings": len(self.warnings),
                "checks_passed": len(self.checks_passed),
            },
            "hard_failures": [f.to_dict() for f in self.hard_failures],
            "warnings": [f.to_dict() for f in self.warnings],
            "checks": [f.to_dict() for f in self.findings],
            "series_results": self.series_results,
            "cross_checks": self.cross_checks,
        }


# ---------------------------------------------------------------------------
# Metadata checks
# ---------------------------------------------------------------------------

def validate_metadata(
    spec: IndicatorSpec, metadata: Mapping[str, Any]
) -> List[Finding]:
    """Compare live source metadata against our IndicatorSpec.

    Semantic comparisons against FRED's coded fields (``frequency_short``,
    ``seasonal_adjustment_short``) rather than its human-readable labels, which
    may be worded differently without any material disagreement.
    """
    findings: List[Finding] = []
    sid = spec.source_series

    # -- series identity --
    actual_id = str(metadata.get("id", "")).strip()
    if actual_id != sid:
        findings.append(Finding(
            code="metadata.series_id_mismatch", severity="hard_failure",
            series_id=sid,
            message=f"source returned metadata for {actual_id!r}, expected {sid!r}",
            detail={"expected": sid, "actual": actual_id},
        ))
    else:
        findings.append(Finding(
            code="metadata.series_id", severity="pass", series_id=sid,
            message=f"series id confirmed as {sid}",
        ))

    # -- frequency --
    code = str(metadata.get("frequency_short", "")).strip().upper()
    actual_frequency = FRED_FREQUENCY_CODES.get(code)
    if actual_frequency is None:
        findings.append(Finding(
            code="metadata.frequency_unrecognised", severity="hard_failure",
            series_id=sid,
            message=(f"{sid}: source frequency code {code!r} "
                     f"({metadata.get('frequency')!r}) is not one this project "
                     f"handles"),
            detail={"expected": spec.frequency.value, "actual_code": code,
                    "actual_label": metadata.get("frequency")},
        ))
    elif actual_frequency is not spec.frequency:
        findings.append(Finding(
            code="metadata.frequency_mismatch", severity="hard_failure",
            series_id=sid,
            message=(f"{sid}: specification declares {spec.frequency.value} but "
                     f"the source publishes {actual_frequency.value}"),
            detail={"expected": spec.frequency.value,
                    "actual": actual_frequency.value,
                    "actual_label": metadata.get("frequency")},
        ))
    else:
        findings.append(Finding(
            code="metadata.frequency", severity="pass", series_id=sid,
            message=f"{sid}: frequency confirmed as {actual_frequency.value}",
            detail={"source_label": metadata.get("frequency")},
        ))

    # -- seasonal adjustment --
    expected = expected_sa_code(spec)
    actual_sa = str(metadata.get("seasonal_adjustment_short", "")).strip().upper()
    if expected is None:
        findings.append(Finding(
            code="metadata.seasonal_adjustment_not_applicable", severity="pass",
            series_id=sid,
            message=(f"{sid}: specification declares seasonal adjustment "
                     f"inapplicable; source reports {actual_sa or 'nothing'} "
                     f"(recorded, not enforced)"),
            detail={"source_code": actual_sa,
                    "source_label": metadata.get("seasonal_adjustment")},
        ))
    elif actual_sa != expected:
        findings.append(Finding(
            code="metadata.seasonal_adjustment_mismatch", severity="hard_failure",
            series_id=sid,
            message=(f"{sid}: specification requires {expected} but the source "
                     f"reports {actual_sa!r} "
                     f"({metadata.get('seasonal_adjustment')!r})"),
            detail={"expected": expected, "actual": actual_sa,
                    "actual_label": metadata.get("seasonal_adjustment")},
        ))
    else:
        findings.append(Finding(
            code="metadata.seasonal_adjustment", severity="pass", series_id=sid,
            message=f"{sid}: seasonal-adjustment basis confirmed as {expected}",
            detail={"source_label": metadata.get("seasonal_adjustment")},
        ))

    return findings


# ---------------------------------------------------------------------------
# Series checks
# ---------------------------------------------------------------------------

def validate_series(
    spec: IndicatorSpec,
    series: NormalisedSeries,
    *,
    now: date,
    metadata: Optional[Mapping[str, Any]] = None,
) -> List[Finding]:
    """Check history sufficiency, ordering, freshness and gaps."""
    findings: List[Finding] = []
    sid = spec.source_series
    observations = series.observations

    # -- sufficient valid history --
    if series.valid_count < spec.minimum_history_required:
        findings.append(Finding(
            code="series.insufficient_history", severity="hard_failure",
            series_id=sid,
            message=(f"{sid}: {series.valid_count} valid observations after "
                     f"missing-value filtering, but the transformation requires "
                     f"{spec.minimum_history_required}"),
            detail={"valid": series.valid_count,
                    "required": spec.minimum_history_required,
                    "missing_filtered": series.missing_count},
        ))
        return findings  # further checks would be meaningless

    findings.append(Finding(
        code="series.sufficient_history", severity="pass", series_id=sid,
        message=(f"{sid}: {series.valid_count} valid observations, "
                 f"{spec.minimum_history_required} required"),
        detail={"valid": series.valid_count,
                "required": spec.minimum_history_required},
    ))

    # -- ordering and uniqueness (normalisation guarantees both; verify) --
    periods = [o.period for o in observations]
    if periods != sorted(periods):
        findings.append(Finding(
            code="series.not_ordered", severity="hard_failure", series_id=sid,
            message=f"{sid}: observations are not in chronological order",
        ))
    elif len(set(periods)) != len(periods):
        findings.append(Finding(
            code="series.duplicate_dates", severity="hard_failure", series_id=sid,
            message=f"{sid}: duplicate observation dates present",
        ))
    else:
        findings.append(Finding(
            code="series.ordered_unique", severity="pass", series_id=sid,
            message=f"{sid}: chronological, no duplicate dates",
        ))

    # -- latest period identifiable --
    latest = series.latest_period
    if latest is None:
        findings.append(Finding(
            code="series.no_latest_period", severity="hard_failure", series_id=sid,
            message=f"{sid}: no latest observation could be identified",
        ))
        return findings

    # -- freshness (warning only) --
    age = (now - latest).days
    tolerance = STALENESS_TOLERANCE_DAYS.get(spec.frequency)
    if tolerance is not None and age > tolerance:
        findings.append(Finding(
            code="series.stale", severity="warning", series_id=sid,
            message=(f"{sid}: latest observation {latest.isoformat()} is {age} "
                     f"calendar days old, beyond the {tolerance}-day "
                     f"{spec.frequency.value} tolerance. The observation is "
                     f"retained; verify against the release calendar."),
            detail={"latest_period": latest.isoformat(), "age_days": age,
                    "tolerance_days": tolerance},
        ))
    else:
        findings.append(Finding(
            code="series.fresh", severity="pass", series_id=sid,
            message=(f"{sid}: latest observation {latest.isoformat()} is {age} "
                     f"days old, within the {tolerance}-day tolerance"),
            detail={"latest_period": latest.isoformat(), "age_days": age,
                    "tolerance_days": tolerance},
        ))

    # -- unusual gaps (warning only, descriptive) --
    gap_bar = GAP_WARNING_DAYS.get(spec.frequency)
    if gap_bar is not None:
        large = [
            {"from": a.isoformat(), "to": b.isoformat(), "days": d}
            for a, b, d in observation_gaps(observations) if d > gap_bar
        ]
        if large:
            findings.append(Finding(
                code="series.unusual_gaps", severity="warning", series_id=sid,
                message=(f"{sid}: {len(large)} gap(s) longer than {gap_bar} days "
                         f"between consecutive observations"),
                detail={"threshold_days": gap_bar, "gaps": large[:10]},
            ))

    # -- source last_updated (warning only) --
    if metadata and metadata.get("last_updated"):
        findings.append(Finding(
            code="series.source_last_updated", severity="pass", series_id=sid,
            message=f"{sid}: source reports last_updated {metadata['last_updated']}",
            detail={"last_updated": str(metadata["last_updated"])},
        ))

    return findings


# ---------------------------------------------------------------------------
# Derived-result checks
# ---------------------------------------------------------------------------

def validate_derived(
    spec: IndicatorSpec, observation: MacroObservation
) -> List[Finding]:
    """Check that a computed result is internally consistent and finite."""
    import math

    findings: List[Finding] = []
    sid = spec.source_series

    finite = True
    for field_name in ("value", "previous_value", "change"):
        figure = getattr(observation, field_name)
        if not isinstance(figure, (int, float)) or math.isnan(figure) or math.isinf(figure):
            finite = False
            findings.append(Finding(
                code="derived.non_finite", severity="hard_failure", series_id=sid,
                message=f"{sid}: derived {field_name} is not finite ({figure!r})",
            ))

    if not finite:
        # The arithmetic and direction checks below assume finite figures. This
        # module must always report rather than raise, so stop here.
        return findings

    # change must equal value - previous_value, to float tolerance
    expected_change = observation.value - observation.previous_value
    if abs(expected_change - observation.change) > 1e-9:
        findings.append(Finding(
            code="derived.inconsistent_change", severity="hard_failure",
            series_id=sid,
            message=(f"{sid}: change {observation.change!r} does not equal "
                     f"value - previous_value ({expected_change!r})"),
        ))

    # direction must agree with the sign of change
    from .models import Direction
    if observation.direction is not Direction.from_change(observation.change):
        findings.append(Finding(
            code="derived.inconsistent_direction", severity="hard_failure",
            series_id=sid,
            message=(f"{sid}: direction {observation.direction.value!r} "
                     f"contradicts change {observation.change!r}"),
        ))

    # the source series on the result must be the one we specified
    if observation.source_series != spec.source_series:
        findings.append(Finding(
            code="derived.wrong_source_series", severity="hard_failure",
            series_id=sid,
            message=(f"derived result claims source {observation.source_series!r}, "
                     f"specification says {spec.source_series!r}"),
        ))

    if not findings:
        findings.append(Finding(
            code="derived.consistent", severity="pass", series_id=sid,
            message=(f"{sid}: derived result finite and internally consistent "
                     f"({observation.indicator_id})"),
        ))
    return findings
