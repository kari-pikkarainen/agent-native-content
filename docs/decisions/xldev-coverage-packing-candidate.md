# Coverage-aware packing development candidate

Date: 2026-09-20

Status: retain as an explicit candidate; do not promote or run a new holdout
until complete balanced XLDev24 confirmation.

## Treatment

The treatment changes only final compiler packing. It rewards marginal query
terms, lexical query facets, explicit table references, pages, and headings,
while retaining origin rank as a relevance prior. Retrieval, reranking,
expansion, deduplication, corpus composition, models, and budgets are fixed.
No answer-generation model was used.

## Two-question table diagnostic

Run `xldev2-coverage-packing-0386cad` uses the committed two-question table
slice and the fixed 11-document XLDev24 retrieval corpus.

| Budget | Ranked recall | Coverage recall | Delta |
| ---: | ---: | ---: | ---: |
| 2K | 0.261 | 0.216 | -0.045 |
| 4K | 0.241 | 0.311 | +0.070 |
| 8K | 0.407 | 0.589 | +0.182 |
| 16K | 0.598 | 0.805 | +0.207 |

The high-budget gain is large, but the 2K regression prevents selection from
this failure-focused slice alone.

## Six-question cross-domain gate

Run `xldev6-coverage-packing-0386cad` uses the committed six-question
cross-domain development slice and the same 11-document corpus.

| Budget | Ranked recall | Coverage recall | Delta | Coverage vs best baseline |
| ---: | ---: | ---: | ---: | ---: |
| 2K | 0.606 | 0.678 | +0.072 | +0.386 |
| 4K | 0.686 | 0.804 | +0.118 | +0.214 |
| 8K | 0.774 | 0.850 | +0.076 | +0.159 |
| 16K | 0.883 | 0.900 | +0.017 | +0.133 |

Full coverage improves from 0.333 to 0.500 at 8K and is unchanged or better
at every other budget. Mean redundancy falls from 0.133/0.188/0.212/0.278 to
0.058/0.125/0.180/0.264.

## Decision

Coverage packing passes the bounded directional gate and remains available as
an explicit configuration. It does not yet authorize a new holdout: the next
quality step is a complete XLDev24 comparison, which is intentionally deferred
while development remains subset-first. Only a consistent balanced-set win
should promote the default and trigger selection of a new untouched holdout.
