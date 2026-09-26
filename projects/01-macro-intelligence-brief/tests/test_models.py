"""Tests for the data model: validation, direction and the rounding boundary."""

import unittest
from datetime import date, datetime

from src.errors import MissingValueError, NonNumericValueError
from src.models import (
    Direction,
    Frequency,
    MacroObservation,
    RawObservation,
    Unit,
    parse_series,
)

RETRIEVED_AT = datetime(2025, 3, 1, 12, 0, 0)


def build(**overrides):
    kwargs = dict(
        indicator_id="us_cpi_inflation_yoy",
        economy="US",
        display_name="CPI Inflation (YoY)",
        period=date(2025, 2, 1),
        frequency=Frequency.MONTHLY,
        value=4.0,
        unit=Unit.PERCENT,
        previous_value=3.0,
        change=1.0,
        change_unit=Unit.PERCENTAGE_POINTS,
        source_series="CPIAUCSL",
        source_name="Federal Reserve Bank of St. Louis (FRED)",
        retrieved_at=RETRIEVED_AT,
    )
    kwargs.update(overrides)
    return MacroObservation.derive(**kwargs)


class TestDirection(unittest.TestCase):
    def test_positive(self):
        self.assertIs(Direction.from_change(0.2), Direction.INCREASED)

    def test_negative(self):
        self.assertIs(Direction.from_change(-0.15), Direction.DECREASED)

    def test_exact_zero(self):
        self.assertIs(Direction.from_change(0.0), Direction.UNCHANGED)

    def test_float_residue_counts_as_unchanged(self):
        # Without a tolerance this would read as an increase.
        self.assertIs(Direction.from_change(1e-15), Direction.UNCHANGED)

    def test_real_movement_is_not_swallowed_by_the_tolerance(self):
        # The smallest change any V1 series actually reports is 0.1.
        self.assertIs(Direction.from_change(0.1), Direction.INCREASED)
        self.assertIs(Direction.from_change(-0.1), Direction.DECREASED)


class TestRawObservation(unittest.TestCase):
    def test_valid(self):
        obs = RawObservation(period=date(2025, 1, 1), value=103.0)
        self.assertEqual(obs.value, 103.0)

    def test_frozen(self):
        obs = RawObservation(period=date(2025, 1, 1), value=103.0)
        with self.assertRaises(Exception):
            obs.value = 104.0

    def test_string_value_rejected(self):
        with self.assertRaises(NonNumericValueError):
            RawObservation(period=date(2025, 1, 1), value="103.0")

    def test_none_value_rejected(self):
        with self.assertRaises(MissingValueError):
            RawObservation(period=date(2025, 1, 1), value=None)

    def test_non_date_period_rejected(self):
        with self.assertRaises(NonNumericValueError):
            RawObservation(period="2025-01-01", value=103.0)


class TestMacroObservation(unittest.TestCase):
    def test_direction_derived(self):
        self.assertIs(build().direction, Direction.INCREASED)
        self.assertIs(build(change=-1.0).direction, Direction.DECREASED)
        self.assertIs(build(change=0.0).direction, Direction.UNCHANGED)

    def test_inconsistent_direction_rejected(self):
        # Constructing directly, bypassing derive(), must still be caught.
        with self.assertRaises(ValueError):
            MacroObservation(
                indicator_id="x",
                economy="US",
                display_name="X",
                period=date(2025, 2, 1),
                frequency=Frequency.MONTHLY,
                value=4.0,
                unit=Unit.PERCENT,
                previous_value=3.0,
                change=1.0,
                change_unit=Unit.PERCENTAGE_POINTS,
                direction=Direction.DECREASED,  # contradicts change=+1.0
                source_series="X",
                source_name="X",
                retrieved_at=RETRIEVED_AT,
            )

    def test_string_value_rejected(self):
        with self.assertRaises(NonNumericValueError):
            build(value="4.0")

    def test_missing_value_rejected(self):
        with self.assertRaises(MissingValueError):
            build(value=None)

    def test_non_datetime_retrieved_at_rejected(self):
        with self.assertRaises(NonNumericValueError):
            build(retrieved_at=date(2025, 3, 1))

    def test_frozen(self):
        obs = build()
        with self.assertRaises(Exception):
            obs.value = 9.9


class TestPresentationBoundary(unittest.TestCase):
    def test_values_stored_unrounded(self):
        obs = build(value=4.060401, previous_value=2.0150500625, change=2.0453509375)
        self.assertEqual(obs.value, 4.060401)
        self.assertEqual(obs.change, 2.0453509375)

    def test_to_display_rounds(self):
        obs = build(value=4.060401, previous_value=2.0150500625, change=2.0453509375)
        shown = obs.to_display()
        self.assertEqual(shown["value"], 4.1)
        self.assertEqual(shown["previous_value"], 2.0)
        self.assertEqual(shown["change"], 2.0)

    def test_to_display_honours_precision(self):
        obs = build(value=4.060401, previous_value=2.0150500625, change=2.0453509375)
        shown = obs.to_display(value_dp=4, change_dp=4)
        self.assertEqual(shown["value"], 4.0604)
        self.assertEqual(shown["change"], 2.0454)

    def test_to_display_carries_units_and_provenance(self):
        shown = build().to_display()
        self.assertEqual(shown["unit"], "percent")
        self.assertEqual(shown["change_unit"], "percentage points")
        self.assertEqual(shown["direction"], "increased")
        self.assertEqual(shown["source_series"], "CPIAUCSL")
        self.assertEqual(shown["period"], "2025-02-01")
        self.assertEqual(shown["retrieved_at"], "2025-03-01T12:00:00")

    def test_to_display_returns_plain_types(self):
        for key, value in build().to_display().items():
            with self.subTest(key=key):
                self.assertIsInstance(value, (str, int, float))


class TestParseSeries(unittest.TestCase):
    def test_missing_observations_key(self):
        with self.assertRaises(MissingValueError):
            parse_series({})

    def test_observation_missing_value(self):
        with self.assertRaises(MissingValueError):
            parse_series({"observations": [{"date": "2025-01-01"}]})

    def test_observation_missing_date(self):
        with self.assertRaises(MissingValueError):
            parse_series({"observations": [{"value": 1.0}]})

    def test_observations_not_a_list(self):
        with self.assertRaises(NonNumericValueError):
            parse_series({"observations": "nope"})

    def test_observation_not_a_mapping(self):
        with self.assertRaises(NonNumericValueError):
            parse_series({"observations": [["2025-01-01", 1.0]]})

    def test_non_string_date(self):
        with self.assertRaises(NonNumericValueError):
            parse_series({"observations": [{"date": 20250101, "value": 1.0}]})


if __name__ == "__main__":
    unittest.main()
