"""Deterministic validation of a model-produced draft.

Nothing the model returns is trusted. Every claim is checked against the brief
input it was given, and a draft that fails any check is **rejected**, never
silently corrected — correcting it would hide the failure and leave a
half-trusted artefact in circulation.

The numeric-grounding check is the important one. A model that fabricates a
plausible number is the failure mode this whole project has been built to
prevent, and prose is where it would appear.

Pure: no I/O, no clock, no model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Set

from .brief_schema import SECTION_IDS, SECTION_INDICATORS, SECTION_TITLES
from .presentation import allowed_numeric_tokens

#: Phrases that indicate the model has left descriptive territory. Matched
#: case-insensitively on word boundaries. Each entry is a category the prompt
#: forbids, made checkable.
FORBIDDEN_PATTERNS: Dict[str, Sequence[str]] = {
    "forecast": [
        r"\bforecast\w*", r"\bproject(?:ed|ion|ions|s)\b", r"\boutlook\b",
        r"\bexpect\w*", r"\banticipat\w*", r"\bwe (?:see|foresee)\b",
        r"\bgoing forward\b", r"\bin the coming (?:months|quarters|weeks)\b",
        r"\blikely to\b", r"\bshould continue\b", r"\btrajectory\b",
    ],
    "consensus": [
        r"\bconsensus\b", r"\bsurvey\w*\b", r"\beconomists\b",
        r"\bmarket expect\w*", r"\bbeat\b", r"\bmissed estimates\b",
    ],
    "investment_advice": [
        r"\binvest\w*", r"\bportfolio\b", r"\ballocat\w*", r"\bbuy\b",
        r"\bsell\b", r"\boverweight\b", r"\bunderweight\b", r"\btrade\w*\b",
        r"\bpositioning\b", r"\byield curve\b", r"\basset (?:price|class)\w*",
    ],
    "market_reaction": [
        r"\bmarkets? (?:reacted|responded|rallied|sold off)\b",
        r"\bequit(?:y|ies)\b", r"\bbond market\b", r"\btreasur(?:y|ies)\b",
        r"\bdollar (?:rose|fell|strengthened|weakened)\b",
    ],
    "causal_claim": [
        r"\bbecause of\b", r"\bdue to\b", r"\bdriven by\b", r"\bas a result of\b",
        r"\bled to\b", r"\bcaused by\b", r"\breflect(?:s|ing) the\b",
        r"\bon the back of\b", r"\battributable to\b",
    ],
    "policy_motive": [
        r"\bthe fed (?:aims|intends|wants|is trying)\b", r"\bpolicymakers (?:aim|intend|want)\b",
        r"\bin order to (?:curb|cool|stimulate)\b", r"\bsignal(?:s|ling|ing) that\b",
    ],
    "regime_label": [
        r"\brecession\w*", r"\bsoft landing\b", r"\bhard landing\b",
        r"\bstagflation\b", r"\boverheating\b", r"\bgoldilocks\b",
        r"\bdownturn\b", r"\bboom\b",
    ],
    "dramatic_language": [
        r"\bsurg\w+", r"\bplummet\w*", r"\bplung\w*", r"\bsoar\w*",
        r"\bcollaps\w*", r"\balarming\b", r"\bworrying\b", r"\btroubling\b",
        r"\brobust\b", r"\bdramatic\w*", r"\bsharply\b", r"\bspike[ds]?\b",
    ],
    "data_invalidity_claim": [
        r"\bdata (?:are|is) (?:invalid|unreliable|untrustworthy)\b",
        r"\bcannot be trusted\b", r"\bshould be disregarded\b",
    ],
}

#: Numbers in prose that are allowed regardless of the supplied figures:
#: small integers used in ordinary phrasing ("the five indicators", "one
#: month"). Anything with a decimal point, or a % / pp suffix, must be grounded.
_BARE_INTEGER_ALLOWLIST = {str(n) for n in range(0, 13)}

_NUMBER_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(%|pp|percentage points?)?")

#: Words that, appearing shortly before a forbidden term, mark it as a DISCLAIMER
#: rather than an instance of the thing. "This briefing contains no forecast" is
#: exactly the sentence the limitations section should carry, and flagging it
#: would reject every honest brief. The window is deliberately short so that
#: "inflation is not expected to..." — a negated forecast, but still a forecast —
#: is not excused by a distant "not".
_NEGATORS = (
    "no", "not", "never", "without", "neither", "nor", "avoids", "avoid",
    "excludes", "exclude", "free of", "absent", "does not", "contains no",
)
_NEGATION_WINDOW = 40


def _is_disclaimer(text: str, start: int) -> bool:
    """True when a forbidden term is being disclaimed rather than used."""
    window = text[max(0, start - _NEGATION_WINDOW):start].lower()
    return any(re.search(r"\b" + re.escape(word) + r"\b", window) for word in _NEGATORS)


@dataclass
class DraftFinding:
    code: str
    severity: str  # "hard_failure" | "warning"
    message: str
    location: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        out = {"code": self.code, "severity": self.severity, "message": self.message}
        if self.location:
            out["location"] = self.location
        if self.detail:
            out["detail"] = self.detail
        return out


@dataclass
class DraftValidation:
    findings: List[DraftFinding] = field(default_factory=list)

    def add(self, finding: DraftFinding) -> None:
        self.findings.append(finding)

    @property
    def hard_failures(self) -> List[DraftFinding]:
        return [f for f in self.findings if f.severity == "hard_failure"]

    @property
    def warnings(self) -> List[DraftFinding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def accepted(self) -> bool:
        return not self.hard_failures

    def to_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "status": "accepted" if self.accepted else "rejected",
            "counts": {"hard_failures": len(self.hard_failures),
                       "warnings": len(self.warnings)},
            "hard_failures": [f.to_dict() for f in self.hard_failures],
            "warnings": [f.to_dict() for f in self.warnings],
        }


def _prose_fields(draft: Dict[str, Any]) -> List[tuple]:
    """Every free-text field, paired with a location label."""
    out = [("executive_summary", draft.get("executive_summary", "")),
           ("limitations", draft.get("limitations", ""))]
    for index, section in enumerate(draft.get("sections") or []):
        if isinstance(section, dict):
            out.append((f"sections[{index}].summary", section.get("summary", "")))
    for index, item in enumerate(draft.get("key_developments") or []):
        out.append((f"key_developments[{index}]", item))
    for index, item in enumerate(draft.get("data_quality_notes") or []):
        out.append((f"data_quality_notes[{index}]", item))
    out.append(("brief_title", draft.get("brief_title", "")))
    return [(loc, text) for loc, text in out if isinstance(text, str)]


def validate_draft(draft: Any, brief_input: Dict[str, Any]) -> DraftValidation:
    """Check a draft against the brief input it was generated from."""
    result = DraftValidation()

    # -- shape ---------------------------------------------------------------
    if not isinstance(draft, dict):
        result.add(DraftFinding(
            code="draft.not_an_object", severity="hard_failure",
            message=f"draft is {type(draft).__name__}, expected a JSON object"))
        return result

    required = ("brief_title", "as_of", "executive_summary", "sections",
                "key_developments", "data_quality_notes", "limitations")
    for key in required:
        if key not in draft:
            result.add(DraftFinding(
                code="draft.missing_field", severity="hard_failure",
                message=f"required field {key!r} is absent", location=key))
    unknown = set(draft) - set(required)
    for key in sorted(unknown):
        result.add(DraftFinding(
            code="draft.unknown_field", severity="hard_failure",
            message=f"unexpected top-level field {key!r}", location=key))
    if result.hard_failures:
        return result

    # -- sections ------------------------------------------------------------
    sections = draft["sections"]
    if not isinstance(sections, list):
        result.add(DraftFinding(
            code="draft.sections_not_a_list", severity="hard_failure",
            message="'sections' must be a list"))
        return result

    seen_ids: List[str] = []
    for index, section in enumerate(sections):
        location = f"sections[{index}]"
        if not isinstance(section, dict):
            result.add(DraftFinding(
                code="draft.section_not_an_object", severity="hard_failure",
                message=f"{location} is not an object", location=location))
            continue
        sid = section.get("section_id")
        if sid not in SECTION_IDS:
            result.add(DraftFinding(
                code="draft.unknown_section", severity="hard_failure",
                message=(f"{location} has section_id {sid!r}, which is not one of "
                         f"the permitted sections {list(SECTION_IDS)}"),
                location=location))
            continue
        seen_ids.append(sid)
        expected_title = SECTION_TITLES[sid]
        if section.get("title") != expected_title:
            result.add(DraftFinding(
                code="draft.section_title_changed", severity="warning",
                message=(f"{location} title is {section.get('title')!r}, expected "
                         f"{expected_title!r}"), location=location))
        cited = section.get("indicator_ids") or []
        permitted = set(SECTION_INDICATORS[sid])
        for indicator_id in cited:
            if indicator_id not in permitted:
                result.add(DraftFinding(
                    code="draft.section_cites_unrelated_indicator",
                    severity="hard_failure",
                    message=(f"{location} ({sid}) cites {indicator_id!r}, which "
                             f"belongs to a different section. Permitted here: "
                             f"{sorted(permitted)}"),
                    location=location))
        if not cited:
            result.add(DraftFinding(
                code="draft.section_cites_nothing", severity="hard_failure",
                message=f"{location} declares no supporting indicator_ids",
                location=location))

    missing_sections = [s for s in SECTION_IDS if s not in seen_ids]
    for sid in missing_sections:
        result.add(DraftFinding(
            code="draft.missing_section", severity="hard_failure",
            message=f"required section {sid!r} ({SECTION_TITLES[sid]}) is absent"))
    duplicates = {s for s in seen_ids if seen_ids.count(s) > 1}
    for sid in sorted(duplicates):
        result.add(DraftFinding(
            code="draft.duplicate_section", severity="hard_failure",
            message=f"section {sid!r} appears more than once"))
    if seen_ids and seen_ids != [s for s in SECTION_IDS if s in seen_ids]:
        result.add(DraftFinding(
            code="draft.section_order_changed", severity="warning",
            message=f"sections are ordered {seen_ids}, expected {list(SECTION_IDS)}"))

    # -- indicator existence -------------------------------------------------
    known_indicators = {e["indicator_id"] for e in brief_input["indicators"]}
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        for indicator_id in section.get("indicator_ids") or []:
            if indicator_id not in known_indicators:
                result.add(DraftFinding(
                    code="draft.unknown_indicator", severity="hard_failure",
                    message=(f"sections[{index}] cites indicator_id "
                             f"{indicator_id!r}, which is not present in the brief "
                             f"input"), location=f"sections[{index}]"))

    # -- warning propagation -------------------------------------------------
    supplied = brief_input.get("warnings") or []
    notes = draft.get("data_quality_notes") or []
    notes_text = " ".join(n for n in notes if isinstance(n, str)).lower()
    for warning in supplied:
        series = (warning.get("series_id") or "").lower()
        if series and series not in notes_text:
            result.add(DraftFinding(
                code="draft.warning_suppressed", severity="hard_failure",
                message=(f"warning {warning['code']!r} for {warning.get('series_id')} "
                         f"is not represented in data_quality_notes. Warnings may "
                         f"be explained but never omitted."),
                location="data_quality_notes",
                detail={"warning_code": warning["code"],
                        "series_id": warning.get("series_id")}))
    if supplied and not notes:
        result.add(DraftFinding(
            code="draft.all_warnings_suppressed", severity="hard_failure",
            message=(f"{len(supplied)} warning(s) were supplied but "
                     f"data_quality_notes is empty"), location="data_quality_notes"))
    if not supplied and notes:
        result.add(DraftFinding(
            code="draft.invented_warning", severity="hard_failure",
            message=("data_quality_notes contains entries although no warnings "
                     "were supplied. Data-quality caveats are determined by the "
                     "validator, not by the model."),
            location="data_quality_notes"))

    # -- forbidden language --------------------------------------------------
    for location, text in _prose_fields(draft):
        lowered = text.lower()
        for category, patterns in FORBIDDEN_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, lowered)
                if match and not _is_disclaimer(lowered, match.start()):
                    result.add(DraftFinding(
                        code=f"draft.forbidden_{category}", severity="hard_failure",
                        message=(f"{location} contains {match.group(0)!r}, which "
                                 f"falls under the forbidden category "
                                 f"{category!r}"),
                        location=location,
                        detail={"category": category, "matched": match.group(0)}))
                    break

    # -- period discipline ---------------------------------------------------
    canonical = {e["period"] for e in brief_input["indicators"]}
    labels = {e["period_label"] for e in brief_input["indicators"]}
    for location, text in _prose_fields(draft):
        for period in canonical:
            if period in text:
                result.add(DraftFinding(
                    code="draft.canonical_period_in_prose", severity="hard_failure",
                    message=(f"{location} uses the canonical period date {period!r} "
                             f"in prose. Periods must be written using "
                             f"period_label."), location=location))
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        summary = section.get("summary", "")
        expected_labels = {
            e["period_label"] for e in brief_input["indicators"]
            if e["indicator_id"] in (section.get("indicator_ids") or [])
        }
        if expected_labels and not any(lbl in summary for lbl in expected_labels):
            result.add(DraftFinding(
                code="draft.period_label_missing", severity="hard_failure",
                message=(f"sections[{index}] ({section.get('section_id')}) does not "
                         f"state the period of its indicator. Expected one of "
                         f"{sorted(expected_labels)}."),
                location=f"sections[{index}]"))
        wrong = {lbl for lbl in labels if lbl in summary} - expected_labels
        if wrong:
            result.add(DraftFinding(
                code="draft.wrong_period", severity="hard_failure",
                message=(f"sections[{index}] ({section.get('section_id')}) states "
                         f"period(s) {sorted(wrong)}, which belong to a different "
                         f"indicator"), location=f"sections[{index}]"))

    # -- numeric grounding ---------------------------------------------------
    allowed = allowed_numeric_tokens(brief_input)
    for location, text in _prose_fields(draft):
        for match in _NUMBER_RE.finditer(text):
            number, suffix = match.group(1), match.group(2)
            economic = bool(suffix) or "." in number
            if not economic and number in _BARE_INTEGER_ALLOWLIST:
                continue
            candidate = number.rstrip("0").rstrip(".") if "." in number else number
            if number in allowed or candidate in allowed:
                continue
            result.add(DraftFinding(
                code="draft.unsupported_number", severity="hard_failure",
                message=(f"{location} contains the economic value "
                         f"{match.group(0).strip()!r}, which does not correspond to "
                         f"any presentation value supplied in the brief input. The "
                         f"draft is rejected rather than corrected."),
                location=location,
                detail={"number": number, "suffix": suffix,
                        "allowed": sorted(allowed)}))

    # -- percent vs percentage-point discipline ------------------------------
    for location, text in _prose_fields(draft):
        for match in re.finditer(r"(\d+(?:\.\d+)?)\s*%", text):
            value = match.group(1)
            change_values = {
                e["presentation"]["change_display"]
                .replace(" pp", "").replace("+", "").replace("−", "").strip()
                for e in brief_input["indicators"]
                if "presentation" in e
            }
            level_values = set()
            for e in brief_input["indicators"]:
                pres = e.get("presentation", {})
                for key in ("value_display", "previous_value_display"):
                    level_values.add(pres.get(key, "").replace("%", "")
                                     .replace("−", "").strip())
            if value in change_values and value not in level_values:
                result.add(DraftFinding(
                    code="draft.percentage_point_as_percent", severity="hard_failure",
                    message=(f"{location} writes {value}% where that figure is a "
                             f"change in percentage POINTS, not a percentage. The "
                             f"two are different quantities."),
                    location=location, detail={"value": value}))

    # -- draft status --------------------------------------------------------
    if "draft" not in (draft.get("brief_title", "") + draft.get("as_of", "")).lower():
        result.add(DraftFinding(
            code="draft.status_not_asserted", severity="warning",
            message=("neither brief_title nor as_of mentions draft status; the "
                     "renderer applies it unconditionally")))

    return result


def assert_brief_input_usable(brief_input: Dict[str, Any],
                             expected_indicators: int = 5) -> None:
    """Gate before synthesis. Raises if the input may not be sent to a model."""
    if not isinstance(brief_input, dict):
        raise ValueError("brief input is not an object")
    if brief_input.get("publication_ready") is not True:
        raise ValueError(
            "refusing to synthesise: brief input has publication_ready="
            f"{brief_input.get('publication_ready')!r}. A model must never be "
            f"given the opportunity to write fluent prose about data that did "
            f"not pass validation."
        )
    indicators = brief_input.get("indicators")
    if not isinstance(indicators, list) or len(indicators) != expected_indicators:
        raise ValueError(
            f"refusing to synthesise: expected exactly {expected_indicators} "
            f"indicators, found "
            f"{len(indicators) if isinstance(indicators, list) else 'none'}"
        )
    for entry in indicators:
        for field_name in ("indicator_id", "period", "period_label", "value",
                           "unit", "presentation"):
            if field_name not in entry:
                raise ValueError(
                    f"refusing to synthesise: indicator "
                    f"{entry.get('indicator_id', '?')} is missing {field_name!r}"
                )
