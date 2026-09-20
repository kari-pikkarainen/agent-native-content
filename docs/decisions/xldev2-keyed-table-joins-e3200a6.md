# XLDev2 keyed cross-table joins at `e3200a6`

Status: directionally successful; retained default-off for broader confirmation.

## Question

Can a deterministic compiler solve an explicitly referenced cross-table
reconciliation by joining rows on a shared identifier, instead of asking the
retriever and packer to rank the two rows independently?

## Treatment

The experiment activates `--compiler-keyed-table-joins`. It:

1. extracts explicit table references from the query;
2. maps those labels onto authoritative table nodes and same-schema
   continuation fragments;
3. extracts identifier-like values only from model/dataset identifier columns;
4. joins rows only on exact normalized identifiers;
5. applies explicit empty-cell constraints to the query-named column;
6. projects only the join key and query-relevant columns;
7. retains both source table nodes and all authoritative source item IDs; and
8. keeps one reranked candidate per normalized entity key.

No LLM, fuzzy entity matcher, generated annotation, or benchmark-specific
answer string is used. Non-contiguous joined sources keep null range metadata
instead of claiming an artificial continuous page span; exact pages remain
recoverable from both source node IDs.

## Controlled runs

Both runs evaluate `configs/subsets/xldev2-tables.json` against the fixed
11-document `configs/subsets/xldev24.json` retrieval corpus.

- Initial join, retaining multiple dataset rows for one key:
  `artifacts/runs/xldev2-keyed-table-joins-7d44762`
- One joined candidate per entity key:
  `artifacts/runs/xldev2-keyed-table-joins-e3200a6`
- Active-compiler control and stage audit:
  `artifacts/runs/xldev2-stage-audit-49a76cb`

No holdout or remaining XL100 question was inspected.

## Mechanism result

For `adubench_single_000703`, the compiler emits this 93-token joined evidence
at every budget:

```text
Joined table key: ipsl-cm5a2-inca
Table AII.10
Institute: Model: IPSL:IPSL-CM5A2-INCA | Dataset citation and DOI: ...
Table AII.5
Models: IPSL-CM5A2-INCA | Main References: [blank]
```

The item cites Docling tables `#/tables/27` and `#/tables/14`. The previous
whole-node, row-retrieval, and query-faceting experiments never packed the
Table AII.5 blank row at any budget.

Question-level page recall improves consistently:

| Question `000703` | 2K | 4K | 8K | 16K |
| --- | ---: | ---: | ---: | ---: |
| Active compiler control | 0.150 | 0.200 | 0.350 | 0.550 |
| Keyed joins | **0.250** | **0.300** | **0.450** | **0.650** |

Question `000324` names only one table, so the join path does not activate and
its recall is unchanged: 0.273/0.182/0.364/0.545. Consequently, mean recall
across the diagnostic improves by exactly 0.050 at all four budgets:

| Treatment | 2K | 4K | 8K | 16K |
| --- | ---: | ---: | ---: | ---: |
| Active compiler control | 0.211 | 0.191 | 0.357 | 0.548 |
| Keyed joins | **0.261** | **0.241** | **0.407** | **0.598** |

Collapsing same-key joins does not change recall. It reduces mean redundancy
from 0.101/0.175/0.243/0.282 in the initial run to
0.084/0.158/0.226/0.279. This remains slightly above the active compiler
control at most budgets, but is far below the approximately 0.64-0.68 reached
by independent table-row retrieval.

## Metric limitation

The question's gold record provides two quoted supporting rows, but its
`evidence_pages` field contains all 20 pages spanned by Tables AII.5 and
AII.10. A compiler that isolates the exact two-row relation is therefore
penalized for omitting irrelevant pages. Keyed joins still trail structural
RAG's broad page recall (0.261/0.332/0.552/0.714 mean across the diagnostic),
even though structural retrieval does not expose the decisive joined relation
at low budgets.

This does not invalidate the page metric, but it means page recall alone cannot
establish whether relational compression improves answer accuracy.

## Decision

Keep keyed joins behind the default-off experiment flag. The mechanism clears
the bounded diagnostic gate: it retrieves the previously missing decisive
evidence, improves its eligible question at every budget, improves the subset
mean at every budget, preserves exact provenance, and avoids row-level
candidate flooding.

Do not promote it as the selected compiler yet. The next milestone is an
XLDev24 confirmation run with the fixed 11-document corpus, followed by
answer-generation evaluation with identical answer models and prompts if the
retrieval behavior remains stable. The full run should also report how many
questions activate the join path; a gain on this single failure-selected
question is not a general benchmark claim.
