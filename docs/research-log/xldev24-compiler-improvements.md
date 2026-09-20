# Experiments: XLDev24 compiler improvements

Date: 2026-09-19

## Scope

XLDev24 is a source-verified development set, not a final claim set. It contains
24 single-document questions outside XL100, balanced across six domains, using
11 PDFs with 1,059 pages total. Six questions are unanswerable and six of the
answerable questions require table, chart, or image evidence.

All runs used the pinned XL-DocBench release, the production BGE embedding model,
the MiniLM cross-encoder, and no answer-generation model.

## Baseline

Run `xldev24-baseline-cd019b6` established the three-system baseline:

| System | Budget | Page recall | Full coverage | Mean tokens | Redundancy |
| --- | ---: | ---: | ---: | ---: | ---: |
| compiler | 2,048 | 0.644 | 0.333 | 2,047 | 0.139 |
| fixed | 2,048 | 0.474 | 0.292 | 2,014 | 0.085 |
| structural | 2,048 | 0.502 | 0.250 | 2,028 | 0.063 |
| compiler | 16,384 | 0.830 | 0.458 | 13,327 | 0.255 |
| fixed | 16,384 | 0.836 | 0.625 | 16,168 | 0.240 |
| structural | 16,384 | 0.810 | 0.542 | 15,398 | 0.151 |

The compiler clearly led at 2K but underfilled the 16K budget and trailed fixed
chunks on high-budget coverage.

## Findings and experiments

1. Signed expansion penalties were incorrect for negative cross-encoder logits:
   multiplying by a factor below one made the score less negative and promoted
   the expanded neighbor. Commit `de8b675` fixes the ordering. On XLDev24 it was
   essentially quality-neutral, slightly reduced redundancy, and is retained as
   a correctness fix.
2. Doubling rerank and expansion capacity on the worst list-heavy question
   increased tokens from 7,991 to 13,269 but did not change 16K recall (0.545).
   Capacity alone was rejected.
3. Three-hop sibling/list expansion increased token use but did not change that
   question's recall. Structural graph adjacency alone was rejected.
4. Multi-scale page-neighbor windows reached 1.000 recall and full coverage on
   the list-heavy diagnostic. Allowing those windows to compete directly with
   core evidence improved aggregate recall but caused several regressions and a
   large latency increase, so direct competition was rejected.
5. The selected design uses page-scale windows only as 16K backfill when unique
   core candidates cannot fill the budget. Core evidence always ranks first.

## Selected result

Run `xldev24-multiscale-backfill-b6eb035` uses a three-page radius, 20 node
anchors, at most 64 page-window candidates, and a 16,384-token activation
threshold.

| Metric at 16K | Compiler baseline | Backfill | Delta |
| --- | ---: | ---: | ---: |
| Page recall | 0.830 | 0.856 | +0.025 |
| Full coverage | 0.458 | 0.500 | +0.042 |
| Mean context tokens | 13,327 | 16,251 | +2,924 |
| Redundancy | 0.255 | 0.298 | +0.043 |
| Mean latency | 3.47 s | 7.59 s | +4.12 s |

No question lost recall at 16K. Two answerable questions improved; one rose from
0.545 recall to 1.000 with full coverage. Context items at 2K, 4K, and 8K were
exactly identical to the signed-penalty baseline.

The selected compiler now exceeds the fixed baseline's 16K mean page recall
(0.856 versus 0.836), but fixed chunks still lead on full coverage (0.625 versus
0.500). The latency and redundancy costs are material. The next optimization
should cache page-window construction/reranking across budgets and investigate
query-faceted retrieval for the remaining dispersed-evidence failures.
