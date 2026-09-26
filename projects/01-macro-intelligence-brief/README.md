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

## V1 economic specification

**Status: frozen and tested.** These definitions are implemented in
[`src/indicators.py`](src/indicators.py), which is the single source of truth — if this table and the
code ever disagree, the code is correct and this table is stale.

Scope of V1: **United States only, five indicators.** No euro-area data, no additional indicators.

### Summary

| # | indicator_id | source_series | transformation | output_unit |
| --- | --- | --- | --- | --- |
| 1 | `us_cpi_inflation_yoy` | CPIAUCSL | Year-over-year % change of the index | percent |
| 2 | `us_unemployment_rate` | UNRATE | None — already a rate | percent |
| 3 | `us_effective_fed_funds_rate` | FEDFUNDS | None — already a rate | percent |
| 4 | `us_real_gdp_growth_qoq_ann` | GDPC1 | Compounded quarterly change, annualised | percent, annual rate |
| 5 | `us_retail_sales_mom` | RSAFS | Month-over-month % change | percent |

Every indicator's **change** is a **percentage-point** difference, without exception.

### 1. CPI inflation

| Field | Value |
| --- | --- |
| `indicator_id` | `us_cpi_inflation_yoy` |
| `display_name` | CPI Inflation (YoY) |
| `economic_concept` | Consumer price inflation rate |
| `source_series` | `CPIAUCSL` — Consumer Price Index for All Urban Consumers: All Items |
| `frequency` | Monthly |
| `raw_unit` | Index level |
| `seasonal_adjustment` | Seasonally adjusted |
| `transformation` | `((CPI_t / CPI_t-12) - 1) * 100` |
| `output_unit` | Percent |
| `comparison` | Same calculation one month earlier (`t-1` vs `t-13`), differenced in percentage points |
| `minimum_history_required` | **14** observations |
| `interpretation` | The rate at which consumer prices are rising over twelve months. **The index level is not the inflation rate.** The index rises in almost every month, so a rising index says nothing about whether inflation accelerated — inflation can decelerate while the index rises. |
| `known_revision_risk` | Low for the headline index. Seasonal factors are revised annually, which affects recent month-over-month figures more than year-over-year ones. |

### 2. Unemployment rate

| Field | Value |
| --- | --- |
| `indicator_id` | `us_unemployment_rate` |
| `display_name` | Unemployment Rate |
| `economic_concept` | Share of the labour force that is unemployed |
| `source_series` | `UNRATE` — Unemployment Rate |
| `frequency` | Monthly |
| `raw_unit` | Percent |
| `seasonal_adjustment` | Seasonally adjusted |
| `transformation` | **None.** Already a rate; reported as published. |
| `output_unit` | Percent |
| `comparison` | Difference against the previous month, in percentage points |
| `minimum_history_required` | **2** observations |
| `interpretation` | Labour market slack. Already a rate, so the change is a percentage-point difference and never a percentage change. A single month's move of 0.1pp is frequently within sampling noise and must not be described as a trend. |
| `known_revision_risk` | Low. Household survey estimates are not routinely revised, though seasonal factors and annual population controls can shift the series. |

### 3. Effective federal funds rate

| Field | Value |
| --- | --- |
| `indicator_id` | `us_effective_fed_funds_rate` |
| `display_name` | **Effective Federal Funds Rate** |
| `economic_concept` | Realised overnight interbank lending rate, monthly average |
| `source_series` | `FEDFUNDS` — Federal Funds Effective Rate |
| `frequency` | Monthly |
| `raw_unit` | Percent |
| `seasonal_adjustment` | Not applicable |
| `transformation` | **None.** Already a rate; reported as published. |
| `output_unit` | Percent |
| `comparison` | Difference against the previous month, in percentage points |
| `minimum_history_required` | **2** observations |
| `interpretation` | The rate actually realised in the market, averaged over the month. **This is NOT the FOMC target range.** It must be labelled "Effective Federal Funds Rate" and never "policy rate", "the Fed's rate" or "target rate", because a monthly average spans any intra-month policy change and sits inside, not at, the target range. |
| `known_revision_risk` | Very low. A realised market average, not an estimate. |

### 4. Real GDP growth

| Field | Value |
| --- | --- |
| `indicator_id` | `us_real_gdp_growth_qoq_ann` |
| `display_name` | Real GDP Growth (QoQ, annualised) |
| `economic_concept` | Real output growth at an annual rate |
| `source_series` | `GDPC1` — Real Gross Domestic Product |
| `frequency` | Quarterly |
| `raw_unit` | Billions of chained dollars |
| `seasonal_adjustment` | Seasonally adjusted annual rate |
| `transformation` | `(((GDP_t / GDP_t-1) ** 4) - 1) * 100` |
| `output_unit` | Percent, annual rate |
| `comparison` | Same calculation for the prior quarter (`t-1` vs `t-2`), differenced in percentage points |
| `minimum_history_required` | **3** observations |
| `interpretation` | The headline United States growth number, quoted at a seasonally adjusted annual rate. **Derived here from the level series, so it must be validated against the official published growth figure before publication.** A difference between two adjacent levels is not a growth rate, and the annualised rate is a *compounded* quarterly change, not four times it. |
| `known_revision_risk` | **HIGH.** Revised across advance, second and third estimates, and again in annual and comprehensive revisions. Revisions of several tenths are routine and can change the sign of a weak quarter. |

### 5. Retail sales

| Field | Value |
| --- | --- |
| `indicator_id` | `us_retail_sales_mom` |
| `display_name` | Retail Sales (MoM) |
| `economic_concept` | Month-over-month growth in nominal retail and food services sales |
| `source_series` | `RSAFS` — Advance Retail Sales: Retail Trade and Food Services |
| `frequency` | Monthly |
| `raw_unit` | Millions of dollars |
| `seasonal_adjustment` | Seasonally adjusted |
| `transformation` | `((Sales_t / Sales_t-1) - 1) * 100` |
| `output_unit` | Percent |
| `comparison` | Prior month's month-over-month change (`t-1` vs `t-2`), differenced in percentage points |
| `minimum_history_required` | **3** observations |
| `interpretation` | Momentum in consumer spending. **The raw dollar level must never be described as growth.** The series is *nominal*, so a rise can coincide with a real decline when inflation is high; any real reading requires explicit deflation, which V1 does not perform. |
| `known_revision_risk` | **MEDIUM.** "Advance" estimates are revised in the following month as more complete survey responses arrive. |

### Design principles

1. **Raw levels and rates must never be confused.** An index level, a dollar level and a rate are
   three different kinds of quantity. Each source series has exactly one stated transformation, and
   the unit of every output is carried explicitly on the result.

2. **Percentage changes and percentage-point changes are different.** A percentage change is the
   relative change in a level or index. A percentage-point change is the arithmetic difference
   between two quantities that are already rates. They are distinct functions, distinct units in the
   `Unit` enumeration, and separately tested.

3. **Calculations are deterministic and testable.** Every transformation is a pure function with no
   I/O, no clock read and no hidden state. `retrieved_at` is passed in rather than read from the
   system clock, so a given input always yields an identical output. Rounding happens only at a
   presentation boundary (`MacroObservation.to_display`), never inside a calculation.

4. **AI receives derived metrics only after validation.** The language model is handed finished
   figures with their units, periods and provenance already attached, and is instructed to describe
   them. It never calculates, infers, adjusts or recalls a statistic. This is the rule the earlier
   prototype broke.

5. **Latest-vintage data will be used in V1.** Each run reads the most recently published value for
   each series. There is no attempt to reconstruct what was known at an earlier date.

6. **Raw source snapshots will later be preserved for reproducibility.** Storing the exact payload
   behind each published figure is a requirement, deferred to a later phase. Until then, a past brief
   cannot be reproduced exactly if the underlying series has since been revised.

7. **Data revisions are acknowledged but full vintage-data infrastructure is out of scope for V1.**
   Revision risk is recorded per indicator above. Real GDP in particular is revised substantially.
   V1 states the retrieval date alongside every figure and does not claim more than that.

### Implementation

| Path | Contents |
| --- | --- |
| [`src/calculations.py`](src/calculations.py) | Pure functions: `percentage_change`, `percentage_point_change`, `yoy_change`, `qoq_annualized_change`, `require_number` |
| [`src/indicators.py`](src/indicators.py) | `IndicatorSpec` for each of the five indicators, plus their transformations |
| [`src/models.py`](src/models.py) | `RawObservation`, `MacroObservation`, `Frequency`, `Unit`, `Direction`, `parse_series` |
| [`src/errors.py`](src/errors.py) | `MissingValueError`, `NonNumericValueError`, `ZeroDenominatorError`, `InsufficientHistoryError` |
| [`data/samples/`](data/samples/) | Synthetic fixtures — **not real data** |
| [`tests/`](tests/) | 101 tests covering all five transformations and their failure modes |

Standard library only; no third-party dependencies. The `src` package performs no I/O whatsoever.

Run the tests from this directory:

```sh
python3 -m unittest discover -s tests -t . -v
```

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

- **The economic definitions are implemented; the pipeline is not.** The five transformations are
  written, documented and covered by 101 tests. There is still **no data collection**, no validation
  gate, no synthesis step and no LLM integration. Nothing produces a brief.
- **Only synthetic data has been used.** Every fixture in `data/samples/` is invented. The
  transformations have never been run against a real observation, so they are verified as *arithmetic*
  but not yet validated as *economics*.
- **Real GDP growth has not been checked against an official figure.** The annualised rate is derived
  from the level series. Agreement with the published BEA growth figure is a required Phase 2 check
  and has not been performed.
- **Coverage is deliberately narrow** — five United States series. Not a complete macroeconomic
  picture. No euro-area data.
- **Retail sales are nominal.** No deflation is applied, so the figure conflates price and volume
  effects.
- **Revisions are acknowledged but not handled.** V1 uses latest-vintage data and records the
  retrieval date. It cannot reconstruct what was known at an earlier date, and real GDP in particular
  is revised substantially.
- **AI-generated text can be wrong** even when the input figures are correct. Human review is the
  mitigation, and it is a required step.
- **Not investment advice.** This is a research exercise.

## Development phases

**Phase 0 — foundation.** Complete. Portfolio structure, shared visual system, documentation,
sanitised legacy material.

**Phase 1 — economic definitions.** Complete. The five transformations are defined, implemented as
pure functions, documented in the specification table above, and covered by tests against synthetic
fixtures. No network access, no API key, no LLM.

**Phase 2 — collection and validation.** Next. Still no language model:

1. Implement a FRED collector reading `FRED_API_KEY` from the environment.
2. Persist the raw payload per run, so a published figure can be traced to what was retrieved.
3. Run the existing transformations against real observations for the first time.
4. **Validate real GDP growth against the official published figure** — the check that the synthetic
   fixtures cannot provide.
5. Implement the validation gate: range, sign, staleness and internal-consistency checks, refusing to
   publish rather than publishing something wrong.
6. Show a computed dataset on the project page.

**Phase 3 — synthesis and review.** AI-assisted drafting from validated figures, plus the human
review step. Deliberately last: there is no point drafting prose until the figures underneath it are
correct.
