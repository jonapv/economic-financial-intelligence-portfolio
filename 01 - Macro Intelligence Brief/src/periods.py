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

from .errors import InvalidPeriodError, MissingRequiredPeriodError
from .models import Frequency, RawObservation


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


# ---------------------------------------------------------------------------
# Human-readable period labels
# ---------------------------------------------------------------------------
#: English month names, indexed 1-12. Hard-coded rather than taken from the
#: locale so that output is identical on every machine, and deliberately not
#: obtained from source metadata: the label must follow from the canonical
#: period and the DECLARED frequency, nothing else.
_MONTH_NAMES = (
    None, "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

#: The only months a quarterly period may fall on, and the quarter each means.
#: A quarterly series is labelled by the first month of its quarter.
_QUARTER_BY_MONTH = {1: 1, 4: 2, 7: 3, 10: 4}


def period_label(period: date, frequency: Frequency) -> str:
    """Render a canonical period as English prose, deterministically.

    This exists because the canonical date is unambiguous to a machine and
    genuinely ambiguous to a reader. ``2026-04-01`` on a quarterly series means
    **2026 Q2**, not "April GDP". ``2026-08-01`` on a monthly series means
    **August 2026**, not activity on the first of the month. A prose layer must
    not be left to infer either.

    Derived only from ``period`` and the declared ``frequency``. No source
    metadata, no locale, no model.

        monthly    2026-08-01  ->  "August 2026"
        quarterly  2026-04-01  ->  "2026 Q2"
        daily      2026-09-24  ->  "24 September 2026"

    Raises :class:`~src.errors.InvalidPeriodError` rather than guessing when a
    period does not fit its frequency's convention.
    """
    if not isinstance(period, date):
        raise InvalidPeriodError(
            f"period must be a datetime.date, got {type(period).__name__}"
        )
    if not isinstance(frequency, Frequency):
        raise InvalidPeriodError(
            f"frequency must be a Frequency, got {type(frequency).__name__!r}. "
            f"The label must follow from the DECLARED frequency, not from free "
            f"text."
        )

    if frequency is Frequency.MONTHLY:
        if period.day != 1:
            raise InvalidPeriodError(
                f"monthly period {period.isoformat()} is not on the first of the "
                f"month. This project's convention labels a monthly observation "
                f"by the first day of the month it covers; a mid-month date "
                f"cannot be labelled without guessing which month is meant."
            )
        return f"{_MONTH_NAMES[period.month]} {period.year}"

    if frequency is Frequency.QUARTERLY:
        if period.day != 1:
            raise InvalidPeriodError(
                f"quarterly period {period.isoformat()} is not on the first of "
                f"the month; a quarterly observation is labelled by the first "
                f"day of its opening month."
            )
        quarter = _QUARTER_BY_MONTH.get(period.month)
        if quarter is None:
            raise InvalidPeriodError(
                f"quarterly period {period.isoformat()} falls in month "
                f"{period.month} ({_MONTH_NAMES[period.month]}), which does not "
                f"open a quarter. A quarterly observation must be dated January, "
                f"April, July or October. Refusing to guess a quarter."
            )
        return f"{period.year} Q{quarter}"

    if frequency is Frequency.DAILY:
        return f"{period.day} {_MONTH_NAMES[period.month]} {period.year}"

    raise InvalidPeriodError(
        f"no label convention defined for frequency {frequency.value!r}"
    )
