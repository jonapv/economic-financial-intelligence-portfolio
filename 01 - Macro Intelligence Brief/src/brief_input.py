"""The brief input contract.

``brief_input.json`` is the **only** structured economic input that a future
synthesis layer is permitted to receive. It is assembled from three things and
nothing else:

* validated :class:`~src.models.MacroObservation` records,
* the :class:`~src.validation.ValidationReport` for the run,
* the :class:`~src.provenance.RunProvenance` for the run.

It is never built from raw source payloads. Anything a prose layer might need
must therefore have survived validation first, which is the point: the model
cannot reach around the gate to the unvalidated data.

Two invariants
--------------
**Publication invariant.** The artefact is produced only when
``publication_ready`` is true. On a hard failure, :func:`build_brief_input`
raises and nothing is written. A language model must never get the opportunity
to write fluent prose about invalid figures — fluency is precisely what makes a
wrong figure dangerous.

**Period presentation.** Each indicator carries both the canonical ``period``
and a deterministically generated ``period_label``. Prose must use the label.
The canonical date stays for traceability and is never reinterpreted.

**Warning propagation.** Machine-generated warnings are carried through in
structured form. The future prose layer may *explain* a warning; it may not
suppress one, and it is never asked to invent or infer data-quality caveats of
its own.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Sequence

from .errors import CollectionError, InvalidPeriodError
from .indicators import SPECS
from .models import MacroObservation
from .periods import period_label
from .presentation import presentation_for
from .provenance import RunProvenance
from .validation import ValidationReport

#: Bump when the structure changes in a way a consumer must notice.
SCHEMA_VERSION = "1.0"

#: Fields carried per indicator. Nothing else is included: no raw payload
#: fields, no credentials, no prose, no forecast, no interpretation.
INDICATOR_FIELDS = (
    "indicator_id",
    "display_name",
    "economic_category",
    "period",
    "period_label",
    "frequency",
    "value",
    "unit",
    "previous_value",
    "change",
    "change_unit",
    "direction",
    "source_series",
    "source_name",
    "source_last_updated",
    "retrieved_at",
    "validation_status",
    "presentation",
)


class PublicationBlockedError(CollectionError):
    """Refused to build a brief input because the validation gate did not pass."""


def _indicator_entry(
    observation: MacroObservation,
    provenance: RunProvenance,
    report: ValidationReport,
) -> Dict[str, Any]:
    spec = SPECS[observation.indicator_id]
    series_prov = provenance.series.get(observation.source_series)
    series_findings = [
        f for f in report.findings
        if f.series_id == observation.source_series and f.severity != "pass"
    ]
    return {
        "indicator_id": observation.indicator_id,
        "display_name": observation.display_name,
        "economic_category": spec.economic_category,
        "period": observation.period.isoformat(),
        "period_label": period_label(observation.period, observation.frequency),
        "frequency": observation.frequency.value,
        "value": observation.value,
        "unit": observation.unit.value,
        "previous_value": observation.previous_value,
        "change": observation.change,
        "change_unit": observation.change_unit.value,
        "direction": observation.direction.value,
        "comparison_basis": spec.comparison,
        "period_selection": spec.period_selection.value,
        "transformation": spec.transformation,
        "source_series": observation.source_series,
        "source_name": observation.source_name,
        "source_last_updated": series_prov.source_last_updated if series_prov else None,
        "retrieved_at": observation.retrieved_at.isoformat(),
        "validation_status": "validated" if not any(
            f.severity == "hard_failure" for f in series_findings
        ) else "failed",
        "warning_codes": sorted({f.code for f in series_findings if f.severity == "warning"}),
        "known_revision_risk": spec.known_revision_risk,
        # Deterministic presentation strings. The model must quote these
        # verbatim and is never asked to round anything itself.
        "presentation": presentation_for(spec, observation),
    }


def build_brief_input(
    observations: Sequence[MacroObservation],
    report: ValidationReport,
    provenance: RunProvenance,
    *,
    generated_at: datetime,
) -> Dict[str, Any]:
    """Assemble the brief input, or refuse.

    Raises :class:`PublicationBlockedError` when the gate has not passed, or
    when the run produced fewer derived records than there are specified
    indicators.
    """
    if not report.publication_ready:
        raise PublicationBlockedError(
            f"refusing to build a brief input: validation status is "
            f"{report.status!r} with {len(report.hard_failures)} hard failure(s). "
            f"No usable economic input may be produced from data that did not "
            f"pass the gate."
        )
    if len(observations) != len(SPECS):
        raise PublicationBlockedError(
            f"refusing to build a brief input: {len(observations)} derived "
            f"record(s) for {len(SPECS)} specified indicators. A partial set "
            f"would invite a brief that silently omits an indicator."
        )

    try:
        indicators = [
            _indicator_entry(obs, provenance, report)
            for obs in sorted(observations, key=lambda o: o.indicator_id)
        ]
    except InvalidPeriodError as exc:
        # A period that cannot be labelled deterministically would force the
        # prose layer to guess, which is the ambiguity this contract removes.
        raise PublicationBlockedError(
            f"refusing to build a brief input: {exc}"
        ) from None

    warnings: List[Dict[str, Any]] = [
        {
            "code": f.code,
            "series_id": f.series_id,
            "message": f.message,
            "detail": f.detail or {},
        }
        for f in report.warnings
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": report.run_id,
        "generated_at": generated_at.isoformat(),
        "publication_ready": True,
        "economy": "US",
        "content": "validated derived macroeconomic statistics",
        "indicator_count": len(indicators),
        "indicators": indicators,
        "warnings": warnings,
        "provenance": provenance.to_dict(),
        "period_note": (
            "Indicators carry different periods by design. The latest available "
            "observation is not the latest economic period: monthly series may "
            "report a month that closed weeks ago, quarterly series a quarter "
            "that closed months ago, and a daily series yesterday. These are not "
            "normalised to a common period and must not be presented as though "
            "they were."
        ),
        "period_field_contract": {
            "period": (
                "Canonical machine-readable source period, required for "
                "traceability. It is the date the source assigns to the "
                "observation, which for monthly and quarterly series is the "
                "FIRST day of the period covered."
            ),
            "period_label": (
                "The human-readable form of the same period, derived "
                "deterministically from period plus the declared frequency. "
                "MUST be used when referring to an observation period in prose."
            ),
            "frequency": "The declared frequency the label was derived from.",
            "why": (
                "The canonical date is unambiguous to a machine and ambiguous to "
                "a reader. On a quarterly series 2026-04-01 means 2026 Q2, NOT "
                "'April GDP'. On a monthly series 2026-08-01 means August 2026, "
                "NOT activity on the first of the month. A prose layer must not "
                "be left to infer either."
            ),
        },
        "usage_contract": {
            "may": [
                "describe each figure using the presentation display strings, "
                "the unit, the period_label and the direction given",
                "state the comparison basis and the source series",
                "explain a warning that is present in this file",
            ],
            "must_not": [
                "compute, adjust, infer or recall any economic statistic",
                "reinterpret the canonical period date, or use it in prose in "
                "place of period_label",
                "present figures from different periods as a single common period",
                "suppress or omit a warning present in this file",
                "add a forecast, a market call or investment advice",
                "introduce any figure not present in this file",
                "round, reformat or recompute any figure — use the presentation "
                "display strings exactly as given",
            ],
        },
        "disclaimer": (
            "Data snapshot. No forecast, no interpretation, no investment advice. "
            "Every figure was computed by this project from the source series "
            "named, and must be verified against the primary release before use."
        ),
    }
