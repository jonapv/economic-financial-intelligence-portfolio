# Project 01 — Macro Intelligence Brief

**Status: in development.** Nothing described here is running in production. No brief is currently
being produced or distributed.

A reproducible weekly reading of the United States macroeconomic picture. Automation handles
collection and computation; a language model drafts the surrounding prose; a person reviews and
approves the result.

---

## Problem

Monitoring the macroeconomic picture typically means consulting several sources by hand, retrieving
each indicator separately, and comparing the latest print with its previous reading. The work is
repetitive, time-consuming and adds little analytical value in itself.

It is also easy to do badly. Most published series are **levels or indices, not rates**. Comparing
two adjacent observations and describing the difference as "the change" does not produce the
statistic an economist would actually quote. The first prototype of this project made exactly that
mistake, which is the main reason it was rebuilt.

## Scope

**In scope**

- A small, fixed set of United States macroeconomic indicators.
- Scheduled retrieval from official statistical sources.
- Explicit, tested computation of the conventional transformation for each series.
- Validation of every computed figure before publication.
- AI-assisted drafting of narrative text from already-validated figures.
- A structured brief, reviewed by a person before it is considered finished.

**Out of scope**

- Forecasting or nowcasting.
- Investment recommendations of any kind.
- Market or price data.
- Real-time or intraday monitoring. The cadence is weekly.
- Any claim of analytical novelty. The transformations are standard; the contribution is
  reproducibility and traceability.

## Intended architecture

```
PRIMARY SOURCES        Official statistical releases, explicitly cited
        |
COLLECTION             Scheduled retrieval, full observation history
        |
NORMALISATION          Frequencies, units, vintages, release dates aligned
        |
ECONOMIC CALCULATIONS  Conventional transformations, computed in tested code
        |
VALIDATION             Range, sign, staleness and consistency checks
        |
AI-ASSISTED SYNTHESIS  Model drafts prose from validated figures only
        |
STRUCTURED BRIEF       Consistent structure, each claim tied to a figure
        |
HUMAN REVIEW           A person reads, corrects and approves. Required.
```

This is a conceptual representation. **It is not implemented.** No stage of this pipeline exists in
code yet.

### Planned layout

```
01-macro-intelligence-brief/
├── index.html          Public case-study page
├── README.md           This document
├── assets/             Page-specific images, screenshots, example output
├── data/
│   ├── latest/         Most recent retrieved + computed dataset (git-ignored)
│   └── samples/        Small curated fixtures, committed, used by tests
├── src/                Collection, normalisation, calculation, validation
└── tests/              Automated tests, especially for the transformations
```

## Design principles

1. **The model never does the arithmetic.** Every economic statistic is computed in code and
   validated before the language model receives it. The model's only job is to describe figures it is
   given. It must never calculate, infer, adjust or recall a number.

2. **Every figure is traceable.** Each published statistic records its source series, its
   observation dates, the transformation applied, and when it was retrieved.

3. **Transformations are explicit and tested.** No transformation is implicit in a query or buried in
   a formatting step. Each one is a named function with unit tests against known values.

4. **Validation gates publication.** A figure that fails a range, sign, staleness or consistency
   check is not passed downstream. The pipeline should refuse to publish rather than publish
   something wrong.

5. **Reproducibility over convenience.** Any past brief should be reconstructible from its recorded
   inputs.

6. **Human review is a pipeline stage.** Not a disclaimer — an actual required step.

---

## Economic method: a correction to the prototype

**This section documents the substantive reason the project is being rebuilt. It is a design rule for
the new implementation, not something already implemented.**

The earlier prototype retrieved each FRED series, took the two most recent observations, and compared
them directly — reporting whether the value had "increased", "decreased" or was "unchanged". That
comparison of raw levels is **not sufficient for professional macroeconomic interpretation.**

Specific problems:

### CPIAUCSL — a price index, not an inflation rate

`CPIAUCSL` is the level of the Consumer Price Index. A rise in the index does **not** by itself mean
that the inflation *rate* increased. The index rises in almost every period; what matters is the rate
of change, and whether that rate is higher or lower than before.

Reporting "CPI increased" is close to vacuous. The conventional statistics are the month-over-month
percentage change (often annualised) and the year-over-year percentage change. Inflation can perfectly
well be *decelerating* while the index is *rising* — the prototype would have described both cases
identically.

### GDPC1 — a level, not a growth rate

`GDPC1` is the level of real Gross Domestic Product in chained dollars. Comparing two adjacent
quarterly levels is not the same thing as reporting a conventional growth rate. United States real
GDP growth is conventionally quoted as a **quarter-over-quarter change at a seasonally adjusted
annual rate**, which requires compounding the quarterly change, not merely differencing two levels.

A raw level difference is not comparable to any published growth figure, so it cannot be discussed
alongside them.

### RSAFS — a level requiring a defined transformation

`RSAFS` is the level of advance retail sales, in millions of dollars. Before it can be interpreted as
"growth" it needs a stated transformation: month-over-month or year-over-year percentage change, on a
defined basis. It is also nominal, so in an inflationary period a nominal rise may coincide with a
real decline — a distinction worth making explicit rather than eliding.

### The other two series

`UNRATE` and `FEDFUNDS` are already expressed as rates, so a level comparison is closer to
meaningful. Even there, the conventional framing is the change in **percentage points** over a stated
horizon, and for the unemployment rate a single month's move is often within noise.

### The resulting design rule

> The new implementation must define, calculate and validate the appropriate transformation for each
> series **before** the language model receives the data.
>
> The language model must never be responsible for calculating or inferring the core economic
> statistics.

Concretely, this means:

- Each series gets an explicitly named transformation, chosen because it is the conventional
  statistic for that series, and documented as such.
- Each transformation is implemented as a tested function, verified against known published values.
- The model receives finished figures with their units and periods already attached, and is
  instructed to describe them without performing any calculation.
- Validation runs between calculation and synthesis, so an implausible figure is caught before it can
  be written up.

**These transformations are not implemented yet.** This section defines the rule; the next
development phase implements it.

---

## Legacy prototype

The first version of this project was built on [n8n](https://n8n.io), a no-code automation platform.
It worked end to end: a weekly trigger fetched five FRED series, a language model produced one
sentence per indicator, and the result was emailed as an HTML brief.

It was retired for three reasons:

1. **The economics were wrong** — the level-comparison problem documented above.
2. **The logic was not testable** — transformations lived in visual nodes and inline snippets inside
   a JSON export, with no way to unit-test them or review a change as a diff.
3. **Secrets were embedded in the workflow** — API keys were written directly into node URL query
   strings, and one was leaked that way.

A sanitised copy is preserved at [`../../legacy/n8n/`](../../legacy/n8n/) as a historical record.
**n8n is not the production architecture** and the email workflow is no longer running.

## Known limitations

- **Nothing is implemented.** This document describes intent. There is no working pipeline, no data
  collection and no LLM integration in the repository at this stage.
- **The economic transformations are specified but not built.** Until they are, no figure from this
  project should be treated as a reliable reading of any indicator.
- **Coverage is deliberately narrow** — a handful of United States series. It is not a complete
  macroeconomic picture, and the indicator set is still under review.
- **Revisions are not yet handled.** Macroeconomic data is revised, and real GDP in particular is
  revised substantially. Vintage handling is a design requirement that has not been designed.
- **AI-generated text can be wrong** even when the input figures are correct. Human review is the
  mitigation, and it is a required step.
- **Not investment advice.** This is a research exercise.

## Next development phase

Phase 1 will implement the **left-hand side of the pipeline only** — collection through validation —
with no language model involved:

1. Decide and document the transformation for each series, with the reasoning for each choice.
2. Implement collection into `src/`, reading `FRED_API_KEY` from the environment.
3. Implement normalisation and the transformation functions.
4. Write tests in `tests/` against committed fixtures in `data/samples/`, verifying each
   transformation against known published values.
5. Implement the validation gate.
6. Publish a sample computed dataset and show it on the project page.

AI-assisted synthesis is deliberately last. There is no point drafting prose until the figures
underneath it are correct.
