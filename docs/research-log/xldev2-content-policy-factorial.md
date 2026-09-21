# XLDev2 content-unit × selection-policy factorial

## Decision

The two-question diagnostic does **not** support an IR-specific retrieval
claim. Under matched selection policies, IR nodes trail the best chunk unit in
seven of eight budget/policy comparisons and lead once, by 4.5 percentage
points at 4K under faceted coverage.

The result instead supports testing the selection policy. Faceted retrieval
plus coverage-aware packing improves page recall in 10 of 12 matched
unit/budget cells, ties once, and loses once. The effect is strongest for fixed
chunks and IR nodes, but query latency rises from roughly 0.36–0.59 seconds to
0.96–1.07 seconds on average, depending on unit type.

This is a mechanism diagnostic on two deliberately table-heavy development
questions. It is too small to estimate a general effect.

## Design

- Questions: `xldev2-tables` (2)
- Retrieval corpus: the fixed 11-document `xldev24` corpus
- Content units: fixed 512/64 chunks, structural chunks, and IR nodes
- Policies: single-query ranked packing and deterministic lexical faceting
  with coverage-aware packing
- Budgets: 2K, 4K, 8K, and 16K tokens
- Shared components: BM25, dense retrieval, reciprocal-rank fusion,
  cross-encoder reranking, candidate limits, tokenizer, and document scope
- Excluded from both policies: structural expansion, table joins,
  page-neighbor backfill, heading injection, sibling/list expansion, and answer
  generation

The run produced 48 unique cells. Every context stayed within its registered
budget, and the manifest binds the result to commit `8c8e044`.

## Main contrasts

IR page-recall effect relative to the best chunk representation under the
same policy:

| Policy | 2K | 4K | 8K | 16K |
| --- | ---: | ---: | ---: | ---: |
| Ranked | -2.5 pp | -9.5 pp | -17.0 pp | -12.0 pp |
| Faceted coverage | -7.0 pp | +4.5 pp | -17.0 pp | -5.0 pp |

Faceted-coverage page-recall effect relative to ranked packing within each
content unit:

| Unit | 2K | 4K | 8K | 16K |
| --- | ---: | ---: | ---: | ---: |
| Fixed | +22.7 pp | +22.7 pp | +13.6 pp | +13.6 pp |
| Structural | -9.1 pp | -6.6 pp | +22.7 pp | +9.1 pp |
| IR | +9.1 pp | +18.2 pp | +22.7 pp | +16.1 pp |

Quote recall is too sparse for a stable comparison: only one question has a
recoverable literal quote, and structural chunks recover it in three cells.
This is useful negative evidence for relying on page recall alone.

## Interpretation and next action

The earlier compiler result is plausibly explained in substantial part by
query faceting and diversified packing rather than the persistent IR. We will
therefore avoid an IR-causal claim and proceed to the metric audit:

1. add answerable-only summaries;
2. add stricter provenance/content coverage;
3. add source-document-clustered paired uncertainty; and
4. inspect the largest low-budget wins and losses.

Canonical source-text-free records are published under
`results/factorial/xldev2-content-policy/`.
