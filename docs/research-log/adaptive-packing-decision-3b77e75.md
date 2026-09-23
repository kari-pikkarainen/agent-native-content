# Decision: budget-adaptive packing is rejected

Date: 2026-09-22

Precommit: `3b77e75`

Canonical runs: `xldev24-adaptive-3b77e75`, `xldev24-ranked-3b77e75`, compared
against `xldev24-rekey-9db9c5d`, which is the incumbent `coverage` policy at
the same code state and is packet-for-packet identical to the published
[`xldev24-phase1-fixes`](../../results/README.md).

Judged against
[the preregistered rule](prereg-adaptive-packing.md) and its addendum, both
committed before any run of this strategy existed.

## Verdict

**`adaptive` is rejected. The default stays `coverage`.**

| Criterion | Result |
| --- | --- |
| **A1** page recall does not regress against the incumbent | **FAIL** |
| **A2** −3 pp non-inferiority against both baselines | **FAIL** |
| **A3** quote recall does not regress against the incumbent | PASS |
| **A4** the 2K quote deficit against structural does not survive | PASS |

A1 fails at **every** budget: adaptive's answerable page recall is below
coverage by 0.0162, 0.0106, 0.0212 and 0.0179 at 2K, 4K, 8K and 16K. The rule
required at least 0.0000 at every budget.

A2 fails at 8K against structural chunks, where the paired lower bound is
−0.0412 against a margin of −0.030.

Two criteria pass and they are the interesting ones, so they are recorded
rather than skipped. A3 passes: quote recall is +0.0370 at 2K, unchanged at 4K
and 16K, and −0.0139 at 8K, inside the −0.0185 resolution floor. A4 passes,
and the addendum requires saying which disjunct carried it: **the point
estimate improved**, from −0.0602 to −0.0231, so this is not a
variance-widening pass. The interval also widened, but it did not have to.

Adoption needs all four. Two failed.

## What the rejection is not

The pre-stated rejection anticipated adaptive buying page recall while leaving
the quote deficit intact. **The opposite happened.** Adaptive gave up page
recall and reduced the quote deficit. The rule rejects it either way, but the
reason recorded here should be the one that occurred.

## The finding that matters more than the verdict

The three policies differ in one thing: how hard they buy page breadth.
`coverage` maximises it, `adaptive` buys it until it stops paying, `ranked`
does not buy it at all. Ordered that way, the compiler arm behaves like this:

| Budget | | coverage | adaptive | ranked |
| ---: | --- | ---: | ---: | ---: |
| 2K | page | **0.6367** | 0.6205 | 0.5302 |
| | quote | 0.1389 | 0.1759 | **0.2130** |
| 4K | page | **0.7248** | 0.7142 | 0.6066 |
| | quote | 0.2315 | 0.2315 | **0.2454** |
| 8K | page | **0.8111** | 0.7898 | 0.7158 |
| | quote | 0.3009 | 0.2870 | **0.3148** |
| 16K | page | **0.8749** | 0.8570 | 0.8329 |
| | quote | 0.3704 | 0.3704 | 0.3704 |

Page recall is monotone decreasing in less coverage at **4 of 4** budgets.
Quote recall is monotone increasing at **3 of 4** — 8K is the exception, where
adaptive sits below both. Mean redundancy at 2K runs 0.0892, 0.0999, 0.1436 in
the same order, which is the breadth these policies are buying, measured
directly.

Against the structural baseline, 2K exact quote recall:

| Policy | delta | interval |
| --- | ---: | --- |
| coverage | −0.0602 | [−0.1250, −0.0114] **excludes zero** |
| adaptive | −0.0231 | [−0.0972, +0.0444] includes zero |
| ranked | **+0.0139** | [−0.0357, +0.0882] includes zero |

**The coverage policy is the source of the 2K quote deficit.** Turning
coverage off removes the deficit entirely and turns it slightly positive. This
is not a one-question artefact: it is a monotone response across three
policies on two metrics in opposite directions, with a measured mechanism
behind it.

The compiler's headline advantage on this benchmark and its exact-evidence
weakness have the **same cause**. Coverage packing selects diverse nodes to
touch more gold pages, and a diverse node is less likely to be the node
carrying the exact quoted span. Page recall rewards that trade and quote
recall punishes it, which is why the project has been reading two different
stories off one policy.

## Next action, as pre-stated

The preregistration says that a rejection here is followed by inspecting
node-boundary failures rather than adding more retrieval machinery. That
applies, and it is now better targeted than when it was written: the thing to
inspect is not the compiler in general but the coverage policy's node
selection, on the questions where it lands on the right page and packs a
sibling without the quote. `adubench_single_000266` is the worked example
already on file in
[the heading ablation](compiler-heading-free-edd196f.md).

`adaptive` stays in the codebase as a non-default strategy with its tests, as
the preregistration specified. Rejection means it is not promoted, not that it
is deleted.

## Known weaknesses

- 24 development questions, 18 eligible per metric, 9 source clusters. The
  monotone pattern is across three policies rather than across questions,
  which is what makes it more than a one-question effect — but the individual
  deltas remain small and several are inside the 0.0185 resolution floor.
- `ranked` is not a candidate for promotion on this evidence. Its page recall
  is far worse, its A2 lower bound is −0.1009, and the project's stated claim
  is a low-budget selection advantage that `ranked` does not deliver.
- No holdout was consulted. `xlholdout6c` stays frozen.
- The no-facets branch of `adaptive` never executed: all 24 development
  questions yield facets, so that design choice is untested here.
