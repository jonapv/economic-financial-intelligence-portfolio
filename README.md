# Economic & Financial Intelligence Projects

A portfolio of research experiments exploring how AI and automation can augment research and
information workflows across **economics, financial markets, geopolitics and financial regulation**.

These are working experiments, not products. Each one documents its method, its assumptions and its
limitations alongside its output.

## Purpose

Economics and financial markets operate in an environment of information abundance. Economic data,
institutional publications, geopolitical developments and regulatory updates are produced
continuously across hundreds of fragmented sources. Collecting that material is slow and repetitive;
interpreting it is where the analytical work actually lies.

The question each project addresses is the same:

> Can AI and automation help professionals spend less time collecting information and more time
> analysing it?

## Projects

| # | Project | Domain | Status |
| --- | --- | --- | --- |
| 01 | [Macro Intelligence Brief](projects/01-macro-intelligence-brief/) | Macroeconomic monitoring | **In development** |
| 02 | [Regulatory Intelligence Monitor](projects/02-regulatory-intelligence-monitor/) | Financial regulation and supervision | Planned |
| 03 | [Geopolitical Risk Monitor](projects/03-geopolitical-risk-monitor/) | Geopolitics and economic transmission | Planned |

## Philosophy

**Automate collection, not judgement.** Automation belongs in the retrieval, normalisation and
computation layers. The economic reasoning and the final interpretation stay with a person.

**Source-grounded analysis.** Every figure must be traceable to the primary source that published
it. Statistics come from official statistical agencies and institutional data providers, never from
a language model's recollection.

**The model never does the arithmetic.** Economic statistics are computed and validated in tested
code *before* a language model sees them. A model may describe a validated figure; it may never
produce, infer or adjust one. This rule exists because the first prototype of Project 01 violated
it — see the [Project 01 method note](projects/01-macro-intelligence-brief/README.md#economic-method-a-correction-to-the-prototype).

**Human review is a required step, not a courtesy.** No output is considered finished until a person
has read, corrected and approved it.

**Document the limitations.** Each project states plainly what it does not do and where it can be
wrong.

## Technology principles

- **Static by default.** The portfolio is plain HTML and CSS, served as static files. No server-side
  rendering, no application server.
- **No build step.** Styling is hand-written CSS with custom properties in a single shared
  stylesheet. There is no bundler, no preprocessor and no CSS framework at runtime.
- **No framework.** No React, Next.js, Astro or equivalent. The pages are documents, so they are
  written as documents.
- **No database.** Data pipelines write versioned files. Nothing here needs relational storage.
- **No authentication.** The portfolio is public by design and holds nothing private.
- **Pipelines are code.** Data collection and economic transformations will be written in Python,
  version-controlled, and covered by automated tests, so any published figure can be reproduced from
  its source.
- **Secrets live in the environment.** API keys are read from environment variables listed in
  [`.env.example`](.env.example). No credential is ever committed.

## Structure

```
.
├── index.html                          Landing page
├── assets/
│   ├── css/base.css                    Shared visual system (single stylesheet)
│   ├── js/site.js                      Shared behaviour (minimal)
│   └── img/                            Shared images
├── projects/
│   ├── 01-macro-intelligence-brief/    Detail page, docs, pipeline source, tests, data
│   ├── 02-regulatory-intelligence-monitor/
│   └── 03-geopolitical-risk-monitor/
└── legacy/
    └── n8n/                            Retired prototype, sanitised, reference only
```

## Viewing locally

The site is static, so opening the file directly works:

```sh
xdg-open index.html
```

To exercise it over HTTP instead (closer to how it will be hosted):

```sh
python3 -m http.server 8000
# then visit http://localhost:8000
```

## Current status

Phase 0 — foundation. The portfolio structure, shared visual system, landing page and Project 01
documentation are in place. **No data pipeline has been implemented yet**, no external API is called,
and no language model is integrated. Project 01's detail page describes an intended architecture, not
a running system.

## Disclaimer

These projects are research exercises. Nothing in this repository constitutes investment advice, and
no generated output should be relied upon without verification against the primary sources.
