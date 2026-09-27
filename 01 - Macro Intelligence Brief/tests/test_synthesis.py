"""Synthesis layer: the gate, the validator, and the renderer.

No test here contacts a provider. The model call is injected as a ``transport``
callable, so every path — including the real entry point — is exercised offline.

The validator is the component that matters. A model that fabricates a plausible
number is the failure this project exists to prevent, and prose is where such a
number would appear.
"""

import copy
import json
import pathlib
import unittest
import urllib.error
from datetime import datetime, timezone

from src.brief_schema import DRAFT_STATUS, SECTION_IDS, SECTION_TITLES, json_schema
from src.draft_validator import assert_brief_input_usable, validate_draft
from src.llm_client import (
    API_ENDPOINT,
    DEFAULT_MODEL,
    InvalidModelConfigurationError,
    MissingLLMCredentialError,
    SynthesisError,
    extract_output_text,
    provider_schema,
    read_credentials,
    request_brief,
    safe_interaction_metadata,
)
from src.presentation import allowed_numeric_tokens, format_change, format_value
from src.render_brief import render_html
from src.synthesize import synthesise

BRIEF_INPUT_PATH = (pathlib.Path(__file__).resolve().parent.parent / "derived"
                    / "brief_input.json")
FAKE_KEY = "test-fake-gemini-key-not-a-real-credential"
#: Deliberately unlike any provider key format, so that publishing this
#: repository cannot trip a secret scanner on a value that is not a secret.
#: The scrubbing tests below are unaffected: what they prove is that whatever
#: string is configured as the credential never reaches an error message, an
#: artefact or a URL — the string's shape is irrelevant to that guarantee.


def load_input():
    return json.loads(BRIEF_INPUT_PATH.read_text(encoding="utf-8"))


def good_draft():
    """A draft that must be accepted: grounded, restrained, complete."""
    return {
        "brief_title": "Weekly Macro Intelligence Brief (Draft)",
        "as_of": "27 September 2026",
        "executive_summary": (
            "Headline CPI inflation was broadly stable at 3.4% year-on-year in "
            "August 2026. The effective federal funds rate stood at 3.88% on "
            "24 September 2026, unchanged from the preceding observation. Real "
            "GDP expanded at an annualised quarterly rate of 1.5% in 2026 Q2, "
            "compared with 2.1% in the preceding quarter. The unemployment rate "
            "was 4.1% in August 2026, unchanged. Retail sales rose 1.2% on the "
            "month in August 2026."
        ),
        "sections": [
            {"section_id": "inflation", "title": "Inflation",
             "indicator_ids": ["us_cpi_inflation_yoy"],
             "summary": ("Headline CPI inflation measured 3.4% year-on-year in "
                         "August 2026. The change from the previous month was "
                         "+0.03 percentage points, smaller than one displayed "
                         "decimal place, so the rate was broadly stable.")},
            {"section_id": "monetary_policy", "title": "Monetary Policy",
             "indicator_ids": ["us_effective_fed_funds_rate"],
             "summary": ("The effective federal funds rate stood at 3.88% on "
                         "24 September 2026, unchanged from the preceding "
                         "available observation. For this series an unchanged "
                         "reading is an ordinary outcome.")},
            {"section_id": "growth", "title": "Growth",
             "indicator_ids": ["us_real_gdp_growth_qoq_ann"],
             "summary": ("Real GDP expanded at an annualised quarterly rate of "
                         "1.5% in 2026 Q2, compared with 2.1% in the preceding "
                         "quarter, a change of −0.61 percentage points.")},
            {"section_id": "labour_market", "title": "Labour Market",
             "indicator_ids": ["us_unemployment_rate"],
             "summary": ("The unemployment rate was 4.1% in August 2026, "
                         "unchanged from the previous calendar month.")},
            {"section_id": "consumption", "title": "Consumption",
             "indicator_ids": ["us_retail_sales_mom"],
             "summary": ("Retail and food services sales rose 1.2% on the month "
                         "in August 2026, against −0.5% in the preceding month, "
                         "a change of +1.78 percentage points. The series is "
                         "nominal.")},
        ],
        "key_developments": [
            "The effective federal funds rate was unchanged at 3.88%.",
            "Annualised real GDP growth was 1.5% in 2026 Q2.",
        ],
        "data_quality_notes": [
            ("The source series CPIAUCNS contains no observation for October "
             "2025, leaving a gap in the historical record."),
            ("The source series UNRATE likewise contains no observation for "
             "October 2025."),
        ],
        "limitations": (
            "This briefing is descriptive. It contains no forecast and no "
            "assessment of causes. Figures are derived from published source "
            "series and should be verified against the primary releases."
        ),
    }


def interaction(text, *, status="completed", steps=None, usage=True,
                model="gemini-3.8-flash"):
    """Build a raw Interaction resource, matching the documented REST shape.

    Deliberately no root-level ``output_text``: that field is an SDK convenience
    property and is absent over REST.
    """
    if steps is None:
        steps = [{"type": "model_output",
                  "content": [{"type": "text", "text": text}]}]
    payload = {
        "created": "2026-09-27T12:25:15Z",
        "updated": "2026-09-27T12:25:15Z",
        "id": "v1_ChdPU0F4YWFtNkFwS2kxZThQZ05lbXdROBIXT1N",
        "object": "interaction",
        "model": model,
        "status": status,
        "steps": steps,
    }
    if usage:
        payload["usage"] = {"total_input_tokens": 2914,
                            "total_output_tokens": 812,
                            "total_tokens": 3726}
    return payload


def transport_returning(draft, metadata=None):
    def transport(system_prompt, user_message, schema):
        assert isinstance(system_prompt, str) and system_prompt
        assert isinstance(user_message, str) and user_message
        assert schema["type"] == "object"
        return draft, metadata or {"model": "test-model", "stop_reason": "end_turn"}
    return transport


class TestCredentialHandling(unittest.TestCase):
    def test_missing_key_fails_clearly(self):
        with self.assertRaises(MissingLLMCredentialError) as ctx:
            read_credentials({})
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))

    def test_blank_key_treated_as_missing(self):
        with self.assertRaises(MissingLLMCredentialError):
            read_credentials({"GEMINI_API_KEY": "  "})

    def test_error_carries_no_value(self):
        with self.assertRaises(MissingLLMCredentialError) as ctx:
            read_credentials({})
        self.assertNotIn(FAKE_KEY, str(ctx.exception))

    def test_model_defaults_when_unset(self):
        key, model = read_credentials({"GEMINI_API_KEY": FAKE_KEY})
        self.assertEqual(key, FAKE_KEY)
        self.assertEqual(model, DEFAULT_MODEL)
        self.assertEqual(DEFAULT_MODEL, "gemini-3.8-flash")

    def test_model_read_from_environment(self):
        _, model = read_credentials({"GEMINI_API_KEY": FAKE_KEY,
                                    "LLM_MODEL": "gemini-3.8-flash"})
        self.assertEqual(model, "gemini-3.8-flash")

    def test_moving_aliases_refused(self):
        for alias in ("gemini-flash-latest", "gemini-3.8-flash-preview",
                      "gemini-2.0-flash-exp"):
            with self.subTest(alias=alias):
                with self.assertRaises(InvalidModelConfigurationError) as ctx:
                    read_credentials({"GEMINI_API_KEY": FAKE_KEY, "LLM_MODEL": alias})
                self.assertIn("alias", str(ctx.exception).lower())

    def test_non_bare_model_identifier_refused(self):
        for bad in ("models/gemini-3.8-flash", "gemini 3.8 flash"):
            with self.subTest(model=bad):
                with self.assertRaises(InvalidModelConfigurationError):
                    read_credentials({"GEMINI_API_KEY": FAKE_KEY, "LLM_MODEL": bad})

    def test_model_error_carries_no_credential(self):
        with self.assertRaises(InvalidModelConfigurationError) as ctx:
            read_credentials({"GEMINI_API_KEY": FAKE_KEY,
                              "LLM_MODEL": "gemini-flash-latest"})
        self.assertNotIn(FAKE_KEY, str(ctx.exception))

    def test_credentials_never_enter_the_prompt(self):
        from src.synthesis_prompt import SYSTEM_PROMPT
        self.assertNotIn("API_KEY", SYSTEM_PROMPT)
        self.assertNotIn(FAKE_KEY, SYSTEM_PROMPT)


class TestInputGate(unittest.TestCase):
    def test_valid_input_passes(self):
        assert_brief_input_usable(load_input())

    def test_publication_ready_false_blocks_synthesis(self):
        payload = load_input()
        payload["publication_ready"] = False
        with self.assertRaises(ValueError) as ctx:
            assert_brief_input_usable(payload)
        self.assertIn("publication_ready", str(ctx.exception))

    def test_publication_ready_missing_blocks_synthesis(self):
        payload = load_input()
        del payload["publication_ready"]
        with self.assertRaises(ValueError):
            assert_brief_input_usable(payload)

    def test_incomplete_indicator_set_blocks_synthesis(self):
        payload = load_input()
        payload["indicators"] = payload["indicators"][:3]
        with self.assertRaises(ValueError) as ctx:
            assert_brief_input_usable(payload)
        self.assertIn("exactly 5", str(ctx.exception))

    def test_indicator_missing_presentation_blocks_synthesis(self):
        payload = load_input()
        del payload["indicators"][0]["presentation"]
        with self.assertRaises(ValueError) as ctx:
            assert_brief_input_usable(payload)
        self.assertIn("presentation", str(ctx.exception))

    def test_gate_runs_before_any_model_call(self):
        called = []

        def transport(*args):
            called.append(args)
            return good_draft(), {}

        payload = load_input()
        payload["publication_ready"] = False
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = pathlib.Path(tmp)
            (d / "brief_input.json").write_text(json.dumps(payload))
            code = synthesise(d, transport=transport)
        self.assertEqual(code, 2)
        self.assertEqual(called, [], "the model must not be contacted")


class TestValidatorAcceptsGoodDraft(unittest.TestCase):
    def setUp(self):
        self.brief_input = load_input()

    def test_good_draft_accepted(self):
        result = validate_draft(good_draft(), self.brief_input)
        self.assertEqual([f.code for f in result.hard_failures], [])
        self.assertTrue(result.accepted)

    def test_report_is_structured(self):
        payload = validate_draft(good_draft(), self.brief_input).to_dict()
        for key in ("accepted", "status", "counts", "hard_failures", "warnings"):
            self.assertIn(key, payload)
        json.dumps(payload)


class TestStructuralRejections(unittest.TestCase):
    def setUp(self):
        self.brief_input = load_input()

    def codes(self, draft):
        return [f.code for f in validate_draft(draft, self.brief_input).hard_failures]

    def test_not_an_object_rejected(self):
        self.assertIn("draft.not_an_object", self.codes("just a string"))
        self.assertIn("draft.not_an_object", self.codes([1, 2, 3]))

    def test_missing_field_rejected(self):
        d = good_draft(); del d["limitations"]
        self.assertIn("draft.missing_field", self.codes(d))

    def test_unknown_top_level_field_rejected(self):
        d = good_draft(); d["recommendation"] = "buy bonds"
        self.assertIn("draft.unknown_field", self.codes(d))

    def test_missing_section_rejected(self):
        d = good_draft(); d["sections"] = d["sections"][:4]
        self.assertIn("draft.missing_section", self.codes(d))

    def test_extra_section_rejected(self):
        d = good_draft()
        d["sections"].append({"section_id": "housing", "title": "Housing",
                              "indicator_ids": ["us_cpi_inflation_yoy"],
                              "summary": "Housing was not part of this dataset at all."})
        self.assertIn("draft.unknown_section", self.codes(d))

    def test_duplicate_section_rejected(self):
        d = good_draft()
        d["sections"].append(copy.deepcopy(d["sections"][0]))
        self.assertIn("draft.duplicate_section", self.codes(d))

    def test_every_required_section_is_checked(self):
        for index, sid in enumerate(SECTION_IDS):
            with self.subTest(section=sid):
                d = good_draft()
                d["sections"] = [s for s in d["sections"] if s["section_id"] != sid]
                self.assertIn("draft.missing_section", self.codes(d))

    def test_section_with_no_indicator_rejected(self):
        d = good_draft(); d["sections"][0]["indicator_ids"] = []
        self.assertIn("draft.section_cites_nothing", self.codes(d))


class TestGroundingRejections(unittest.TestCase):
    def setUp(self):
        self.brief_input = load_input()

    def codes(self, draft):
        return [f.code for f in validate_draft(draft, self.brief_input).hard_failures]

    def test_invented_indicator_rejected(self):
        d = good_draft()
        d["sections"][0]["indicator_ids"] = ["us_house_price_index"]
        codes = self.codes(d)
        self.assertTrue({"draft.unknown_indicator",
                         "draft.section_cites_unrelated_indicator"} & set(codes))

    def test_section_citing_another_sections_indicator_rejected(self):
        d = good_draft()
        d["sections"][0]["indicator_ids"] = ["us_real_gdp_growth_qoq_ann"]
        self.assertIn("draft.section_cites_unrelated_indicator", self.codes(d))

    def test_unsupported_number_rejected(self):
        d = good_draft()
        d["sections"][0]["summary"] = (
            "Headline CPI inflation measured 3.7% year-on-year in August 2026.")
        self.assertIn("draft.unsupported_number", self.codes(d))

    def test_unsupported_number_in_executive_summary_rejected(self):
        d = good_draft()
        d["executive_summary"] += " Core inflation was 2.8% over the same period."
        self.assertIn("draft.unsupported_number", self.codes(d))

    def test_unsupported_number_in_key_developments_rejected(self):
        d = good_draft()
        d["key_developments"].append("Inflation has averaged 2.9% over five years.")
        self.assertIn("draft.unsupported_number", self.codes(d))

    def test_supplied_numbers_accepted(self):
        for figure in ("3.4%", "3.88%", "1.5%", "2.1%", "4.1%", "1.2%"):
            with self.subTest(figure=figure):
                d = good_draft()
                d["key_developments"] = [f"The reported figure was {figure}."]
                self.assertNotIn("draft.unsupported_number", self.codes(d))

    def test_wrong_period_rejected(self):
        d = good_draft()
        d["sections"][0]["summary"] = (
            "Headline CPI inflation measured 3.4% year-on-year in 2026 Q2.")
        self.assertIn("draft.wrong_period", self.codes(d))

    def test_canonical_period_date_in_prose_rejected(self):
        d = good_draft()
        d["sections"][2]["summary"] = (
            "Real GDP expanded at an annualised rate of 1.5% in 2026-04-01.")
        self.assertIn("draft.canonical_period_in_prose", self.codes(d))

    def test_missing_period_label_rejected(self):
        d = good_draft()
        d["sections"][3]["summary"] = "The unemployment rate was 4.1%, unchanged."
        self.assertIn("draft.period_label_missing", self.codes(d))

    def test_percentage_point_written_as_percent_rejected(self):
        # 1.78 is a percentage-POINT change, not a percentage.
        d = good_draft()
        d["sections"][4]["summary"] = (
            "Retail sales rose 1.2% on the month in August 2026, an acceleration "
            "of 1.78% from the preceding month.")
        self.assertIn("draft.percentage_point_as_percent", self.codes(d))


class TestWarningRejections(unittest.TestCase):
    def setUp(self):
        self.brief_input = load_input()

    def codes(self, draft, brief_input=None):
        return [f.code for f in
                validate_draft(draft, brief_input or self.brief_input).hard_failures]

    def test_all_warnings_suppressed_rejected(self):
        d = good_draft(); d["data_quality_notes"] = []
        self.assertIn("draft.all_warnings_suppressed", self.codes(d))

    def test_one_warning_suppressed_rejected(self):
        d = good_draft()
        d["data_quality_notes"] = [d["data_quality_notes"][0]]  # drops UNRATE
        self.assertIn("draft.warning_suppressed", self.codes(d))

    def test_invented_warning_rejected(self):
        payload = load_input(); payload["warnings"] = []
        d = good_draft()
        self.assertIn("draft.invented_warning", self.codes(d, payload))

    def test_no_warnings_and_no_notes_accepted(self):
        payload = load_input(); payload["warnings"] = []
        d = good_draft(); d["data_quality_notes"] = []
        self.assertNotIn("draft.invented_warning", self.codes(d, payload))
        self.assertNotIn("draft.all_warnings_suppressed", self.codes(d, payload))


class TestForbiddenLanguage(unittest.TestCase):
    def setUp(self):
        self.brief_input = load_input()

    def codes(self, draft):
        return [f.code for f in validate_draft(draft, self.brief_input).hard_failures]

    def with_summary(self, text):
        d = good_draft()
        d["sections"][0]["summary"] = (
            "Headline CPI inflation measured 3.4% year-on-year in August 2026. " + text)
        return d

    def test_forecast_language_rejected(self):
        for text in ("Inflation is likely to moderate further.",
                     "The outlook is for continued disinflation.",
                     "We expect the rate to decline.",
                     "Going forward, price pressures persist."):
            with self.subTest(text=text):
                self.assertIn("draft.forbidden_forecast",
                              self.codes(self.with_summary(text)))

    def test_investment_advice_rejected(self):
        for text in ("Investors should reduce duration.",
                     "This supports an overweight in equities.",
                     "Portfolio positioning should adjust accordingly."):
            with self.subTest(text=text):
                self.assertIn("draft.forbidden_investment_advice",
                              self.codes(self.with_summary(text)))

    def test_causal_claim_rejected(self):
        for text in ("The move was driven by energy prices.",
                     "This was due to weaker demand.",
                     "Prices eased because of lower import costs."):
            with self.subTest(text=text):
                self.assertIn("draft.forbidden_causal_claim",
                              self.codes(self.with_summary(text)))

    def test_consensus_language_rejected(self):
        self.assertIn("draft.forbidden_consensus",
                      self.codes(self.with_summary("The print beat consensus.")))

    def test_market_reaction_rejected(self):
        self.assertIn("draft.forbidden_market_reaction",
                      self.codes(self.with_summary("Treasuries rallied on the news.")))

    def test_regime_label_rejected(self):
        self.assertIn("draft.forbidden_regime_label",
                      self.codes(self.with_summary("A soft landing now looks plausible.")))

    def test_dramatic_language_rejected(self):
        for text in ("Retail sales surged.", "Growth plunged.",
                     "The figure is worrying."):
            with self.subTest(text=text):
                self.assertIn("draft.forbidden_dramatic_language",
                              self.codes(self.with_summary(text)))

    def test_policy_motive_rejected(self):
        self.assertIn("draft.forbidden_policy_motive",
                      self.codes(self.with_summary(
                          "The Fed aims to bring inflation back to target.")))

    def test_data_invalidity_claim_rejected(self):
        d = good_draft()
        d["data_quality_notes"].append("The data are unreliable as a result.")
        self.assertIn("draft.forbidden_data_invalidity_claim", self.codes(d))

    def test_restrained_gap_description_accepted(self):
        d = good_draft()
        d["data_quality_notes"] = [
            "The source series CPIAUCNS contains no observation for October 2025.",
            "The source series UNRATE contains no observation for October 2025.",
        ]
        self.assertNotIn("draft.forbidden_dramatic_language", self.codes(d))
        self.assertTrue(validate_draft(d, self.brief_input).accepted)


class TestPresentationHelpers(unittest.TestCase):
    def test_value_formatting(self):
        from src.models import Unit
        self.assertEqual(format_value(3.3965478924, Unit.PERCENT, 1), "3.4%")
        self.assertEqual(format_value(3.88, Unit.PERCENT, 2), "3.88%")
        self.assertEqual(format_value(-0.5366991635, Unit.PERCENT, 1), "−0.5%")

    def test_change_formatting(self):
        self.assertEqual(format_change(0.03172285), "+0.03 pp")
        self.assertEqual(format_change(-0.60553019), "−0.61 pp")
        self.assertEqual(format_change(0.0), "0.00 pp")

    def test_model_never_asked_to_round(self):
        from src.synthesis_prompt import SYSTEM_PROMPT
        self.assertIn("Reproduce those strings exactly", SYSTEM_PROMPT)

    def test_allowed_tokens_include_display_values_and_years(self):
        allowed = allowed_numeric_tokens(load_input()["indicators"])
        for token in ("3.4", "3.88", "1.5", "2.1", "4.1", "1.2", "2026", "24"):
            with self.subTest(token=token):
                self.assertIn(token, allowed)

    def test_comparison_note_present_where_precision_hides_the_change(self):
        cpi = next(e for e in load_input()["indicators"]
                   if e["source_series"] == "CPIAUCNS")
        self.assertIn("comparison_note", cpi["presentation"])
        self.assertIn("broadly stable", cpi["presentation"]["comparison_note"])


class TestSchema(unittest.TestCase):
    def test_schema_is_closed(self):
        schema = json_schema()
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(schema["properties"]["sections"]["items"]["additionalProperties"])

    def test_section_count_is_fixed(self):
        schema = json_schema()
        self.assertEqual(schema["properties"]["sections"]["minItems"], 5)
        self.assertEqual(schema["properties"]["sections"]["maxItems"], 5)

    def test_section_ids_are_enumerated(self):
        enum = json_schema()["properties"]["sections"]["items"]["properties"]["section_id"]["enum"]
        self.assertEqual(set(enum), set(SECTION_IDS))

    def test_schema_is_json_serialisable(self):
        json.dumps(json_schema())


class TestEndToEndOffline(unittest.TestCase):
    """The real entry point, with the provider replaced by a stub."""

    def run_with(self, draft):
        import tempfile, shutil
        tmp = pathlib.Path(tempfile.mkdtemp())
        shutil.copy(BRIEF_INPUT_PATH, tmp / "brief_input.json")
        code = synthesise(tmp, transport=transport_returning(draft),
                          now=datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc))
        return code, tmp

    def test_good_draft_produces_html(self):
        code, tmp = self.run_with(good_draft())
        self.assertEqual(code, 0)
        self.assertTrue((tmp / "brief_draft.json").exists())
        self.assertTrue((tmp / "brief.html").exists())
        html = (tmp / "brief.html").read_text()
        self.assertIn(DRAFT_STATUS, html)
        for title in SECTION_TITLES.values():
            self.assertIn(title, html)

    def test_rejected_draft_writes_no_html(self):
        bad = good_draft()
        bad["sections"][0]["summary"] = "Inflation was 9.9% in August 2026."
        code, tmp = self.run_with(bad)
        self.assertEqual(code, 1)
        self.assertTrue((tmp / "brief_draft.json").exists(),
                        "a rejected draft is still written, for inspection")
        self.assertFalse((tmp / "brief.html").exists(),
                         "a rejected draft must never become a readable document")

    def test_deterministic_input_is_never_overwritten(self):
        before = BRIEF_INPUT_PATH.read_bytes()
        self.run_with(good_draft())
        self.assertEqual(BRIEF_INPUT_PATH.read_bytes(), before)

    def test_draft_file_records_provenance_and_no_credential(self):
        code, tmp = self.run_with(good_draft())
        record = json.loads((tmp / "brief_draft.json").read_text())
        for key in ("prompt_version", "generated_at", "input_run_id", "model",
                    "review_status"):
            self.assertIn(key, record["synthesis"])
        text = (tmp / "brief_draft.json").read_text()
        self.assertNotIn(FAKE_KEY, text)
        self.assertNotIn("api_key", text.lower())

    def test_rendered_html_contains_no_credential(self):
        code, tmp = self.run_with(good_draft())
        html = (tmp / "brief.html").read_text()
        self.assertNotIn(FAKE_KEY, html)
        self.assertNotIn("api_key", html.lower())

    def test_rendered_html_shows_sources_and_periods(self):
        code, tmp = self.run_with(good_draft())
        html = (tmp / "brief.html").read_text()
        for series in ("CPIAUCNS", "UNRATE", "DFF", "GDPC1", "RSAFS"):
            self.assertIn(series, html)
        self.assertIn("2026 Q2", html)
        self.assertIn("24 September 2026", html)

    def test_malformed_json_from_provider_rejected(self):
        # The transport returns a non-object, as a broken response would parse to.
        code, tmp = self.run_with("not a json object at all")
        self.assertEqual(code, 1)
        record = json.loads((tmp / "brief_draft.json").read_text())
        self.assertIn("draft.not_an_object",
                      [f["code"] for f in record["validation"]["hard_failures"]])


class TestNoLiveCalls(unittest.TestCase):
    SRC = pathlib.Path(__file__).resolve().parent.parent / "src"

    def test_no_test_module_opens_a_connection(self):
        for path in (pathlib.Path(__file__).resolve().parent).glob("test_*.py"):
            with self.subTest(module=path.name):
                offenders = [
                    line for line in path.read_text().splitlines()
                    if line.strip().startswith(("urllib.request.urlopen",
                                                "import requests",
                                                "from requests"))
                ]
                self.assertEqual(offenders, [])

    def test_only_the_client_modules_reach_the_network(self):
        allowed = {"fred_client.py", "llm_client.py"}
        for path in sorted(self.SRC.glob("*.py")):
            if path.name in allowed:
                continue
            with self.subTest(module=path.name):
                self.assertNotIn("urlopen", path.read_text())

    def test_project_uses_no_third_party_package(self):
        # The project is standard library only; the provider integration is a
        # plain HTTPS POST, so nothing needs installing to run any of this.
        for path in sorted(self.SRC.glob("*.py")):
            source = path.read_text()
            for package in ("import anthropic", "from anthropic", "import google",
                            "from google", "import requests", "from requests",
                            "import httpx", "from httpx"):
                with self.subTest(module=path.name, package=package):
                    self.assertNotIn(package, source)

    def test_no_requirements_file_is_needed(self):
        self.assertFalse((self.SRC.parent / "requirements.txt").exists())

    def test_provider_independent_modules_name_no_provider(self):
        for name in ("draft_validator.py", "render_brief.py", "presentation.py",
                     "brief_schema.py", "synthesis_prompt.py", "synthesize.py"):
            source = (self.SRC / name).read_text().lower()
            for provider in ("anthropic", "generativelanguage", "openai",
                             "x-goog-api-key"):
                with self.subTest(module=name, provider=provider):
                    self.assertNotIn(provider, source)


class TestGeminiTransport(unittest.TestCase):
    """The provider boundary, with the HTTPS POST stubbed."""

    ENV = {"GEMINI_API_KEY": FAKE_KEY, "LLM_MODEL": "gemini-3.8-flash"}

    def call(self, fetch):
        return request_brief("system", "user", json_schema(), env=self.ENV, fetch=fetch)

    @staticmethod
    def responder(body, recorder=None):
        def fetch(url, payload, headers):
            if recorder is not None:
                recorder.append((url, json.loads(payload.decode()), headers))
            if isinstance(body, Exception):
                raise body
            return body if isinstance(body, bytes) else json.dumps(body).encode()
        return fetch

    def test_valid_structured_response_parsed(self):
        draft = good_draft()
        result, metadata = self.call(
            self.responder(interaction(json.dumps(draft))))
        self.assertEqual(result["brief_title"], draft["brief_title"])
        self.assertEqual(metadata["model_requested"], "gemini-3.8-flash")
        self.assertEqual(metadata["status"], "completed")

    def test_request_shape_matches_the_documented_interface(self):
        seen = []
        self.call(self.responder(interaction(json.dumps(good_draft())), seen))
        url, payload, headers = seen[0]
        self.assertEqual(url, API_ENDPOINT)
        self.assertEqual(payload["model"], "gemini-3.8-flash")
        self.assertEqual(payload["input"], "user")
        self.assertEqual(payload["system_instruction"], "system")
        self.assertEqual(payload["response_format"]["mime_type"], "application/json")
        self.assertIn("schema", payload["response_format"])
        self.assertEqual(payload["generation_config"]["thinking_level"], "low")
        self.assertEqual(payload["generation_config"]["temperature"], 0.0)

    def test_credential_travels_in_a_header_not_the_url(self):
        seen = []
        self.call(self.responder(interaction(json.dumps(good_draft())), seen))
        url, payload, headers = seen[0]
        self.assertEqual(headers["x-goog-api-key"], FAKE_KEY)
        self.assertNotIn(FAKE_KEY, url)
        self.assertNotIn("key=", url)
        self.assertNotIn(FAKE_KEY, json.dumps(payload))

    def test_schema_is_constrained_not_free_form(self):
        seen = []
        self.call(self.responder(interaction(json.dumps(good_draft())), seen))
        schema = seen[0][1]["response_format"]["schema"]
        self.assertEqual(schema["type"], "object")
        self.assertIn("sections", schema["properties"])
        self.assertEqual(
            set(schema["properties"]["sections"]["items"]["properties"]
                ["section_id"]["enum"]), set(SECTION_IDS))

    def test_unsupported_schema_keywords_are_stripped_and_reported(self):
        adapted, dropped = provider_schema(json_schema())
        self.assertIn("minLength", dropped)
        self.assertNotIn("minLength", json.dumps(adapted))
        # The canonical schema is untouched.
        self.assertIn("minLength", json.dumps(json_schema()))

    def test_dropped_keywords_recorded_in_metadata(self):
        _, metadata = self.call(self.responder(interaction(json.dumps(good_draft()))))
        self.assertIn("minLength", metadata["schema_keywords_dropped_for_provider"])

    def test_http_error_becomes_synthesis_error(self):
        import io
        error = urllib.error.HTTPError(
            API_ENDPOINT, 400, "Bad Request", {},
            io.BytesIO(json.dumps({"error": {"message": "invalid model"}}).encode()))
        with self.assertRaises(SynthesisError) as ctx:
            self.call(self.responder(error))
        self.assertIn("400", str(ctx.exception))
        self.assertIn("invalid model", str(ctx.exception))

    def test_http_error_never_leaks_the_credential(self):
        import io
        leaky = f"failure while calling with key {FAKE_KEY}"
        error = urllib.error.HTTPError(
            API_ENDPOINT, 403, "Forbidden", {},
            io.BytesIO(json.dumps({"error": {"message": leaky}}).encode()))
        with self.assertRaises(SynthesisError) as ctx:
            self.call(self.responder(error))
        self.assertNotIn(FAKE_KEY, str(ctx.exception))
        self.assertIn("<redacted>", str(ctx.exception))

    def test_connection_error_becomes_synthesis_error(self):
        with self.assertRaises(SynthesisError):
            self.call(self.responder(urllib.error.URLError("no route to host")))

    def test_arbitrary_exception_is_scrubbed(self):
        with self.assertRaises(SynthesisError) as ctx:
            self.call(self.responder(RuntimeError(f"boom {FAKE_KEY}")))
        self.assertNotIn(FAKE_KEY, str(ctx.exception))

    def test_non_json_body_rejected(self):
        with self.assertRaises(SynthesisError) as ctx:
            self.call(self.responder(b"<html>gateway error</html>"))
        self.assertIn("not JSON", str(ctx.exception))

    def test_json_array_body_rejected(self):
        with self.assertRaises(SynthesisError):
            self.call(self.responder(b"[1,2,3]"))

    def test_api_error_object_rejected(self):
        with self.assertRaises(SynthesisError) as ctx:
            self.call(self.responder({"error": {"message": "quota exhausted"}}))
        self.assertIn("quota exhausted", str(ctx.exception))

    def test_empty_text_rejected(self):
        with self.assertRaises(SynthesisError):
            self.call(self.responder(interaction("   ")))

    def test_text_that_is_not_json_rejected(self):
        with self.assertRaises(SynthesisError) as ctx:
            self.call(self.responder(interaction("Here is your brief: ...")))
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_missing_credential_blocks_before_any_request(self):
        attempts = []

        def fetch(url, payload, headers):
            attempts.append(url)
            return b"{}"

        with self.assertRaises(MissingLLMCredentialError):
            request_brief("s", "u", json_schema(), env={}, fetch=fetch)
        self.assertEqual(attempts, [], "no request may be made without a credential")

    def test_structured_output_does_not_replace_validation(self):
        # A schema-valid response that is factually wrong must still be rejected.
        bad = good_draft()
        bad["sections"][0]["summary"] = "Inflation was 9.9% in August 2026."
        draft, _ = self.call(self.responder(interaction(json.dumps(bad))))
        result = validate_draft(draft, load_input())
        self.assertFalse(result.accepted)
        self.assertIn("draft.unsupported_number",
                      [f.code for f in result.hard_failures])


class TestInteractionResponseParsing(unittest.TestCase):
    """Parsing the raw Interaction resource, not an SDK convenience property.

    ``output_text`` is added by the Google GenAI SDK and does NOT appear in the
    REST response. An implementation that read it would pass a stubbed test and
    fail on the first live call, so these tests assert the documented shape:

        status == "completed"
          -> steps[type == "model_output"]
            -> content[type == "text"].text
    """

    PAYLOAD = '{"ok": true}'

    def test_single_text_block_extracted(self):
        self.assertEqual(
            extract_output_text(interaction(self.PAYLOAD)), self.PAYLOAD)

    def test_structured_json_round_trips(self):
        draft = good_draft()
        text = extract_output_text(interaction(json.dumps(draft)))
        self.assertEqual(json.loads(text)["brief_title"], draft["brief_title"])

    def test_root_level_output_text_is_not_required(self):
        # Regression guard for the defect this phase corrected.
        payload = interaction(self.PAYLOAD)
        self.assertNotIn("output_text", payload)
        self.assertEqual(extract_output_text(payload), self.PAYLOAD)

    def test_root_level_output_text_is_ignored_if_present(self):
        # Even if an SDK-shaped field appears, the steps are the source of truth.
        payload = interaction(self.PAYLOAD)
        payload["output_text"] = '{"ok": "WRONG"}'
        self.assertEqual(extract_output_text(payload), self.PAYLOAD)

    # -- status handling --------------------------------------------------
    def test_failed_status_rejected(self):
        with self.assertRaises(SynthesisError) as ctx:
            extract_output_text(interaction(self.PAYLOAD, status="failed"))
        self.assertIn("failed", str(ctx.exception))

    def test_incomplete_status_rejected(self):
        with self.assertRaises(SynthesisError) as ctx:
            extract_output_text(interaction(self.PAYLOAD, status="incomplete"))
        self.assertIn("truncated", str(ctx.exception))

    def test_every_non_completed_status_rejected(self):
        for status in ("in_progress", "requires_action", "cancelled",
                       "budget_exceeded", "queued", "failed", "incomplete"):
            with self.subTest(status=status):
                with self.assertRaises(SynthesisError):
                    extract_output_text(interaction(self.PAYLOAD, status=status))

    def test_unrecognised_status_rejected(self):
        with self.assertRaises(SynthesisError) as ctx:
            extract_output_text(interaction(self.PAYLOAD, status="something_new"))
        self.assertIn("unrecognised status", str(ctx.exception))

    def test_missing_status_rejected(self):
        payload = interaction(self.PAYLOAD)
        del payload["status"]
        with self.assertRaises(SynthesisError):
            extract_output_text(payload)

    # -- step structure ---------------------------------------------------
    def test_missing_model_output_step_rejected(self):
        payload = interaction(self.PAYLOAD, steps=[
            {"type": "user_input", "content": [{"type": "text", "text": "hi"}]}])
        with self.assertRaises(SynthesisError) as ctx:
            extract_output_text(payload)
        self.assertIn("model_output", str(ctx.exception))
        self.assertIn("user_input", str(ctx.exception))

    def test_no_steps_at_all_rejected(self):
        with self.assertRaises(SynthesisError):
            extract_output_text(interaction(self.PAYLOAD, steps=[]))

    def test_steps_not_a_list_rejected(self):
        payload = interaction(self.PAYLOAD)
        payload["steps"] = {"type": "model_output"}
        with self.assertRaises(SynthesisError) as ctx:
            extract_output_text(payload)
        self.assertIn("malformed", str(ctx.exception))

    def test_malformed_step_rejected(self):
        with self.assertRaises(SynthesisError) as ctx:
            extract_output_text(interaction(self.PAYLOAD, steps=["not an object"]))
        self.assertIn("expected an object", str(ctx.exception))

    def test_multiple_model_output_steps_rejected_conservatively(self):
        payload = interaction(self.PAYLOAD, steps=[
            {"type": "model_output", "content": [{"type": "text", "text": '{"a":1}'}]},
            {"type": "model_output", "content": [{"type": "text", "text": '{"b":2}'}]},
        ])
        with self.assertRaises(SynthesisError) as ctx:
            extract_output_text(payload)
        self.assertIn("will not guess", str(ctx.exception))

    def test_user_input_step_alongside_model_output_is_fine(self):
        payload = interaction(self.PAYLOAD, steps=[
            {"type": "user_input", "content": [{"type": "text", "text": "prompt"}]},
            {"type": "model_output", "content": [{"type": "text",
                                                  "text": self.PAYLOAD}]},
        ])
        self.assertEqual(extract_output_text(payload), self.PAYLOAD)

    # -- content structure ------------------------------------------------
    def test_model_output_without_text_block_rejected(self):
        payload = interaction(self.PAYLOAD, steps=[
            {"type": "model_output",
             "content": [{"type": "function_call", "name": "x"}]}])
        with self.assertRaises(SynthesisError) as ctx:
            extract_output_text(payload)
        self.assertIn("no 'text' content block", str(ctx.exception))

    def test_model_output_with_empty_content_rejected(self):
        payload = interaction(self.PAYLOAD,
                              steps=[{"type": "model_output", "content": []}])
        with self.assertRaises(SynthesisError):
            extract_output_text(payload)

    def test_model_output_with_missing_content_rejected(self):
        payload = interaction(self.PAYLOAD, steps=[{"type": "model_output"}])
        with self.assertRaises(SynthesisError) as ctx:
            extract_output_text(payload)
        self.assertIn("no 'content' list", str(ctx.exception))

    def test_malformed_content_block_rejected(self):
        payload = interaction(self.PAYLOAD, steps=[
            {"type": "model_output", "content": ["plain string"]}])
        with self.assertRaises(SynthesisError):
            extract_output_text(payload)

    def test_text_field_of_wrong_type_rejected(self):
        payload = interaction(self.PAYLOAD, steps=[
            {"type": "model_output", "content": [{"type": "text", "text": 42}]}])
        with self.assertRaises(SynthesisError) as ctx:
            extract_output_text(payload)
        self.assertIn("expected a string", str(ctx.exception))

    def test_consecutive_text_blocks_concatenated(self):
        # The documented semantic: consecutive text blocks form one message.
        payload = interaction(None, steps=[{"type": "model_output", "content": [
            {"type": "text", "text": '{"brief_title":'},
            {"type": "text", "text": ' "split across blocks"}'},
        ]}])
        self.assertEqual(json.loads(extract_output_text(payload))["brief_title"],
                         "split across blocks")

    def test_interleaved_text_blocks_rejected_not_stitched(self):
        payload = interaction(None, steps=[{"type": "model_output", "content": [
            {"type": "text", "text": '{"a":'},
            {"type": "thought", "text": "reasoning"},
            {"type": "text", "text": '1}'},
        ]}])
        with self.assertRaises(SynthesisError) as ctx:
            extract_output_text(payload)
        self.assertIn("interleaved", str(ctx.exception))

    def test_leading_non_text_block_tolerated(self):
        payload = interaction(None, steps=[{"type": "model_output", "content": [
            {"type": "thought", "text": "reasoning"},
            {"type": "text", "text": self.PAYLOAD},
        ]}])
        self.assertEqual(extract_output_text(payload), self.PAYLOAD)


class TestInteractionMetadata(unittest.TestCase):
    def test_usage_extracted_safely(self):
        metadata = safe_interaction_metadata(interaction('{"a":1}'))
        self.assertEqual(metadata["usage"]["total_input_tokens"], 2914)
        self.assertEqual(metadata["usage"]["total_output_tokens"], 812)
        self.assertEqual(metadata["usage"]["total_tokens"], 3726)

    def test_identity_and_status_preserved(self):
        metadata = safe_interaction_metadata(interaction('{"a":1}'))
        self.assertTrue(metadata["interaction_id"])
        self.assertEqual(metadata["interaction_object"], "interaction")
        self.assertEqual(metadata["status"], "completed")
        self.assertEqual(metadata["model_reported"], "gemini-3.8-flash")
        self.assertEqual(metadata["step_count"], 1)

    def test_absent_usage_handled(self):
        metadata = safe_interaction_metadata(interaction('{"a":1}', usage=False))
        self.assertIsNone(metadata["usage"])

    def test_malformed_usage_handled(self):
        payload = interaction('{"a":1}')
        payload["usage"] = "not an object"
        self.assertIsNone(safe_interaction_metadata(payload)["usage"])

    def test_unexpected_usage_keys_ignored(self):
        payload = interaction('{"a":1}')
        payload["usage"]["some_future_field"] = {"nested": 1}
        metadata = safe_interaction_metadata(payload)
        self.assertNotIn("some_future_field", metadata["usage"])

    def test_model_as_object_handled(self):
        payload = interaction('{"a":1}', model={"model": "gemini-3.8-flash"})
        self.assertEqual(safe_interaction_metadata(payload)["model_reported"],
                         "gemini-3.8-flash")

    def test_metadata_contains_no_credential_or_url(self):
        metadata = safe_interaction_metadata(interaction('{"a":1}'))
        text = json.dumps(metadata)
        self.assertNotIn(FAKE_KEY, text)
        self.assertNotIn("x-goog-api-key", text)
        self.assertNotIn("generativelanguage", text)

    def test_full_call_metadata_has_no_credential(self):
        def fetch(url, payload, headers):
            return json.dumps(interaction(json.dumps(good_draft()))).encode()
        _, metadata = request_brief(
            "system", "user", json_schema(),
            env={"GEMINI_API_KEY": FAKE_KEY, "LLM_MODEL": "gemini-3.8-flash"},
            fetch=fetch)
        text = json.dumps(metadata)
        self.assertNotIn(FAKE_KEY, text)
        self.assertIn("steps[type=model_output]", metadata["response_parsing"])
