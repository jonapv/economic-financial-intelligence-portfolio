"""Tests for the collection boundary: client, normalisation, validation, gate.

No test in this file touches the network. Every HTTP response is stubbed, so the
suite is runnable offline and deterministic. Live access happens only in
``python3 -m src.run_collection``, which the tests never invoke.
"""

import json
import pathlib
import tempfile
import unittest
import urllib.error
import urllib.parse
from datetime import date, datetime, timezone

from src.errors import (
    CollectionError,
    MissingCredentialError,
    SourcePayloadError,
    SourceRequestError,
)
from src.fred_client import FredClient, read_api_key
from src.indicators import SPECS, compute
from src.normalisation import (
    MISSING_SENTINEL,
    normalise_observations,
    observation_gaps,
)
from src.snapshot import SecretLeakError, assert_secret_free, scan_tree_for_secret, write_json
from src.validation import (
    STALENESS_TOLERANCE_DAYS,
    Finding,
    ValidationReport,
    expected_sa_code,
    validate_derived,
    validate_metadata,
    validate_series,
)

FAKE_KEY = "0123456789abcdef0123456789abcdef"


# ---------------------------------------------------------------------------
# Stub HTTP layer
# ---------------------------------------------------------------------------

def observations_payload(pairs, *, units="lin", newest_first=True):
    """Build a FRED-shaped observations payload. Values are STRINGS, as FRED sends."""
    rows = [{"realtime_start": "2025-01-01", "realtime_end": "9999-12-31",
             "date": d, "value": v} for d, v in pairs]
    if newest_first:
        rows = list(reversed(rows))
    return {"realtime_start": "2025-01-01", "realtime_end": "9999-12-31",
            "units": units, "output_type": 1, "file_type": "json",
            "order_by": "observation_date",
            "sort_order": "desc" if newest_first else "asc",
            "count": len(rows), "offset": 0, "limit": len(rows),
            "observations": rows}


def metadata_payload(series_id, *, frequency_short="M", sa_short="NSA",
                     frequency="Monthly", sa="Not Seasonally Adjusted"):
    return {"seriess": [{
        "id": series_id, "realtime_start": "2025-01-01", "realtime_end": "9999-12-31",
        "title": f"Test series {series_id}", "observation_start": "1947-01-01",
        "observation_end": "2025-02-01", "frequency": frequency,
        "frequency_short": frequency_short, "units": "Index", "units_short": "Index",
        "seasonal_adjustment": sa, "seasonal_adjustment_short": sa_short,
        "last_updated": "2025-03-01 08:31:02-06", "popularity": 50, "notes": "test",
    }]}


def stub_fetch(routes, recorder=None):
    """Return a fetch(url) that dispatches on (endpoint, series_id, units)."""
    def fetch(url):
        if recorder is not None:
            recorder.append(url)
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        endpoint = parsed.path.split("/fred/", 1)[-1]
        key = (endpoint, query.get("series_id", [""])[0], query.get("units", ["-"])[0])
        for candidate in (key, (endpoint, key[1], "-"), (endpoint, "", "-")):
            if candidate in routes:
                result = routes[candidate]
                if isinstance(result, Exception):
                    raise result
                if isinstance(result, bytes):
                    return result
                return json.dumps(result).encode()
        raise AssertionError(f"no stub route for {key}")
    return fetch


# A 14-point CPI series whose YoY is exactly 4.0% now and 3.0% before.
CPI_PAIRS = [
    ("2024-01-01", "100.0"), ("2024-02-01", "100.0"), ("2024-03-01", "100.9"),
    ("2024-04-01", "101.3"), ("2024-05-01", "101.6"), ("2024-06-01", "101.8"),
    ("2024-07-01", "102.1"), ("2024-08-01", "102.0"), ("2024-09-01", "101.7"),
    ("2024-10-01", "101.5"), ("2024-11-01", "101.9"), ("2024-12-01", "102.4"),
    ("2025-01-01", "103.0"), ("2025-02-01", "104.0"),
]


class TestApiKeyHandling(unittest.TestCase):
    def test_missing_key_fails_clearly(self):
        with self.assertRaises(MissingCredentialError) as ctx:
            read_api_key({})
        message = str(ctx.exception)
        self.assertIn("FRED_API_KEY", message)
        self.assertIn("environment", message)

    def test_blank_key_treated_as_missing(self):
        with self.assertRaises(MissingCredentialError):
            read_api_key({"FRED_API_KEY": "   "})

    def test_key_read_and_stripped(self):
        self.assertEqual(read_api_key({"FRED_API_KEY": f" {FAKE_KEY} "}), FAKE_KEY)

    def test_error_message_contains_no_key(self):
        with self.assertRaises(MissingCredentialError) as ctx:
            read_api_key({})
        self.assertNotIn(FAKE_KEY, str(ctx.exception))

    def test_empty_key_rejected_by_client(self):
        with self.assertRaises(MissingCredentialError):
            FredClient("", fetch=stub_fetch({}))

    def test_key_is_sent_in_request(self):
        seen = []
        client = FredClient(FAKE_KEY, fetch=stub_fetch(
            {("series", "UNRATE", "-"): metadata_payload("UNRATE")}, seen))
        client.series_metadata("UNRATE")
        self.assertIn(f"api_key={FAKE_KEY}", seen[0])


class TestRequestDescription(unittest.TestCase):
    """What gets written to the manifest must never carry the credential."""

    def test_api_key_excluded(self):
        described = FredClient.describe_request(
            "series/observations",
            {"series_id": "DFF", "limit": "40", "api_key": FAKE_KEY, "units": "lin"},
        )
        self.assertNotIn("api_key", described["params"])
        self.assertNotIn(FAKE_KEY, json.dumps(described))

    def test_no_url_is_returned(self):
        described = FredClient.describe_request("series", {"series_id": "DFF"})
        self.assertEqual(set(described), {"endpoint", "params"})
        self.assertNotIn("url", described)


class TestMetadataFetch(unittest.TestCase):
    def test_successful_metadata_parsing(self):
        client = FredClient(FAKE_KEY, fetch=stub_fetch(
            {("series", "CPIAUCNS", "-"): metadata_payload("CPIAUCNS")}))
        metadata = client.series_metadata("CPIAUCNS")
        self.assertEqual(metadata["id"], "CPIAUCNS")
        self.assertEqual(metadata["frequency_short"], "M")
        self.assertEqual(metadata["seasonal_adjustment_short"], "NSA")

    def test_empty_seriess_rejected(self):
        client = FredClient(FAKE_KEY, fetch=stub_fetch(
            {("series", "CPIAUCNS", "-"): {"seriess": []}}))
        with self.assertRaises(SourcePayloadError):
            client.series_metadata("CPIAUCNS")

    def test_missing_seriess_rejected(self):
        client = FredClient(FAKE_KEY, fetch=stub_fetch(
            {("series", "CPIAUCNS", "-"): {"unexpected": 1}}))
        with self.assertRaises(SourcePayloadError):
            client.series_metadata("CPIAUCNS")


class TestObservationFetch(unittest.TestCase):
    def test_successful_observation_parsing(self):
        client = FredClient(FAKE_KEY, fetch=stub_fetch(
            {("series/observations", "CPIAUCNS", "lin"): observations_payload(CPI_PAIRS)}))
        payload = client.observations("CPIAUCNS", limit=24)
        self.assertEqual(len(payload["observations"]), 14)

    def test_default_units_are_raw(self):
        seen = []
        client = FredClient(FAKE_KEY, fetch=stub_fetch(
            {("series/observations", "CPIAUCNS", "lin"): observations_payload(CPI_PAIRS)}, seen))
        client.observations("CPIAUCNS", limit=24)
        self.assertIn("units=lin", seen[0])

    def test_missing_observations_list_rejected(self):
        client = FredClient(FAKE_KEY, fetch=stub_fetch(
            {("series/observations", "X", "lin"): {"count": 0}}))
        with self.assertRaises(SourcePayloadError):
            client.observations("X", limit=5)


class TestTransportFailures(unittest.TestCase):
    def test_http_error_becomes_source_request_error(self):
        error = urllib.error.HTTPError("https://api.stlouisfed.org/x", 400,
                                       "Bad Request", {}, None)
        client = FredClient(FAKE_KEY, fetch=stub_fetch({("series", "X", "-"): error}))
        with self.assertRaises(SourceRequestError) as ctx:
            client.series_metadata("X")
        self.assertIn("400", str(ctx.exception))

    def test_http_error_message_never_contains_key(self):
        # Even when the failing URL carries the key, it must not surface.
        leaky = f"https://api.stlouisfed.org/fred/series?api_key={FAKE_KEY}"
        error = urllib.error.HTTPError(leaky, 403, "Forbidden", {}, None)
        client = FredClient(FAKE_KEY, fetch=stub_fetch({("series", "X", "-"): error}))
        with self.assertRaises(SourceRequestError) as ctx:
            client.series_metadata("X")
        self.assertNotIn(FAKE_KEY, str(ctx.exception))

    def test_arbitrary_exception_is_scrubbed(self):
        leaky = RuntimeError(f"connection reset while fetching api_key={FAKE_KEY}")
        client = FredClient(FAKE_KEY, fetch=stub_fetch({("series", "X", "-"): leaky}))
        with self.assertRaises(SourceRequestError) as ctx:
            client.series_metadata("X")
        self.assertNotIn(FAKE_KEY, str(ctx.exception))
        self.assertIn("<redacted>", str(ctx.exception))

    def test_url_error_becomes_source_request_error(self):
        client = FredClient(FAKE_KEY, fetch=stub_fetch(
            {("series", "X", "-"): urllib.error.URLError("no route to host")}))
        with self.assertRaises(SourceRequestError):
            client.series_metadata("X")

    def test_malformed_json_rejected(self):
        client = FredClient(FAKE_KEY, fetch=stub_fetch(
            {("series", "X", "-"): b"{not json at all"}))
        with self.assertRaises(SourcePayloadError):
            client.series_metadata("X")

    def test_json_array_rejected(self):
        client = FredClient(FAKE_KEY, fetch=stub_fetch({("series", "X", "-"): b"[1,2,3]"}))
        with self.assertRaises(SourcePayloadError):
            client.series_metadata("X")

    def test_fred_error_message_surfaced(self):
        client = FredClient(FAKE_KEY, fetch=stub_fetch(
            {("series", "X", "-"): {"error_code": 400,
                                    "error_message": "Bad Request. Invalid series_id."}}))
        with self.assertRaises(SourceRequestError) as ctx:
            client.series_metadata("X")
        self.assertIn("Invalid series_id", str(ctx.exception))

    def test_fred_error_message_never_leaks_key(self):
        client = FredClient(FAKE_KEY, fetch=stub_fetch(
            {("series", "X", "-"): {"error_message": f"bad api_key={FAKE_KEY}"}}))
        with self.assertRaises(SourceRequestError) as ctx:
            client.series_metadata("X")
        self.assertNotIn(FAKE_KEY, str(ctx.exception))


class TestNormalisation(unittest.TestCase):
    def test_strings_become_floats(self):
        series = normalise_observations(observations_payload(CPI_PAIRS), "CPIAUCNS")
        self.assertEqual(series.valid_count, 14)
        for obs in series.observations:
            self.assertIsInstance(obs.value, float)

    def test_observations_returned_chronologically(self):
        # The payload arrives newest-first; output must be oldest-first.
        series = normalise_observations(observations_payload(CPI_PAIRS), "CPIAUCNS")
        periods = [o.period for o in series.observations]
        self.assertEqual(periods, sorted(periods))
        self.assertEqual(periods[0], date(2024, 1, 1))
        self.assertEqual(periods[-1], date(2025, 2, 1))

    def test_missing_sentinel_is_excluded_not_coerced(self):
        payload = observations_payload([
            ("2025-01-01", "4.1"), ("2025-01-02", MISSING_SENTINEL),
            ("2025-01-03", "4.3"),
        ])
        series = normalise_observations(payload, "DFF")
        self.assertEqual(series.valid_count, 2)
        self.assertEqual(series.missing_count, 1)
        self.assertEqual(series.missing_dates, (date(2025, 1, 2),))
        values = [o.value for o in series.observations]
        self.assertNotIn(0.0, values)
        for value in values:
            self.assertFalse(value != value)  # not NaN

    def test_missing_dates_are_reported_not_lost(self):
        payload = observations_payload([("2025-01-01", "."), ("2025-01-02", "4.3")])
        series = normalise_observations(payload, "DFF")
        self.assertIn("2025-01-01", series.summary()["missing_dates"])
        self.assertEqual(series.summary()["raw_count"], 2)

    def test_malformed_numeric_value_fails(self):
        payload = observations_payload([("2025-01-01", "4.1"), ("2025-01-02", "n/a")])
        with self.assertRaises(SourcePayloadError) as ctx:
            normalise_observations(payload, "DFF")
        self.assertIn("malformed", str(ctx.exception))

    def test_empty_string_value_fails(self):
        payload = observations_payload([("2025-01-01", "")])
        with self.assertRaises(SourcePayloadError):
            normalise_observations(payload, "DFF")

    def test_null_value_fails(self):
        payload = {"observations": [{"date": "2025-01-01", "value": None}]}
        with self.assertRaises(SourcePayloadError):
            normalise_observations(payload, "DFF")

    def test_duplicate_date_fails(self):
        payload = observations_payload([("2025-01-01", "4.1"), ("2025-01-01", "4.2")])
        with self.assertRaises(SourcePayloadError) as ctx:
            normalise_observations(payload, "DFF")
        self.assertIn("duplicate", str(ctx.exception).lower())

    def test_unparseable_date_fails(self):
        payload = observations_payload([("01/02/2025", "4.1")])
        with self.assertRaises(SourcePayloadError) as ctx:
            normalise_observations(payload, "DFF")
        self.assertIn("date", str(ctx.exception).lower())

    def test_missing_keys_fail(self):
        with self.assertRaises(SourcePayloadError):
            normalise_observations({"observations": [{"date": "2025-01-01"}]}, "X")
        with self.assertRaises(SourcePayloadError):
            normalise_observations({"observations": [{"value": "1.0"}]}, "X")

    def test_no_observations_key_fails(self):
        with self.assertRaises(SourcePayloadError):
            normalise_observations({}, "X")

    def test_thousands_separator_accepted(self):
        series = normalise_observations(
            observations_payload([("2025-01-01", "20,301.0")]), "GDPC1")
        self.assertAlmostEqual(series.observations[0].value, 20301.0)

    def test_gaps_are_described_not_judged(self):
        payload = observations_payload([
            ("2025-02-20", "4.48"), ("2025-02-21", "4.48"), ("2025-02-24", "4.48"),
        ])
        series = normalise_observations(payload, "DFF")
        gaps = observation_gaps(series.observations)
        self.assertEqual([g[2] for g in gaps], [1, 3])


class TestEngineSeparation(unittest.TestCase):
    """The collector normalises; src.indicators calculates. No duplicated formulas."""

    def test_normalised_real_shaped_data_feeds_existing_engine(self):
        series = normalise_observations(observations_payload(CPI_PAIRS), "CPIAUCNS")
        obs = compute("us_cpi_inflation_yoy", series.observations,
                      retrieved_at=datetime(2025, 3, 1, tzinfo=timezone.utc))
        self.assertAlmostEqual(obs.value, 4.0, places=9)
        self.assertAlmostEqual(obs.previous_value, 3.0, places=9)
        self.assertAlmostEqual(obs.change, 1.0, places=9)

    def test_collector_modules_contain_no_formula(self):
        import src.normalisation as n
        import src.fred_client as f
        for module in (n, f):
            source = pathlib.Path(module.__file__).read_text()
            with self.subTest(module=module.__name__):
                self.assertNotIn("** 4", source)
                self.assertNotIn("- 1.0) * 100", source)


class TestMetadataValidation(unittest.TestCase):
    def setUp(self):
        self.cpi = SPECS["us_cpi_inflation_yoy"]
        self.gdp = SPECS["us_real_gdp_growth_qoq_ann"]
        self.dff = SPECS["us_effective_fed_funds_rate"]

    @staticmethod
    def codes(findings, severity):
        return [f.code for f in findings if f.severity == severity]

    def test_matching_metadata_passes(self):
        findings = validate_metadata(
            self.cpi, metadata_payload("CPIAUCNS")["seriess"][0])
        self.assertEqual(self.codes(findings, "hard_failure"), [])
        self.assertIn("metadata.series_id", self.codes(findings, "pass"))

    def test_wrong_series_id_is_hard_failure(self):
        findings = validate_metadata(
            self.cpi, metadata_payload("CPIAUCSL")["seriess"][0])
        self.assertIn("metadata.series_id_mismatch", self.codes(findings, "hard_failure"))

    def test_wrong_frequency_is_hard_failure(self):
        meta = metadata_payload("CPIAUCNS", frequency_short="D", frequency="Daily")["seriess"][0]
        findings = validate_metadata(self.cpi, meta)
        self.assertIn("metadata.frequency_mismatch", self.codes(findings, "hard_failure"))

    def test_unrecognised_frequency_is_hard_failure(self):
        meta = metadata_payload("CPIAUCNS", frequency_short="W", frequency="Weekly")["seriess"][0]
        findings = validate_metadata(self.cpi, meta)
        self.assertIn("metadata.frequency_unrecognised",
                      self.codes(findings, "hard_failure"))

    def test_wrong_seasonal_adjustment_is_hard_failure(self):
        # The exact error Phase 1.1 was meant to prevent.
        meta = metadata_payload("CPIAUCNS", sa_short="SA",
                                sa="Seasonally Adjusted")["seriess"][0]
        findings = validate_metadata(self.cpi, meta)
        self.assertIn("metadata.seasonal_adjustment_mismatch",
                      self.codes(findings, "hard_failure"))

    def test_gdp_expects_saar(self):
        self.assertEqual(expected_sa_code(self.gdp), "SAAR")
        meta = metadata_payload("GDPC1", frequency_short="Q", frequency="Quarterly",
                                sa_short="SAAR",
                                sa="Seasonally Adjusted Annual Rate")["seriess"][0]
        self.assertEqual(self.codes(validate_metadata(self.gdp, meta), "hard_failure"), [])

    def test_gdp_rejects_plain_sa(self):
        meta = metadata_payload("GDPC1", frequency_short="Q", frequency="Quarterly",
                                sa_short="SA", sa="Seasonally Adjusted")["seriess"][0]
        self.assertIn("metadata.seasonal_adjustment_mismatch",
                      self.codes(validate_metadata(self.gdp, meta), "hard_failure"))

    def test_not_applicable_spec_is_not_enforced(self):
        # DFF declares SA inapplicable; whatever the source says is recorded only.
        self.assertIsNone(expected_sa_code(self.dff))
        meta = metadata_payload("DFF", frequency_short="D", frequency="Daily",
                                sa_short="NSA")["seriess"][0]
        findings = validate_metadata(self.dff, meta)
        self.assertEqual(self.codes(findings, "hard_failure"), [])
        self.assertIn("metadata.seasonal_adjustment_not_applicable",
                      self.codes(findings, "pass"))

    def test_human_readable_label_wording_does_not_matter(self):
        # Semantic check on the code, not the prose label.
        meta = metadata_payload("CPIAUCNS", sa_short="NSA",
                                sa="NOT seasonally adjusted (whatever)")["seriess"][0]
        self.assertEqual(self.codes(validate_metadata(self.cpi, meta), "hard_failure"), [])


class TestSeriesValidation(unittest.TestCase):
    def setUp(self):
        self.cpi = SPECS["us_cpi_inflation_yoy"]
        self.dff = SPECS["us_effective_fed_funds_rate"]

    @staticmethod
    def codes(findings, severity):
        return [f.code for f in findings if f.severity == severity]

    def test_sufficient_history_passes(self):
        series = normalise_observations(observations_payload(CPI_PAIRS), "CPIAUCNS")
        findings = validate_series(self.cpi, series, now=date(2025, 3, 15))
        self.assertEqual(self.codes(findings, "hard_failure"), [])
        self.assertIn("series.sufficient_history", self.codes(findings, "pass"))

    def test_insufficient_history_is_hard_failure(self):
        series = normalise_observations(observations_payload(CPI_PAIRS[:13]), "CPIAUCNS")
        findings = validate_series(self.cpi, series, now=date(2025, 3, 15))
        self.assertIn("series.insufficient_history", self.codes(findings, "hard_failure"))

    def test_history_counted_after_missing_filtering(self):
        # 14 rows, one of them "." -> only 13 valid -> insufficient.
        pairs = list(CPI_PAIRS)
        pairs[5] = (pairs[5][0], MISSING_SENTINEL)
        series = normalise_observations(observations_payload(pairs), "CPIAUCNS")
        self.assertEqual(series.valid_count, 13)
        findings = validate_series(self.cpi, series, now=date(2025, 3, 15))
        self.assertIn("series.insufficient_history", self.codes(findings, "hard_failure"))

    def test_stale_series_is_warning_not_failure(self):
        series = normalise_observations(observations_payload(CPI_PAIRS), "CPIAUCNS")
        findings = validate_series(self.cpi, series, now=date(2026, 1, 1))
        self.assertEqual(self.codes(findings, "hard_failure"), [])
        self.assertIn("series.stale", self.codes(findings, "warning"))

    def test_stale_observation_is_retained(self):
        series = normalise_observations(observations_payload(CPI_PAIRS), "CPIAUCNS")
        validate_series(self.cpi, series, now=date(2030, 1, 1))
        self.assertEqual(series.valid_count, 14)  # nothing removed

    def test_fresh_series_passes(self):
        series = normalise_observations(observations_payload(CPI_PAIRS), "CPIAUCNS")
        findings = validate_series(self.cpi, series, now=date(2025, 3, 1))
        self.assertIn("series.fresh", self.codes(findings, "pass"))

    def test_tolerances_are_frequency_aware_and_generous(self):
        from src.models import Frequency
        self.assertGreaterEqual(STALENESS_TOLERANCE_DAYS[Frequency.MONTHLY], 60)
        self.assertGreaterEqual(STALENESS_TOLERANCE_DAYS[Frequency.QUARTERLY], 150)
        self.assertGreaterEqual(STALENESS_TOLERANCE_DAYS[Frequency.DAILY], 7)

    def test_unusual_gap_is_warning(self):
        payload = observations_payload([
            ("2025-01-02", "4.33"), ("2025-01-20", "4.33"), ("2025-01-21", "4.33")])
        series = normalise_observations(payload, "DFF")
        findings = validate_series(self.dff, series, now=date(2025, 1, 22))
        self.assertEqual(self.codes(findings, "hard_failure"), [])
        self.assertIn("series.unusual_gaps", self.codes(findings, "warning"))

    def test_normal_weekend_gap_is_not_flagged(self):
        payload = observations_payload([
            ("2025-02-21", "4.33"), ("2025-02-24", "4.33"), ("2025-02-25", "4.33")])
        series = normalise_observations(payload, "DFF")
        findings = validate_series(self.dff, series, now=date(2025, 2, 26))
        self.assertNotIn("series.unusual_gaps", self.codes(findings, "warning"))


class TestDerivedValidation(unittest.TestCase):
    def setUp(self):
        self.spec = SPECS["us_cpi_inflation_yoy"]
        series = normalise_observations(observations_payload(CPI_PAIRS), "CPIAUCNS")
        self.obs = compute(self.spec.indicator_id, series.observations,
                           retrieved_at=datetime(2025, 3, 1, tzinfo=timezone.utc))

    def test_consistent_result_passes(self):
        findings = validate_derived(self.spec, self.obs)
        self.assertEqual([f.code for f in findings if f.severity == "hard_failure"], [])

    def test_inconsistent_change_is_hard_failure(self):
        import dataclasses
        from src.models import Direction
        broken = dataclasses.replace(self.obs, change=9.9, direction=Direction.INCREASED)
        findings = validate_derived(self.spec, broken)
        self.assertIn("derived.inconsistent_change",
                      [f.code for f in findings if f.severity == "hard_failure"])

    def test_wrong_source_series_is_hard_failure(self):
        import dataclasses
        broken = dataclasses.replace(self.obs, source_series="CPIAUCSL")
        findings = validate_derived(self.spec, broken)
        self.assertIn("derived.wrong_source_series",
                      [f.code for f in findings if f.severity == "hard_failure"])

    def test_model_refuses_to_construct_a_non_finite_observation(self):
        # First line of defence: MacroObservation itself rejects inf/NaN, so a
        # non-finite figure cannot reach the gate through the normal path.
        import dataclasses
        from src.errors import NonNumericValueError
        from src.models import Direction
        for bad in (float("inf"), float("-inf"), float("nan")):
            with self.subTest(value=bad):
                with self.assertRaises(NonNumericValueError):
                    dataclasses.replace(self.obs, value=bad)

    def test_gate_still_catches_a_non_finite_result(self):
        # Backstop: if a non-finite figure ever arrived by another route, the
        # gate must report it as a hard failure rather than pass it through.
        from types import SimpleNamespace
        from src.models import Direction
        smuggled = SimpleNamespace(
            indicator_id=self.obs.indicator_id,
            source_series=self.spec.source_series,
            value=float("inf"), previous_value=3.0, change=float("inf"),
            direction=Direction.INCREASED,
        )
        findings = validate_derived(self.spec, smuggled)
        self.assertIn("derived.non_finite",
                      [f.code for f in findings if f.severity == "hard_failure"])


class TestValidationGate(unittest.TestCase):
    def report(self):
        return ValidationReport(run_id="test",
                                generated_at=datetime(2025, 3, 1, tzinfo=timezone.utc))

    def test_clean_report_is_publication_ready(self):
        r = self.report()
        r.add(Finding(code="x.ok", severity="pass", message="fine"))
        self.assertTrue(r.publication_ready)
        self.assertEqual(r.status, "passed")

    def test_warning_does_not_block_publication(self):
        r = self.report()
        r.add(Finding(code="series.stale", severity="warning", message="old"))
        self.assertTrue(r.publication_ready)
        self.assertEqual(r.status, "passed_with_warnings")

    def test_hard_failure_blocks_publication(self):
        r = self.report()
        r.add(Finding(code="series.stale", severity="warning", message="old"))
        r.add(Finding(code="metadata.frequency_mismatch", severity="hard_failure",
                      message="wrong"))
        self.assertFalse(r.publication_ready)
        self.assertEqual(r.status, "failed")

    def test_report_is_structured(self):
        r = self.report()
        r.add(Finding(code="a", severity="pass", message="m"))
        r.add(Finding(code="b", severity="warning", message="w", series_id="DFF"))
        payload = r.to_dict()
        for key in ("status", "publication_ready", "hard_failures", "warnings",
                    "checks", "series_results", "cross_checks", "counts"):
            self.assertIn(key, payload)
        self.assertEqual(payload["counts"]["warnings"], 1)

    def test_report_is_json_serialisable(self):
        r = self.report()
        r.add(Finding(code="a", severity="warning", message="m", detail={"n": 1}))
        json.dumps(r.to_dict())


class TestSnapshotSecrecy(unittest.TestCase):
    def test_payload_with_key_is_refused(self):
        with self.assertRaises(SecretLeakError):
            assert_secret_free(f'{{"u": "...api_key={FAKE_KEY}"}}', FAKE_KEY)

    def test_api_key_substring_alone_is_refused(self):
        with self.assertRaises(SecretLeakError):
            assert_secret_free('{"url": "https://x?api_key=whatever"}', None)

    def test_clean_payload_allowed(self):
        assert_secret_free('{"series_id": "DFF", "value": "4.33"}', FAKE_KEY)

    def test_write_json_refuses_leaky_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "out.json"
            with self.assertRaises(SecretLeakError):
                write_json(target, {"url": f"https://x?api_key={FAKE_KEY}"}, secret=FAKE_KEY)
            self.assertFalse(target.exists())  # nothing written

    def test_write_json_writes_clean_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "sub" / "out.json"
            write_json(target, {"series_id": "DFF"}, secret=FAKE_KEY)
            self.assertTrue(target.exists())
            self.assertNotIn(FAKE_KEY, target.read_text())

    def test_tree_scan_finds_planted_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "clean.json").write_text('{"ok": 1}')
            (root / ".hidden").write_text(f"key={FAKE_KEY}")
            offenders = scan_tree_for_secret(root, FAKE_KEY)
            self.assertEqual([p.name for p in offenders], [".hidden"])

    def test_tree_scan_clean_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "a.json").write_text('{"value": "4.33"}')
            self.assertEqual(scan_tree_for_secret(root, FAKE_KEY), [])


if __name__ == "__main__":
    unittest.main()


class TestHttpErrorBodyDiagnostics(unittest.TestCase):
    """A 4xx body carries FRED's real reason; it must be surfaced and scrubbed."""

    @staticmethod
    def http_error(body_obj, code=400):
        import io
        body = json.dumps(body_obj).encode()
        return urllib.error.HTTPError(
            "https://api.stlouisfed.org/fred/series", code, "Bad Request",
            {}, io.BytesIO(body),
        )

    def test_error_message_from_body_is_surfaced(self):
        error = self.http_error({
            "error_code": 400,
            "error_message": "Bad Request. The value for variable api_key is not "
                             "a 32 character alpha-numeric lower-case string.",
        })
        client = FredClient(FAKE_KEY, fetch=stub_fetch({("series", "X", "-"): error}))
        with self.assertRaises(SourceRequestError) as ctx:
            client.series_metadata("X")
        self.assertIn("32 character", str(ctx.exception))

    def test_body_diagnostic_is_scrubbed(self):
        error = self.http_error({"error_message": f"bad key api_key={FAKE_KEY}"})
        client = FredClient(FAKE_KEY, fetch=stub_fetch({("series", "X", "-"): error}))
        with self.assertRaises(SourceRequestError) as ctx:
            client.series_metadata("X")
        self.assertNotIn(FAKE_KEY, str(ctx.exception))

    def test_unreadable_body_does_not_mask_the_status(self):
        error = urllib.error.HTTPError(
            "https://api.stlouisfed.org/fred/series", 500,
            "Internal Server Error", {}, None)
        client = FredClient(FAKE_KEY, fetch=stub_fetch({("series", "X", "-"): error}))
        with self.assertRaises(SourceRequestError) as ctx:
            client.series_metadata("X")
        self.assertIn("500", str(ctx.exception))


class TestCalendarAnchoredPeriods(unittest.TestCase):
    """Regression tests for the gap bug that the FRED cross-check exposed.

    Real CPIAUCNS and UNRATE data is missing October 2025. Selecting comparison
    periods by list position silently compared 2026-08 with 2025-07 — thirteen
    months apart — and produced 3.6936% instead of the correct 3.3965%. Periods
    are now selected by calendar date.
    """

    RETRIEVED = datetime(2026, 9, 27, tzinfo=timezone.utc)

    # The real values, as retrieved from FRED.
    CPI_REAL = [
        ("2024-09-01", "315.301"), ("2024-10-01", "315.664"), ("2024-11-01", "315.493"),
        ("2024-12-01", "315.605"), ("2025-01-01", "317.671"), ("2025-02-01", "319.082"),
        ("2025-03-01", "319.799"), ("2025-04-01", "320.795"), ("2025-05-01", "321.465"),
        ("2025-06-01", "322.561"), ("2025-07-01", "323.048"), ("2025-08-01", "323.976"),
        ("2025-09-01", "324.800"), ("2025-10-01", "."),       ("2025-11-01", "324.122"),
        ("2025-12-01", "324.054"), ("2026-01-01", "325.252"), ("2026-02-01", "326.785"),
        ("2026-03-01", "330.213"), ("2026-04-01", "333.020"), ("2026-05-01", "335.123"),
        ("2026-06-01", "333.952"), ("2026-07-01", "333.918"), ("2026-08-01", "334.980"),
    ]

    def cpi_series(self):
        return normalise_observations(
            observations_payload(self.CPI_REAL), "CPIAUCNS").observations

    def test_gap_is_present_in_the_fixture(self):
        series = self.cpi_series()
        self.assertEqual(len(series), 23)  # 24 rows, one missing
        self.assertNotIn(date(2025, 10, 1), {o.period for o in series})

    def test_yoy_uses_the_same_month_a_year_earlier(self):
        obs = compute("us_cpi_inflation_yoy", self.cpi_series(), retrieved_at=self.RETRIEVED)
        # 334.980 / 323.976 - 1 = 3.396548%, which is what FRED's pc1 reports.
        self.assertAlmostEqual(obs.value, 3.396548, places=5)

    def test_positional_indexing_would_have_been_wrong(self):
        # Demonstrates the defect explicitly: position -13 is 2025-07, not 2025-08.
        series = self.cpi_series()
        self.assertEqual(series[-13].period, date(2025, 7, 1))
        wrong = (series[-1].value / series[-13].value - 1) * 100
        self.assertAlmostEqual(wrong, 3.693569, places=5)
        obs = compute("us_cpi_inflation_yoy", series, retrieved_at=self.RETRIEVED)
        self.assertNotAlmostEqual(obs.value, wrong, places=3)

    def test_previous_yoy_also_calendar_anchored(self):
        obs = compute("us_cpi_inflation_yoy", self.cpi_series(), retrieved_at=self.RETRIEVED)
        # 333.918 (2026-07) / 323.048 (2025-07) - 1 = 3.364825%
        self.assertAlmostEqual(obs.previous_value, 3.364825, places=5)

    def test_missing_required_period_fails_loudly(self):
        from src.errors import MissingRequiredPeriodError
        # Drop the exact period the YoY needs; plenty of observations remain.
        pairs = [p for p in self.CPI_REAL if p[0] != "2025-08-01"]
        series = normalise_observations(observations_payload(pairs), "CPIAUCNS").observations
        self.assertGreaterEqual(len(series), 14)
        with self.assertRaises(MissingRequiredPeriodError) as ctx:
            compute("us_cpi_inflation_yoy", series, retrieved_at=self.RETRIEVED)
        self.assertIn("2025-08-01", str(ctx.exception))
        self.assertIn("CPI_t-12", str(ctx.exception))

    def test_no_substitute_observation_is_used(self):
        from src.errors import MissingRequiredPeriodError
        pairs = [p for p in self.CPI_REAL if p[0] != "2025-08-01"]
        series = normalise_observations(observations_payload(pairs), "CPIAUCNS").observations
        with self.assertRaises(MissingRequiredPeriodError):
            compute("us_cpi_inflation_yoy", series, retrieved_at=self.RETRIEVED)

    def test_unemployment_requires_the_previous_calendar_month(self):
        from src.errors import MissingRequiredPeriodError
        # 2026-08 present, 2026-07 absent -> must fail, not use 2026-06.
        pairs = [("2026-05-01", "4.3"), ("2026-06-01", "4.2"), ("2026-08-01", "4.1")]
        series = normalise_observations(observations_payload(pairs), "UNRATE").observations
        with self.assertRaises(MissingRequiredPeriodError):
            compute("us_unemployment_rate", series, retrieved_at=self.RETRIEVED)

    def test_gdp_requires_adjacent_calendar_quarters(self):
        from src.errors import MissingRequiredPeriodError
        pairs = [("2025-07-01", "24026.834"), ("2026-01-01", "24180.419"),
                 ("2026-04-01", "24269.613")]  # 2025-10 quarter absent
        series = normalise_observations(observations_payload(pairs), "GDPC1").observations
        with self.assertRaises(MissingRequiredPeriodError):
            compute("us_real_gdp_growth_qoq_ann", series, retrieved_at=self.RETRIEVED)

    def test_retail_requires_adjacent_calendar_months(self):
        from src.errors import MissingRequiredPeriodError
        pairs = [("2026-05-01", "766192.0"), ("2026-07-01", "764462.0"),
                 ("2026-08-01", "773947.0")]  # 2026-06 absent
        series = normalise_observations(observations_payload(pairs), "RSAFS").observations
        with self.assertRaises(MissingRequiredPeriodError):
            compute("us_retail_sales_mom", series, retrieved_at=self.RETRIEVED)

    def test_dff_remains_previous_available_by_design(self):
        # DFF's spec defines 'previous' as the preceding AVAILABLE observation,
        # so a calendar gap must NOT cause a failure there.
        pairs = [("2026-09-21", "3.88"), ("2026-09-24", "3.88")]
        series = normalise_observations(observations_payload(pairs), "DFF").observations
        obs = compute("us_effective_fed_funds_rate", series, retrieved_at=self.RETRIEVED)
        self.assertEqual(obs.change, 0.0)
        self.assertEqual(obs.period, date(2026, 9, 24))


class TestPeriodArithmetic(unittest.TestCase):
    def test_month_subtraction_crosses_year(self):
        from src.periods import add_months
        self.assertEqual(add_months(date(2026, 8, 1), -12), date(2025, 8, 1))
        self.assertEqual(add_months(date(2026, 1, 1), -1), date(2025, 12, 1))
        self.assertEqual(add_months(date(2026, 8, 1), -13), date(2025, 7, 1))

    def test_quarter_subtraction(self):
        from src.periods import add_quarters
        self.assertEqual(add_quarters(date(2026, 4, 1), -1), date(2026, 1, 1))
        self.assertEqual(add_quarters(date(2026, 4, 1), -2), date(2025, 10, 1))

    def test_day_is_clamped_to_month_length(self):
        from src.periods import add_months
        self.assertEqual(add_months(date(2026, 3, 31), -1), date(2026, 2, 28))
        self.assertEqual(add_months(date(2024, 3, 31), -1), date(2024, 2, 29))  # leap
