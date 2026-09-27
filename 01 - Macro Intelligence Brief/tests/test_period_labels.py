"""Deterministic period labels.

The canonical period date is unambiguous to a machine and ambiguous to a
reader: ``2026-04-01`` on a quarterly series means 2026 Q2, not "April GDP".
These tests pin the label for every frequency, and pin the refusal to guess when
a period does not fit its frequency's convention.

Nothing here requires a network connection or a language model. The labels are
generated from ``period`` plus the declared ``frequency`` and nothing else.
"""

import json
import pathlib
import unittest
from datetime import date

from src.errors import InvalidPeriodError
from src.models import Frequency
from src.periods import period_label

REAL_BRIEF = (pathlib.Path(__file__).resolve().parent.parent / "derived"
              / "brief_input.json")


class TestMonthlyLabels(unittest.TestCase):
    def test_august(self):
        self.assertEqual(period_label(date(2026, 8, 1), Frequency.MONTHLY),
                         "August 2026")

    def test_every_month_renders(self):
        expected = ["January", "February", "March", "April", "May", "June", "July",
                    "August", "September", "October", "November", "December"]
        for month, name in enumerate(expected, start=1):
            with self.subTest(month=month):
                self.assertEqual(period_label(date(2026, month, 1), Frequency.MONTHLY),
                                 f"{name} 2026")

    def test_year_is_included(self):
        self.assertEqual(period_label(date(2025, 8, 1), Frequency.MONTHLY),
                         "August 2025")

    def test_mid_month_date_rejected(self):
        with self.assertRaises(InvalidPeriodError) as ctx:
            period_label(date(2026, 8, 15), Frequency.MONTHLY)
        self.assertIn("first of the month", str(ctx.exception))

    def test_no_day_number_in_a_monthly_label(self):
        label = period_label(date(2026, 8, 1), Frequency.MONTHLY)
        self.assertNotIn("1", label.replace("2026", ""))


class TestQuarterlyLabels(unittest.TestCase):
    def test_q1(self):
        self.assertEqual(period_label(date(2026, 1, 1), Frequency.QUARTERLY),
                         "2026 Q1")

    def test_q2(self):
        self.assertEqual(period_label(date(2026, 4, 1), Frequency.QUARTERLY),
                         "2026 Q2")

    def test_q3(self):
        self.assertEqual(period_label(date(2026, 7, 1), Frequency.QUARTERLY),
                         "2026 Q3")

    def test_q4(self):
        self.assertEqual(period_label(date(2026, 10, 1), Frequency.QUARTERLY),
                         "2026 Q4")

    def test_quarter_mapping_is_exactly_the_four_opening_months(self):
        mapping = {1: "2026 Q1", 4: "2026 Q2", 7: "2026 Q3", 10: "2026 Q4"}
        for month, expected in mapping.items():
            with self.subTest(month=month):
                self.assertEqual(period_label(date(2026, month, 1),
                                              Frequency.QUARTERLY), expected)

    def test_invalid_quarterly_month_rejected(self):
        # Every month that does not open a quarter must be refused, not guessed.
        for month in (2, 3, 5, 6, 8, 9, 11, 12):
            with self.subTest(month=month):
                with self.assertRaises(InvalidPeriodError) as ctx:
                    period_label(date(2026, month, 1), Frequency.QUARTERLY)
                self.assertIn("does not", str(ctx.exception))

    def test_refusal_names_the_permitted_months(self):
        with self.assertRaises(InvalidPeriodError) as ctx:
            period_label(date(2026, 5, 1), Frequency.QUARTERLY)
        message = str(ctx.exception)
        for month in ("January", "April", "July", "October"):
            self.assertIn(month, message)
        self.assertIn("Refusing to guess", message)

    def test_mid_month_quarterly_date_rejected(self):
        with self.assertRaises(InvalidPeriodError):
            period_label(date(2026, 4, 15), Frequency.QUARTERLY)

    def test_quarterly_label_does_not_name_a_month(self):
        # "2026 Q2", never "April 2026" — the defect this contract prevents.
        label = period_label(date(2026, 4, 1), Frequency.QUARTERLY)
        self.assertNotIn("April", label)
        self.assertEqual(label, "2026 Q2")


class TestDailyLabels(unittest.TestCase):
    def test_renders_the_actual_date(self):
        self.assertEqual(period_label(date(2026, 9, 24), Frequency.DAILY),
                         "24 September 2026")

    def test_single_digit_day_not_zero_padded(self):
        self.assertEqual(period_label(date(2026, 9, 4), Frequency.DAILY),
                         "4 September 2026")

    def test_first_of_month_is_a_real_day_for_a_daily_series(self):
        # Unlike monthly, day 1 is a genuine observation date here.
        self.assertEqual(period_label(date(2026, 9, 1), Frequency.DAILY),
                         "1 September 2026")

    def test_any_day_is_accepted(self):
        for day in (1, 15, 28, 30):
            with self.subTest(day=day):
                self.assertIn("September 2026",
                              period_label(date(2026, 9, day), Frequency.DAILY))


class TestDerivationInvariant(unittest.TestCase):
    """The label follows from period + declared frequency, nothing else."""

    def test_same_date_labels_differently_by_frequency(self):
        day = date(2026, 4, 1)
        self.assertEqual(period_label(day, Frequency.MONTHLY), "April 2026")
        self.assertEqual(period_label(day, Frequency.QUARTERLY), "2026 Q2")
        self.assertEqual(period_label(day, Frequency.DAILY), "1 April 2026")

    def test_free_text_frequency_rejected(self):
        # Must not be derived from source metadata strings such as "Daily, 7-Day".
        for bad in ("monthly", "Daily, 7-Day", "Quarterly", None, 3):
            with self.subTest(frequency=bad):
                with self.assertRaises(InvalidPeriodError):
                    period_label(date(2026, 8, 1), bad)

    def test_non_date_period_rejected(self):
        with self.assertRaises(InvalidPeriodError):
            period_label("2026-08-01", Frequency.MONTHLY)

    def test_output_is_deterministic(self):
        for _ in range(3):
            self.assertEqual(period_label(date(2026, 4, 1), Frequency.QUARTERLY),
                             "2026 Q2")

    def test_labels_are_english_and_locale_independent(self):
        # Month names are hard-coded, so no locale can change the output.
        self.assertEqual(period_label(date(2026, 1, 1), Frequency.MONTHLY),
                         "January 2026")


class TestFirstRealLabels(unittest.TestCase):
    """The committed artefact must carry the expected labels."""

    def setUp(self):
        if not REAL_BRIEF.exists():
            self.skipTest("first real brief input not present")
        self.brief = json.loads(REAL_BRIEF.read_text())
        self.by_series = {i["source_series"]: i for i in self.brief["indicators"]}

    def test_cpi_label(self):
        self.assertEqual(self.by_series["CPIAUCNS"]["period_label"], "August 2026")

    def test_unemployment_label(self):
        self.assertEqual(self.by_series["UNRATE"]["period_label"], "August 2026")

    def test_retail_label(self):
        self.assertEqual(self.by_series["RSAFS"]["period_label"], "August 2026")

    def test_dff_label(self):
        self.assertEqual(self.by_series["DFF"]["period_label"], "24 September 2026")

    def test_gdp_label(self):
        self.assertEqual(self.by_series["GDPC1"]["period_label"], "2026 Q2")

    def test_gdp_label_is_not_april(self):
        # The exact misreading this phase removes.
        self.assertNotIn("April", self.by_series["GDPC1"]["period_label"])

    def test_all_five_carry_frequency(self):
        for series, entry in self.by_series.items():
            with self.subTest(series=series):
                self.assertIn(entry["frequency"], ("monthly", "quarterly", "daily"))

    def test_all_five_carry_period_and_label(self):
        for series, entry in self.by_series.items():
            with self.subTest(series=series):
                self.assertIn("period", entry)
                self.assertIn("period_label", entry)
                self.assertTrue(entry["period_label"])

    def test_canonical_period_unchanged(self):
        expected = {"CPIAUCNS": "2026-08-01", "UNRATE": "2026-08-01",
                    "RSAFS": "2026-08-01", "DFF": "2026-09-24",
                    "GDPC1": "2026-04-01"}
        for series, period in expected.items():
            with self.subTest(series=series):
                self.assertEqual(self.by_series[series]["period"], period)

    def test_label_is_reproducible_from_the_stored_fields(self):
        # Regenerating the label from the file's own period + frequency must
        # give back exactly what the file stores.
        for series, entry in self.by_series.items():
            with self.subTest(series=series):
                self.assertEqual(
                    period_label(date.fromisoformat(entry["period"]),
                                 Frequency(entry["frequency"])),
                    entry["period_label"])

    def test_contract_documents_the_field_distinction(self):
        contract = self.brief["period_field_contract"]
        for key in ("period", "period_label", "frequency", "why"):
            self.assertIn(key, contract)
        self.assertIn("MUST be used", contract["period_label"])
        self.assertIn("2026 Q2", contract["why"])

    def test_usage_contract_forbids_reinterpreting_the_canonical_date(self):
        must_not = " ".join(self.brief["usage_contract"]["must_not"]).lower()
        self.assertIn("reinterpret the canonical period date", must_not)


class TestNoExternalDependency(unittest.TestCase):
    def test_periods_module_performs_no_io(self):
        source = pathlib.Path(
            __file__).resolve().parent.parent.joinpath("src/periods.py").read_text()
        for forbidden in ("import urllib", "import socket", "import requests",
                          "open(", "os.environ", "getenv", "datetime.now"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_no_locale_dependent_formatting(self):
        # strftime("%B") would give a translated month name on a non-English
        # machine. Month names are hard-coded for exactly that reason.
        source = pathlib.Path(
            __file__).resolve().parent.parent.joinpath("src/periods.py").read_text()
        for forbidden in ("import locale", "setlocale", "strftime", "%B", "%b"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_no_model_involved(self):
        source = pathlib.Path(
            __file__).resolve().parent.parent.joinpath("src/periods.py").read_text()
        for forbidden in ("gemini", "openai", "anthropic", "claude", "llm"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source.lower())
