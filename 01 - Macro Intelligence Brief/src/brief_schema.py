"""Output schema for the synthesis step.

The model returns JSON conforming to this schema and nothing else. The section
set is closed: exactly five sections, fixed ids, in a fixed order, each bound to
the indicators it is allowed to discuss. A model cannot invent a section, drop
one, or discuss an indicator outside its own section without the draft being
rejected.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

#: Ordered, closed set of sections. Each maps to the indicator_ids it may cite.
#: The binding is what makes "no section cites an unrelated indicator"
#: checkable rather than a matter of judgement.
SECTIONS: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("inflation", "Inflation", ("us_cpi_inflation_yoy",)),
    ("monetary_policy", "Monetary Policy", ("us_effective_fed_funds_rate",)),
    ("growth", "Growth", ("us_real_gdp_growth_qoq_ann",)),
    ("labour_market", "Labour Market", ("us_unemployment_rate",)),
    ("consumption", "Consumption", ("us_retail_sales_mom",)),
)

SECTION_IDS: Tuple[str, ...] = tuple(s[0] for s in SECTIONS)
SECTION_TITLES: Dict[str, str] = {s[0]: s[1] for s in SECTIONS}
SECTION_INDICATORS: Dict[str, Tuple[str, ...]] = {s[0]: s[2] for s in SECTIONS}

#: Status every generated brief carries until a person signs it off.
DRAFT_STATUS = "DRAFT — HUMAN REVIEW REQUIRED"

#: Bump when the schema changes shape.
SCHEMA_VERSION = "1.0"


def json_schema() -> dict:
    """The canonical JSON Schema for a draft.

    This is the source of truth. The provider integration adapts it to whatever
    keyword subset that provider supports, and records anything it had to drop;
    this definition is never weakened to suit a provider, and provider-side
    schema enforcement never replaces the deterministic validator.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "brief_title", "as_of", "executive_summary", "sections",
            "key_developments", "data_quality_notes", "limitations",
        ],
        "properties": {
            "brief_title": {"type": "string", "minLength": 3, "maxLength": 120},
            "as_of": {"type": "string", "minLength": 4, "maxLength": 40},
            "executive_summary": {"type": "string", "minLength": 40, "maxLength": 1200},
            "sections": {
                "type": "array",
                "minItems": len(SECTIONS),
                "maxItems": len(SECTIONS),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["section_id", "title", "indicator_ids", "summary"],
                    "properties": {
                        "section_id": {"type": "string", "enum": list(SECTION_IDS)},
                        "title": {"type": "string", "minLength": 3, "maxLength": 60},
                        "indicator_ids": {
                            "type": "array", "minItems": 1, "maxItems": 2,
                            "items": {"type": "string"},
                        },
                        "summary": {"type": "string", "minLength": 40, "maxLength": 900},
                    },
                },
            },
            "key_developments": {
                "type": "array", "minItems": 1, "maxItems": 5,
                "items": {"type": "string", "minLength": 10, "maxLength": 300},
            },
            "data_quality_notes": {
                "type": "array", "minItems": 0, "maxItems": 6,
                "items": {"type": "string", "minLength": 10, "maxLength": 400},
            },
            "limitations": {"type": "string", "minLength": 40, "maxLength": 900},
        },
    }
