# Synthetic test fixtures

**Every file in this directory is synthetic. None of it is real FRED data.**

These values were invented, not observed. They were chosen so that the expected
result of each transformation is exact and can be verified by hand — for
example, GDP levels whose quarterly ratios are exactly `1.01` and `1.005`.

They exist to test the calculation layer. They must never be published, charted,
quoted, or presented as observations of the United States economy. Every file
carries a `_synthetic` flag and a `_warning` string, plus a `_designed_so_that`
block recording the arithmetic each fixture is built to produce.

| File | Series | Frequency | Obs. | Purpose |
| --- | --- | --- | --- | --- |
| `cpiaucns_synthetic.json` | CPIAUCNS | monthly | 14 | Year-over-year inflation: 4.0% now, 3.0% prior, +1.0pp |
| `unrate_synthetic.json` | UNRATE | monthly | 3 | Rate as published: 4.3%, prior 4.1%, +0.2pp |
| `dff_synthetic.json` | DFF | daily | 7 | Rate as published: 4.33%, prior 4.33%, unchanged; with a step-down and a calendar gap |
| `gdpc1_synthetic.json` | GDPC1 | quarterly | 3 | QoQ annualised: 4.060401%, prior 2.0150500625%, +2.0453509375pp |
| `rsafs_synthetic.json` | RSAFS | monthly | 3 | MoM: 0.5%, prior 1.0%, −0.5pp momentum |

For every series except `DFF`, the observation count is the documented minimum
history for that transformation, so the fixture doubles as the boundary case:
removing one observation must raise `InsufficientHistoryError`.

`dff_synthetic.json` carries five observations beyond its minimum of two, on
purpose. Slicing it exercises three distinct situations from one fixture:

- the **unchanged** case, which is the normal state of the effective rate
  between policy moves;
- a **step down** (4.48% → 4.33%), giving a −0.15pp change;
- a **calendar gap** — there is no observation for 2025-02-22 or 2025-02-23 —
  confirming that "previous" means the previous *available* observation rather
  than a fixed one-day lag.

## Superseded fixtures

Two fixtures were renamed in Phase 1.1 when their source series changed:

| Was | Now | Reason |
| --- | --- | --- |
| `cpiaucsl_synthetic.json` | `cpiaucns_synthetic.json` | V1 uses the not-seasonally-adjusted CPI index for the headline twelve-month figure |
| `fedfunds_synthetic.json` | `dff_synthetic.json` | V1 uses the daily effective rate, not the monthly average, for a weekly brief |

The CPI values were left unchanged, so the expected results are identical; the
intra-year path was made non-monotonic to resemble an unadjusted index. No
arithmetic changed in either case.

## A note on value types

Values here are JSON numbers. The real FRED API returns them as **strings**,
with `"."` for a missing observation. That conversion is the collector's job in
Phase 2. The calculation layer rejects strings deliberately, so that a malformed
payload fails at the collection boundary rather than silently propagating into a
published figure.
