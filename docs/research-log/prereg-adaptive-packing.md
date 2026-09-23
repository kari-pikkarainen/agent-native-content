# Preregistration: budget-adaptive packing

Date: 2026-09-22

Written at `124ecca`, **before** the strategy is implemented and before any
run of it exists. Nothing in this file may be revised after a result is seen.
If it turns out to be the wrong rule, the correct response is to record that
the rule was wrong and why, not to edit it.

Covers Phase 1 task 4 of the [improvement plan](../plans/2026-09-21-improvement-plan.md)
and the non-inferiority report in task 5.

## What is being tested

A third packing strategy, `adaptive`, alongside `coverage` (the shipped
default) and `ranked` (an ablation control). It coverage-packs until the query
facets are covered or no candidate adds a new page, then backfills the
remaining budget in plain reranked order from the same candidate pool.

`coverage` and `ranked` remain as controls and are not removed.

## Decision metrics

Three, jointly. No one of them selects the configuration.

1. `answerable_mean_evidence_page_recall`
2. `answerable_mean_content_verified_page_recall`
3. `quoted_mean_evidence_quote_recall`

Each is reported at 2K, 4K, 8K and 16K, for the compiler arm, against **both**
the fixed and the structural RAG baselines, with paired source-cluster
bootstrap intervals at 10,000 resamples.

Page and content-verified recall have moved in near-lockstep on every `xldev24`
run so far, so they are in practice close to one metric. Quote recall is the
one that discriminates, and it is the one this rule is built around.

## The instrument's granularity, stated before use

18 questions are eligible on each metric, over 9 source clusters. On quote
recall, one question moving from 0.0 to 1.0 is worth **0.0556**. The finest
movement observed on any run to date is **0.0185**, one gold quote of three on
a single question.

Any threshold finer than 0.0185 would be below the resolution of the
instrument. Any claim resting on a delta smaller than 0.0556 is a claim about
at most one question. Both facts are recorded here so that neither can be
discovered conveniently later.

## The incumbent

`coverage` at `9110e70`, published as
[`xldev24-phase1-fixes`](../../results/README.md), compiler arm:

| Budget | page | content-verified | quote |
| ---: | ---: | ---: | ---: |
| 2K | 0.6367 | 0.6311 | 0.1389 |
| 4K | 0.7248 | 0.7192 | 0.2315 |
| 8K | 0.8111 | 0.8055 | 0.3009 |
| 16K | 0.8749 | 0.8694 | 0.3704 |

And the fact the rule exists to confront: compiler minus structural on quote
recall at 2K is **−0.0602 [−0.1250, −0.0114]**, an interval excluding zero.
The compiler is measurably behind a RAG baseline on exact evidence at the
budget it is supposed to own. That deficit is about one question wide.

## Acceptance rule

`adaptive` is adopted as the Phase 1 configuration only if **all four** hold.

**A1 — page recall does not regress against the incumbent.** At every budget,
the point estimate of `adaptive` minus `coverage` on answerable page recall is
at least 0.0000.

**A2 — the preregistered non-inferiority margin holds against both baselines.**
At every budget, for both fixed and structural, the lower bound of the paired
95% interval on compiler-minus-baseline answerable page recall is at least
**−0.03**. This is the margin the plan already fixed and it is not changed
here.

**A3 — quote recall does not regress against the incumbent.** At 2K and 4K,
the point estimate of `adaptive` minus `coverage` on quote recall is at least
0.0000. At 8K and 16K it is at least **−0.0185**, one quote on one question,
which is the resolution floor stated above.

**A4 — the 2K quote deficit against structural chunks does not survive
unchanged.** Either the point estimate of compiler minus structural on quote
recall at 2K improves on −0.0602, or its interval ceases to exclude zero.

## Pre-stated rejection

If `adaptive` improves page recall while **A4 fails** — that is, the 2K quote
deficit against structural persists at full strength — it is **rejected**, and
the next action is to inspect node-boundary failures rather than to add more
retrieval machinery. Selecting a policy that buys pages while leaving exact
evidence behind is the specific failure this project exists to avoid, and it
would be the third time page recall flattered a change in this phase.

A rejected `adaptive` still ships as a non-default strategy with its tests, so
the ablation remains available. Rejection means it does not become the
default, not that the code is discarded.

## Evidence status

`xldev24` is **development evidence and selects the configuration**. It does
not confirm anything. `xlholdout6c` stays frozen and is not consulted, not
inspected, and not run until the Phase 1 configuration is frozen, after which
it is run exactly once.

If `adaptive` is adopted, the holdout result is a test of it, not an
opportunity to reconsider it.

## What would make this rule wrong

Recorded now, so it is not reconstructed later:

- 18 questions cannot separate a one-question effect from noise, and A3 and A4
  both operate at roughly that scale. A pass on either may be luck.
- A1 and A3 compare against an incumbent measured on the same 24 questions the
  policy will be tuned on. Nothing here corrects for that.
- The −3 pp margin in A2 was fixed before any of Phase 1's findings and has
  not been rejustified against them.
