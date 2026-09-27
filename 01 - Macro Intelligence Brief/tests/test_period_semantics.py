"""Period-selection semantics: a systematic guard against the Phase 2 defect.

Phase 2 shipped a figure that was wrong by 0.30pp because comparison periods
were chosen by list position. Across a gap in the source data, position -13 is
not twelve months earlier. The defect raised no exception and 119 tests passed.

These tests assert the semantics of every indicator, and that a missing required
period fails loudly rather than being bridged by a neighbouring observation.
"""

import unittest
from datetime import date, datetime, timezone

from src.errors import MissingRequiredPeriodError
from src.indicators import SPECS, compute
from src.models import Frequency, PeriodSelection
from src.normalisation import normalise_observations
from src.validation import CALENDAR_REQUIRED_FREQUENCIES, validate_period_semantics

RETRIEVED = datetime(2026, 9, 27, tzinfo=timezone.utc)


def series(pairs, series_id="X"):
    payload = {"observations": [{"date": d, "value": v} for d, v in pairs]}
    return normalise_observations(payload, series_id).observations


class TestDeclaredSemantics(unittest.TestCase):
    """Each indicator must declare, not imply, how it selects periods."""

    EXPECTED = {
        "CPIAUCNS": PeriodSelection.CALENDAR,
        "UNRATE": PeriodSelection.CALENDAR,
        "RSAFS": PeriodSelection.CALENDAR,
        "GDPC1": PeriodSelection.CALENDAR,
        "DFF": PeriodSelection.PREVIOUS_AVAILABLE,
    }

    def test_every_indicator_declares_its_selection(self):
        for spec in SPECS.values():
            with self.subTest(series=spec.source_series):
                self.assertIs(spec.period_selection,
                              self.EXPECTED[spec.source_series])

    def test_only_dff_is_previous_available(self):
        positional = {s.source_series for s in SPECS.values()
                      if s.period_selection is PeriodSelection.PREVIOUS_AVAILABLE}
        self.assertEqual(positional, {"DFF"})

    def test_monthly_and_quarterly_must_be_calendar(self):
        for spec in SPECS.values():
            if spec.frequency in CALENDAR_REQUIRED_FREQUENCIES:
                with self.subTest(series=spec.source_series):
                    self.assertIs(spec.period_selection, PeriodSelection.CALENDAR)

    def test_invariant_passes_for_every_real_spec(self):
        for spec in SPECS.values():
            with self.subTest(series=spec.source_series):
                findings = validate_period_semantics(spec)
                self.assertEqual(
                    [f for f in findings if f.severity == "hard_failure"], [])

    def test_invariant_rejects_positional_on_a_monthly_series(self):
        import dataclasses
        broken = dataclasses.replace(
            SPECS["us_cpi_inflation_yoy"],
            period_selection=PeriodSelection.PREVIOUS_AVAILABLE)
        findings = validate_period_semantics(broken)
        codes = [f.code for f in findings if f.severity == "hard_failure"]
        self.assertIn("semantics.positional_selection_forbidden", codes)

    def test_invariant_rejects_positional_on_a_quarterly_series(self):
        import dataclasses
        broken = dataclasses.replace(
            SPECS["us_real_gdp_growth_qoq_ann"],
            period_selection=PeriodSelection.PREVIOUS_AVAILABLE)
        codes = [f.code for f in validate_period_semantics(broken)
                 if f.severity == "hard_failure"]
        self.assertIn("semantics.positional_selection_forbidden", codes)

    def test_comparison_text_states_the_basis(self):
        for spec in SPECS.values():
            with self.subTest(series=spec.source_series):
                text = spec.comparison.lower()
                if spec.period_selection is PeriodSelection.CALENDAR:
                    self.assertIn("calendar", text)
                else:
                    self.assertIn("available", text)


class TestUnrateRequiredMonthGap(unittest.TestCase):
    """The previous CALENDAR month must be used, never an older observation."""

    def test_missing_previous_month_fails(self):
        # 2026-08 present, 2026-07 absent, older months present.
        s = series([("2026-04-01", "4.3"), ("2026-05-01", "4.3"),
                    ("2026-06-01", "4.2"), ("2026-08-01", "4.1")], "UNRATE")
        self.assertGreaterEqual(len(s), 2)  # history is not the problem
        with self.assertRaises(MissingRequiredPeriodError) as ctx:
            compute("us_unemployment_rate", s, retrieved_at=RETRIEVED)
        self.assertIn("2026-07-01", str(ctx.exception))

    def test_older_observation_is_not_substituted(self):
        s = series([("2026-06-01", "4.2"), ("2026-08-01", "4.1")], "UNRATE")
        with self.assertRaises(MissingRequiredPeriodError):
            compute("us_unemployment_rate", s, retrieved_at=RETRIEVED)

    def test_adjacent_month_present_succeeds(self):
        s = series([("2026-07-01", "4.2"), ("2026-08-01", "4.1")], "UNRATE")
        obs = compute("us_unemployment_rate", s, retrieved_at=RETRIEVED)
        self.assertAlmostEqual(obs.change, -0.1, places=10)

    def test_irrelevant_historical_gap_does_not_block(self):
        # 2025-10 missing — the real gap — but every required period is present.
        s = series([("2025-09-01", "4.4"), ("2025-11-01", "4.5"),
                    ("2026-07-01", "4.2"), ("2026-08-01", "4.1")], "UNRATE")
        obs = compute("us_unemployment_rate", s, retrieved_at=RETRIEVED)
        self.assertAlmostEqual(obs.value, 4.1, places=10)
        self.assertAlmostEqual(obs.previous_value, 4.2, places=10)


class TestRsafsRequiredMonthGap(unittest.TestCase):
    def test_missing_previous_month_fails(self):
        s = series([("2026-04-01", "759097.0"), ("2026-05-01", "766192.0"),
                    ("2026-06-01", "768587.0"), ("2026-08-01", "773947.0")], "RSAFS")
        with self.assertRaises(MissingRequiredPeriodError) as ctx:
            compute("us_retail_sales_mom", s, retrieved_at=RETRIEVED)
        self.assertIn("2026-07-01", str(ctx.exception))

    def test_missing_second_previous_month_fails(self):
        # t and t-1 present, t-2 absent: the previous MoM cannot be formed.
        s = series([("2026-05-01", "766192.0"), ("2026-07-01", "764462.0"),
                    ("2026-08-01", "773947.0")], "RSAFS")
        with self.assertRaises(MissingRequiredPeriodError) as ctx:
            compute("us_retail_sales_mom", s, retrieved_at=RETRIEVED)
        self.assertIn("2026-06-01", str(ctx.exception))

    def test_irrelevant_historical_gap_does_not_block(self):
        s = series([("2025-09-01", "732192.0"), ("2025-12-01", "734717.0"),
                    ("2026-06-01", "768587.0"), ("2026-07-01", "764462.0"),
                    ("2026-08-01", "773947.0")], "RSAFS")
        obs = compute("us_retail_sales_mom", s, retrieved_at=RETRIEVED)
        self.assertAlmostEqual(obs.value, 1.2407418550562266, places=9)


class TestGdpRequiredQuarterGap(unittest.TestCase):
    def test_missing_previous_quarter_fails(self):
        # 2026-Q2 present, 2026-Q1 absent, older quarters present.
        s = series([("2025-07-01", "24026.834"), ("2025-10-01", "24055.749"),
                    ("2026-04-01", "24269.613")], "GDPC1")
        with self.assertRaises(MissingRequiredPeriodError) as ctx:
            compute("us_real_gdp_growth_qoq_ann", s, retrieved_at=RETRIEVED)
        self.assertIn("2026-01-01", str(ctx.exception))

    def test_older_quarter_is_not_substituted(self):
        # Four observations, so the history precheck passes; 2026-Q1 is absent, so
        # the required-period lookup is what must fail. 2025-Q4 sits immediately
        # before 2026-Q2 in the list and must NOT be used in its place.
        s = series([("2025-04-01", "23770.976"), ("2025-07-01", "24026.834"),
                    ("2025-10-01", "24055.749"), ("2026-04-01", "24269.613")], "GDPC1")
        self.assertGreaterEqual(len(s), 3)  # history is not the problem
        self.assertEqual(s[-2].period, date(2025, 10, 1))  # the tempting substitute
        with self.assertRaises(MissingRequiredPeriodError) as ctx:
            compute("us_real_gdp_growth_qoq_ann", s, retrieved_at=RETRIEVED)
        self.assertIn("2026-01-01", str(ctx.exception))

    def test_missing_second_previous_quarter_fails(self):
        s = series([("2025-07-01", "24026.834"), ("2026-01-01", "24180.419"),
                    ("2026-04-01", "24269.613")], "GDPC1")
        with self.assertRaises(MissingRequiredPeriodError) as ctx:
            compute("us_real_gdp_growth_qoq_ann", s, retrieved_at=RETRIEVED)
        self.assertIn("2025-10-01", str(ctx.exception))

    def test_irrelevant_historical_gap_does_not_block(self):
        s = series([("2024-07-01", "23478.57"), ("2025-10-01", "24055.749"),
                    ("2026-01-01", "24180.419"), ("2026-04-01", "24269.613")], "GDPC1")
        obs = compute("us_real_gdp_growth_qoq_ann", s, retrieved_at=RETRIEVED)
        self.assertAlmostEqual(obs.value, 1.4836587880023622, places=9)


class TestCpiRequiredMonthGap(unittest.TestCase):
    """Retained from Phase 2: the case that exposed the defect."""

    REAL = [
        ("2024-09-01", "315.301"), ("2024-10-01", "315.664"), ("2024-11-01", "315.493"),
        ("2024-12-01", "315.605"), ("2025-01-01", "317.671"), ("2025-02-01", "319.082"),
        ("2025-03-01", "319.799"), ("2025-04-01", "320.795"), ("2025-05-01", "321.465"),
        ("2025-06-01", "322.561"), ("2025-07-01", "323.048"), ("2025-08-01", "323.976"),
        ("2025-09-01", "324.800"), ("2025-10-01", "."),       ("2025-11-01", "324.122"),
        ("2025-12-01", "324.054"), ("2026-01-01", "325.252"), ("2026-02-01", "326.785"),
        ("2026-03-01", "330.213"), ("2026-04-01", "333.020"), ("2026-05-01", "335.123"),
        ("2026-06-01", "333.952"), ("2026-07-01", "333.918"), ("2026-08-01", "334.980"),
    ]

    def test_irrelevant_gap_does_not_block_and_answer_is_right(self):
        s = series(self.REAL, "CPIAUCNS")
        obs = compute("us_cpi_inflation_yoy", s, retrieved_at=RETRIEVED)
        self.assertAlmostEqual(obs.value, 3.396548, places=5)
        self.assertNotAlmostEqual(obs.value, 3.693569, places=4)  # the old wrong answer

    def test_missing_year_ago_month_fails(self):
        s = series([p for p in self.REAL if p[0] != "2025-08-01"], "CPIAUCNS")
        with self.assertRaises(MissingRequiredPeriodError) as ctx:
            compute("us_cpi_inflation_yoy", s, retrieved_at=RETRIEVED)
        self.assertIn("CPI_t-12", str(ctx.exception))

    def test_missing_thirteen_month_counterpart_fails(self):
        s = series([p for p in self.REAL if p[0] != "2025-07-01"], "CPIAUCNS")
        with self.assertRaises(MissingRequiredPeriodError) as ctx:
            compute("us_cpi_inflation_yoy", s, retrieved_at=RETRIEVED)
        self.assertIn("CPI_t-13", str(ctx.exception))


class TestDffPreviousAvailableRetained(unittest.TestCase):
    """DFF must keep previous-available semantics; a calendar gap must not fail."""

    def test_weekend_style_gap_does_not_fail(self):
        s = series([("2026-09-18", "3.88"), ("2026-09-21", "3.88")], "DFF")
        obs = compute("us_effective_fed_funds_rate", s, retrieved_at=RETRIEVED)
        self.assertEqual(obs.period, date(2026, 9, 21))
        self.assertEqual(obs.change, 0.0)

    def test_long_gap_does_not_fail(self):
        s = series([("2026-08-01", "3.63"), ("2026-09-24", "3.88")], "DFF")
        obs = compute("us_effective_fed_funds_rate", s, retrieved_at=RETRIEVED)
        self.assertAlmostEqual(obs.change, 0.25, places=10)

    def test_real_policy_move_is_captured(self):
        # The move visible in the real retrieved window.
        s = series([("2026-09-16", "3.63"), ("2026-09-17", "3.88")], "DFF")
        obs = compute("us_effective_fed_funds_rate", s, retrieved_at=RETRIEVED)
        self.assertAlmostEqual(obs.value, 3.88, places=10)
        self.assertAlmostEqual(obs.change, 0.25, places=10)

    def test_never_raises_missing_required_period(self):
        s = series([("2026-01-05", "3.63"), ("2026-09-24", "3.88")], "DFF")
        try:
            compute("us_effective_fed_funds_rate", s, retrieved_at=RETRIEVED)
        except MissingRequiredPeriodError:
            self.fail("DFF must not require a calendar-adjacent observation")


class TestToleranceCategories(unittest.TestCase):
    """The two tolerances answer different questions and must stay distinct."""

    def test_computational_tolerance_is_tight(self):
        from src.validation import FRED_COMPUTATIONAL_TOLERANCE_PP
        self.assertEqual(FRED_COMPUTATIONAL_TOLERANCE_PP, 0.001)

    def test_official_publication_tolerance_is_looser(self):
        from src.validation import OFFICIAL_PUBLICATION_TOLERANCE_PP
        self.assertEqual(OFFICIAL_PUBLICATION_TOLERANCE_PP, 0.05)

    def test_the_two_are_not_the_same_value(self):
        from src.validation import (FRED_COMPUTATIONAL_TOLERANCE_PP,
                                    OFFICIAL_PUBLICATION_TOLERANCE_PP)
        self.assertLess(FRED_COMPUTATIONAL_TOLERANCE_PP,
                        OFFICIAL_PUBLICATION_TOLERANCE_PP)

    def test_real_observed_differences_sit_inside_the_tight_bound(self):
        from src.validation import FRED_COMPUTATIONAL_TOLERANCE_PP
        for observed in (2.1075635143752436e-06, 1.211997637806661e-06):
            with self.subTest(observed=observed):
                self.assertLess(abs(observed), FRED_COMPUTATIONAL_TOLERANCE_PP)

    def test_the_phase2_defect_would_now_be_a_hard_failure(self):
        from src.validation import FRED_COMPUTATIONAL_TOLERANCE_PP
        defect = 3.693569 - 3.396548
        self.assertGreater(abs(defect), FRED_COMPUTATIONAL_TOLERANCE_PP)

    def test_publication_rounding_fits_the_official_tolerance(self):
        # BEA publishes to 1dp: the worst case a correct figure can differ is 0.05.
        from src.validation import OFFICIAL_PUBLICATION_TOLERANCE_PP
        self.assertLessEqual(abs(1.4836587880023622 - 1.5),
                             OFFICIAL_PUBLICATION_TOLERANCE_PP)
        self.assertGreater(abs(1.4836587880023622 - 1.5), 0.001)  # would fail (A)
