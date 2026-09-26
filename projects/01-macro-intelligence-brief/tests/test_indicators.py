"""Tests for the five V1 indicator transformations, driven by synthetic fixtures.

Every expected value here is stated explicitly and is verifiable by hand from
the fixture, not computed by re-running the implementation.
"""

import json
import pathlib
import unittest
from datetime import date, datetime

from src.errors import InsufficientHistoryError, NonNumericValueError, ZeroDenominatorError
from src.indicators import (
    CPI_INFLATION,
    EFFECTIVE_FED_FUNDS,
    REAL_GDP_GROWTH,
    RETAIL_SALES,
    SPECS,
    UNEMPLOYMENT_RATE,
    compute,
    compute_cpi_inflation,
    compute_effective_fed_funds_rate,
    compute_real_gdp_growth,
    compute_retail_sales_growth,
    compute_unemployment_rate,
)
from src.models import Direction, Frequency, Unit, parse_series

SAMPLES = pathlib.Path(__file__).resolve().parent.parent / "data" / "samples"
RETRIEVED_AT = datetime(2025, 3, 1, 12, 0, 0)


def load(name):
    """Load a synthetic fixture into RawObservations. Local file only, no network."""
    with (SAMPLES / name).open(encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["_synthetic"] is True, "fixture must be marked synthetic"
    return parse_series(payload)


class TestCpiInflation(unittest.TestCase):
    """CPIAUCSL: an index, so the output must be a year-over-year rate."""

    def setUp(self):
        self.series = load("cpiaucsl_synthetic.json")

    def test_fixture_shape(self):
        self.assertEqual(len(self.series), 14)
        self.assertEqual(self.series[-1].period, date(2025, 2, 1))
        self.assertEqual(self.series[-1].value, 104.0)

    def test_current_yoy_is_four_percent(self):
        # 104.0 / 100.0 - 1 = 4.0 percent  (2025-02 vs 2024-02)
        obs = compute_cpi_inflation(self.series, retrieved_at=RETRIEVED_AT)
        self.assertAlmostEqual(obs.value, 4.0, places=10)

    def test_previous_yoy_is_three_percent(self):
        # 103.0 / 100.0 - 1 = 3.0 percent  (2025-01 vs 2024-01)
        obs = compute_cpi_inflation(self.series, retrieved_at=RETRIEVED_AT)
        self.assertAlmostEqual(obs.previous_value, 3.0, places=10)

    def test_change_is_one_percentage_point(self):
        obs = compute_cpi_inflation(self.series, retrieved_at=RETRIEVED_AT)
        self.assertAlmostEqual(obs.change, 1.0, places=10)
        self.assertIs(obs.change_unit, Unit.PERCENTAGE_POINTS)
        self.assertIs(obs.direction, Direction.INCREASED)

    def test_output_is_a_rate_not_an_index(self):
        obs = compute_cpi_inflation(self.series, retrieved_at=RETRIEVED_AT)
        self.assertIs(obs.unit, Unit.PERCENT)
        # The raw index level (104.0) must not appear as the reported value.
        self.assertNotAlmostEqual(obs.value, 104.0, places=6)

    def test_metadata(self):
        obs = compute_cpi_inflation(self.series, retrieved_at=RETRIEVED_AT)
        self.assertEqual(obs.source_series, "CPIAUCSL")
        self.assertEqual(obs.economy, "US")
        self.assertEqual(obs.period, date(2025, 2, 1))
        self.assertIs(obs.frequency, Frequency.MONTHLY)
        self.assertEqual(obs.retrieved_at, RETRIEVED_AT)

    def test_minimum_history_is_fourteen(self):
        self.assertEqual(CPI_INFLATION.minimum_history_required, 14)

    def test_thirteen_observations_is_insufficient(self):
        with self.assertRaises(InsufficientHistoryError):
            compute_cpi_inflation(self.series[1:], retrieved_at=RETRIEVED_AT)

    def test_fourteen_observations_is_sufficient(self):
        obs = compute_cpi_inflation(self.series, retrieved_at=RETRIEVED_AT)
        self.assertAlmostEqual(obs.value, 4.0, places=10)


class TestUnemploymentRate(unittest.TestCase):
    """UNRATE: already a rate, so no transformation and a pp difference."""

    def setUp(self):
        self.series = load("unrate_synthetic.json")

    def test_current_rate(self):
        obs = compute_unemployment_rate(self.series, retrieved_at=RETRIEVED_AT)
        self.assertAlmostEqual(obs.value, 4.3, places=10)

    def test_previous_rate(self):
        obs = compute_unemployment_rate(self.series, retrieved_at=RETRIEVED_AT)
        self.assertAlmostEqual(obs.previous_value, 4.1, places=10)

    def test_percentage_point_change(self):
        obs = compute_unemployment_rate(self.series, retrieved_at=RETRIEVED_AT)
        self.assertAlmostEqual(obs.change, 0.2, places=10)
        self.assertIs(obs.change_unit, Unit.PERCENTAGE_POINTS)
        self.assertIs(obs.direction, Direction.INCREASED)

    def test_value_is_published_rate_untransformed(self):
        obs = compute_unemployment_rate(self.series, retrieved_at=RETRIEVED_AT)
        self.assertEqual(obs.value, self.series[-1].value)
        self.assertIn("None", UNEMPLOYMENT_RATE.transformation)

    def test_one_observation_is_insufficient(self):
        with self.assertRaises(InsufficientHistoryError):
            compute_unemployment_rate(self.series[-1:], retrieved_at=RETRIEVED_AT)


class TestEffectiveFedFundsRate(unittest.TestCase):
    """FEDFUNDS: same structure as UNRATE, plus strict naming."""

    def setUp(self):
        self.series = load("fedfunds_synthetic.json")

    def test_current_rate(self):
        obs = compute_effective_fed_funds_rate(self.series, retrieved_at=RETRIEVED_AT)
        self.assertAlmostEqual(obs.value, 4.33, places=10)

    def test_previous_rate(self):
        obs = compute_effective_fed_funds_rate(self.series, retrieved_at=RETRIEVED_AT)
        self.assertAlmostEqual(obs.previous_value, 4.33, places=10)

    def test_unchanged_change_is_zero(self):
        obs = compute_effective_fed_funds_rate(self.series, retrieved_at=RETRIEVED_AT)
        self.assertEqual(obs.change, 0.0)
        self.assertIs(obs.direction, Direction.UNCHANGED)
        self.assertIs(obs.change_unit, Unit.PERCENTAGE_POINTS)

    def test_decrease_on_the_earlier_pair(self):
        obs = compute_effective_fed_funds_rate(self.series[:2], retrieved_at=RETRIEVED_AT)
        self.assertAlmostEqual(obs.value, 4.33, places=10)
        self.assertAlmostEqual(obs.previous_value, 4.48, places=10)
        self.assertAlmostEqual(obs.change, -0.15, places=10)
        self.assertIs(obs.direction, Direction.DECREASED)

    def test_described_as_effective_rate_not_policy_rate(self):
        obs = compute_effective_fed_funds_rate(self.series, retrieved_at=RETRIEVED_AT)
        self.assertEqual(obs.display_name, "Effective Federal Funds Rate")
        self.assertIn("Effective", obs.display_name)
        lowered = obs.display_name.lower()
        self.assertNotIn("policy rate", lowered)
        self.assertNotIn("target", lowered)

    def test_spec_warns_it_is_not_the_target_range(self):
        interpretation = EFFECTIVE_FED_FUNDS.interpretation
        self.assertIn("NOT the FOMC target range", interpretation)
        self.assertIn("never 'policy rate'", interpretation)

    def test_one_observation_is_insufficient(self):
        with self.assertRaises(InsufficientHistoryError):
            compute_effective_fed_funds_rate(self.series[-1:], retrieved_at=RETRIEVED_AT)


class TestRealGdpGrowth(unittest.TestCase):
    """GDPC1: a level, so the output must be an annualised growth rate."""

    def setUp(self):
        self.series = load("gdpc1_synthetic.json")

    def test_current_qoq_annualized(self):
        # 20301 / 20100 = 1.01 exactly; (1.01 ** 4 - 1) * 100 = 4.060401
        obs = compute_real_gdp_growth(self.series, retrieved_at=RETRIEVED_AT)
        self.assertAlmostEqual(obs.value, 4.060401, places=9)

    def test_previous_quarter_qoq_annualized(self):
        # 20100 / 20000 = 1.005 exactly; (1.005 ** 4 - 1) * 100 = 2.0150500625
        obs = compute_real_gdp_growth(self.series, retrieved_at=RETRIEVED_AT)
        self.assertAlmostEqual(obs.previous_value, 2.0150500625, places=9)

    def test_change_in_percentage_points(self):
        obs = compute_real_gdp_growth(self.series, retrieved_at=RETRIEVED_AT)
        self.assertAlmostEqual(obs.change, 2.0453509375, places=9)
        self.assertIs(obs.change_unit, Unit.PERCENTAGE_POINTS)
        self.assertIs(obs.direction, Direction.INCREASED)

    def test_output_is_annualised_and_not_a_level(self):
        obs = compute_real_gdp_growth(self.series, retrieved_at=RETRIEVED_AT)
        self.assertIs(obs.unit, Unit.PERCENT_ANNUALISED)
        self.assertIs(obs.frequency, Frequency.QUARTERLY)
        self.assertLess(obs.value, 100.0)  # a rate, not 20301.0

    def test_not_a_difference_of_levels(self):
        obs = compute_real_gdp_growth(self.series, retrieved_at=RETRIEVED_AT)
        level_difference = self.series[-1].value - self.series[-2].value
        self.assertEqual(level_difference, 201.0)
        self.assertNotAlmostEqual(obs.value, level_difference, places=2)

    def test_zero_denominator_failure(self):
        from src.models import RawObservation

        broken = [
            RawObservation(period=date(2024, 7, 1), value=20000.0),
            RawObservation(period=date(2024, 10, 1), value=0.0),
            RawObservation(period=date(2025, 1, 1), value=20301.0),
        ]
        with self.assertRaises(ZeroDenominatorError):
            compute_real_gdp_growth(broken, retrieved_at=RETRIEVED_AT)

    def test_two_observations_is_insufficient(self):
        with self.assertRaises(InsufficientHistoryError):
            compute_real_gdp_growth(self.series[-2:], retrieved_at=RETRIEVED_AT)

    def test_revision_risk_is_documented_as_high(self):
        self.assertIn("HIGH", REAL_GDP_GROWTH.known_revision_risk)


class TestRetailSalesGrowth(unittest.TestCase):
    """RSAFS: a level in dollars, so the output must be a percentage change."""

    def setUp(self):
        self.series = load("rsafs_synthetic.json")

    def test_current_mom(self):
        # 710535 / 707000 = 1.005 exactly => 0.5 percent
        obs = compute_retail_sales_growth(self.series, retrieved_at=RETRIEVED_AT)
        self.assertAlmostEqual(obs.value, 0.5, places=10)

    def test_previous_mom(self):
        # 707000 / 700000 = 1.01 exactly => 1.0 percent
        obs = compute_retail_sales_growth(self.series, retrieved_at=RETRIEVED_AT)
        self.assertAlmostEqual(obs.previous_value, 1.0, places=10)

    def test_momentum_difference_is_negative(self):
        # Sales still grew, but more slowly: 0.5 - 1.0 = -0.5pp
        obs = compute_retail_sales_growth(self.series, retrieved_at=RETRIEVED_AT)
        self.assertAlmostEqual(obs.change, -0.5, places=10)
        self.assertIs(obs.direction, Direction.DECREASED)
        self.assertGreater(obs.value, 0.0)  # deceleration, not contraction

    def test_output_is_not_the_dollar_level(self):
        obs = compute_retail_sales_growth(self.series, retrieved_at=RETRIEVED_AT)
        self.assertIs(obs.unit, Unit.PERCENT)
        self.assertNotAlmostEqual(obs.value, 710535.0, places=2)

    def test_nominal_caveat_is_documented(self):
        self.assertIn("NOMINAL", RETAIL_SALES.interpretation)

    def test_two_observations_is_insufficient(self):
        with self.assertRaises(InsufficientHistoryError):
            compute_retail_sales_growth(self.series[-2:], retrieved_at=RETRIEVED_AT)


class TestRegistryAndSpecs(unittest.TestCase):
    def test_five_indicators_registered(self):
        self.assertEqual(len(SPECS), 5)

    def test_compute_dispatches_by_id(self):
        obs = compute(
            "us_cpi_inflation_yoy",
            load("cpiaucsl_synthetic.json"),
            retrieved_at=RETRIEVED_AT,
        )
        self.assertAlmostEqual(obs.value, 4.0, places=10)

    def test_unknown_indicator_id(self):
        with self.assertRaises(KeyError):
            compute("us_house_prices", [], retrieved_at=RETRIEVED_AT)

    def test_every_change_is_in_percentage_points(self):
        fixtures = {
            "us_cpi_inflation_yoy": "cpiaucsl_synthetic.json",
            "us_unemployment_rate": "unrate_synthetic.json",
            "us_effective_fed_funds_rate": "fedfunds_synthetic.json",
            "us_real_gdp_growth_qoq_ann": "gdpc1_synthetic.json",
            "us_retail_sales_mom": "rsafs_synthetic.json",
        }
        for indicator_id, fixture in fixtures.items():
            with self.subTest(indicator_id=indicator_id):
                obs = compute(indicator_id, load(fixture), retrieved_at=RETRIEVED_AT)
                self.assertIs(obs.change_unit, Unit.PERCENTAGE_POINTS)
                self.assertEqual(obs.economy, "US")

    def test_every_spec_documents_revision_risk(self):
        for indicator_id, spec in SPECS.items():
            with self.subTest(indicator_id=indicator_id):
                self.assertTrue(spec.known_revision_risk.strip())
                self.assertTrue(spec.interpretation.strip())
                self.assertGreaterEqual(spec.minimum_history_required, 2)

    def test_malformed_payload_rejected(self):
        with self.assertRaises(NonNumericValueError):
            parse_series({"observations": [{"date": "2025-01-01", "value": "103.0"}]})

    def test_fred_missing_sentinel_rejected(self):
        with self.assertRaises(NonNumericValueError):
            parse_series({"observations": [{"date": "2025-01-01", "value": "."}]})

    def test_series_is_sorted_oldest_first(self):
        parsed = parse_series(
            {
                "observations": [
                    {"date": "2025-02-01", "value": 2.0},
                    {"date": "2024-12-01", "value": 1.0},
                ]
            }
        )
        self.assertEqual([obs.period.isoformat() for obs in parsed],
                         ["2024-12-01", "2025-02-01"])


if __name__ == "__main__":
    unittest.main()
