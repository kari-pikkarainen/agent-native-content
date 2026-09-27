# Research Log

This directory preserves the chronological development record: diagnostics,
ablations, rejected defaults, performance investigations, and decisions made
while tuning on development data.

These notes are not equally strong evidence. Their filenames identify the
subset and, where applicable, the relevant Git commit. The compact result set
supporting current public claims lives in [`results/`](../../results/README.md).

Do not treat a failure-selected diagnostic, smoke test, or development result
as an independent validation result.

## Start here

The current results rest on this chain of records, in order. Each names the
commit it was measured at.

1. [Gate 0 re-baseline](gate0-rebaseline-67aef47.md) — the measurement repaired
   and the low-budget advantage confirmed on development data.
2. [`xlholdout6c` freeze](xlholdout6c-freeze.md) — the Gate 1 holdout selected
   and frozen before any Phase 1 change.
3. [Heading-free compiler search](compiler-heading-free-edd196f.md) — rejected
   under a joint-metric rule.
4. [Phase 1 correctness fixes](phase1-correctness-fixes-9110e70.md) — three
   defects, including IR reading order, measured per arm.
5. [Adaptive packing: preregistration](prereg-adaptive-packing.md) and
   [decision](adaptive-packing-decision-3b77e75.md) — rejected, and the
   page-versus-quote trade traced to coverage packing.
6. [Factorial and expansion ladder](phase1-ablations-6cc7fd9.md) — what the
   page advantage does and does not come from.
7. [Phase 1 close-out](phase1-closeout-c7e56fa.md) — the quote-metric audit,
   the frozen configuration and every Gate 1 pin.
8. [Gate 1](gate1-xlholdout6c-60e5836.md) — the one holdout run: a pass on page
   recall, with exact quote recall pointing the other way.
9. [Generation preregistration](prereg-xlholdout6c-generation.md) and
   [Gate 2, stage 1](gate2-stage1-xlholdout6c-generation.md) — the answers
   were no better than fixed RAG's, and the two-stage gate stopped at stage 1.
10. [Gate 2 failure analysis](gate2-failure-analysis.md) — the run measured
    abstention rather than evidence; four instrument defects, and the
    fragmentation mechanism that survives.
11. [Rendered-evidence budget and node merging](stepc-rendered-budget-merge-f916545.md)
    — every arm charged for what it renders; merging helps at 8K/16K on
    development data, not on the fresh smoke set, and is not frozen.
12. [Representation preregistration](prereg-xldev24-representation-gemma.md)
    and [result](representation-xldev24-gemma-b3d53c0.md) — the same gold pages
    as text or as Content IR: no benefit from structure for a local 12B model,
    at about twice the tokens.
12. [Parallel parsing performance](parallel-parsing-performance-46c2a61.md) —
    a six-document operational benchmark; two workers reduced end-to-end wall
    time by 22%, while four were slower and used more memory.

Everything else in this directory is earlier development history. Several of
those records describe configurations, metrics or holdouts that the chain
above supersedes; read them as history, not as current claims.
