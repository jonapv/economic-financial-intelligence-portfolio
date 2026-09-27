# Project 02 — Regulatory Intelligence Monitor

**Status: planned.** Not started. This document records the intent only.

Regulatory publications → Relevant developments

## Problem

Supervisory and regulatory bodies publish continuously: consultations, final rules, technical
standards, guidelines, Q&As, enforcement decisions, speeches. For any given mandate, the overwhelming
majority of that output is irrelevant — but the small remainder matters a great deal, and missing it
is costly. Filtering by hand is slow and inconsistent.

## Intended direction

Monitor a defined set of official regulatory sources, and filter their output down to the
developments that bear on a stated mandate, with each item traceable to the originating document.

Expected to follow the same discipline as Project 01:

- Collection and filtering automated; relevance judgement assisted but reviewable.
- Every item linked to the primary document, with its publication date and issuing body.
- A language model may summarise and classify; it never asserts a legal requirement or a deadline
  that is not present in the source text.
- Human review before anything is treated as actionable.

## Open questions

- Which jurisdictions and bodies to cover, given that scope drives everything else.
- How to represent "a mandate" concretely enough to filter against.
- How to handle documents that are long, amended in place, or published only as PDFs.
- How to measure whether the filter is working — what a false negative costs here.

## Status

Nothing implemented. Work begins after Project 01 reaches a working pipeline.

---

Nothing in this project constitutes legal or compliance advice.
