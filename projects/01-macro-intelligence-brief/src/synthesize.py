"""Entry point for AI-assisted synthesis.

    export GEMINI_API_KEY="$(sed -n 's/^GEMINI_API_KEY=//p' ../../.env | tr -d '[:space:]')"
    export LLM_MODEL="gemini-3.8-flash"
    python3 -m src.synthesize

Sequence:

    brief_input.json  ->  gate  ->  constrained model call  ->  brief_draft.json
    ->  deterministic validation  ->  brief.html  ->  human review

The gate runs before the model is contacted, so an input that failed validation
never reaches a provider. The draft is written to disk **before** validation so a
rejected draft can be inspected, and the HTML is rendered **only** if validation
accepted it — a rejected draft never becomes a readable document.

The deterministic input is never overwritten.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import sys
from typing import Any, Dict, Optional

from .brief_schema import DRAFT_STATUS, SCHEMA_VERSION, SECTIONS, json_schema
from .draft_validator import assert_brief_input_usable, validate_draft
from .render_brief import render_html
from .snapshot import write_json
from .synthesis_prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_user_message

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_DERIVED = (PROJECT_ROOT / "data" / "reference" / "phase2-first-real-run"
                   / "derived")


def _render(draft, brief_input, metadata, derived_dir: pathlib.Path) -> str:
    """Render with link prefixes computed from where the file will actually sit."""
    repo_root = PROJECT_ROOT.parent.parent
    to_root = os.path.relpath(repo_root, derived_dir)
    to_project = os.path.relpath(PROJECT_ROOT, derived_dir)
    return render_html(
        draft, brief_input, metadata,
        root_prefix=to_root.rstrip("/") + "/",
        project_prefix=to_project.rstrip("/") + "/",
    )


def render_only(derived_dir: pathlib.Path = DEFAULT_DERIVED) -> int:
    """Re-render brief.html from the stored draft. No provider call.

    Exists so that a bug in presentation never costs a second model request: the
    draft is already on disk and validated, and re-rendering it is deterministic.
    Refuses to render a draft whose stored validation did not pass.
    """
    record = json.loads((derived_dir / "brief_draft.json").read_text(encoding="utf-8"))
    if not record.get("validation", {}).get("accepted"):
        print("refusing to render: the stored draft did not pass validation",
              file=sys.stderr)
        return 1
    brief_input = json.loads((derived_dir / "brief_input.json").read_text(encoding="utf-8"))
    html = _render(record["draft"], brief_input, record["synthesis"], derived_dir)
    (derived_dir / "brief.html").write_text(html, encoding="utf-8")
    print(f"re-rendered {(derived_dir / 'brief.html')} from the stored draft "
          f"(no provider call)")
    return 0


def synthesise(
    derived_dir: pathlib.Path = DEFAULT_DERIVED,
    *,
    transport=None,
    now: Optional[_dt.datetime] = None,
) -> int:
    """Run one synthesis. ``transport`` is injectable so tests never call a provider."""
    input_path = derived_dir / "brief_input.json"
    draft_path = derived_dir / "brief_draft.json"
    html_path = derived_dir / "brief.html"

    brief_input = json.loads(input_path.read_text(encoding="utf-8"))

    # -- gate, before the model is contacted ------------------------------
    try:
        assert_brief_input_usable(brief_input)
    except ValueError as exc:
        print(f"synthesis aborted: {exc}", file=sys.stderr)
        return 2
    print(f"input            {input_path.name}")
    print(f"run_id           {brief_input['run_id']}")
    print(f"publication_ready {brief_input['publication_ready']}")
    print(f"indicators       {len(brief_input['indicators'])}")
    print(f"warnings         {len(brief_input['warnings'])}")
    print(f"prompt           {PROMPT_VERSION}")
    print()

    generated_at = now or _dt.datetime.now(_dt.timezone.utc)
    user_message = build_user_message(brief_input, SECTIONS)
    schema = json_schema()

    if transport is None:
        from .llm_client import SynthesisError, request_brief
        try:
            draft, call_metadata = request_brief(SYSTEM_PROMPT, user_message, schema)
        except SynthesisError as exc:
            print(f"synthesis failed: {exc}", file=sys.stderr)
            return 3
    else:
        draft, call_metadata = transport(SYSTEM_PROMPT, user_message, schema)

    metadata: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "generated_at": generated_at.isoformat(),
        "input_run_id": brief_input["run_id"],
        "input_file": input_path.name,
        "review_status": DRAFT_STATUS,
        **call_metadata,
    }

    # -- persist the draft before judging it -----------------------------
    validation = validate_draft(draft, brief_input)
    write_json(draft_path, {
        "schema_version": SCHEMA_VERSION,
        "review_status": DRAFT_STATUS,
        "synthesis": metadata,
        "validation": validation.to_dict(),
        "draft": draft,
    })
    print(f"draft written    {draft_path.name}")
    print(f"validation       {'ACCEPTED' if validation.accepted else 'REJECTED'}")
    print(f"hard failures    {len(validation.hard_failures)}")
    print(f"warnings         {len(validation.warnings)}")
    for finding in validation.hard_failures:
        print(f"  HARD FAILURE  {finding.code}: {finding.message}")
    for finding in validation.warnings:
        print(f"  WARNING       {finding.code}: {finding.message}")

    if not validation.accepted:
        print("\nno HTML rendered: a rejected draft is never turned into a readable "
              "document, and is never silently corrected.", file=sys.stderr)
        return 1

    html_path.write_text(_render(draft, brief_input, metadata, derived_dir),
                        encoding="utf-8")
    print(f"\nrendered         {html_path.name}")
    print(f"status           {DRAFT_STATUS}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate one AI-assisted macro brief from a validated brief "
                    "input. Performs one live model request."
    )
    parser.add_argument("--derived-dir", type=pathlib.Path, default=DEFAULT_DERIVED)
    parser.add_argument("--render-only", action="store_true",
                        help="re-render brief.html from the stored draft; makes no "
                             "provider call")
    args = parser.parse_args(argv)
    if args.render_only:
        return render_only(args.derived_dir)
    return synthesise(args.derived_dir)


if __name__ == "__main__":
    sys.exit(main())
