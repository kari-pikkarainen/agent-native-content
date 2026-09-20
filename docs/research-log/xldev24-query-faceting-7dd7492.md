# Experiment: XLDev24 deterministic query faceting

Date: 2026-09-20

## Decision

Enable deterministic lexical query faceting by default for compiler retrieval.
Split complex questions into at most three meaningful clauses, retrieve each
with the same BM25, dense, RRF, and cross-encoder stack, then combine the full
and facet rankings using weighted reciprocal-rank fusion. Keep the final
candidate capacity unchanged and give the full query twice the weight of each
facet.

No LLM, generated query, or model unavailable to the baselines is introduced.
The compiler's extra retrieval calls are treatment cost and remain included in
latency.

## Diagnostic

A failure-selected six-question diagnostic compared faceting off and on with
the same corpus and configuration. At 16K, mean recall rose from 0.677 to 0.748
and full coverage from 0.333 to 0.500. One 2K question regressed, so the feature
advanced to balanced XLDev24 validation rather than being selected directly.

## Balanced XLDev24 validation

Run `xldev24-facets-7dd7492` was compared with selected non-faceted run
`xldev24-multiscale-backfill-b6eb035`.

| Budget | Recall before | Recall faceted | Coverage before | Coverage faceted |
| ---: | ---: | ---: | ---: | ---: |
| 2,048 | 0.644 | 0.647 | 0.333 | 0.333 |
| 4,096 | 0.710 | 0.713 | 0.333 | 0.333 |
| 8,192 | 0.768 | 0.791 | 0.417 | 0.417 |
| 16,384 | 0.856 | 0.891 | 0.500 | 0.667 |

At 16K, seven answerable questions improved and none regressed. Full coverage
increased on four questions. The faceted compiler exceeds the fixed baseline at
16K on both mean page recall (0.891 versus 0.836) and full coverage (0.667
versus 0.625).

Mean compiler latency increased from approximately 3.6 seconds to 5.9–6.0
seconds at 2K–8K, and from 7.6 seconds to 10.1 seconds at 16K. Mean redundancy
was slightly lower at 4K and 8K and effectively unchanged at 16K. The quality
gain, especially the 0.167 absolute full-coverage improvement at 16K, justifies
the additional retrieval cost for the research configuration.

XLDev24 is a development set and no answer-generation model was used. The
selected configuration still requires held-out XL100 confirmation before a
broader technical claim.
