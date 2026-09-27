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


class CollectionError(Exception):
    """Base class for failures in the collection boundary.

    Deliberately not a subclass of :class:`CalculationError`: a retrieval or
    parsing problem is a different kind of fault from a calculation problem,
    and the two are reported separately.
    """


class MissingCredentialError(CollectionError):
    """``FRED_API_KEY`` was absent from the process environment."""


class SourceRequestError(CollectionError):
    """The source could not be reached, or returned a non-success status.

    Messages raised from this class are scrubbed of the API key before they
    reach a log, a report or a traceback.
    """


class SourcePayloadError(CollectionError):
    """The source returned something that is not a usable payload.

    Malformed JSON, a missing expected key, or an observation value that is
    neither a valid number nor the documented missing-value sentinel.
    """


class MissingRequiredPeriodError(InsufficientHistoryError):
    """A specific calendar period required by a transformation is absent.

    Distinct from a plain shortage of observations: the series may hold plenty
    of data and still be missing the exact period a comparison needs. Raised
    rather than silently substituting a neighbouring observation, which would
    produce a figure that looks plausible and is wrong.
    """
