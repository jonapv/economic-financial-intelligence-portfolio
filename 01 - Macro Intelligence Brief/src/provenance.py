"""Provenance: what a figure came from, and when.

Kept as a companion object rather than as extra fields on
:class:`~src.models.MacroObservation`. That model describes a *statistic*; this
one describes the *retrieval* behind it. Bundling them would force every
calculation to carry collection metadata it has no use for, and would make the
pure engine depend on how the data arrived.

The invariant this exists to guarantee:

    a sentence in a future brief must be traceable to the exact validated
    observation set used to produce it.

A vintage note that matters more than it appears to
---------------------------------------------------
**The latest available observation is not the latest economic period.** These
are different things and conflating them is how a brief ends up implying data
it does not have. A brief generated in late September 2026 legitimately
contains August CPI, August unemployment, a 24 September effective rate and
*second-quarter* GDP — because that is what has been published. The periods
differ by design and must never be normalised into a single fake "current"
period.

Each figure therefore carries its own ``period``, and separately the moment it
was ``retrieved_at``, and separately again the source's own ``last_updated``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class SeriesProvenance:
    """Where one series came from, and which stored files hold its raw payload."""

    series_id: str
    source_name: str
    source_last_updated: Optional[str]
    frequency: str
    seasonal_adjustment: Optional[str]
    earliest_period: Optional[str]
    latest_period: Optional[str]
    raw_count: int
    valid_count: int
    missing_count: int
    missing_dates: tuple = ()
    raw_metadata_file: Optional[str] = None
    raw_observations_file: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "series_id": self.series_id,
            "source_name": self.source_name,
            "source_last_updated": self.source_last_updated,
            "frequency": self.frequency,
            "seasonal_adjustment": self.seasonal_adjustment,
            "observation_window": {
                "earliest_period": self.earliest_period,
                "latest_period": self.latest_period,
            },
            "observation_counts": {
                "retrieved": self.raw_count,
                "valid": self.valid_count,
                "missing": self.missing_count,
                "missing_dates": list(self.missing_dates),
            },
            "raw_snapshot_files": {
                "metadata": self.raw_metadata_file,
                "observations": self.raw_observations_file,
            },
        }


@dataclass(frozen=True)
class RunProvenance:
    """Everything needed to identify and re-find one collection run."""

    run_id: str
    retrieved_at: datetime
    source_name: str
    snapshot_directory: str
    git_commit: Optional[str] = None
    series: Dict[str, SeriesProvenance] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "retrieved_at_utc": self.retrieved_at.isoformat(),
            "source_name": self.source_name,
            "raw_snapshot_directory": self.snapshot_directory,
            "git_commit_at_run": self.git_commit,
            "vintage_policy": (
                "Latest-vintage data. Each figure reports the most recently "
                "published value for its own period at retrieved_at. The latest "
                "AVAILABLE observation is not the latest economic period: "
                "indicators legitimately carry different periods, and these are "
                "never normalised to a common one."
            ),
            "reproducibility": (
                "Every figure is recomputable from the raw payloads stored in "
                "raw_snapshot_directory by the transformations in "
                "src/indicators.py. The stored run is a fixed record, not a "
                "live dataset."
            ),
            "series": {sid: sp.to_dict() for sid, sp in sorted(self.series.items())},
        }


def series_provenance_from(
    series_id: str,
    *,
    metadata: Dict[str, Any],
    normalised,
    source_name: str,
    raw_metadata_file: Optional[str] = None,
    raw_observations_file: Optional[str] = None,
) -> SeriesProvenance:
    """Assemble series provenance from live metadata and a normalised series.

    Only the metadata fields that describe provenance are carried over. The rest
    of the source payload (titles, popularity, notes, realtime windows) is left
    in the raw snapshot where it belongs.
    """
    summary = normalised.summary()
    return SeriesProvenance(
        series_id=series_id,
        source_name=source_name,
        source_last_updated=metadata.get("last_updated"),
        frequency=str(metadata.get("frequency", "")),
        seasonal_adjustment=metadata.get("seasonal_adjustment"),
        earliest_period=summary["earliest_period"],
        latest_period=summary["latest_period"],
        raw_count=summary["raw_count"],
        valid_count=summary["valid_count"],
        missing_count=summary["missing_count"],
        missing_dates=tuple(summary["missing_dates"]),
        raw_metadata_file=raw_metadata_file,
        raw_observations_file=raw_observations_file,
    )
