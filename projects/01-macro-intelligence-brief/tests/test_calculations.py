"""Tests for the pure calculation functions, including failure modes."""

import math
import unittest

from src.calculations import (
    percentage_change,
    percentage_point_change,
    qoq_annualized_change,
    require_number,
    yoy_change,
)
from src.errors import (
    CalculationError,
    InsufficientHistoryError,
    MissingValueError,
    NonNumericValueError,
    ZeroDenominatorError,
)


class TestPercentageChange(unittest.TestCase):
    def test_simple_increase(self):
        # 110 from 100 is a 10 percent increase.
        self.assertAlmostEqual(percentage_change(110.0, 100.0), 10.0, places=10)

    def test_simple_decrease(self):
        self.assertAlmostEqual(percentage_change(90.0, 100.0), -10.0, places=10)

    def test_no_change(self):
        self.assertEqual(percentage_change(100.0, 100.0), 0.0)

    def test_accepts_int(self):
        self.assertAlmostEqual(percentage_change(110, 100), 10.0, places=10)

    def test_zero_denominator_rejected(self):
        with self.assertRaises(ZeroDenominatorError):
            percentage_change(10.0, 0.0)

    def test_negative_denominator_is_arithmetically_defined(self):
        # Permitted here: percentage_change is generic. Series where a negative
        # denominator would be meaningful are not part of V1.
        self.assertAlmostEqual(percentage_change(-90.0, -100.0), -10.0, places=10)


class TestPercentagePointChange(unittest.TestCase):
    def test_increase(self):
        self.assertAlmostEqual(percentage_point_change(4.3, 4.1), 0.2, places=10)

    def test_decrease(self):
        self.assertAlmostEqual(percentage_point_change(4.33, 4.48), -0.15, places=10)

    def test_unchanged_is_exactly_zero(self):
        self.assertEqual(percentage_point_change(4.33, 4.33), 0.0)

    def test_zero_denominator_is_not_an_error_here(self):
        # A difference has no denominator, unlike a percentage change.
        self.assertEqual(percentage_point_change(2.0, 0.0), 2.0)

    def test_differs_from_percentage_change(self):
        # The distinction that matters: 4.3 vs 4.1 is +0.2pp, not +4.88%.
        pp = percentage_point_change(4.3, 4.1)
        pct = percentage_change(4.3, 4.1)
        self.assertAlmostEqual(pp, 0.2, places=10)
        self.assertAlmostEqual(pct, 4.878048780487809, places=10)
        self.assertNotAlmostEqual(pp, pct, places=3)


class TestYoyChange(unittest.TestCase):
    def test_monthly_yoy(self):
        series = [100.0] + [0.0] * 11 + [104.0]
        # Index 0 is twelve positions before index 12.
        self.assertAlmostEqual(yoy_change(series), 4.0, places=10)

    def test_quarterly_yoy_uses_four_periods(self):
        series = [100.0, 0.0, 0.0, 0.0, 103.0]
        self.assertAlmostEqual(yoy_change(series, periods_per_year=4), 3.0, places=10)

    def test_insufficient_history(self):
        with self.assertRaises(InsufficientHistoryError):
            yoy_change([100.0] * 12)  # needs 13

    def test_boundary_history_is_accepted(self):
        self.assertIsInstance(yoy_change([100.0] * 13), float)

    def test_invalid_periods_per_year(self):
        with self.assertRaises(CalculationError):
            yoy_change([1.0, 2.0], periods_per_year=0)


class TestQoqAnnualizedChange(unittest.TestCase):
    def test_one_percent_quarterly_compounds(self):
        # (1.01 ** 4 - 1) * 100 = 4.060401
        self.assertAlmostEqual(
            qoq_annualized_change(20301.0, 20100.0), 4.060401, places=9
        )

    def test_half_percent_quarterly_compounds(self):
        # (1.005 ** 4 - 1) * 100 = 2.0150500625
        self.assertAlmostEqual(
            qoq_annualized_change(20100.0, 20000.0), 2.0150500625, places=9
        )

    def test_is_not_four_times_the_quarterly_change(self):
        annualised = qoq_annualized_change(20301.0, 20100.0)
        naive = percentage_change(20301.0, 20100.0) * 4
        self.assertAlmostEqual(naive, 4.0, places=6)
        self.assertNotAlmostEqual(annualised, naive, places=4)

    def test_contraction(self):
        # (0.99 ** 4 - 1) * 100 = -3.940399
        self.assertAlmostEqual(
            qoq_annualized_change(19800.0, 20000.0), -3.940399, places=9
        )

    def test_zero_denominator_rejected(self):
        with self.assertRaises(ZeroDenominatorError):
            qoq_annualized_change(20000.0, 0.0)

    def test_non_positive_ratio_rejected(self):
        # A negative ratio raised to the fourth power would look like growth.
        with self.assertRaises(CalculationError):
            qoq_annualized_change(-20000.0, 20000.0)


class TestNumericGuards(unittest.TestCase):
    """Bad input must fail loudly, never be coerced."""

    def test_none_is_missing(self):
        with self.assertRaises(MissingValueError):
            require_number(None, "cpi")

    def test_numeric_string_is_rejected(self):
        # The important one: FRED returns "307.026", and accepting it here is
        # how string arithmetic enters a pipeline.
        with self.assertRaises(NonNumericValueError):
            require_number("307.026", "cpi")

    def test_non_numeric_string_is_rejected(self):
        with self.assertRaises(NonNumericValueError):
            require_number(".", "cpi")  # FRED's missing-observation sentinel

    def test_bool_is_rejected(self):
        with self.assertRaises(NonNumericValueError):
            require_number(True, "cpi")

    def test_nan_is_rejected(self):
        with self.assertRaises(NonNumericValueError):
            require_number(float("nan"), "cpi")

    def test_infinity_is_rejected(self):
        with self.assertRaises(NonNumericValueError):
            require_number(math.inf, "cpi")

    def test_none_propagates_through_percentage_change(self):
        with self.assertRaises(MissingValueError):
            percentage_change(None, 100.0)
        with self.assertRaises(MissingValueError):
            percentage_change(100.0, None)

    def test_string_propagates_through_every_public_function(self):
        for func in (percentage_change, percentage_point_change, qoq_annualized_change):
            with self.subTest(func=func.__name__):
                with self.assertRaises(NonNumericValueError):
                    func("100", 100.0)

    def test_no_internal_rounding(self):
        # A result that is not round must be returned unrounded.
        result = percentage_change(100.0, 3.0)
        self.assertGreater(len(repr(result).split(".")[-1]), 6)


if __name__ == "__main__":
    unittest.main()
