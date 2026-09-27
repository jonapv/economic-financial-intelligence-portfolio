"""Calendar period arithmetic and lookup.

A transformation that compares "this month with the same month a year ago" must
select that observation **by calendar date**, never by counting back a fixed
number of positions in a list. The two coincide only when the series has no
gaps, and real published series do have gaps: October 2025 is absent from both
CPIAUCNS and UNRATE.

Selecting by position across a gap silently compares the wrong periods and
yields a figure that looks entirely plausible. Selecting by calendar either
finds the right observation or fails loudly.

Pure: no I/O, no clock.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, Sequence

from .errors import MissingRequiredPeriodError
from .models import RawObservation


def add_months(period: date, months: int) -> date:
    """Shift a period label by ``months``, preserving the day of month.

    Monthly and quarterly series are labelled on the first day of the period, so
    day-of-month arithmetic is not exercised in practice; the day is preserved
    anyway, clamped to the length of the target month.
    """
    total = (period.year * 12 + (period.month - 1)) + months
    year, month = divmod(total, 12)
    month += 1
    # Clamp the day so that e.g. 31 January minus one month is a valid date.
    if month == 2:
        last = 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28
    elif month in (4, 6, 9, 11):
        last = 30
    else:
        last = 31
    return date(year, month, min(period.day, last))


def add_quarters(period: date, quarters: int) -> date:
    """Shift a quarterly period label by ``quarters``."""
    return add_months(period, 3 * quarters)


def index_by_period(series: Sequence[RawObservation]) -> Dict[date, RawObservation]:
    """Index observations by their period for exact lookup."""
    return {obs.period: obs for obs in series}


def require_period(
    index: Dict[date, RawObservation],
    period: date,
    *,
    series_id: str,
    role: str,
) -> RawObservation:
    """Return the observation for ``period``, or fail naming what is missing.

    ``role`` describes the position in the formula (for example ``"CPI_t-12"``)
    so that a failure says which comparison could not be formed.
    """
    try:
        return index[period]
    except KeyError:
        raise MissingRequiredPeriodError(
            f"{series_id}: the observation for {period.isoformat()} is required "
            f"as {role} but is not present in the series. It is either missing "
            f"at the source or outside the retrieved window. No substitute "
            f"observation is used, because comparing a different period would "
            f"produce a plausible-looking but incorrect figure."
        ) from None
