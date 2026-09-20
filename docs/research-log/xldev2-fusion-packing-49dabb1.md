# Experiment: XLDev2 structural fusion and facet packing at `49dabb1`

Status: rejected and reverted by `5e6280e`.

## Question

Can explicit document-reference facets, balanced structural/node candidate
fusion, and query-facet-aware packing turn the complementary candidate recall
observed in the stage audit into better packed evidence recall?

## Controlled runs

Both immutable runs evaluate `benchmarks/xl-docbench/subsets/xldev2-tables.json` while using
`benchmarks/xl-docbench/subsets/xldev24.json` as the fixed retrieval corpus.

- Combined reference facets, structural fusion, and facet packing:
  `artifacts/runs/xldev2-fusion-facet-49dabb1`
- Structural fusion only:
  `artifacts/runs/xldev2-structural-fusion-49dabb1`
- Control:
  `artifacts/runs/xldev2-stage-audit-49a76cb`

All runs use the same 2,048, 4,096, 8,192, and 16,384 token budgets and the
same 11-document XLDev24 retrieval corpus. No holdout or remaining XL100
question was inspected.

## Aggregate compiler results

| Treatment | 2K recall | 4K recall | 8K recall | 16K recall |
| --- | ---: | ---: | ---: | ---: |
| Control | **0.211** | 0.191 | 0.357 | **0.548** |
| Structural fusion only | 0.191 | **0.236** | 0.286 | 0.477 |
| Combined treatment | 0.145 | **0.236** | **0.377** | 0.502 |

Neither treatment improves the recall curve consistently. Relative to the
control, fusion-only loses 0.020, gains 0.045, loses 0.071, and loses 0.071
recall across the four budgets. The combined treatment loses 0.066, gains
0.045, gains 0.020, and loses 0.046.

Fusion-only mean redundancy rises from 0.058/0.099/0.197/0.256 in the control
to 0.102/0.217/0.257/0.320. Mean compiler latency rises from approximately
5.0-6.2 seconds to 9.0-10.2 seconds. The combined treatment reaches up to
0.356 redundancy and 12.3-13.4 seconds latency.

## Stage findings

For question `000324`, structural fusion works at the candidate boundary:
recall rises from 0.909 after node expansion to 1.000 after fusion and remains
1.000 after deduplication. Packing nevertheless retains only 0.182, 0.273,
0.273, and 0.455 recall. The added representation therefore increases the
candidate ceiling but worsens ordering and consumes budget with overlapping
evidence.

For question `000703`, raw nodes, reference-faceted nodes, structural
candidates, their union, expansion, fusion, and deduplication all remain at
0.700 recall. Explicit `Table AII.10` and `Table AII.5` facets do not retrieve
the six missing pages. The treatment cannot repair this upstream miss.

Facet-reserved packing produces only small, inconsistent changes relative to
fusion alone. It cannot compensate for the larger, redundant candidate stream.

## Decision

Reject all three policies as implemented. Commit `5e6280e` removes them from
the active compiler while retaining the experimental commit and immutable run
artifacts for reproduction.

Do not retry candidate concatenation or rank interleaving. A more promising
next experiment is structural-anchor compilation: use the stronger structural
ranking to choose source regions, map those chunks back to their IR nodes, and
then apply compiler expansion/deduplication/packing once. This avoids feeding
both overlapping representations into the token budget and tests whether IR
processing adds value downstream of the stronger baseline retriever.
