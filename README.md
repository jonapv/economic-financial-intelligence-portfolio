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
| 01 | [Macro Intelligence Brief](01%20-%20Macro%20Intelligence%20Brief/) | Macroeconomic monitoring | **Completed** |
| 02 | [Regulatory Intelligence Monitor](02%20-%20Regulatory%20Intelligence%20Monitor/) | Financial regulation and supervision | Next |
| 03 | [Geopolitical Risk Monitor](03%20-%20Geopolitical%20Risk%20Monitor/) | Geopolitics and economic transmission | Planned |

## Philosophy

The portfolio rests on one combination:

> **domain knowledge + deterministic analysis + AI-assisted information workflows**

Domain knowledge decides *which* statistic answers the question. Deterministic code computes and
validates it. AI is used afterwards, for the part it is actually good at — turning validated figures
into readable prose.

**AI is not the source of economic facts.** This is the load-bearing principle. Data comes from
official statistical sources, every statistic is computed and validated in tested code, and only then
does a language model see finished figures. It never calculates, retrieves, or selects a period.

**Automate collection, not judgement.** Automation belongs in the retrieval, normalisation and
computation layers. The economic reasoning and the final interpretation stay with a person.

**Source-grounded analysis.** Every figure must be traceable to the primary source that published
it. Statistics come from official statistical agencies and institutional data providers, never from
a language model's recollection.

**The model never does the arithmetic.** Economic statistics are computed and validated in tested
code *before* a language model sees them. A model may describe a validated figure; it may never
produce, infer or adjust one. This rule exists because the first prototype of Project 01 violated
it — see the [Project 01 method note](01%20-%20Macro%20Intelligence%20Brief/README.md#economic-method-a-correction-to-the-prototype).

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

**Project 01 — Macro Intelligence Brief: complete.** The pipeline retrieves five United States series
from official sources, computes and validates the conventional transformations deterministically,
cross-checks them against the provider's own computation and against the originating agencies, and
uses a language model as a constrained final step. It has been run end to end, and the validated
example brief is committed as a static file. 432 tests, standard library only.

The clearest result was a methodological one. A figure selected by array position rather than calendar
date produced a plausible, wrong inflation rate that raised no error and passed every test, because the
synthetic fixtures had no gaps. An independent cross-check found it. That finding shaped the rest of
the project and is documented in the
[case study](01%20-%20Macro%20Intelligence%20Brief/).

**Project 02 — Regulatory Intelligence Monitor: next.** Not started.

## Disclaimer

These projects are research exercises. Nothing in this repository constitutes investment advice, and
no generated output should be relied upon without verification against the primary sources.
