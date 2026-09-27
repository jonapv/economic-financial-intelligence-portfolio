# Project 01 — Macro Intelligence Brief

**Status: complete.** The pipeline runs end to end and the validated example brief is committed. This
document is the deep methodology; the [case study page](index.html) is the five-minute version.

Nothing runs on a schedule, no brief is distributed, and every generated brief remains a **draft
pending human review**. This is a research exercise, not a production research system.

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

> **Note on series identifiers in this section.** The series named below are the ones the *legacy
> prototype* used. Two have since been superseded for V1: `CPIAUCSL` → **`CPIAUCNS`** and `FEDFUNDS` →
> **`DFF`**. The active V1 series are listed in the
> [specification](#v1-economic-specification) further down. The critique below applies regardless of
> which variant of each series is used — it is about levels versus rates, not about seasonal
> adjustment or frequency.

Specific problems:

### CPIAUCSL (legacy series) — a price index, not an inflation rate

`CPIAUCSL` is the level of the Consumer Price Index. A rise in the index does **not** by itself mean
that the inflation *rate* increased. The index rises in almost every period; what matters is the rate
of change, and whether that rate is higher or lower than before.

Reporting "CPI increased" is close to vacuous. The conventional statistics are the month-over-month
percentage change (often annualised) and the year-over-year percentage change. Inflation can perfectly
well be *decelerating* while the index is *rising* — the prototype would have described both cases
identically.

The same objection applies to `CPIAUCNS`, the series V1 actually uses: it too is an index level, and
it too is never itself an inflation rate.

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

### The other two series (legacy identifiers)

`UNRATE` and `FEDFUNDS` are already expressed as rates, so a level comparison is closer to
meaningful. Even there, the conventional framing is the change in **percentage points** over a stated
horizon, and for the unemployment rate a single month's move is often within noise.

V1 replaces `FEDFUNDS` with `DFF`, the daily effective rate, for the reason given in the
specification below. The point above is unchanged by that substitution: both are already rates, so
both are differenced in percentage points.

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
| 1 | `us_cpi_inflation_yoy` | CPIAUCNS | Year-over-year % change of the index | percent |
| 2 | `us_unemployment_rate` | UNRATE | None — already a rate | percent |
| 3 | `us_effective_fed_funds_rate` | DFF | None — already a rate | percent |
| 4 | `us_real_gdp_growth_qoq_ann` | GDPC1 | Compounded quarterly change, annualised | percent, annual rate |
| 5 | `us_retail_sales_mom` | RSAFS | Month-over-month % change | percent |

Every indicator's **change** is a **percentage-point** difference, without exception.

### 1. CPI inflation

| Field | Value |
| --- | --- |
| `indicator_id` | `us_cpi_inflation_yoy` |
| `display_name` | CPI Inflation (YoY) |
| `economic_concept` | Headline consumer price inflation rate |
| `source_series` | `CPIAUCNS` — Consumer Price Index for All Urban Consumers: All Items, **not seasonally adjusted** |
| `frequency` | Monthly |
| `raw_unit` | Index level |
| `seasonal_adjustment` | **Not seasonally adjusted** |
| `transformation` | `((CPI_t / CPI_t-12) - 1) * 100` |
| `output_unit` | Percent |
| `comparison` | Same calculation one month earlier (`t-1` vs `t-13`), differenced in percentage points |
| `minimum_history_required` | **14** observations |
| `interpretation` | The rate at which consumer prices are rising over twelve months. **The index level is not the inflation rate.** The index rises in almost every month, so a rising index says nothing about whether inflation accelerated — inflation can decelerate while the index rises. The NSA index is the conventional basis for the headline twelve-month figure (see below). **Corollary: this series must not be used for month-over-month inflation**, which does require seasonal adjustment. |
| `known_revision_risk` | Very low. The NSA index is not subject to the annual seasonal-factor revisions that alter the adjusted series, so published NSA index values are effectively final. |

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
| `economic_concept` | Realised overnight interbank lending rate, daily |
| `source_series` | `DFF` — Federal Funds Effective Rate, **daily** |
| `frequency` | **Daily** |
| `raw_unit` | Percent |
| `seasonal_adjustment` | Not applicable |
| `transformation` | **None.** Already a rate; reported as published. |
| `output_unit` | Percent |
| `comparison` | Difference against the **immediately preceding available daily observation**, in percentage points |
| `minimum_history_required` | **2** observations |
| `interpretation` | The rate actually realised in the overnight market, at daily frequency. **This is NOT the FOMC target range**, which is a separate concept set by the FOMC; the effective rate is where transactions actually settle, inside that range. It must be labelled "Effective Federal Funds Rate" and never "policy rate", "the Fed's rate" or "target rate". **An unchanged reading is the normal case**: the effective rate commonly holds flat for weeks or months between policy moves, so "unchanged" is not a finding. |
| `known_revision_risk` | Very low. A realised market average rather than an estimate, though the most recent daily observations can be revised slightly. |

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

### Why these source series

Two source-series choices are deliberate and were corrected before any real data entered the system.
Both changes affect *which series is read*; neither changes any arithmetic.

#### CPIAUCNS rather than CPIAUCSL, for headline YoY inflation

`CPIAUCSL` is the seasonally adjusted CPI-U index; `CPIAUCNS` is the same index **not** seasonally
adjusted. V1 uses the NSA series, because:

- **It is the conventional basis for the headline figure.** The twelve-month CPI change that is
  published and quoted is computed from the unadjusted index.
- **Seasonal adjustment is not required for the headline twelve-month CPI measure used in this
  project.** A twelve-month comparison already spans a full seasonal cycle: comparing February with
  the previous February controls for seasonality by construction. This says nothing about seasonal
  adjustment in general, which is necessary and appropriate for other purposes — including
  short-term monthly CPI analysis, where the adjusted series is the correct choice.
- **The NSA index is effectively final once published.** The adjusted series is revised when seasonal
  factors are re-estimated annually, which can move recent history. The unadjusted index is not, so a
  figure computed from it is more reproducible — which matters for a project whose stated aim is that
  any published number can be reconstructed from its source.

**The corollary is a constraint, not a bonus:** because this series is unadjusted, it must **not** be
used for month-over-month inflation. A single month's unadjusted change mixes the price signal with
the seasonal pattern, which is precisely the problem seasonal adjustment exists to solve. V1 computes
only the twelve-month change, so the constraint is respected. Short-term monthly CPI analysis is a
legitimate exercise and would appropriately use `CPIAUCSL`, under its own specification — the two
series serve different questions rather than one being better than the other.

`CPIAUCNS` remains an **index level**. It is never itself an inflation rate.

#### DFF rather than FEDFUNDS, for the effective rate

`FEDFUNDS` is a **monthly average** of the daily effective federal funds rate. `DFF` is the same rate
at **daily** frequency. V1 uses the daily series, because:

- **The product is a weekly brief.** A monthly average is a poor fit for weekly monitoring: for most
  of any month the latest `FEDFUNDS` observation describes a period that has already closed, and a
  policy change mid-month is blurred across the average rather than visible on the day it took effect.
- **A daily series gives the current rate.** For a brief published on a given date, the useful figure
  is the most recent effective rate, not last month's mean.
- **The monthly average obscures exactly what is interesting.** A monthly mean of 4.40% can describe a
  month that began at 4.48% and ended at 4.33%, reporting a level that was never actually realised for
  long.

Two consequences are handled explicitly:

1. **Unchanged is the normal case.** The effective rate holds flat for weeks or months between policy
   moves. A change of `0.0` percentage points is the expected reading and is not a finding; the brief
   must not imply otherwise.
2. **"Previous" means the previous *available* observation**, not a fixed one-day calendar lag. Gaps in
   the publication calendar therefore do not distort the change, and no assumption is made about which
   calendar days carry an observation.

**This is not the FOMC target range.** The target range is a separate concept, set by the FOMC; the
effective rate is where transactions actually settle, inside that range. `DFEDTARL` and `DFEDTARU` are
deliberately **not** part of V1, which remains five indicators.

### Cross-validation required in Phase 2

Two figures are *derived* rather than read directly, so each must be checked against an independently
published equivalent the first time real data is used. Until these checks pass, neither figure should
be published.

| Derived figure | Validate against | Why it matters |
| --- | --- | --- |
| CPI YoY, computed from the `CPIAUCNS` index | The published twelve-month percent change for the same month, where practical — e.g. an independently transformed CPI series or the figure in the source release | Confirms the lag convention (`t` vs `t-12`), the base of the comparison, and that no rounding or index-base issue has crept in |
| Real GDP QoQ annualised, computed from the `GDPC1` level series | The corresponding **BEA published growth figure** for the same quarter | Confirms the compounding convention. This is the higher-risk check: the synthetic fixtures verify the arithmetic, but only agreement with BEA confirms the *convention* is the one BEA actually uses |

Expect small differences from rounding and from the vintage of the level series. What matters is
agreement to within a tenth or so, and identical sign and direction. A discrepancy larger than that
means the specification is wrong, not the source.

The three remaining indicators — `UNRATE`, `DFF` and `RSAFS` — need no such check for their primary
value, since each is reported as published. Their percentage-point changes are arithmetic on published
figures.

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
| [`src/periods.py`](src/periods.py) | Calendar period arithmetic and exact lookup |
| [`src/provenance.py`](src/provenance.py) | `RunProvenance`, `SeriesProvenance` |
| [`src/brief_input.py`](src/brief_input.py) | The brief input contract and the publication invariant |
| [`src/errors.py`](src/errors.py) | `MissingValueError`, `NonNumericValueError`, `ZeroDenominatorError`, `InsufficientHistoryError`, `MissingRequiredPeriodError` |
| [`data/samples/`](data/samples/) | Synthetic fixtures, one per source series — **not real data** |
| [`tests/`](tests/) | 431 tests: transformations, collection boundary, period semantics, period labels, the brief input contract, synthesis and rendering |

Standard library only; no third-party dependencies. The `src` package performs no I/O whatsoever.

Run the tests from this directory:

```sh
python3 -m unittest discover -s tests -t . -v
```

---

## Phase 2 — collection, validation and the first real-data run

**Status: complete.** The pipeline from the official source through the validation gate is implemented
and has been run against live data. Stages 06–08 of the conceptual pipeline (synthesis, brief, review)
do **not** exist. No brief is produced, nothing runs on a schedule, and no language model is involved.

### Collector boundary

One module opens a network connection: [`src/fred_client.py`](src/fred_client.py). Everything else is
pure.

| Module | Role | I/O |
| --- | --- | --- |
| [`src/fred_client.py`](src/fred_client.py) | HTTPS requests to FRED via `urllib` | network |
| [`src/normalisation.py`](src/normalisation.py) | Wire format → clean observations | none |
| [`src/periods.py`](src/periods.py) | Calendar period arithmetic and lookup | none |
| [`src/validation.py`](src/validation.py) | The gate: hard failures vs warnings | none |
| [`src/snapshot.py`](src/snapshot.py) | Writes artefacts, refuses leaky payloads | filesystem |
| [`src/run_collection.py`](src/run_collection.py) | Entry point, wiring only | orchestration |

**The collector never calculates an economic statistic.** It retrieves and normalises; every figure
comes from `src/indicators.py`. A test asserts that the collector modules contain no formula.

**Credential handling.** `FRED_API_KEY` is read from the process environment only — never from source,
never from a file the application parses. It is never written to a log, an exception, a snapshot, an
output file or any stored URL. The manifest records each request as an endpoint name plus its
parameters *with `api_key` removed*, and stores no URL at all. `_scrub()` removes the key from every
error message, including the body of a 4xx response. `write_json()` refuses to write any payload
containing the key or the substring `api_key=`, and writes nothing if it finds one.

Run it manually:

```sh
cd projects/01-macro-intelligence-brief
export FRED_API_KEY="$(sed -n 's/^FRED_API_KEY=//p' ../../.env | tr -d '[:space:]')"
python3 -m src.run_collection
```

Exit status is non-zero when the gate reports `publication_ready = false`. The test suite never invokes
this command and never touches the network.

### Real source metadata checks

Live metadata from `fred/series` is compared against each `IndicatorSpec`. Comparisons are **semantic**,
against FRED's coded fields (`frequency_short`, `seasonal_adjustment_short`) rather than its
human-readable labels, which may be worded differently without any material disagreement. A mismatch in
series identity, frequency or seasonal-adjustment basis is a **hard failure**.

Confirmed by the source on the first run:

| Series | FRED frequency | FRED seasonal adjustment | Matches spec |
| --- | --- | --- | --- |
| `CPIAUCNS` | Monthly | Not Seasonally Adjusted | yes |
| `UNRATE` | Monthly | Seasonally Adjusted | yes |
| `DFF` | **Daily, 7-Day** | Not Seasonally Adjusted | yes (basis not enforced) |
| `GDPC1` | Quarterly | Seasonally Adjusted Annual Rate | yes |
| `RSAFS` | Monthly | Seasonally Adjusted | yes |

`DFF` declares seasonal adjustment inapplicable in our spec, so the source's value is recorded rather
than enforced — there is no meaningful check to impose.

### Raw snapshot policy

Every payload is written to disk exactly as received, **before** anything transforms it, under
[`data/reference/phase2-first-real-run/`](data/reference/phase2-first-real-run/):

```
manifest.json                      run id, UTC timestamp, git commit, endpoints, request
                                   descriptions with no credential
raw/<SERIES>.metadata.json         source metadata as received
raw/<SERIES>.observations.json     source observations as received, sentinels intact
raw/<SERIES>.crosscheck.*.json     FRED server-side transformations used as cross-checks
derived/macro_snapshot.json        the five derived statistics
derived/validation_report.json     structured gate output
validation_notes/official_spot_checks.json   agency comparisons
```

This is a reproducibility artefact and is tracked in Git, having been confirmed free of credentials.
It is a record of one run, not a live dataset: it is not refreshed and must not be read as current.

### Missing-value handling

FRED delivers observation values as **strings** and uses `"."` for a missing observation. Both are
handled at the normalisation boundary and nowhere else.

- `"."` is recognised as **missing**. It never becomes `0`, `NaN` or an empty string. It is excluded
  from the series passed downstream, and the dates on which it occurred are recorded in the validation
  report so that nothing disappears silently.
- Any other non-numeric value is a **hard error**. Nothing is coerced.
- Sufficient-history checks count observations **after** filtering, so a gap cannot leave a series
  short without the gate noticing.

The first run found a real gap: **October 2025 is absent from both `CPIAUCNS` and `UNRATE`** — 23 of 24
and 11 of 12 observations valid respectively. `RSAFS`, produced by the Census Bureau rather than the
BLS, has no such gap.

### Validation gate

Two severities, kept strictly apart. Any hard failure sets `publication_ready = false` and the run exits
non-zero.

**Hard failures:** wrong series id · unexpected frequency · unexpected seasonal-adjustment basis ·
malformed date · malformed numeric value · duplicate date · insufficient valid history · a required
calendar period absent · transformation failure · non-finite derived result · derived result
inconsistent with its own components · derived result claiming the wrong source series.

**Warnings** — never block publication, never remove an observation: stale latest observation · unusual
observation gaps · a cross-check that disagrees or is unavailable.

No economic forecasts and no anomaly thresholds. The gate checks that data matches its declared
specification; it does not judge whether a figure is economically plausible.

#### Freshness tolerances

Deliberately generous, and **not** a release calendar. The subtlety is that a period is labelled by its
*first* day: a quarterly observation for Q2 is dated 1 April and is already ~120 days old at its advance
estimate, reaching ~210 days just before the next quarter's. Tolerances must clear that whole cycle.

| Frequency | Tolerance | Reasoning |
| --- | --- | --- |
| Daily | 10 days | `DFF` publishes every calendar day; 10 clears any holiday |
| Monthly | 95 days | label + month length (31) + publication lag (~45) + buffer |
| Quarterly | 220 days | label + quarter length (92) + lag to the next advance estimate (~120) |

An earlier quarterly setting of 160 days was wrong and warned on `GDPC1` at 179 days while the series
was perfectly current. It was corrected for that reason.

### FRED secondary cross-check methodology

FRED's server-side transformations are used **only** as secondary cross-checks. The primary calculation
always requests `units=lin` — the raw source values — and computes everything in
`src/indicators.py`.

| Series | FRED `units` | Meaning | Maps cleanly? |
| --- | --- | --- | --- |
| `CPIAUCNS` | `pc1` | Percent change from year ago | yes — identical concept to our YoY |
| `GDPC1` | `pca` | Compounded annual rate of change | yes — for a quarterly series this is annualised QoQ growth |

`UNRATE`, `DFF` and `RSAFS` have no cross-check: the first two are reported as published, and forcing a
comparison where the concepts are not identical would be worse than having none.

A disagreement is **reported as a warning**, never silently reconciled, and our calculation is never
altered to match FRED. Tolerance is 0.05 in the unit of the figure, because FRED rounds its transformed
output.

First-run results — both agree, to within FRED's five-decimal rounding:

| Series | Period | Ours | FRED | Difference |
| --- | --- | --- | --- | --- |
| `CPIAUCNS` | 2026-08 | 3.3965479 | 3.39655 | −2.1×10⁻⁶ |
| `GDPC1` | 2026-Q2 | 1.4836588 | 1.48366 | −1.2×10⁻⁶ |

### A methodological defect the cross-check caught

**This is the most important result of Phase 2.** On the first run the CPI cross-check disagreed by
0.297pp — ours 3.6936% against FRED's 3.3965%. FRED was right.

The transformations selected comparison periods **by list position**: `series[-13]` for the observation
twelve months earlier. That is correct only when the series has no gaps. With October 2025 filtered out,
position −13 was **2025-07**, thirteen months before 2026-08:

| | Periods compared | Result |
| --- | --- | --- |
| Positional (defective) | 2026-08 vs **2025-07** | 3.6936% |
| Calendar (correct) | 2026-08 vs **2025-08** | 3.3965% |

The figure was wrong by a third of a percentage point and looked entirely plausible. Nothing in the data
was malformed; no exception was raised.

**The fix does not change any formula.** The arithmetic is identical; only the selection of operands
changed. Periods are now resolved by calendar date via [`src/periods.py`](src/periods.py), and a missing
required period raises `MissingRequiredPeriodError` — the pipeline refuses to produce a figure rather
than substituting a neighbouring observation.

| Series | Comparison basis |
| --- | --- |
| `CPIAUCNS` | calendar: `t` vs `t−12` months; previous `t−1` vs `t−13` |
| `UNRATE` | calendar: previous calendar month |
| `GDPC1` | calendar: previous and second-previous calendar quarter |
| `RSAFS` | calendar: previous and second-previous calendar month |
| `DFF` | **positional, by design** — the previous *available* observation, as its specification states |

`DFF` is deliberately the exception: its specification defines "previous" as the preceding available
observation, so a calendar gap must not cause a failure there.

Two lessons recorded rather than glossed over. First, a cross-check against an independent computation
of the same concept is worth more than any number of internal consistency checks — self-consistent code
was producing a confidently wrong number. Second, real data breaks assumptions that synthetic fixtures
cannot: the fixtures had no gaps, so 119 passing tests said nothing about this.

### BLS / BEA independent spot-check methodology

The FRED cross-checks share a provider with the primary data, so the methodology is also checked against
the **originating agencies**. These are one-off recorded checks, not automated application logic, and no
external value is hard-coded into the pipeline. Full detail:
[`validation_notes/official_spot_checks.json`](data/reference/phase2-first-real-run/validation_notes/official_spot_checks.json).

**CPI — U.S. Bureau of Labor Statistics.** Series `CUUR0000SA0` via the BLS public API, which needs no
credential: a different agency, endpoint and series identifier. The BLS index values proved **identical**
to FRED's `CPIAUCNS` for all four periods examined, and the twelve-month change is **3.396548%** against
our **3.396548%** — an exact match, 0.000000pp.

**Real GDP — Bureau of Economic Analysis.** Series `A191RL1Q225SBEA`, which is BEA's **own published
growth rate**, not a FRED transformation of the level series (FRED is only the redistributor here). BEA
publishes **1.5%** for 2026-Q2 against our **1.4837%**, a difference of −0.0163pp. Our unrounded figure
rounds to exactly 1.5%, so the residual is **publication rounding, not an arithmetic disagreement**. The
same holds for 2026-Q1: BEA 2.1%, ours 2.0892%.

A genuine vintage mismatch exists and is identified as such rather than treated as a failure: `GDPC1`
reports `last_updated` 2026-08-26 while the published growth series reports 2026-07-30, so the level may
already incorporate a revision the published rate does not. They agree after rounding regardless.

`UNRATE`, `DFF` and `RSAFS` need no agency check: each primary value is reported exactly as published.

### DFF observed calendar behaviour

Phase 1.1 deliberately made no assumption about the publication calendar. The question is now answered
empirically, and two independent findings agree:

- **Observed:** 40 consecutive observations, **every gap exactly 1 day**, including **11 weekend
  observations**. No weekend or holiday is omitted.
- **Declared:** FRED's metadata gives the frequency as **"Daily, 7-Day"**.

So `DFF` publishes on a **seven-day calendar, carrying the rate forward** across weekends rather than
omitting them. The "previous available observation" rule is therefore equivalent to a one-day lag *in
practice* for this series — but the rule is kept as stated, because it is correct either way and does not
depend on the calendar continuing to behave this way. A policy move is visible in the retrieved window:
3.63% to 3.88% on 2026-09-17.

### First real-data run

`run_id` `phase2-20260927T000634Z-b7ea4089`, retrieved 2026-09-27T00:06:34Z.

```
status             passed_with_warnings
publication_ready  true
hard failures      0
warnings           2
checks passed      42
derived records    5 of 5
```

| Indicator | Series | Period | Value | Previous | Change |
| --- | --- | --- | --- | --- | --- |
| CPI inflation, YoY | `CPIAUCNS` | 2026-08 | 3.3965% | 3.3648% | +0.0317 pp |
| Unemployment rate | `UNRATE` | 2026-08 | 4.1% | 4.1% | 0.0000 pp |
| Effective federal funds rate | `DFF` | 2026-09-24 | 3.88% | 3.88% | 0.0000 pp |
| Real GDP growth, QoQ annualised | `GDPC1` | 2026-Q2 | 1.4837% | 2.0892% | −0.6055 pp |
| Retail sales, MoM | `RSAFS` | 2026-08 | 1.2407% | −0.5367% | +1.7774 pp |

Both warnings are the same genuine finding: a 61-day gap between 2025-09 and 2025-11 in `CPIAUCNS` and
`UNRATE`, caused by the missing October 2025 observation. Flagging it is correct behaviour.

**This is a data snapshot, not a forecast and not investment advice.** No interpretation of these figures
is offered anywhere in this project.

---

## Phase 2.1 — hardening and the brief input contract

A deterministic hardening pass, run **before** any language model is allowed near the data. No LLM, no
scheduling, no email, no new indicators.

The reason for the pass: Phase 2 produced a figure that was wrong by 0.30pp, looked entirely plausible,
raised no exception, and passed 119 tests. It was caught only by comparison against an independent
computation. Everything below exists because of that.

### Period-selection semantics, by series

Each indicator now **declares** how it selects the observation it compares against, as a field on its
`IndicatorSpec` rather than as an implicit property of the code.

| Series | Frequency | Selection | What "previous" means |
| --- | --- | --- | --- |
| `CPIAUCNS` | monthly | **calendar** | `t−12` months for the current YoY; `t−1` and `t−13` for the prior YoY |
| `UNRATE` | monthly | **calendar** | the immediately preceding **calendar month** |
| `RSAFS` | monthly | **calendar** | the preceding and second-preceding **calendar months** |
| `GDPC1` | quarterly | **calendar** | the preceding and second-preceding **calendar quarters** |
| `DFF` | daily | **previous available** | whichever valid observation immediately precedes the latest — deliberate |

If a required calendar period is absent, the transformation raises `MissingRequiredPeriodError`, the gate
records a hard failure, and `publication_ready` becomes false for the run. **No neighbouring observation
is ever substituted.**

`DFF` is the single intentional exception. Its specification defines "previous" as the preceding
*available* observation, so a calendar gap must not cause a failure there. (Phase 2 established
empirically that `DFF` in fact publishes every calendar day — but the rule is kept as stated, because it
is correct either way and does not depend on that continuing.)

### Why positional indexing is forbidden for monthly and quarterly transformations

A monthly or quarterly series is published on a calendar grid, so "twelve months earlier" has one exact
meaning. Counting back a fixed number of **positions** in a list gives the same answer only when the
series has no gaps — and real series have gaps. October 2025 is absent from both `CPIAUCNS` and `UNRATE`.

Across that gap, position −13 was **2025-07**, thirteen months before 2026-08:

| | Periods compared | Result |
| --- | --- | --- |
| Positional | 2026-08 vs 2025-07 | 3.6936% |
| Calendar | 2026-08 vs 2025-08 | **3.3965%** |

Nothing in the data was malformed. No value was missing where the code looked. The arithmetic was
correct. Only the operands were wrong, and the result was a confident, publishable, incorrect number.

This is enforced structurally as well as behaviourally: `validate_period_semantics` records a **hard
failure** if any monthly or quarterly indicator declares positional selection, so a future indicator
cannot quietly reintroduce the defect.

### Cross-check tolerance distinction

One universal tolerance would be wrong, because the two comparisons answer different questions.

| | (A) Same-source computational | (B) Independent published-official |
| --- | --- | --- |
| **Compares** | our calculation vs the provider's own transformation of the same series | our unrounded figure vs an agency's already-rounded published figure |
| **Examples** | our CPI YoY vs FRED `pc1`; our annualised growth vs FRED `pca` | our 1.4837% vs BEA's published 1.5% |
| **Tolerance** | **0.001 pp** | **0.05 pp** |
| **On breach** | **HARD FAILURE** — publication blocked | recorded in the spot-check artefact; not an automated gate |
| **Rationale** | both sides compute the same statistic from the same observations, so they should agree to the provider's output rounding and no further | BEA publishes to one decimal place, so 1.5% represents anything in [1.45, 1.55); 0.05 is exactly half of one decimal place, the maximum a correct figure can differ from its own published rounding |

Observed differences on real data are ~2×10⁻⁶ pp, roughly five hundred times inside (A). The Phase 2
defect was 0.297 pp, so **(A) would now block publication outright** rather than emitting a warning.

(B) is deliberately not an automated gate, because that comparison also carries vintage risk: the agency
figure may reflect an earlier vintage than the level series we read. A difference there needs a human to
decide whether it is rounding, a revision, or a genuine method error.

### Provenance and vintage policy

Provenance lives in a companion object ([`src/provenance.py`](src/provenance.py)) rather than as extra
fields on `MacroObservation`. That model describes a *statistic*; provenance describes the *retrieval*
behind it. Merging them would make the pure calculation engine depend on how data arrived.

Every figure is traceable to: `indicator_id` · `period` · `source_series` · `source_name` ·
`retrieved_at` · `source_last_updated` · `run_id` · the raw snapshot directory and the specific files
within it · the git commit at run time.

> **The latest available observation is not the latest economic period.**

These are different things, and conflating them is how a brief ends up implying data it does not have. A
brief generated in late September 2026 legitimately contains **August** CPI, **August** unemployment, a
**24 September** effective rate and **second-quarter** GDP, because that is what has been published. The
periods differ by design and are **never normalised into a single "current" period**. The contract states
this explicitly in a `period_note` field, so a prose layer cannot claim it was not told.

### Brief input contract

[`src/brief_input.py`](src/brief_input.py) produces `derived/brief_input.json`, which is the **only**
structured economic input a future synthesis layer may receive. It is assembled from validated
`MacroObservation` records, the validation report, and the provenance object — **never from raw source
payloads**. Anything a prose layer might want must therefore have survived the gate first.

Per indicator: `indicator_id`, `display_name`, `economic_category`, `period`, `frequency`, `value`,
`unit`, `previous_value`, `change`, `change_unit`, `direction`, `comparison_basis`, `period_selection`,
`transformation`, `source_series`, `source_name`, `source_last_updated`, `retrieved_at`,
`validation_status`, `warning_codes`, `known_revision_risk`, and the period fields described below.

Values are carried at **full float precision**. Rounding remains a presentation concern.

Excluded by construction: credentials, any URL, raw payload fields (titles, realtime windows,
popularity, notes), AI prose, forecasts, market interpretation.

The file also carries a `usage_contract` stating what a consumer may and may not do — most importantly
that it may not compute, adjust, infer or recall any statistic, may not present figures from different
periods as one period, and may not introduce a figure that is not in the file.

#### Canonical period versus period label

Each indicator carries **both** representations of its period, and they are not
interchangeable.

| Field | Example | Role |
| --- | --- | --- |
| `period` | `2026-04-01` | Canonical machine date, required for traceability. Never reinterpreted. |
| `period_label` | `2026 Q2` | Human-readable form, **required in prose**. |
| `frequency` | `quarterly` | The declared frequency the label was derived from. |

The distinction exists because the canonical date is unambiguous to a machine and
genuinely ambiguous to a reader:

| Frequency | `period` | `period_label` | The misreading it prevents |
| --- | --- | --- | --- |
| monthly | `2026-08-01` | August 2026 | "prices on 1 August" |
| quarterly | `2026-04-01` | **2026 Q2** | **"April GDP"** |
| daily | `2026-09-24` | 24 September 2026 | — (the date is the observation) |

The quarterly case is the one that matters. A quarterly series is labelled by the
first day of its quarter, so `2026-04-01` means the whole of April to June —
**2026 Q2** — and not April. A prose layer asked to work that out from the raw
date would get it right most of the time, which is the worst possible failure
mode: plausible and occasionally wrong.

Labels are generated by `period_label()` in [`src/periods.py`](src/periods.py)
from `period` plus the **declared** frequency, never from free-text source
metadata such as FRED's `"Daily, 7-Day"`. Month names are hard-coded rather than
taken from the locale, so output is identical on any machine. A quarterly period
dated in a month that does not open a quarter is **rejected**, not guessed, and a
period that cannot be labelled blocks publication rather than producing an
unlabelled figure.

The contract states the rule in the file itself, under `period_field_contract`:
the synthesis layer **must** use `period_label` when referring to a period, and
**must not** reinterpret the canonical date or use it in prose in its place.

### Publication invariant

`build_brief_input` **raises** `PublicationBlockedError` and writes nothing unless
`publication_ready == true`. It also refuses a partial indicator set, which would invite a brief that
silently omits an indicator.

The point is narrow and deliberate: a language model must never have the opportunity to write fluent
prose about invalid figures. Fluency is exactly what makes a wrong figure dangerous — the Phase 2 defect
would have been written up perfectly persuasively.

### Warning propagation rule

Warnings are carried into the contract in structured form, with their code, series, message and detail
intact, and the affected indicator additionally lists its own `warning_codes`. No warnings gives
`warnings: []`.

The future prose layer **may explain** a warning. It **may not suppress** one, and it is **never asked to
invent or infer** a data-quality caveat of its own — data quality is determined by the validator, not by
a model's impression of the numbers.

### Offline rebuild and the reproducibility guard

[`src/build_brief_input.py`](src/build_brief_input.py) regenerates the contract from a stored run with
**no network access**:

```sh
python3 -m src.build_brief_input --run-dir data/reference/phase2-first-real-run
```

It re-runs normalisation, validation and the transformations from the preserved raw payloads, then
compares every recomputed figure against the stored snapshot at full precision. A mismatch beyond 1e-12
aborts the rebuild: a stored artefact that cannot be reproduced from its own raw payloads would not be
what it claims to be. On the Phase 2 run, all five figures reproduce exactly.

### The lesson, stated plainly

**Synthetic correctness is insufficient.** The synthetic fixtures had no missing periods, so they could
not have exposed this defect, and no amount of internal-consistency checking would have either — the code
was perfectly consistent with itself while being wrong. What caught it was comparison against an
independent computation of the same concept.

Real data contains missing periods, revisions, vintage mismatches and publication rounding. Each of those
had to be met before the pipeline was trustworthy, and each was met only by actually running against real
data.

**This is not production-grade infrastructure.** It is a research pipeline with one validated run, no
scheduling, no monitoring, no alerting and no operational history. What it does have is a gate that
refuses to publish what it cannot verify.

---

## Phase 3 — AI-assisted synthesis

**Status: complete for one brief.** The full pipeline has been run end to end once. Nothing runs on a
schedule, no brief is distributed, and every generated brief stays a draft until a person reviews it.

### The language layer, and its boundary

The model is a **language layer**. It received the validated `brief_input.json` and nothing else:

| It may | It may not |
| --- | --- |
| describe a figure using the supplied presentation string | compute, adjust, infer or recall any statistic |
| state the comparison basis and source series | retrieve data, or choose an observation period |
| use `period_label` for periods | reinterpret the canonical period date |
| explain a supplied warning | suppress a warning, or invent one |
| | forecast, or give investment advice |
| | explain *why* anything happened |

```
validated brief_input.json → gate → constrained model call → brief_draft.json
  → deterministic validation → brief.html → human review
```

### Modules

| Module | Role | Provider-specific |
| --- | --- | --- |
| [`src/presentation.py`](src/presentation.py) | Deterministic rounding, **before** the call | no |
| [`src/brief_schema.py`](src/brief_schema.py) | Closed five-section schema | no |
| [`src/synthesis_prompt.py`](src/synthesis_prompt.py) | Versioned prompt (`synthesis-v1`) | no |
| [`src/llm_client.py`](src/llm_client.py) | Gemini Interactions REST call | **yes, only here** |
| [`src/draft_validator.py`](src/draft_validator.py) | Deterministic claim validation | no |
| [`src/render_brief.py`](src/render_brief.py) | HTML renderer | no |
| [`src/synthesize.py`](src/synthesize.py) | Entry point | no |

The project remains **standard library only**. There is no SDK and no `requirements.txt`: the provider
call is one HTTPS POST, so `urllib` is sufficient and the whole test suite runs with nothing installed.

### Provider integration

Google Gemini, model `gemini-3.8-flash`, via the **Interactions** REST endpoint:

```
POST https://generativelanguage.googleapis.com/v1beta/interactions
x-goog-api-key: <from GEMINI_API_KEY>
{ "model": …, "input": …, "system_instruction": …,
  "response_format": { "mime_type": "application/json", "schema": … },
  "generation_config": { "thinking_level": "low", "temperature": 0.0 } }
```

The credential travels in a **header, never a query string**. That is deliberate: the retired prototype
put its keys in URL query parameters, which is exactly how this project's first key leaked.

Two interface corrections were made before the first call, both found by reading the reference rather
than by running anything:

1. The synthesis layer was first written against a different provider's API. Rewriting it touched only
   `llm_client.py`; the schema, prompt, presentation layer, validator, renderer and their tests were
   provider-independent and did not change. That is the boundary working.
2. **The response is parsed from the raw Interaction resource**, not from `output_text`. That field is
   a convenience property added by Google's SDK and does **not** exist in the REST response. The parser
   walks `status == "completed"` → `steps[type == "model_output"]` → `content[type == "text"]` → `text`,
   rejects all seven non-completed statuses with a specific reason each, refuses more than one
   `model_output` step rather than guessing which is the brief, joins only *consecutive* text blocks,
   and rejects interleaved output. Reading `output_text` would have passed every stubbed test and
   failed on the first live call.

### Structured output is not validation

The request constrains the response to JSON matching the schema, so no free-form prose is parsed after
the fact. The canonical schema in `brief_schema.py` is the source of truth; `provider_schema()` adapts a
*copy* to the keyword subset the provider documents, and records what it dropped (`minLength`,
`maxLength`) rather than hiding the difference.

**Schema enforcement guarantees shape, not truth.** The deterministic validator runs over every
response regardless, and a test proves it: a schema-*valid* draft containing a fabricated figure is
still rejected.

### The publication invariant

`build_brief_input` refuses to produce a brief input unless `publication_ready` is true, and
`synthesize.py` re-checks the gate **before contacting the provider** — a test asserts the transport is
never called when the gate fails. A model must never get the opportunity to write fluent prose about
invalid figures, because fluency is what makes a wrong figure dangerous.

A rejected draft is written to disk for inspection but **never rendered**. There is no silent repair.

### First real synthesis

One request, one draft, accepted. No retry, no prompt adjustment, no regeneration.

| | |
| --- | --- |
| Model requested / reported | `gemini-3.8-flash` / `gemini-3.8-flash` |
| Interaction status | `completed` |
| Tokens | 6,202 in · 972 out · 7,174 total |
| Prompt version | `synthesis-v1` |
| Input run | `phase2-20260927T000634Z-b7ea4089` |
| Deterministic validation | **accepted**, 0 hard failures, 1 advisory warning |
| Factual audit | **19 sentences, 0 unsupported claims** |
| Review status | `DRAFT — HUMAN REVIEW REQUIRED` |

The audit checked every number, unit, period, direction-of-change claim, comparison and data-quality
statement against `brief_input.json`: 55 numeric tokens, 81 unit checks, 14 period checks, 17
direction checks. Both warnings were carried through. No forecast, causal claim, market reference or
advice appeared.

One result is worth recording because it validates a design decision. CPI inflation was 3.3965% against
a previous 3.3648% — both render as **3.4%** at CPI's conventional precision, while the direction is
`increased`. The presentation layer detected that the change was smaller than one displayed decimal
place and supplied a `comparison_note` instructing the model to call it broadly stable and explicitly
*not* to write that it moved from 3.4% to 3.4%. The model complied and still disclosed the
`+0.03 pp` change. Without that note, the most likely output was a sentence that read as self-contradictory.

Artefacts: [`derived/brief_draft.json`](data/reference/phase2-first-real-run/derived/brief_draft.json)
(raw draft, provider metadata, validation result) and
[`derived/brief.html`](data/reference/phase2-first-real-run/derived/brief.html) (rendered brief).
The deterministic input is never overwritten.

### Example output on the portfolio

The Project 01 page links the committed static brief. Opening either page makes **no** request to any
provider, so visiting the portfolio never triggers a paid model call. There is no email form.

### What Phase 3 does not establish

One brief, from one dataset, on one day. It shows the pipeline runs end to end and that this particular
output survived every check. It does not establish that the model behaves this well across datasets,
that the forbidden-language patterns catch paraphrase, or that the numeric grounding catches a claim
built from correct numbers arranged wrongly. Those need more than one sample.

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

- **One brief, one dataset, one day.** The pipeline has run end to end once. That the output survived
  every check says nothing yet about how the model behaves across datasets, and there is no operational
  history at all.
- **The forbidden-language check is regex-based.** It catches the phrasings it knows and will miss
  paraphrase. It also over-fires: two false positives appeared in a single realistic draft during
  development, both fixed, and more certainly exist.
- **Numeric grounding is textual.** It cannot catch a claim built entirely from correct numbers arranged
  wrongly — attributing the right figure to the wrong indicator in prose that avoids period labels would
  pass.
- **The publication invariant is enforced in code, not by process.** Nothing stops a future author
  reading `macro_snapshot.json` directly and bypassing the contract.
- **One run, one moment.** The stored dataset is a single snapshot from 2026-09-27. It is not refreshed,
  there is no scheduling, and it must not be read as current.
- **A silent-wrong-answer class of bug reached real data before being caught.** Positional period
  selection produced a plausible CPI figure that was wrong by 0.30pp, and 119 passing tests did not
  detect it because the synthetic fixtures had no gaps. It was caught only by an independent
  cross-check. Similar assumptions may remain elsewhere; the lesson is that internal consistency proves
  much less than external comparison.
- **Only latest-vintage data.** Each run reads the most recent published value. There is no vintage
  reconstruction, so a past figure cannot be reproduced once the source revises. The raw snapshot
  mitigates this only for runs actually performed.
- **Real GDP is revised substantially**, across advance, second and third estimates and again annually.
  The first run already shows a vintage mismatch between the level series and the published growth rate.
- **Retail sales are nominal.** No deflation, so price and volume effects are conflated.
- **The cross-check tolerance (0.05) is reasoned, not calibrated.** It is loose enough to absorb FRED's
  rounding and tight enough to have caught a 0.30pp error, but it has not been tested against a range of
  real disagreements.
- **The freshness tolerances are not release calendars.** They detect a series that has stopped
  updating, nothing finer. One of them was already found to be mis-set on first contact with real data.
- **Two of five indicators are cross-checked.** `UNRATE`, `DFF` and `RSAFS` are reported as published,
  so there is no derived statistic to verify — but that also means no independent check on the retrieval
  path for those three beyond the metadata comparison.
- **Coverage is deliberately narrow:** five United States series. Not a macroeconomic picture. No
  euro-area data.
- **The publication invariant is enforced in code, not by process.** `build_brief_input` refuses to run
  on a failed gate, but nothing prevents a future author from reading `macro_snapshot.json` directly and
  bypassing the contract. The invariant holds only as long as the synthesis layer uses the contract.
- **The 0.001pp computational tolerance is reasoned from one run.** It is five hundred times looser than
  the observed differences and five hundred times tighter than the defect it would have caught, which is
  a comfortable margin — but it has been exercised against exactly two real comparisons.
- **Only two of five indicators have a computational cross-check.** `UNRATE`, `DFF` and `RSAFS` are
  reported as published, so there is no derived statistic to verify. Their retrieval path is checked only
  by metadata comparison and the period-semantics invariant.
- **Not investment advice.** No interpretation of any figure is offered.

## Development phases

**Phase 0 — foundation.** Complete. Portfolio structure, shared visual system, documentation, sanitised
legacy material.

**Phase 1 — economic definitions.** Complete. Five transformations defined, implemented as pure
functions and tested against synthetic fixtures.

**Phase 1.1 — source-series refinement.** Complete. `CPIAUCSL` → `CPIAUCNS`; `FEDFUNDS` → `DFF`.

**Phase 2 — collection and validation.** Complete. FRED collector, normalisation boundary, validation
gate, raw snapshot preservation, FRED cross-checks, BLS/BEA spot checks, and one validated real-data run.
A methodological defect in period selection was found and fixed. 207 tests, none touching the network.

**Phase 2.1 — hardening and the brief input contract.** Complete. Period-selection semantics declared
per series and enforced structurally; cross-check tolerances split into computational (0.001pp, hard
failure) and published-official (0.05pp, recorded); provenance and vintage policy defined; the brief input
contract frozen behind a publication invariant. 275 tests, none touching the network.

**Phase 2.2 — period presentation contract.** Complete. Each indicator now carries `frequency`, the
canonical `period` and a deterministically generated `period_label`, removing the last semantic ambiguity
before a model reads the file. All five numeric values verified bit-identical across the change. 313
tests.

**Phase 4 — portfolio finalisation.** Complete. The project page was rewritten as a case study in
narrative order, the architecture diagram updated to the nine implemented stages, the technology
section corrected, and the validation finding written up as a methodological lesson.

**Phase 3 — AI-assisted synthesis.** Complete for one brief. Constrained Gemini synthesis from
`brief_input.json`, deterministic draft validation, rendered HTML, and a required human-review status.
One live request produced a draft that passed validation with zero hard failures and a sentence-by-sentence
factual audit with zero unsupported claims. 431 tests, none touching a provider.

Deliberately last, and Phase 2 showed why: a confidently wrong figure would have been written up in
fluent prose and read perfectly well.
