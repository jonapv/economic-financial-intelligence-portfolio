"""Exceptions raised by the calculation layer.

Bad input is always an error. Nothing is silently coerced, defaulted or
skipped: a wrong number is more dangerous than a missing one, because a wrong
number gets published.
"""


class CalculationError(Exception):
    """Base class for every failure in the calculation layer."""


class MissingValueError(CalculationError):
    """A required observation was absent (``None``, or a gap in the series)."""


class NonNumericValueError(CalculationError):
    """A value was present but not a usable finite number.

    Raised for strings (including numeric-looking ones), booleans, ``NaN`` and
    infinities. Source APIs commonly deliver numbers as strings and missing
    observations as sentinel characters; converting those is the collector's
    job, not this layer's.
    """


class ZeroDenominatorError(CalculationError):
    """A ratio would divide by zero."""


class InsufficientHistoryError(CalculationError):
    """Fewer observations were supplied than the transformation requires."""
