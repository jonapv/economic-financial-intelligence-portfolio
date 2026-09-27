"""The brief input contract, and the publication invariant that guards it.

The artefact tested here is the only structured economic input a future
synthesis layer may receive. The invariant that matters most: it does not exist
when validation failed. A language model must never get the chance to write
fluent prose about invalid figures, because fluency is what makes a wrong figure
dangerous.
"""

import json
import pathlib
import unittest
from datetime import date, datetime, timezone

from src.brief_input import (
    SCHEMA_VERSION,
    PublicationBlockedError,
    build_brief_input,
)
from src.indicators import SPECS, compute
from src.normalisation import normalise_observations
from src.provenance import RunProvenance, SeriesProvenance, series_provenance_from
from src.validation import Finding, ValidationReport, validate_series

RETRIEVED = datetime(2026, 9, 27, 0, 6, 34, tzinfo=timezone.utc)
GENERATED = datetime(2026, 9, 27, 2, 0, 0, tzinfo=timezone.utc)
FAKE_KEY = "0123456789abcdef0123456789abcdef"

# Minimal real-shaped input sufficient to produce all five indicators.
FIXTURES = {
    "CPIAUCNS": [(f"{y}-{m:02d}-01", v) for y, m, v in [
        (2025, 6, "322.561"), (2025, 7, "323.048"), (2025, 8, "323.976"),
        (2025, 9, "324.800"), (2025, 11, "324.122"), (2025, 12, "324.054"),
        (2026, 1, "325.252"), (2026, 2, "326.785"), (2026, 3, "330.213"),
        (2026, 4, "333.020"), (2026, 5, "335.123"), (2026, 6, "333.952"),
        (2026, 7, "333.918"), (2026, 8, "334.980")]],
    "UNRATE": [("2026-06-01", "4.2"), ("2026-07-01", "4.1"), ("2026-08-01", "4.1")],
    "DFF": [("2026-09-22", "3.88"), ("2026-09-23", "3.88"), ("2026-09-24", "3.88")],
    "GDPC1": [("2025-10-01", "24055.749"), ("2026-01-01", "24180.419"),
              ("2026-04-01", "24269.613")],
    "RSAFS": [("2026-06-01", "768587.0"), ("2026-07-01", "764462.0"),
              ("2026-08-01", "773947.0")],
}

METADATA = {
    "CPIAUCNS": {"frequency": "Monthly", "seasonal_adjustment": "Not Seasonally Adjusted",
                 "last_updated": "2026-09-11 08:37:49-05"},
    "UNRATE": {"frequency": "Monthly", "seasonal_adjustment": "Seasonally Adjusted",
               "last_updated": "2026-09-04 08:27:31-05"},
    "DFF": {"frequency": "Daily, 7-Day", "seasonal_adjustment": "Not Seasonally Adjusted",
            "last_updated": "2026-09-25 15:16:33-05"},
    "GDPC1": {"frequency": "Quarterly",
              "seasonal_adjustment": "Seasonally Adjusted Annual Rate",
              "last_updated": "2026-08-26 07:49:02-05"},
    "RSAFS": {"frequency": "Monthly", "seasonal_adjustment": "Seasonally Adjusted",
              "last_updated": "2026-09-16 07:39:53-05"},
}


#: A contiguous CPI series, fully synthetic, for tests that need a run with NO
#: warnings at all. The series above is real and deliberately contains the
#: October 2025 gap, which legitimately raises series.unusual_gaps — so it
#: cannot be used to test the warning-free case.
CPI_GAPLESS_SYNTHETIC = [
    ("2025-07-01", "100.0"), ("2025-08-01", "100.2"), ("2025-09-01", "100.4"),
    ("2025-10-01", "100.6"), ("2025-11-01", "100.8"), ("2025-12-01", "101.0"),
    ("2026-01-01", "101.2"), ("2026-02-01", "101.4"), ("2026-03-01", "101.6"),
    ("2026-04-01", "101.8"), ("2026-05-01", "102.0"), ("2026-06-01", "102.2"),
    ("2026-07-01", "102.4"), ("2026-08-01", "103.0"),
]


def build_fixture_run(*, extra_findings=(), gapless=False):
    """Compute all five indicators and assemble a report plus provenance.

    ``gapless=True`` swaps in a contiguous synthetic CPI series so the run
    produces no warnings of its own.
    """
    report = ValidationReport(run_id="test-run", generated_at=RETRIEVED)
    observations, provenance_series = [], {}
    for spec in SPECS.values():
        sid = spec.source_series
        pairs = (CPI_GAPLESS_SYNTHETIC if (gapless and sid == "CPIAUCNS")
                 else FIXTURES[sid])
        payload = {"observations": [{"date": d, "value": v} for d, v in pairs]}
        normalised = normalise_observations(payload, sid)
        for finding in validate_series(spec, normalised, now=date(2026, 9, 27),
                                       metadata=METADATA[sid]):
            report.add(finding)
        provenance_series[sid] = series_provenance_from(
            sid, metadata=METADATA[sid], normalised=normalised,
            source_name="Federal Reserve Bank of St. Louis (FRED)",
            raw_metadata_file=f"raw/{sid}.metadata.json",
            raw_observations_file=f"raw/{sid}.observations.json")
        observations.append(compute(spec.indicator_id, normalised.observations,
                                    retrieved_at=RETRIEVED))
    for finding in extra_findings:
        report.add(finding)
    provenance = RunProvenance(
        run_id="test-run", retrieved_at=RETRIEVED,
        source_name="Federal Reserve Bank of St. Louis (FRED)",
        snapshot_directory="data/reference/test-run",
        git_commit="8083c141401dc90506f4d7f1f79126ac3ea8f687",
        series=provenance_series)
    return observations, report, provenance


class TestPublicationInvariant(unittest.TestCase):
    """No brief input may exist unless the gate passed."""

    def test_built_when_publication_ready(self):
        obs, report, prov = build_fixture_run()
        self.assertTrue(report.publication_ready)
        brief = build_brief_input(obs, report, prov, generated_at=GENERATED)
        self.assertTrue(brief["publication_ready"])
        self.assertEqual(brief["indicator_count"], 5)

    def test_blocked_on_hard_failure(self):
        obs, report, prov = build_fixture_run(extra_findings=[
            Finding(code="metadata.frequency_mismatch", severity="hard_failure",
                    series_id="GDPC1", message="frequency disagrees")])
        self.assertFalse(report.publication_ready)
        with self.assertRaises(PublicationBlockedError) as ctx:
            build_brief_input(obs, report, prov, generated_at=GENERATED)
        self.assertIn("hard failure", str(ctx.exception))

    def test_blocked_on_crosscheck_disagreement(self):
        # A cross-check disagreement is now a hard failure, so it must block.
        obs, report, prov = build_fixture_run(extra_findings=[
            Finding(code="crosscheck.disagrees", severity="hard_failure",
                    series_id="CPIAUCNS", message="ours 3.69 vs source 3.40")])
        with self.assertRaises(PublicationBlockedError):
            build_brief_input(obs, report, prov, generated_at=GENERATED)

    def test_blocked_on_partial_indicator_set(self):
        obs, report, prov = build_fixture_run()
        with self.assertRaises(PublicationBlockedError) as ctx:
            build_brief_input(obs[:3], report, prov, generated_at=GENERATED)
        self.assertIn("partial", str(ctx.exception).lower())

    def test_warning_alone_does_not_block(self):
        obs, report, prov = build_fixture_run(extra_findings=[
            Finding(code="series.stale", severity="warning", series_id="GDPC1",
                    message="old")])
        brief = build_brief_input(obs, report, prov, generated_at=GENERATED)
        self.assertTrue(brief["publication_ready"])


class TestSchemaAndValues(unittest.TestCase):
    def setUp(self):
        obs, report, prov = build_fixture_run()
        self.observations = {o.indicator_id: o for o in obs}
        self.brief = build_brief_input(obs, report, prov, generated_at=GENERATED)

    def test_top_level_shape(self):
        for key in ("schema_version", "run_id", "generated_at", "publication_ready",
                    "indicators", "warnings", "provenance"):
            self.assertIn(key, self.brief)
        self.assertEqual(self.brief["schema_version"], SCHEMA_VERSION)

    def test_required_indicator_fields_present(self):
        required = ("indicator_id", "display_name", "economic_category", "period",
                    "value", "unit", "previous_value", "change", "change_unit",
                    "direction", "source_series", "source_name",
                    "source_last_updated", "retrieved_at", "validation_status")
        for entry in self.brief["indicators"]:
            with self.subTest(indicator=entry["indicator_id"]):
                for field in required:
                    self.assertIn(field, entry)
                    self.assertIsNotNone(entry[field], field)

    def test_exact_values_preserved_before_presentation_rounding(self):
        # The contract carries full float precision; rounding happens later.
        for entry in self.brief["indicators"]:
            source = self.observations[entry["indicator_id"]]
            with self.subTest(indicator=entry["indicator_id"]):
                self.assertEqual(entry["value"], source.value)
                self.assertEqual(entry["previous_value"], source.previous_value)
                self.assertEqual(entry["change"], source.change)

    def test_a_value_is_not_pre_rounded(self):
        cpi = next(e for e in self.brief["indicators"]
                   if e["indicator_id"] == "us_cpi_inflation_yoy")
        self.assertNotEqual(cpi["value"], round(cpi["value"], 2))
        self.assertGreater(len(repr(cpi["value"]).split(".")[-1]), 6)

    def test_economic_categories_assigned(self):
        categories = {e["source_series"]: e["economic_category"]
                      for e in self.brief["indicators"]}
        self.assertEqual(categories, {
            "CPIAUCNS": "Inflation", "UNRATE": "Labour market",
            "DFF": "Monetary policy", "GDPC1": "Growth", "RSAFS": "Consumption"})

    def test_periods_are_not_normalised_to_a_common_period(self):
        periods = {e["source_series"]: e["period"] for e in self.brief["indicators"]}
        self.assertEqual(periods["CPIAUCNS"], "2026-08-01")
        self.assertEqual(periods["DFF"], "2026-09-24")
        self.assertEqual(periods["GDPC1"], "2026-04-01")
        self.assertGreater(len(set(periods.values())), 1)

    def test_period_note_explains_the_distinction(self):
        note = self.brief["period_note"].lower()
        self.assertIn("latest available observation is not the latest economic period",
                      note)

    def test_usage_contract_forbids_calculation(self):
        must_not = " ".join(self.brief["usage_contract"]["must_not"]).lower()
        for forbidden in ("compute", "forecast", "suppress", "investment advice"):
            self.assertIn(forbidden, must_not)

    def test_is_json_serialisable(self):
        json.dumps(self.brief)

    def test_no_forecast_or_prose_fields(self):
        text = json.dumps(self.brief).lower()
        for banned in ("forecast:", "outlook", "we expect", "prediction"):
            self.assertNotIn(banned, text)


class TestProvenance(unittest.TestCase):
    def setUp(self):
        obs, report, prov = build_fixture_run()
        self.brief = build_brief_input(obs, report, prov, generated_at=GENERATED)
        self.prov = self.brief["provenance"]

    def test_run_level_fields(self):
        for key in ("run_id", "retrieved_at_utc", "source_name",
                    "raw_snapshot_directory", "git_commit_at_run", "series",
                    "vintage_policy", "reproducibility"):
            self.assertIn(key, self.prov)

    def test_every_series_has_provenance(self):
        self.assertEqual(set(self.prov["series"]),
                         {"CPIAUCNS", "UNRATE", "DFF", "GDPC1", "RSAFS"})

    def test_series_provenance_fields(self):
        for sid, entry in self.prov["series"].items():
            with self.subTest(series=sid):
                self.assertIsNotNone(entry["source_last_updated"])
                self.assertIn("observation_window", entry)
                self.assertIn("observation_counts", entry)
                self.assertIn("raw_snapshot_files", entry)
                self.assertTrue(entry["raw_snapshot_files"]["observations"])

    def test_source_last_updated_reaches_each_indicator(self):
        for entry in self.brief["indicators"]:
            with self.subTest(indicator=entry["indicator_id"]):
                self.assertEqual(
                    entry["source_last_updated"],
                    METADATA[entry["source_series"]]["last_updated"])

    def test_vintage_policy_states_the_distinction(self):
        self.assertIn("not the latest economic period",
                      self.prov["vintage_policy"].lower())

    def test_observation_counts_are_carried(self):
        counts = self.prov["series"]["CPIAUCNS"]["observation_counts"]
        self.assertEqual(counts["valid"], 14)
        self.assertEqual(counts["retrieved"], 14)

    def test_a_missing_observation_is_recorded_not_hidden(self):
        # A "." sentinel must surface in provenance as a named missing date.
        payload = {"observations": [{"date": "2026-07-01", "value": "."},
                                    {"date": "2026-08-01", "value": "4.1"}]}
        normalised = normalise_observations(payload, "UNRATE")
        prov = series_provenance_from(
            "UNRATE", metadata=METADATA["UNRATE"], normalised=normalised,
            source_name="FRED").to_dict()
        self.assertEqual(prov["observation_counts"]["missing"], 1)
        self.assertEqual(prov["observation_counts"]["missing_dates"], ["2026-07-01"])

    def test_traceable_to_a_run_and_a_file(self):
        self.assertEqual(self.prov["run_id"], self.brief["run_id"])
        self.assertTrue(self.prov["raw_snapshot_directory"])


class TestWarningPropagation(unittest.TestCase):
    def test_no_warnings_yields_empty_list(self):
        obs, report, prov = build_fixture_run(gapless=True)
        brief = build_brief_input(obs, report, prov, generated_at=GENERATED)
        self.assertEqual(brief["warnings"], [])
        self.assertIsInstance(brief["warnings"], list)

    def test_real_fixture_warning_is_not_invented_by_the_test(self):
        # The gap warning comes from the validator, not from the test harness.
        obs, report, prov = build_fixture_run()
        brief = build_brief_input(obs, report, prov, generated_at=GENERATED)
        codes = {w["code"] for w in brief["warnings"]}
        self.assertIn("series.unusual_gaps", codes)

    def test_warnings_carried_in_structured_form(self):
        obs, report, prov = build_fixture_run(gapless=True, extra_findings=[
            Finding(code="series.unusual_gaps", severity="warning",
                    series_id="CPIAUCNS", message="1 gap longer than 40 days",
                    detail={"gaps": [{"from": "2025-09-01", "to": "2025-11-01",
                                      "days": 61}]})])
        brief = build_brief_input(obs, report, prov, generated_at=GENERATED)
        self.assertEqual(len(brief["warnings"]), 1)
        warning = brief["warnings"][0]
        self.assertEqual(warning["code"], "series.unusual_gaps")
        self.assertEqual(warning["series_id"], "CPIAUCNS")
        self.assertEqual(warning["detail"]["gaps"][0]["days"], 61)

    def test_warning_codes_attached_to_the_affected_indicator(self):
        obs, report, prov = build_fixture_run(gapless=True, extra_findings=[
            Finding(code="series.stale", severity="warning", series_id="GDPC1",
                    message="old")])
        brief = build_brief_input(obs, report, prov, generated_at=GENERATED)
        gdp = next(e for e in brief["indicators"] if e["source_series"] == "GDPC1")
        other = next(e for e in brief["indicators"] if e["source_series"] == "DFF")
        self.assertIn("series.stale", gdp["warning_codes"])
        self.assertEqual(other["warning_codes"], [])

    def test_contract_forbids_suppressing_a_warning(self):
        obs, report, prov = build_fixture_run()
        brief = build_brief_input(obs, report, prov, generated_at=GENERATED)
        must_not = " ".join(brief["usage_contract"]["must_not"]).lower()
        self.assertIn("suppress", must_not)


class TestNoSecrets(unittest.TestCase):
    def test_no_credential_or_url_in_the_contract(self):
        obs, report, prov = build_fixture_run()
        text = json.dumps(build_brief_input(obs, report, prov, generated_at=GENERATED))
        self.assertNotIn(FAKE_KEY, text)
        self.assertNotIn("api_key", text)
        self.assertNotIn("stlouisfed.org/fred", text)

    def test_snapshot_guard_accepts_the_contract(self):
        from src.snapshot import assert_secret_free
        obs, report, prov = build_fixture_run()
        text = json.dumps(build_brief_input(obs, report, prov, generated_at=GENERATED))
        assert_secret_free(text, FAKE_KEY)  # must not raise

    def test_no_raw_payload_fields_leak_through(self):
        obs, report, prov = build_fixture_run()
        brief = build_brief_input(obs, report, prov, generated_at=GENERATED)
        for entry in brief["indicators"]:
            for noise in ("realtime_start", "realtime_end", "popularity", "notes",
                          "observation_start", "title"):
                self.assertNotIn(noise, entry)


class TestStoredArtefact(unittest.TestCase):
    """The committed first real brief input must satisfy the contract."""

    PATH = (pathlib.Path(__file__).resolve().parent.parent / "data" / "reference"
            / "phase2-first-real-run" / "derived" / "brief_input.json")

    def setUp(self):
        if not self.PATH.exists():
            self.skipTest("first real brief input not present")
        self.brief = json.loads(self.PATH.read_text())

    def test_publication_ready(self):
        self.assertTrue(self.brief["publication_ready"])

    def test_five_indicators(self):
        self.assertEqual(len(self.brief["indicators"]), 5)

    def test_matches_the_stored_macro_snapshot(self):
        snapshot = json.loads((self.PATH.parent / "macro_snapshot.json").read_text())
        stored = {r["indicator_id"]: r for r in snapshot["observations_full_precision"]}
        for entry in self.brief["indicators"]:
            with self.subTest(indicator=entry["indicator_id"]):
                recorded = stored[entry["indicator_id"]]
                self.assertEqual(entry["value"], recorded["value"])
                self.assertEqual(entry["previous_value"], recorded["previous_value"])
                self.assertEqual(entry["change"], recorded["change"])

    def test_periods_differ_as_expected(self):
        periods = {e["source_series"]: e["period"] for e in self.brief["indicators"]}
        self.assertEqual(periods["CPIAUCNS"], "2026-08-01")
        self.assertEqual(periods["UNRATE"], "2026-08-01")
        self.assertEqual(periods["RSAFS"], "2026-08-01")
        self.assertEqual(periods["DFF"], "2026-09-24")
        self.assertEqual(periods["GDPC1"], "2026-04-01")

    def test_contains_no_credential(self):
        text = self.PATH.read_text()
        self.assertNotIn("api_key", text)

    def test_warnings_preserved_from_the_real_run(self):
        codes = {w["code"] for w in self.brief["warnings"]}
        self.assertIn("series.unusual_gaps", codes)
