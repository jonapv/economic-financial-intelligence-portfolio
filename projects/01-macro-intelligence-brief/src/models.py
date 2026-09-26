"""Data model for raw and derived macroeconomic observations.

Minimal by intent: two frozen dataclasses and three small enumerations. There
is no ORM, no registry of registries and no plugin system — just enough
structure to make a derived figure carry its own provenance and units.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from .calculations import DIRECTION_TOLERANCE, require_number
from .errors import MissingValueError, NonNumericValueError


class Frequency(str, Enum):
    """Observation frequency of a source series."""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class Unit(str, Enum):
    """Unit of a value or of a change.

    Keeping these distinct in the type system is the point: it is what stops a
    percentage change being reported as a percentage-point change.
    """

    PERCENT = "percent"
    PERCENT_ANNUALISED = "percent, annual rate"
    PERCENTAGE_POINTS = "percentage points"
    INDEX = "index"
    MILLIONS_USD = "millions of dollars"
    BILLIONS_CHAINED_USD = "billions of chained dollars"


class Direction(str, Enum):
    """Sign of a change, classified once so wording stays consistent."""

    INCREASED = "increased"
    DECREASED = "decreased"
    UNCHANGED = "unchanged"

    @classmethod
    def from_change(cls, change: float, tolerance: float = DIRECTION_TOLERANCE) -> "Direction":
        value = require_number(change, "change")
        if value > tolerance:
            return cls.INCREASED
        if value < -tolerance:
            return cls.DECREASED
        return cls.UNCHANGED


@dataclass(frozen=True)
class RawObservation:
    """One observation exactly as published: a period and a value.

    No transformation has been applied. ``value`` is the raw level, index or
    rate in the source series' own units.
    """

    period: date
    value: float

    def __post_init__(self) -> None:
        if not isinstance(self.period, date):
            raise NonNumericValueError(
                f"period must be a datetime.date, got {type(self.period).__name__}"
            )
        require_number(self.value, f"value for {self.period.isoformat()}")


@dataclass(frozen=True)
class MacroObservation:
    """A derived macroeconomic statistic, with its provenance and units.

    ``value`` is the result of a stated transformation, never a raw level. The
    fields are unrounded; use :meth:`to_display` at a presentation boundary.
    """

    indicator_id: str
    economy: str
    display_name: str
    period: date
    frequency: Frequency
    value: float
    unit: Unit
    previous_value: float
    change: float
    change_unit: Unit
    direction: Direction
    source_series: str
    source_name: str
    retrieved_at: datetime

    def __post_init__(self) -> None:
        require_number(self.value, "value")
        require_number(self.previous_value, "previous_value")
        require_number(self.change, "change")
        if not isinstance(self.period, date):
            raise NonNumericValueError("period must be a datetime.date")
        if not isinstance(self.retrieved_at, datetime):
            raise NonNumericValueError("retrieved_at must be a datetime.datetime")
        expected = Direction.from_change(self.change)
        if self.direction is not expected:
            raise ValueError(
                f"direction {self.direction.value!r} contradicts change "
                f"{self.change!r} (expected {expected.value!r})"
            )

    @classmethod
    def derive(
        cls,
        *,
        indicator_id: str,
        economy: str,
        display_name: str,
        period: date,
        frequency: Frequency,
        value: float,
        unit: Unit,
        previous_value: float,
        change: float,
        change_unit: Unit,
        source_series: str,
        source_name: str,
        retrieved_at: datetime,
    ) -> "MacroObservation":
        """Build an observation, classifying ``direction`` from ``change``."""
        return cls(
            indicator_id=indicator_id,
            economy=economy,
            display_name=display_name,
            period=period,
            frequency=frequency,
            value=value,
            unit=unit,
            previous_value=previous_value,
            change=change,
            change_unit=change_unit,
            direction=Direction.from_change(change),
            source_series=source_series,
            source_name=source_name,
            retrieved_at=retrieved_at,
        )

    def to_display(self, value_dp: int = 1, change_dp: int = 1) -> dict:
        """Round for presentation. The only place rounding is permitted.

        Returns plain types so the result can be serialised or handed to a
        template without the caller reaching back into the model.
        """
        return {
            "indicator_id": self.indicator_id,
            "economy": self.economy,
            "display_name": self.display_name,
            "period": self.period.isoformat(),
            "frequency": self.frequency.value,
            "value": round(self.value, value_dp),
            "unit": self.unit.value,
            "previous_value": round(self.previous_value, value_dp),
            "change": round(self.change, change_dp),
            "change_unit": self.change_unit.value,
            "direction": self.direction.value,
            "source_series": self.source_series,
            "source_name": self.source_name,
            "retrieved_at": self.retrieved_at.isoformat(),
        }


def parse_series(payload: Mapping[str, Any]) -> list:
    """Turn a loaded fixture/response mapping into ``RawObservation`` objects.

    Pure: takes an already-loaded mapping, does no file or network access.
    Observations are returned sorted oldest to newest, which every
    transformation in this package assumes.

    Values must already be numeric. Source APIs typically return them as
    strings, with a sentinel for missing observations; converting those is the
    collector's responsibility (Phase 2), so that a malformed payload fails at
    the boundary rather than deep inside a calculation.
    """
    observations = payload.get("observations")
    if observations is None:
        raise MissingValueError("payload has no 'observations' key")
    if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)):
        raise NonNumericValueError("'observations' must be a list of mappings")

    parsed = []
    for index, item in enumerate(observations):
        if not isinstance(item, Mapping):
            raise NonNumericValueError(
                f"observation {index} is {type(item).__name__}, expected a mapping"
            )
        if "date" not in item:
            raise MissingValueError(f"observation {index} has no 'date'")
        if "value" not in item:
            raise MissingValueError(f"observation {index} has no 'value'")
        raw_date = item["date"]
        if not isinstance(raw_date, str):
            raise NonNumericValueError(
                f"observation {index} date must be an ISO string, got "
                f"{type(raw_date).__name__}"
            )
        parsed.append(RawObservation(period=date.fromisoformat(raw_date), value=item["value"]))

    return sorted(parsed, key=lambda obs: obs.period)
