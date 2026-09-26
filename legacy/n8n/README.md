# Legacy — n8n prototype

Reference material. **Not part of the production architecture.**

## What this is

`macro-brief-prototype.json` is a sanitised export of the first working prototype of
**Project 01 — Macro Intelligence Brief**. It was built in [n8n](https://n8n.io), a no-code
automation platform, and it did genuinely work: on a weekly schedule it fetched five United States
series from the FRED API, extracted the latest and previous observation of each, passed them to a
language model in a single call, and emailed the resulting text as an HTML brief.

It is kept here because it documents how the project started and what was learned from it.

## Why it was retired

Three reasons, in order of importance.

1. **The economics were wrong.** The prototype compared raw series levels directly and described the
   difference as a change. For an index such as CPIAUCSL or a level such as GDPC1, that does not
   produce the statistic an economist would quote. This is the substantive reason, and it is
   documented in full in
   [`../../projects/01-macro-intelligence-brief/README.md`](../../projects/01-macro-intelligence-brief/README.md).

> **Series identifiers in this file are historical.** The workflow reads `CPIAUCSL` and `FEDFUNDS`.
> V1 has since superseded both: `CPIAUCSL` → `CPIAUCNS` (the unadjusted index, the conventional basis
> for the headline twelve-month figure) and `FEDFUNDS` → `DFF` (the daily effective rate, rather than a
> monthly average, for a weekly brief). Do not treat the identifiers in this export as current.

2. **The calculations were not testable.** Logic lived in visual nodes and inline JavaScript
   snippets inside a JSON export. There was no way to unit-test a transformation, review a change as
   a diff, or reproduce a past brief from its inputs.

3. **Secrets were unavoidably embedded.** API keys were written directly into node URL query
   strings, where they are easy to leak when the workflow is exported or shared.

## What replaces it

A code-based pipeline: explicit, version-controlled transformations with automated tests, where
economic statistics are computed and validated before a language model is involved at all. The
language model drafts prose from figures that have already been verified; it never calculates them.

See the [Project 01 README](../../projects/01-macro-intelligence-brief/README.md) for the intended
architecture.

## Sanitisation

This export has been stripped of all credentials and infrastructure identifiers. The following were
removed and replaced with environment-variable references or redaction markers:

| Item | Replaced with |
| --- | --- |
| FRED API key (5 occurrences, in URL query strings) | `{{ $env.FRED_API_KEY }}` |
| Google Gemini API key / project identifier | `{{ $env.LLM_API_KEY }}` |
| Personal Gmail recipient address | `{{ $env.BRIEF_RECIPIENT }}` |
| Webhook endpoint path | `redacted-webhook-path` |
| Webhook UUIDs (2) | removed entirely |

The original API key was treated as compromised and must be rotated at the provider regardless of
this cleanup. OAuth credentials were already absent from the original export — n8n strips those
automatically. It does not strip anything you type into a URL by hand, which is precisely how the
key leaked.

**Do not import and run this file expecting it to work.** It is a historical record. It also
contains no working endpoint, by design.

## Note on the duplicate

The original source directory contained a second, near-identical export
(`macro_brief_schedule_only.json`) that was a strict subset of this one: the same 18 data nodes
without the webhook trigger and rate-limiting branch. It was not carried over, as it added nothing
and contained the same leaked key.
