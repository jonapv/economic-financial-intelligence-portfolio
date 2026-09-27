"""Pure economic calculations.

Deterministic, side-effect-free functions. No rounding happens here: results
are returned at full float precision and rounded only at a presentation
boundary (see ``models.MacroObservation.to_display``). Rounding early would
make an intermediate result unreproducible and could change a reported figure.

Two units are involved throughout and must never be confused:

* a **percentage change** is the relative change in a level or index;
* a **percentage-point change** is the arithmetic difference between two
  quantities that are already rates.
"""

from __future__ import annotations

import math
from typing import Sequence, Union

from .errors import (
    CalculationError,
    InsufficientHistoryError,
    MissingValueError,
    NonNumericValueError,
    ZeroDenominatorError,
)

Number = Union[int, float]

#: Differences smaller than this are treated as no change when classifying
#: direction. Guards against a float residue such as 4.33 - 4.33 presenting as
#: an increase. Far below the reporting precision of any series used here.
DIRECTION_TOLERANCE = 1e-12


def require_number(value: object, name: str = "value") -> float:
    """Return ``value`` as a finite float, or raise.

    Deliberately strict. Strings are rejected even when they look numeric,
    because accepting them is how string arithmetic silently enters a pipeline.
    """
    if value is None:
        raise MissingValueError(f"{name} is missing (None)")
    if isinstance(value, bool):
        raise NonNumericValueError(
            f"{name} is a bool ({value!r}), not a numeric measurement"
        )
    if not isinstance(value, (int, float)):
        raise NonNumericValueError(
            f"{name} has type {type(value).__name__} ({value!r}); a numeric "
            f"value is required. Strings are rejected deliberately — convert "
            f"at the collection boundary, not here."
        )
    numeric = float(value)
    if math.isnan(numeric):
        raise NonNumericValueError(f"{name} is NaN")
    if math.isinf(numeric):
        raise NonNumericValueError(f"{name} is infinite ({value!r})")
    return numeric


def percentage_change(current: Number, previous: Number) -> float:
    """Percentage change between two levels or index values.

    ``((current / previous) - 1) * 100``. Result is in **percent**.
    """
    curr = require_number(current, "current")
    prev = require_number(previous, "previous")
    if prev == 0.0:
        raise ZeroDenominatorError(
            "cannot compute a percentage change against a previous value of zero"
        )
    return ((curr / prev) - 1.0) * 100.0


def percentage_point_change(current: Number, previous: Number) -> float:
    """Difference between two quantities that are already rates.

    ``current - previous``. Result is in **percentage points**. Applying this
    to levels or index values would be a category error.
    """
    curr = require_number(current, "current")
    prev = require_number(previous, "previous")
    return curr - prev


def yoy_change(series: Sequence[Number], periods_per_year: int = 12) -> float:
    """Year-over-year percentage change of the most recent observation.

    ``series`` is ordered oldest to newest. Compares the final observation with
    the one ``periods_per_year`` positions earlier, so at least
    ``periods_per_year + 1`` observations are required.
    """
    if periods_per_year < 1:
        raise CalculationError("periods_per_year must be at least 1")
    required = periods_per_year + 1
    if len(series) < required:
        raise InsufficientHistoryError(
            f"year-over-year change needs at least {required} observations, "
            f"got {len(series)}"
        )
    return percentage_change(series[-1], series[-1 - periods_per_year])


def qoq_annualized_change(current: Number, previous: Number) -> float:
    """Quarter-over-quarter change expressed at an annual rate.

    ``(((current / previous) ** 4) - 1) * 100``. Result is in **percent at an
    annual rate**, the convention used for United States real GDP growth.

    This compounds the quarterly change; it is not four times the quarterly
    change, and it is not a difference of levels.
    """
    curr = require_number(current, "current")
    prev = require_number(previous, "previous")
    if prev == 0.0:
        raise ZeroDenominatorError(
            "cannot annualise a quarterly change against a previous level of zero"
        )
    ratio = curr / prev
    if ratio <= 0.0:
        raise CalculationError(
            f"quarterly ratio is not positive ({ratio!r}); raising a negative "
            f"ratio to the fourth power would yield a meaningless positive "
            f"growth rate"
        )
    return ((ratio ** 4) - 1.0) * 100.0
