"""Deterministic presentation values.

All rounding for human consumption happens here, **before** the model call. The
model is never asked to round, and never sees a figure it is expected to
reformat: it receives finished strings and must reproduce them.

One case in the real data makes this necessary rather than merely tidy. CPI
inflation was 3.3965% against a previous 3.3648%. Both round to ``3.4%`` at the
one decimal place CPI is conventionally quoted to, yet the direction is
``increased``. A model handed those two numbers and told inflation rose would
reasonably write "rose from 3.4% to 3.4%", which is absurd. So where the current
and previous values are indistinguishable at display precision, this module says
so explicitly in a ``comparison_note``, and the model is instructed to use it.

Pure: no I/O, no clock, no model.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from .indicators import IndicatorSpec
from .models import MacroObservation, Unit

#: Changes are expressed in percentage points and shown to this precision.
#: Two places, because the real CPI change (+0.03pp) is invisible at one.
CHANGE_DECIMALS = 2

#: Unit suffixes used in prose.
_SUFFIX = {
    Unit.PERCENT: "%",
    Unit.PERCENT_ANNUALISED: "%",
    Unit.PERCENTAGE_POINTS: " pp",
    Unit.INDEX: "",
    Unit.MILLIONS_USD: "",
    Unit.BILLIONS_CHAINED_USD: "",
}


def format_value(value: float, unit: Unit, decimals: int) -> str:
    """Round and suffix a value. The only place a figure becomes a string.

    Negatives use a true minus sign rather than a hyphen, matching
    :func:`format_change`, so the rendered brief is typographically consistent.
    """
    rounded = round(value, decimals)
    sign = "\u2212" if rounded < 0 else ""
    return f"{sign}{abs(rounded):.{decimals}f}{_SUFFIX.get(unit, '')}"


def format_change(change: float, decimals: int = CHANGE_DECIMALS) -> str:
    """Format a percentage-point change with an explicit sign.

    A minus sign is used, not a hyphen, so the rendered brief reads correctly.
    Zero carries no sign.
    """
    rounded = round(change, decimals)
    if rounded == 0:
        return f"{0:.{decimals}f} pp"
    sign = "+" if rounded > 0 else "−"
    return f"{sign}{abs(rounded):.{decimals}f} pp"


def presentation_for(
    spec: IndicatorSpec, observation: MacroObservation
) -> Dict[str, Any]:
    """Build the presentation block the model is allowed to quote from."""
    decimals = spec.display_decimals
    value_display = format_value(observation.value, observation.unit, decimals)
    previous_display = format_value(observation.previous_value, observation.unit, decimals)
    change_display = format_change(observation.change)

    indistinguishable = (
        round(observation.value, decimals) == round(observation.previous_value, decimals)
        and observation.direction.value != "unchanged"
    )

    block: Dict[str, Any] = {
        "value_display": value_display,
        "previous_value_display": previous_display,
        "change_display": change_display,
        "display_decimals": decimals,
        "change_decimals": CHANGE_DECIMALS,
    }

    if indistinguishable:
        block["comparison_note"] = (
            f"The current and previous values are identical at the displayed "
            f"precision ({value_display}). The change of {change_display} is "
            f"smaller than one displayed decimal place. Describe this as broadly "
            f"stable or little changed; do NOT write that it moved from "
            f"{previous_display} to {value_display}, which would read as no "
            f"change at all."
        )
    elif observation.direction.value == "unchanged":
        block["comparison_note"] = (
            f"The value is unchanged from the previous observation "
            f"({value_display}). For this series an unchanged reading is an "
            f"ordinary outcome and is not itself a development."
        )

    return block


def allowed_numeric_tokens(brief_input) -> set:
    """Every numeric string the model is permitted to write.

    Used by the draft validator to reject any economic number the model did not
    receive. Includes:

    * the deterministic display values;
    * numbers occurring inside ``period_label`` (years, day numbers, quarters);
    * every integer appearing in the machine-generated ``warnings``, which are
      grounded by construction — a note about a gap in October 2025 has to be
      able to say 2025.

    Accepts either a full brief input or a bare list of indicators, so callers
    that only hold the indicator list still work.
    """
    import re as _re

    if isinstance(brief_input, dict):
        indicators = brief_input.get("indicators", [])
        warnings = brief_input.get("warnings", [])
    else:
        indicators, warnings = brief_input, []

    allowed = set()
    for entry in indicators:
        presentation = entry.get("presentation", {})
        for key in ("value_display", "previous_value_display", "change_display"):
            text = presentation.get(key)
            if not text:
                continue
            bare = text.replace("%", "").replace(" pp", "").replace("+", "")
            bare = bare.replace("−", "").replace("-", "").strip()
            allowed.add(bare)
            # A trailing-zero form such as "3.40" is also legitimately written
            # as "3.4"; accept both so the model is not penalised for either.
            if "." in bare:
                trimmed = bare.rstrip("0").rstrip(".")
                if trimmed:
                    allowed.add(trimmed)
        label = entry.get("period_label", "")
        for token in label.replace("Q", " ").split():
            if token.isdigit():
                allowed.add(token)

    # Warnings are machine-generated, so any figure in them is already grounded.
    warning_text = json.dumps(warnings, ensure_ascii=False) if warnings else ""
    for token in _re.findall(r"\d+", warning_text):
        allowed.add(token)
        allowed.add(token.lstrip("0") or "0")

    return allowed
