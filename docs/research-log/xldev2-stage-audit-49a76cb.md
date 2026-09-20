# Experiment: XLDev2 compiler stage audit at `49a76cb`

Status: diagnostic complete; no compiler policy selected.

## Question

Do the two XLDev24 table failures originate in node retrieval, faceted fusion,
structural expansion, deduplication, or final packing? Does the union of the
compiler and structural candidate pools contain evidence that neither pool
contains alone?

## Controlled run

The immutable run is
`artifacts/runs/xldev2-stage-audit-49a76cb`. It evaluates the two questions in
`benchmarks/xl-docbench/subsets/xldev2-tables.json` while indexing every document referenced
by `benchmarks/xl-docbench/subsets/xldev24.json`.

- Git commit: `49a76cb63a1d448d6d6456c6b7b7f50b6e5c64ad`
- Evaluated questions: 2
- Retrieval-corpus questions: 24
- Retrieval-corpus documents: 11
- Budgets: 2,048, 4,096, 8,192, and 16,384 tokens
- Models ran from the local offline cache.

The audit did not change selection. `contexts.jsonl` is byte-identical to the
fixed-corpus control at `artifacts/runs/xldev2-fixed-corpus-control-f258ade`,
and every retrieval metric other than latency is identical.

## Results

Candidate recall below is measured over the complete bounded pool returned at
the run's maximum retrieval budget. Packed recall is budget-specific.

| Question | Raw nodes | Faceted nodes | Structural | Faceted + structural | Expanded | Deduplicated | Packed at 2K / 4K / 8K / 16K |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `000324` | 0.909 | 0.909 | 0.909 | **1.000** | 0.909 | 0.909 | 0.273 / 0.182 / 0.364 / 0.545 |
| `000703` | 0.700 | 0.700 | 0.700 | 0.700 | 0.700 | 0.700 | 0.150 / 0.200 / 0.350 / 0.550 |

For `000324`, node retrieval finds every gold page except page 4 and structural
retrieval finds every gold page except page 19. Their union therefore reaches
all 11 gold pages. This is direct evidence that the two representations contain
complementary evidence, but the current compiler cannot consume that
complementarity because it only expands node candidates.

For `000703`, all retrieval variants find the same 14 of 20 gold pages. Pages
16 through 21 are absent even from the union. The query asks for a row-level
join between the multi-page Tables AII.10 and AII.5, so this failure starts
upstream of expansion and packing. Inspection of the authoritative Docling
artifact confirms that the target model occurs in separate page-level tables
on pages 18 and 29; those target-bearing table chunks are not present in the
bounded candidate pools.

Expansion and deduplication preserve candidate recall exactly for both
questions. They are not responsible for these failures. Packing is a second,
independent bottleneck: at 16K it retains only 6 of the 10 node-retrievable
pages for `000324` and 11 of the 14 retrievable pages for `000703`. The pools
contain roughly 33K-41K tokens before expansion and up to 72K tokens in the
compiler/structural union, so greedy score-order packing discards substantial
reachable evidence.

## Decision

Do not tune expansion or deduplication next. The next bounded experiment should
combine structural chunks with compiler node candidates, then use a
budget-aware selection policy that rewards coverage across explicit query
facets/table references instead of greedily filling by one global score.

The experiment must be evaluated first on this fixed-corpus two-question slice
and then on XLDev24. The holdout and remaining XL100 questions stay untouched.
