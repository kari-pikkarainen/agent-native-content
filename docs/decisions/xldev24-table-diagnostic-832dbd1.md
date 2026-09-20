# XLDev24 table-structure diagnostic

Date: 2026-09-20

## Decision

Reject unconditional large-table fragmentation and explicit table-continuation
expansion. Restore the compiler implementation and defaults selected in
`5833467`.

Neither experiment provides valid evidence of a general improvement. The full
XLDev24 confirmation for table continuation produced zero context or evidence
metric changes at every budget.

## Failure diagnosis

The two XLDev24 questions where the selected compiler trails the best baseline
at 16K are both scientific cross-table reconciliation tasks:

- `adubench_single_000324`: compiler recall 0.545 versus 0.727 structural.
- `adubench_single_000703`: compiler recall 0.550 versus 0.700 structural.

The compiler often packs complete 1K-2K token table nodes while structural
retrieval uses smaller table regions. This suggested that table granularity or
continuation structure might explain the gap.

## Rejected experiments

Run `xldev2-table-fragments-bbb1e59` fragmented every table larger than the
configured 512-token table chunk size. On the failure-selected two-question
diagnostic, 16K recall rose by 0.182 on question 000324 but fell by 0.300 on
question 000703. Redundancy also rose sharply. The change was rejected.

Run `xldev2-table-capacity-04a5c8d` corrected the expansion-capacity estimate
to count independently packable fragments. It produced the same diagnostic
contexts and metrics, so it did not address the fragment flooding failure and
was also rejected.

Runs `xldev2-table-neighbors-03e917c` and
`xldev2-table-neighbors-clean-832dbd1` tried deterministic continuation of
explicitly named tables across adjacent pages with matching schemas. The small
diagnostic appeared mixed, but that comparison was not valid because its index
contained only two documents.

The full-corpus run `xldev24-table-neighbors-832dbd1` used the same 11-document
XLDev24 retrieval corpus as selected run `xldev24-facets-7dd7492`. All compiler
contexts, token counts, recalls, coverage values, and redundancies were exactly
identical at all four budgets. The continuation candidates never changed final
packing, so the feature was rejected.

## Methodological finding

The benchmark currently builds each retrieval index from only the documents
referenced by the evaluation subset. BM25 inverse-document-frequency values
therefore change when a failure-selected question subset uses fewer documents.
Comparing a two-question diagnostic run directly with a 24-question run can
attribute corpus-composition effects to a compiler change.

Future fast diagnostics must keep the retrieval corpus fixed while narrowing
only the evaluated questions. Commit `f258ade` adds that separation through
`--retrieval-corpus-subset-file` and records both subsets in the run manifest.
Acceptance run `xldev2-fixed-corpus-control-f258ade` evaluates the two
diagnostic questions against all 11 XLDev24 documents. Its eight compiler
contexts and evidence records match the corresponding full XLDev24 cells
exactly, excluding measured latency.

No XLHoldout6 or additional XL100 result was inspected during these experiments.
