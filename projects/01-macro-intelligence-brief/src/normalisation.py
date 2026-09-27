"""Normalisation boundary: raw FRED payloads to clean observations.

This is the single place where FRED's wire format becomes usable numbers. FRED
returns every observation value as a **string**, and uses ``"."`` for a missing
observation. Both are handled here and nowhere else, so that the deterministic
engine downstream can keep refusing strings outright.

Rules enforced here:

* ``"."`` is recognised as **missing**. It never becomes ``0``, ``NaN`` or an
  empty string. It is excluded from the series handed downstream, and the dates
  on which it occurred are reported so nothing disappears silently.
* Any other value that is not a finite number is a **hard error**. Unexpected
  data is never silently coerced.
* Dates must parse as ISO calendar dates.
* Duplicate observation dates are a hard error.
* Output is sorted oldest to newest, which every transformation assumes.

Pure: takes an already-decoded payload, performs no I/O.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any, List, Mapping, Sequence, Tuple

from .errors import SourcePayloadError
from .models import RawObservation

#: FRED's documented sentinel for an observation that does not exist.
MISSING_SENTINEL = "."


@dataclass(frozen=True)
class NormalisedSeries:
    """A cleaned series plus what was discarded on the way."""

    series_id: str
    observations: List[RawObservation]
    missing_dates: Tuple[date, ...] = ()
    raw_count: int = 0

    @property
    def valid_count(self) -> int:
        return len(self.observations)

    @property
    def missing_count(self) -> int:
        return len(self.missing_dates)

    @property
    def latest_period(self):
        return self.observations[-1].period if self.observations else None

    @property
    def earliest_period(self):
        return self.observations[0].period if self.observations else None

    def summary(self) -> dict:
        """Plain-dict summary for the validation report."""
        return {
            "series_id": self.series_id,
            "raw_count": self.raw_count,
            "valid_count": self.valid_count,
            "missing_count": self.missing_count,
            "missing_dates": [d.isoformat() for d in self.missing_dates],
            "earliest_period": self.earliest_period.isoformat() if self.observations else None,
            "latest_period": self.latest_period.isoformat() if self.observations else None,
        }


def _parse_date(raw: Any, series_id: str, index: int) -> date:
    if not isinstance(raw, str):
        raise SourcePayloadError(
            f"{series_id}: observation {index} has a non-string date "
            f"({type(raw).__name__})"
        )
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        raise SourcePayloadError(
            f"{series_id}: observation {index} has an unparseable date {raw!r}; "
            f"expected ISO YYYY-MM-DD"
        ) from None


def _parse_value(raw: Any, series_id: str, observed_on: date) -> float:
    """Convert one FRED value string to a float, or raise.

    Callers must check for :data:`MISSING_SENTINEL` before calling this.
    """
    if raw is None:
        raise SourcePayloadError(
            f"{series_id}: observation for {observed_on.isoformat()} has a null "
            f"value; FRED uses {MISSING_SENTINEL!r} for a missing observation, "
            f"not null"
        )
    if isinstance(raw, bool):
        raise SourcePayloadError(
            f"{series_id}: observation for {observed_on.isoformat()} is a bool"
        )
    if isinstance(raw, (int, float)):
        numeric = float(raw)
    elif isinstance(raw, str):
        text = raw.strip().replace(",", "")
        if not text:
            raise SourcePayloadError(
                f"{series_id}: observation for {observed_on.isoformat()} is an "
                f"empty string; FRED uses {MISSING_SENTINEL!r} for a missing "
                f"observation"
            )
        try:
            numeric = float(text)
        except ValueError:
            raise SourcePayloadError(
                f"{series_id}: observation for {observed_on.isoformat()} has a "
                f"malformed numeric value {raw!r}. Only a valid number or the "
                f"missing-value sentinel {MISSING_SENTINEL!r} is accepted; "
                f"values are never coerced."
            ) from None
    else:
        raise SourcePayloadError(
            f"{series_id}: observation for {observed_on.isoformat()} has type "
            f"{type(raw).__name__}, expected a numeric string"
        )

    if math.isnan(numeric) or math.isinf(numeric):
        raise SourcePayloadError(
            f"{series_id}: observation for {observed_on.isoformat()} is not "
            f"finite ({raw!r})"
        )
    return numeric


def normalise_observations(
    payload: Mapping[str, Any], series_id: str
) -> NormalisedSeries:
    """Turn a FRED observations payload into a chronological clean series."""
    raw_observations = payload.get("observations")
    if not isinstance(raw_observations, Sequence) or isinstance(
        raw_observations, (str, bytes)
    ):
        raise SourcePayloadError(
            f"{series_id}: payload has no 'observations' list"
        )

    kept: List[RawObservation] = []
    missing: List[date] = []
    seen: dict = {}

    for index, item in enumerate(raw_observations):
        if not isinstance(item, Mapping):
            raise SourcePayloadError(
                f"{series_id}: observation {index} is {type(item).__name__}, "
                f"expected an object"
            )
        if "date" not in item:
            raise SourcePayloadError(f"{series_id}: observation {index} has no 'date'")
        if "value" not in item:
            raise SourcePayloadError(f"{series_id}: observation {index} has no 'value'")

        observed_on = _parse_date(item["date"], series_id, index)

        if observed_on in seen:
            raise SourcePayloadError(
                f"{series_id}: duplicate observation date "
                f"{observed_on.isoformat()} (positions {seen[observed_on]} and "
                f"{index})"
            )
        seen[observed_on] = index

        value = item["value"]
        if isinstance(value, str) and value.strip() == MISSING_SENTINEL:
            missing.append(observed_on)
            continue

        kept.append(
            RawObservation(
                period=observed_on,
                value=_parse_value(value, series_id, observed_on),
            )
        )

    kept.sort(key=lambda obs: obs.period)
    missing.sort()

    return NormalisedSeries(
        series_id=series_id,
        observations=kept,
        missing_dates=tuple(missing),
        raw_count=len(raw_observations),
    )


def observation_gaps(series: Sequence[RawObservation]) -> List[Tuple[date, date, int]]:
    """Return ``(previous, next, day_gap)`` for each consecutive pair.

    Used to describe what a source's publication calendar actually does, rather
    than assuming it. No judgement is applied here.
    """
    return [
        (series[i - 1].period, series[i].period,
         (series[i].period - series[i - 1].period).days)
        for i in range(1, len(series))
    ]
