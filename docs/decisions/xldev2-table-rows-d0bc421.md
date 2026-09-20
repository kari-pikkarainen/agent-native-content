# XLDev2 provenance-preserving table-row retrieval at `d0bc421`

Status: rejected and reverted by `1248799`.

## Question

Can source-derived table rows provide a better evidence unit than whole-table
nodes for cross-table questions, while preserving authoritative source-node and
source-item provenance?

## Controlled runs

Every run evaluates `configs/subsets/xldev2-tables.json` against the fixed
`configs/subsets/xldev24.json` retrieval corpus: two failure-selected table
questions, 11 corpus documents, and the same 2K, 4K, 8K, and 16K budgets.

- Single rows with repeated headers:
  `artifacts/runs/xldev2-table-rows-157d76c`
- Search-only compact header aliases:
  `artifacts/runs/xldev2-table-rows-alias-dbf6072`
- Two-row groups:
  `artifacts/runs/xldev2-table-row-pairs-5f3583e`
- Source table labels propagated across continuation fragments:
  `artifacts/runs/xldev2-table-labels-cc4fbfb`
- Exact table-reference query facets:
  `artifacts/runs/xldev2-table-reference-facets-85112ee`
- Table-reference facets with their local query constraints:
  `artifacts/runs/xldev2-table-context-facets-d0bc421`
- Whole-node control and stage audit:
  `artifacts/runs/xldev2-stage-audit-49a76cb`

No holdout or remaining XL100 question was inspected.

## Aggregate results

Mean evidence-page recall across the two questions:

| Treatment | 2K | 4K | 8K | 16K |
| --- | ---: | ---: | ---: | ---: |
| Fixed baseline | 0.145 | 0.145 | 0.473 | 0.614 |
| Structural baseline | 0.261 | 0.332 | **0.552** | **0.714** |
| Whole-node compiler control | 0.211 | 0.191 | 0.357 | 0.548 |
| Single rows | **0.336** | **0.361** | 0.411 | 0.548 |
| Compact header aliases | **0.336** | 0.316 | 0.411 | 0.689 |
| Two-row groups | 0.291 | 0.336 | 0.411 | 0.639 |
| Continuation labels | 0.266 | 0.341 | 0.411 | 0.548 |
| Exact reference facets | **0.336** | 0.341 | 0.457 | 0.502 |
| Contextual reference facets | 0.266 | **0.361** | 0.411 | 0.502 |

Rows improve some low-budget cells, but no variant beats the structural
baseline across the curve. The strongest 16K row result remains 0.025 below
structural recall, and the reference-faceted variants fall 0.212 below it.

The row variants also repeat wide schemas for every candidate. Mean redundancy
in the final two faceting runs is 0.650/0.666/0.664/0.637 and
0.654/0.683/0.672/0.636. Structural redundancy is only
0.112/0.145/0.200/0.240. Compiler latency rises to roughly 6.5-9.0 seconds,
versus 1.3-1.5 seconds for the baselines.

## Decisive row-level finding

Question `adubench_single_000703` asks which dataset listed in Table AII.10 has
a blank `MainReferences` entry in Table AII.5. The answer is
`IPSL-CM5A2-INCA`.

The Table AII.10 dataset row enters every packed context in the final two
runs. The corresponding Table AII.5 row, rendered explicitly with
`Main References: [blank]`, enters none of the four budgets. Exact reference
faceting raises candidate-page recall from 0.55 to 0.60, but does not promote
the decisive row. Adding the local constraint (`blank MainReferences ... Table
AII.5`) produces the same 0.60 candidate ceiling and still does not pack the
row. At 16K, expansion can reach full page coverage, but packing falls back to
0.55 recall.

This is not a missing-header, missing-empty-cell, or continuation-provenance
problem. It is a relational ranking problem: hundreds of independently ranked
rows cannot infer that a model identifier retrieved from one table should be
used to select a row in another table. Repeating headers and labels increases
the shared lexical signal and therefore the crowding.

## Decision

Reject row-level retrieval, row grouping, search aliases, continuation-label
propagation, and table-reference faceting as implemented. Commit `1248799`
restores the selected compiler while retaining the experimental commits and
immutable run artifacts for reproduction.

Do not run the full XLDev24 set for these policies. The bounded diagnostic has
already failed the mechanism-level acceptance criteria.

The next distinct hypothesis is deterministic keyed row joining: retrieve
rows from explicitly referenced tables, discover exact shared cell values such
as model identifiers, and score/pack a compact joined evidence unit while
retaining both rows' provenance. This would directly test the missing
cross-table operation instead of adding more independent row candidates.
