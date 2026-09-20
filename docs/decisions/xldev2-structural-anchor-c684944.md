# XLDev2 structural-anchor compilation at `c684944`

Status: rejected and reverted by `9a4ac1f` and `f5992d5`.

## Question

Can the compiler use structural retrieval only to select source regions, map
those regions back to canonical IR nodes, and then outperform structural RAG
through deterministic expansion, deduplication, and packing without placing
both representations in the context?

## Controlled runs

Both runs evaluate `configs/subsets/xldev2-tables.json` against the fixed
`configs/subsets/xldev24.json` retrieval corpus.

- Depth-first bounded node projection:
  `artifacts/runs/xldev2-structural-anchor-9c137f4`
- Breadth-preserving bounded node projection:
  `artifacts/runs/xldev2-anchor-breadth-c684944`
- Control stage audit:
  `artifacts/runs/xldev2-stage-audit-49a76cb`

No holdout or remaining XL100 question was inspected.

## Projection diagnosis

The first implementation projected every source node from the highest-ranked
structural region before moving to the next region. Question `000324` reached
the 250-node bound early, reducing candidate recall from the structural pool's
0.909 to 0.364. Question `000703` produced only 153 unique nodes and preserved
its 0.700 ceiling.

The corrected implementation takes one node from every ranked structural
region before taking a second node from any region. This restores candidate
recall exactly:

| Question | Structural pool | Anchored IR nodes | After expansion | After deduplication |
| --- | ---: | ---: | ---: | ---: |
| `000324` | 0.909 | 0.909 | 0.909 | 0.909 |
| `000703` | 0.700 | 0.700 | 0.700 | 0.700 |

The refined projection therefore provides a fair test of downstream
compilation rather than an artifact of the candidate bound.

## Packed results

| Question | System | 2K | 4K | 8K | 16K |
| --- | --- | ---: | ---: | ---: | ---: |
| `000324` | Structural RAG | 0.273 | **0.364** | **0.455** | **0.727** |
| `000324` | Structural anchor | 0.273 | 0.273 | 0.273 | 0.455 |
| `000703` | Structural RAG | **0.250** | **0.300** | **0.650** | **0.700** |
| `000703` | Structural anchor | 0.200 | 0.200 | 0.250 | 0.500 |

The two-question anchor means are 0.236, 0.236, 0.261, and 0.477. Structural
RAG reaches 0.261, 0.332, 0.552, and 0.714. The anchor compiler is worse at
every budget. Its latency is reasonably close to structural retrieval, so
latency is not the rejection reason.

## Interpretation

Mapping a coherent structural chunk into individually packed IR nodes preserves
the available pages but destroys the chunk's useful within-region grouping and
ranking. Expansion and deduplication do not recover that lost packing quality.
This is not evidence that adding more structural candidates would help: the
earlier fusion experiment already showed that overlapping representations
increase redundancy and consume budget.

## Decision

Reject structural-anchor compilation. The active compiler is restored to the
selected node-retrieval implementation; the audit machinery remains.

Do not pursue another node/structural ordering heuristic on these questions.
The remaining distinct structural opportunity is finer table representation:
source-derived, provenance-preserving table-row or row-group candidates with
repeated headers and explicit empty-cell rendering. That would test whether the
compiler can exploit table structure unavailable to ordinary structural chunks
rather than rearranging the same evidence units again.
