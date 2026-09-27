"""Indicator specifications and their transformations — V1, United States only.

This module is the single source of truth for the economic definitions. The
table in ``README.md`` mirrors it; if the two ever disagree, this file is
correct and the README is stale.

Each indicator pairs a declarative :class:`IndicatorSpec` with a transformation
that turns raw source observations into one :class:`MacroObservation`. The
transformation for each series is chosen because it is the conventional
statistic for that series — not because it is convenient to compute.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Sequence

from .calculations import (
    percentage_change,
    percentage_point_change,
    qoq_annualized_change,
)
from .errors import InsufficientHistoryError
from .models import (
    Frequency,
    MacroObservation,
    PeriodSelection,
    RawObservation,
    Unit,
)
from .periods import add_months, add_quarters, index_by_period, require_period

ECONOMY = "US"
SOURCE_NAME = "Federal Reserve Bank of St. Louis (FRED)"


@dataclass(frozen=True)
class IndicatorSpec:
    """Declarative definition of one indicator.

    Field names match the columns of the specification table in the project
    README, so the documentation and the code cannot drift apart silently.
    """

    indicator_id: str
    display_name: str
    economic_concept: str
    economic_category: str
    source_series: str
    frequency: Frequency
    raw_unit: Unit
    seasonal_adjustment: str
    transformation: str
    output_unit: Unit
    comparison: str
    period_selection: PeriodSelection
    display_decimals: int
    minimum_history_required: int
    interpretation: str
    known_revision_risk: str
    source_name: str = SOURCE_NAME
    economy: str = ECONOMY


# ---------------------------------------------------------------------------
# Specifications
# ---------------------------------------------------------------------------

CPI_INFLATION = IndicatorSpec(
    indicator_id="us_cpi_inflation_yoy",
    display_name="CPI Inflation (YoY)",
    economic_concept="Headline consumer price inflation rate",
    economic_category="Inflation",
    source_series="CPIAUCNS",
    frequency=Frequency.MONTHLY,
    raw_unit=Unit.INDEX,
    seasonal_adjustment="Not seasonally adjusted",
    transformation="Year-over-year percentage change of the index: ((CPI_t / CPI_t-12) - 1) * 100",
    output_unit=Unit.PERCENT,
    comparison=(
        "Against the same calculation one calendar month earlier (t-1 vs t-13), "
        "differenced in percentage points. Periods are selected by calendar date, "
        "never by list position"
    ),
    period_selection=PeriodSelection.CALENDAR,
    display_decimals=1,
    minimum_history_required=14,
    interpretation=(
        "The rate at which consumer prices are rising over twelve months. The "
        "index level itself is not the inflation rate: the index rises in "
        "almost every month, so a rising index says nothing about whether "
        "inflation accelerated. Inflation can decelerate while the index rises. "
        "The non-seasonally-adjusted index is the conventional basis for the "
        "headline twelve-month figure: a twelve-month comparison already spans "
        "a full seasonal cycle, so seasonal adjustment is unnecessary for this "
        "transformation. The corollary is that this series must NOT be used for "
        "month-over-month inflation, which does require adjustment."
    ),
    known_revision_risk=(
        "Very low. The not-seasonally-adjusted index is not subject to the "
        "annual seasonal-factor revisions that alter the adjusted series, so "
        "published NSA index values are effectively final."
    ),
)

UNEMPLOYMENT_RATE = IndicatorSpec(
    indicator_id="us_unemployment_rate",
    display_name="Unemployment Rate",
    economic_concept="Share of the labour force that is unemployed",
    economic_category="Labour market",
    source_series="UNRATE",
    frequency=Frequency.MONTHLY,
    raw_unit=Unit.PERCENT,
    seasonal_adjustment="Seasonally adjusted",
    transformation="None. The series is already a rate and is reported as published.",
    output_unit=Unit.PERCENT,
    comparison=(
        "Difference against the previous calendar month, in percentage points. "
        "The preceding month must be present; a gap is not bridged"
    ),
    period_selection=PeriodSelection.CALENDAR,
    display_decimals=1,
    minimum_history_required=2,
    interpretation=(
        "Labour market slack. Already a rate, so the change is a "
        "percentage-point difference and never a percentage change. A single "
        "month's move of 0.1pp is frequently within sampling noise and should "
        "not be described as a trend."
    ),
    known_revision_risk=(
        "Low. Household survey estimates are not routinely revised, though "
        "seasonal factors and annual population controls can shift the series."
    ),
)

EFFECTIVE_FED_FUNDS = IndicatorSpec(
    indicator_id="us_effective_fed_funds_rate",
    display_name="Effective Federal Funds Rate",
    economic_concept="Realised overnight interbank lending rate, daily",
    economic_category="Monetary policy",
    source_series="DFF",
    frequency=Frequency.DAILY,
    raw_unit=Unit.PERCENT,
    seasonal_adjustment="Not applicable",
    transformation="None. The series is already a rate and is reported as published.",
    output_unit=Unit.PERCENT,
    comparison=(
        "Difference against the immediately preceding available daily "
        "observation, in percentage points"
    ),
    period_selection=PeriodSelection.PREVIOUS_AVAILABLE,
    display_decimals=2,
    minimum_history_required=2,
    interpretation=(
        "The rate actually realised in the overnight market, at daily "
        "frequency. This is NOT the FOMC target range. It must be labelled "
        "'Effective Federal Funds Rate' and never 'policy rate', 'the Fed's "
        "rate' or 'target rate': the target range is a separate concept set by "
        "the FOMC, and the effective rate is where transactions actually "
        "settle, inside that range. The effective rate commonly remains "
        "unchanged for weeks or months between policy moves, so an unchanged "
        "reading is the normal case and is not evidence of anything. Because "
        "the comparison is against the previous available observation rather "
        "than a fixed calendar lag, gaps in the publication calendar do not "
        "distort the change."
    ),
    known_revision_risk=(
        "Very low. A realised market average rather than an estimate, though "
        "the most recent daily observations can be revised slightly."
    ),
)

REAL_GDP_GROWTH = IndicatorSpec(
    indicator_id="us_real_gdp_growth_qoq_ann",
    display_name="Real GDP Growth (QoQ, annualised)",
    economic_concept="Real output growth at an annual rate",
    economic_category="Growth",
    source_series="GDPC1",
    frequency=Frequency.QUARTERLY,
    raw_unit=Unit.BILLIONS_CHAINED_USD,
    seasonal_adjustment="Seasonally adjusted annual rate",
    transformation="Compounded quarterly change: (((GDP_t / GDP_t-1) ** 4) - 1) * 100",
    output_unit=Unit.PERCENT_ANNUALISED,
    comparison=(
        "Against the same calculation for the prior calendar quarter (t-1 vs t-2), "
        "differenced in percentage points. Quarters are selected by calendar date"
    ),
    period_selection=PeriodSelection.CALENDAR,
    display_decimals=1,
    minimum_history_required=3,
    interpretation=(
        "The headline United States growth number, quoted at a seasonally "
        "adjusted annual rate. Derived here from the level series, so it must "
        "be validated against the official published growth figure before "
        "publication. A difference between two adjacent levels is not a growth "
        "rate, and the annualised rate is a compounded quarterly change rather "
        "than four times it."
    ),
    known_revision_risk=(
        "HIGH. Revised across advance, second and third estimates and again in "
        "annual and comprehensive revisions. Revisions of several tenths are "
        "routine and can change the sign of a weak quarter."
    ),
)

RETAIL_SALES = IndicatorSpec(
    indicator_id="us_retail_sales_mom",
    display_name="Retail Sales (MoM)",
    economic_concept="Month-over-month growth in nominal retail and food services sales",
    economic_category="Consumption",
    source_series="RSAFS",
    frequency=Frequency.MONTHLY,
    raw_unit=Unit.MILLIONS_USD,
    seasonal_adjustment="Seasonally adjusted",
    transformation="Month-over-month percentage change: ((Sales_t / Sales_t-1) - 1) * 100",
    output_unit=Unit.PERCENT,
    comparison=(
        "Against the prior calendar month's month-over-month change (t-1 vs t-2), "
        "differenced in percentage points. Months are selected by calendar date"
    ),
    period_selection=PeriodSelection.CALENDAR,
    display_decimals=1,
    minimum_history_required=3,
    interpretation=(
        "Momentum in consumer spending. The raw level is a dollar amount and "
        "must never be described as growth. The series is NOMINAL, so a rise "
        "can coincide with a real decline when inflation is high; any real "
        "reading requires explicit deflation, which V1 does not perform."
    ),
    known_revision_risk=(
        "MEDIUM. 'Advance' estimates are revised in the following month as more "
        "complete survey responses arrive."
    ),
)

SPECS = {
    spec.indicator_id: spec
    for spec in (
        CPI_INFLATION,
        UNEMPLOYMENT_RATE,
        EFFECTIVE_FED_FUNDS,
        REAL_GDP_GROWTH,
        RETAIL_SALES,
    )
}

SERIES_TO_INDICATOR = {spec.source_series: spec.indicator_id for spec in SPECS.values()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_history(spec: IndicatorSpec, series: Sequence[RawObservation]) -> None:
    if len(series) < spec.minimum_history_required:
        raise InsufficientHistoryError(
            f"{spec.indicator_id} ({spec.source_series}) requires at least "
            f"{spec.minimum_history_required} observations to compute "
            f"'{spec.transformation.split(':')[0]}', got {len(series)}"
        )


def _build(
    spec: IndicatorSpec,
    *,
    period,
    value: float,
    previous_value: float,
    change: float,
    retrieved_at: datetime,
) -> MacroObservation:
    return MacroObservation.derive(
        indicator_id=spec.indicator_id,
        economy=spec.economy,
        display_name=spec.display_name,
        period=period,
        frequency=spec.frequency,
        value=value,
        unit=spec.output_unit,
        previous_value=previous_value,
        change=change,
        change_unit=Unit.PERCENTAGE_POINTS,
        source_series=spec.source_series,
        source_name=spec.source_name,
        retrieved_at=retrieved_at,
    )


# ---------------------------------------------------------------------------
# Transformations
# ---------------------------------------------------------------------------

def compute_cpi_inflation(
    series: Sequence[RawObservation], *, retrieved_at: datetime
) -> MacroObservation:
    """Year-over-year CPI inflation, and its change against the prior month.

    Needs 14 observations: t and t-12 for the current rate, t-1 and t-13 for
    the previous rate.
    """
    spec = CPI_INFLATION
    _check_history(spec, series)
    index = index_by_period(series)
    latest = series[-1].period
    t_12 = require_period(index, add_months(latest, -12),
                          series_id=spec.source_series, role="CPI_t-12")
    t_1 = require_period(index, add_months(latest, -1),
                         series_id=spec.source_series, role="CPI_t-1")
    t_13 = require_period(index, add_months(latest, -13),
                          series_id=spec.source_series, role="CPI_t-13")
    current = percentage_change(series[-1].value, t_12.value)
    previous = percentage_change(t_1.value, t_13.value)
    return _build(
        spec,
        period=series[-1].period,
        value=current,
        previous_value=previous,
        change=percentage_point_change(current, previous),
        retrieved_at=retrieved_at,
    )


def compute_unemployment_rate(
    series: Sequence[RawObservation], *, retrieved_at: datetime
) -> MacroObservation:
    """Latest unemployment rate as published, differenced in percentage points."""
    spec = UNEMPLOYMENT_RATE
    _check_history(spec, series)
    index = index_by_period(series)
    latest = series[-1].period
    current = series[-1].value
    previous = require_period(index, add_months(latest, -1),
                              series_id=spec.source_series,
                              role="previous month").value
    return _build(
        spec,
        period=series[-1].period,
        value=current,
        previous_value=previous,
        change=percentage_point_change(current, previous),
        retrieved_at=retrieved_at,
    )


def compute_effective_fed_funds_rate(
    series: Sequence[RawObservation], *, retrieved_at: datetime
) -> MacroObservation:
    """Latest effective federal funds rate, differenced in percentage points.

    Daily series (DFF). ``current`` is the latest observation supplied and
    ``previous`` is the immediately preceding one in the series, so gaps in the
    publication calendar are handled without a calendar-lag assumption.

    The realised market rate, not the FOMC target range.
    """
    spec = EFFECTIVE_FED_FUNDS
    _check_history(spec, series)
    current = series[-1].value
    previous = series[-2].value
    return _build(
        spec,
        period=series[-1].period,
        value=current,
        previous_value=previous,
        change=percentage_point_change(current, previous),
        retrieved_at=retrieved_at,
    )


def compute_real_gdp_growth(
    series: Sequence[RawObservation], *, retrieved_at: datetime
) -> MacroObservation:
    """Quarter-over-quarter annualised real GDP growth, and its change.

    Needs 3 observations: t and t-1 for the current quarter, t-1 and t-2 for
    the prior quarter.
    """
    spec = REAL_GDP_GROWTH
    _check_history(spec, series)
    index = index_by_period(series)
    latest = series[-1].period
    q_1 = require_period(index, add_quarters(latest, -1),
                         series_id=spec.source_series, role="GDP_t-1")
    q_2 = require_period(index, add_quarters(latest, -2),
                         series_id=spec.source_series, role="GDP_t-2")
    current = qoq_annualized_change(series[-1].value, q_1.value)
    previous = qoq_annualized_change(q_1.value, q_2.value)
    return _build(
        spec,
        period=series[-1].period,
        value=current,
        previous_value=previous,
        change=percentage_point_change(current, previous),
        retrieved_at=retrieved_at,
    )


def compute_retail_sales_growth(
    series: Sequence[RawObservation], *, retrieved_at: datetime
) -> MacroObservation:
    """Month-over-month retail sales growth, and the change in that momentum."""
    spec = RETAIL_SALES
    _check_history(spec, series)
    index = index_by_period(series)
    latest = series[-1].period
    m_1 = require_period(index, add_months(latest, -1),
                         series_id=spec.source_series, role="Sales_t-1")
    m_2 = require_period(index, add_months(latest, -2),
                         series_id=spec.source_series, role="Sales_t-2")
    current = percentage_change(series[-1].value, m_1.value)
    previous = percentage_change(m_1.value, m_2.value)
    return _build(
        spec,
        period=series[-1].period,
        value=current,
        previous_value=previous,
        change=percentage_point_change(current, previous),
        retrieved_at=retrieved_at,
    )


TRANSFORMATIONS: dict = {
    CPI_INFLATION.indicator_id: compute_cpi_inflation,
    UNEMPLOYMENT_RATE.indicator_id: compute_unemployment_rate,
    EFFECTIVE_FED_FUNDS.indicator_id: compute_effective_fed_funds_rate,
    REAL_GDP_GROWTH.indicator_id: compute_real_gdp_growth,
    RETAIL_SALES.indicator_id: compute_retail_sales_growth,
}


def compute(
    indicator_id: str, series: Sequence[RawObservation], *, retrieved_at: datetime
) -> MacroObservation:
    """Apply the transformation registered for ``indicator_id``."""
    try:
        transform: Callable = TRANSFORMATIONS[indicator_id]
    except KeyError:
        raise KeyError(
            f"unknown indicator_id {indicator_id!r}; known: {sorted(TRANSFORMATIONS)}"
        ) from None
    return transform(series, retrieved_at=retrieved_at)
