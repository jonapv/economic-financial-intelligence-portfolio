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

#: Display names for the economy code carried in the brief input. Presentation
#: only; an unknown code is shown as-is rather than guessed.
ECONOMY_NAMES = {"US": "United States"}


def _esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def _paragraphs(text: str) -> str:
    blocks = [b.strip() for b in str(text).split("\n\n") if b.strip()]
    return "".join(f'<p class="prose">{_esc(b)}</p>' for b in blocks) or ""


def _anchor(section_id: str) -> str:
    return "s-" + section_id.replace("_", "-")


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
            f'<td class="num period" data-label="Period">{_esc(entry["period_label"])}</td>'
            f'<td class="value num-col" data-label="Value">{_esc(pres["value_display"])}</td>'
            f'<td class="num num-col" data-label="Previous">{_esc(pres["previous_value_display"])}</td>'
            f'<td class="change num-col" data-label="Change">{_esc(pres["change_display"])}</td>'
            "</tr>"
        )

    section_html: List[str] = []
    toc: List[str] = []
    for position, sid in enumerate(SECTION_IDS, start=1):
        section = sections_by_id.get(sid)
        if not section:
            continue
        cited = [i for i in (section.get("indicator_ids") or []) if i in by_id]
        provenance = " · ".join(
            f'{_esc(by_id[i]["source_series"])} ({_esc(by_id[i]["period_label"])})'
            for i in cited
        )
        # The figure beside each section is the first cited indicator's supplied
        # display value, never a number of the renderer's own.
        figure = ""
        if cited:
            lead = by_id[cited[0]]
            pres = lead["presentation"]
            figure = (
                '<div class="narrative__figure">'
                f'<span class="narrative__value">{_esc(pres["value_display"])}</span>'
                f'<span class="narrative__change">{_esc(pres["change_display"])}</span>'
                f'<span class="narrative__period">{_esc(lead["period_label"])}</span>'
                "</div>"
            )
        title = _esc(SECTION_TITLES[sid])
        section_html.append(
            f'<li class="narrative__item" id="{_anchor(sid)}">'
            f'<span class="narrative__num" aria-hidden="true">{position:02d}</span>'
            "<div>"
            f'<h3 class="narrative__title">{title}</h3>'
            f'{_paragraphs(section["summary"])}'
            f'<p class="narrative__source">Source: {provenance}</p>'
            "</div>"
            f"{figure}"
            "</li>"
        )
        toc.append(f'<li><a href="#{_anchor(sid)}">{title}</a></li>')

    developments = "".join(
        f"<li>{_esc(item)}</li>" for item in draft.get("key_developments", [])
    )
    quality = "".join(
        f"<li>{_esc(item)}</li>" for item in draft.get("data_quality_notes", [])
    ) or "<li>No data-quality warnings were raised for this dataset.</li>"

    sources = "".join(
        f'<li>{_esc(e["source_series"])} — {_esc(e["source_name"])}</li>'
        for e in sorted(brief_input["indicators"], key=lambda e: e["source_series"])
    )
    prov = brief_input["provenance"]
    economy = brief_input.get("economy", "")
    economy_name = ECONOMY_NAMES.get(economy, economy)
    model = metadata.get("model_reported") or metadata.get("model_requested", "unrecorded")

    return f"""<!DOCTYPE html>
<html lang="en" class="no-js">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_esc(draft["brief_title"])}</title>
  <meta name="description" content="Descriptive macroeconomic briefing generated from validated source data. Draft, pending human review.">
  <meta name="theme-color" content="#0B0D10">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='4' fill='%230B0D10'/%3E%3Crect x='3.5' y='3.5' width='25' height='25' rx='3' fill='none' stroke='%23C6A15B'/%3E%3Ctext x='16' y='22' font-family='Georgia,serif' font-size='16' fill='%23C6A15B' text-anchor='middle'%3EE%3C/text%3E%3C/svg%3E">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&family=Newsreader:ital,opsz,wght@0,6..72,400;1,6..72,400&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{root_prefix}assets/css/base.css">
</head>
<body>
  <a class="skip-link" href="#main">Skip to content</a>

  <header class="site-header">
    <div class="container site-header__inner">
      <a class="backlink" href="{project_prefix}index.html"><span class="backlink__arrow" aria-hidden="true">&#8592;</span> Project 01</a>
      <a class="brand" href="{root_prefix}index.html">
        <span class="brand__mark" aria-hidden="true">E</span>
        <span class="brand__text">EFI <span>/</span> Projects</span>
      </a>
    </div>
    <span class="progress" aria-hidden="true"></span>
  </header>

  <main id="main">
    <div class="container brief-head">
      <div class="brief-head__top">
        <p class="eyebrow eyebrow--gold eyebrow--rule">{_esc(economy_name)} &middot; Macro Intelligence Brief</p>
        <span class="pill pill--draft"><span class="pill__dot" aria-hidden="true"></span>{_esc(DRAFT_STATUS)}</span>
      </div>
      <h1 class="display-lg brief-head__title">{_esc(draft["brief_title"])}</h1>
      <div class="brief-head__meta">
        <dl class="meta-grid">
          <div><dt>As of</dt><dd class="tnum">{_esc(draft["as_of"])}</dd></div>
          <div><dt>Status</dt><dd class="is-gold">{_esc(DRAFT_STATUS)}</dd></div>
          <div><dt>Source</dt><dd>Official data &middot; {_esc(prov["source_name"])}</dd></div>
          <div><dt>Prose</dt><dd>AI-assisted &middot; {_esc(model)}</dd></div>
        </dl>
      </div>
    </div>

    <div class="container brief-layout">
      <nav class="brief-toc" aria-label="Brief contents">
        <p class="label">Contents</p>
        <ol class="mt-1">
          <li><a href="#summary">Executive Summary</a></li>
          <li><a href="#data">Validated Data</a></li>
          {"".join(toc)}
          <li><a href="#developments">Key Developments</a></li>
          <li><a href="#notes">Quality &amp; Methodology</a></li>
        </ol>
      </nav>

      <div>
        <section class="brief-block" id="summary" aria-labelledby="h-summary">
          <div class="brief-block__head"><span class="section-num">A</span><h2 class="brief-block__title" id="h-summary">Executive Summary</h2></div>
          <div class="summary-panel">{_paragraphs(draft["executive_summary"])}</div>
        </section>

        <section class="brief-block" id="data" aria-labelledby="h-data">
          <div class="brief-block__head"><span class="section-num">B</span><h2 class="brief-block__title" id="h-data">Validated Data</h2></div>
          <div class="table-wrap table-wrap--stack">
            <table class="data-table data-table--stack">
              <caption>Every figure below was computed and validated before this brief was written. Displayed values are rounded deterministically; the pipeline retains full precision.</caption>
              <thead><tr>
                <th scope="col">Indicator</th><th scope="col">Series</th>
                <th scope="col">Period</th><th scope="col" class="num-col">Value</th>
                <th scope="col" class="num-col">Previous</th><th scope="col" class="num-col">Change</th>
              </tr></thead>
              <tbody>{"".join(rows)}</tbody>
            </table>
          </div>
        </section>

        <section class="brief-block" aria-labelledby="h-narrative">
          <div class="brief-block__head"><span class="section-num">C</span><h2 class="brief-block__title" id="h-narrative">By Section</h2></div>
          <ol class="narrative">{"".join(section_html)}</ol>
        </section>

        <section class="brief-block" id="developments" aria-labelledby="h-developments">
          <div class="brief-block__head"><span class="section-num">D</span><h2 class="brief-block__title" id="h-developments">Key Developments</h2></div>
          <ol class="dev-list">{developments}</ol>
        </section>

        <section class="brief-block" id="notes" aria-labelledby="h-notes">
          <div class="brief-block__head"><span class="section-num">E</span><h2 class="brief-block__title" id="h-notes">Quality &amp; Methodology</h2></div>
          <div class="aux-grid">
            <div class="aux">
              <h3 class="aux__title">Data Quality Notes</h3>
              <ul class="aux__list">{quality}</ul>
            </div>
            <div class="aux">
              <h3 class="aux__title">Sources &amp; Methodology</h3>
              <ul class="aux__list">{sources}</ul>
              <p>Figures were retrieved from the source, normalised, and transformed
              by tested deterministic code. A language model wrote the prose from those validated
              figures only: it performed no calculation, chose no period, and received no
              unvalidated data. The draft was then checked programmatically against its input, and
              every number in it corresponds to a supplied presentation value.</p>
              <p class="small">Indicators cover different periods by design. The latest
              available observation is not the latest economic period.</p>
            </div>
            <div class="aux">
              <h3 class="aux__title">Limitations</h3>
              {_paragraphs(draft["limitations"])}
              <p><span class="emphasis">{_esc(DRAFT_STATUS)}.</span>
              This document is a research exercise. It is not investment advice, contains no
              forecast, and must be verified against the primary releases before any use.</p>
            </div>
          </div>
          <details class="accordion mt-2">
            <summary>Run provenance</summary>
            <div class="accordion__body">
              <p class="small">
                Run {_esc(prov["run_id"])} &middot; retrieved {_esc(prov["retrieved_at_utc"])} &middot;
                raw payloads preserved at {_esc(prov["raw_snapshot_directory"])} &middot;
                model {_esc(model)} &middot;
                prompt {_esc(metadata.get("prompt_version", "unrecorded"))}
              </p>
            </div>
          </details>
        </section>
      </div>
    </div>
  </main>

  <footer class="site-footer">
    <div class="site-footer__bar"><div class="container">
      <span><a href="{root_prefix}index.html">EFI / Projects</a></span>
      <span class="tnum">{_esc(DRAFT_STATUS)}</span>
    </div></div>
  </footer>

  <script src="{root_prefix}assets/js/site.js"></script>
</body>
</html>
"""
