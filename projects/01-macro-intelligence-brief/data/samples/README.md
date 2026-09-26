# Synthetic test fixtures

**Every file in this directory is synthetic. None of it is real FRED data.**

These values were invented, not observed. They were chosen so that the expected
result of each transformation is exact and can be verified by hand — for
example, GDP levels whose quarterly ratios are exactly `1.01` and `1.005`.

They exist to test the calculation layer. They must never be published, charted,
quoted, or presented as observations of the United States economy. Every file
carries a `_synthetic` flag and a `_warning` string, plus a `_designed_so_that`
block recording the arithmetic each fixture is built to produce.

| File | Series | Observations | Purpose |
| --- | --- | --- | --- |
| `cpiaucsl_synthetic.json` | CPIAUCSL | 14 | Year-over-year inflation: 4.0% now, 3.0% prior, +1.0pp |
| `unrate_synthetic.json` | UNRATE | 3 | Rate as published: 4.3%, prior 4.1%, +0.2pp |
| `fedfunds_synthetic.json` | FEDFUNDS | 3 | Rate as published: 4.33%, prior 4.33%, unchanged |
| `gdpc1_synthetic.json` | GDPC1 | 3 | QoQ annualised: 4.060401%, prior 2.0150500625%, +2.0453509375pp |
| `rsafs_synthetic.json` | RSAFS | 3 | MoM: 0.5%, prior 1.0%, −0.5pp momentum |

Observation counts are the documented minimum history for each transformation,
so the fixtures also serve as the boundary case: removing one observation from
any of them must raise `InsufficientHistoryError`.

## A note on value types

Values here are JSON numbers. The real FRED API returns them as **strings**,
with `"."` for a missing observation. That conversion is the collector's job in
Phase 2. The calculation layer rejects strings deliberately, so that a malformed
payload fails at the collection boundary rather than silently propagating into a
published figure.
