"""Render a validated draft as HTML, using the portfolio's visual language.

Pure string assembly over an already-validated draft. No model, no network, no
figures of its own: every number in the output came from the draft, which was
itself checked against the brief input.

The draft status is applied unconditionally by this renderer rather than taken
from the model, so a brief cannot present itself as reviewed.
"""

from __future__ import annotations

import html
from typing import Any, Dict, List

from .brief_schema import (
    DRAFT_STATUS,
    SECTION_IDS,
    SECTION_INDICATORS,
    SECTION_TITLES,
)


def _esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def _paragraphs(text: str) -> str:
    blocks = [b.strip() for b in str(text).split("\n\n") if b.strip()]
    return "".join(f'<p class="prose">{_esc(b)}</p>' for b in blocks) or ""


def render_html(draft: Dict[str, Any], brief_input: Dict[str, Any],
                metadata: Dict[str, Any], *,
                root_prefix: str = "../../../../../../",
                project_prefix: str = "../../../../") -> str:
    """Return a standalone HTML brief.

    ``root_prefix`` and ``project_prefix`` are relative paths from the rendered
    file back to the repository root and to the Project 01 page. They are passed
    in rather than hardcoded because the brief is written several directories
    deep inside a run folder, and counting the levels by hand is exactly the kind
    of thing that silently produces a page with no stylesheet.
    """
    by_id = {e["indicator_id"]: e for e in brief_input["indicators"]}
    sections_by_id = {s["section_id"]: s for s in draft["sections"]}

    # Order the table to match the section order, so the table and the narrative
    # read in the same sequence. Alphabetical ordering put Consumption first.
    narrative_order = {
        indicator_id: position
        for position, sid in enumerate(SECTION_IDS)
        for indicator_id in SECTION_INDICATORS[sid]
    }
    rows: List[str] = []
    for entry in sorted(brief_input["indicators"],
                        key=lambda e: narrative_order.get(e["indicator_id"], 99)):
        pres = entry["presentation"]
        rows.append(
            "<tr>"
            f'<td class="name">{_esc(entry["display_name"])}</td>'
            f'<td class="series">{_esc(entry["source_series"])}</td>'
            f'<td class="num">{_esc(entry["period_label"])}</td>'
            f'<td class="num">{_esc(pres["value_display"])}</td>'
            f'<td class="num">{_esc(pres["previous_value_display"])}</td>'
            f'<td class="num">{_esc(pres["change_display"])}</td>'
            "</tr>"
        )

    section_html: List[str] = []
    for sid in SECTION_IDS:
        section = sections_by_id.get(sid)
        if not section:
            continue
        cited = section.get("indicator_ids") or []
        provenance = " · ".join(
            f'{_esc(by_id[i]["source_series"])} ({_esc(by_id[i]["period_label"])})'
            for i in cited if i in by_id
        )
        section_html.append(
            '<div class="def-row">'
            f'<dt>{_esc(SECTION_TITLES[sid])}</dt>'
            f'<dd>{_paragraphs(section["summary"])}'
            f'<p class="small-print mt-3">Source: {provenance}</p>'
            "</dd></div>"
        )

    developments = "".join(
        f'<li class="chip">{_esc(item)}</li>' for item in draft.get("key_developments", [])
    )
    quality = "".join(
        f'<p class="prose">{_esc(item)}</p>' for item in draft.get("data_quality_notes", [])
    ) or '<p class="prose">No data-quality warnings were raised for this dataset.</p>'

    sources = " · ".join(
        f'{_esc(e["source_series"])} — {_esc(e["source_name"])}'
        for e in sorted(brief_input["indicators"], key=lambda e: e["source_series"])
    )
    prov = brief_input["provenance"]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_esc(draft["brief_title"])}</title>
  <meta name="description" content="Descriptive macroeconomic briefing generated from validated source data. Draft, pending human review.">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{root_prefix}assets/css/base.css">
</head>
<body>

  <header class="site-header">
    <div class="container site-header__inner">
      <a class="wordmark" href="{root_prefix}index.html">EFI<span class="wordmark__sep">/</span>Projects</a>
      <a class="backlink" href="{project_prefix}index.html"><span aria-hidden="true">&#8592;</span> Project 01</a>
    </div>
  </header>

  <main>
    <div class="container page-head">
      <div class="project-head rule-below">
        <div>
          <p class="eyebrow">Macro Intelligence Brief</p>
          <h1 class="title-lg mt-1">{_esc(draft["brief_title"])}</h1>
          <p class="meta mt-1">As of {_esc(draft["as_of"])}</p>
        </div>
        <span class="pill pill--planned">{_esc(DRAFT_STATUS)}</span>
      </div>
    </div>

    <div class="container page-body">
      <dl class="defs">

        <div class="def-row">
          <dt>Executive Summary</dt>
          <dd>{_paragraphs(draft["executive_summary"])}</dd>
        </div>

        <div class="def-row">
          <dt>Validated Data</dt>
          <dd>
            <div class="data-table-wrap">
              <table class="data-table">
                <caption>Every figure below was computed and validated before this brief was written. Displayed values are rounded deterministically; the pipeline retains full precision.</caption>
                <thead><tr>
                  <th scope="col">Indicator</th><th scope="col">Series</th>
                  <th scope="col">Period</th><th scope="col">Value</th>
                  <th scope="col">Previous</th><th scope="col">Change</th>
                </tr></thead>
                <tbody>{"".join(rows)}</tbody>
              </table>
            </div>
          </dd>
        </div>

        {"".join(section_html)}

        <div class="def-row">
          <dt>Key Developments</dt>
          <dd><ul class="chips">{developments}</ul></dd>
        </div>

        <div class="def-row">
          <dt>Data Quality Notes</dt>
          <dd><div class="note">{quality}</div></dd>
        </div>

        <div class="def-row">
          <dt>Sources &amp; Methodology</dt>
          <dd>
            <p class="prose">{sources}</p>
            <p class="prose">Figures were retrieved from the source, normalised, and transformed
            by tested deterministic code. A language model wrote the prose from those validated
            figures only: it performed no calculation, chose no period, and received no
            unvalidated data. The draft was then checked programmatically against its input, and
            every number in it corresponds to a supplied presentation value.</p>
            <p class="small-print mt-3">
              Run {_esc(prov["run_id"])} &middot; retrieved {_esc(prov["retrieved_at_utc"])} &middot;
              raw payloads preserved at {_esc(prov["raw_snapshot_directory"])} &middot;
              model {_esc(metadata.get("model_reported")
                          or metadata.get("model_requested", "unrecorded"))} &middot;
              prompt {_esc(metadata.get("prompt_version", "unrecorded"))}
            </p>
            <p class="small-print">Indicators cover different periods by design. The latest
            available observation is not the latest economic period.</p>
          </dd>
        </div>

        <div class="def-row">
          <dt>Limitations</dt>
          <dd><div class="note">{_paragraphs(draft["limitations"])}
            <p class="prose"><span class="emphasis">{_esc(DRAFT_STATUS)}.</span>
            This document is a research exercise. It is not investment advice, contains no
            forecast, and must be verified against the primary releases before any use.</p>
          </div></dd>
        </div>

      </dl>
    </div>
  </main>

  <footer class="site-footer">
    <div class="site-footer__bar"><div class="container">
      <span>EFI / Projects</span>
      <span class="tnum">{_esc(DRAFT_STATUS)}</span>
    </div></div>
  </footer>

</body>
</html>
"""
