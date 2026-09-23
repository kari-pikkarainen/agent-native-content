# Phase 1 tasks 6 and 8: the factorial and the expansion ladder

Date: 2026-09-22

Precommit: `6cc7fd9`

Canonical runs: `xldev24-factorial-6cc7fd9` and seven `xldev24-*-6cc7fd9`
retrieval runs, published under [`results/`](../../results/README.md) as
`xldev24-content-policy-corrected` and `xldev24-ablation-*`. All eight are
clean-worktree at the same commit, with both model revisions pinned.

## The expansion ladder

Benchmark specification section 25 requires four compiler ablations and asks
them to "identify why" rather than attributing improvements vaguely to the IR.
The CLI could not reach the fields they need, so they had never been run. The
settings are now fixed as data in `evaluation/ablations.py` and checked by a
test that drives each rung's own rendered command line.

Two configurations outside the spec series were added, and are labelled as
such rather than folded in as extra rungs. The spec ladder sets the
page-neighbour radius to zero on every rung, so it attributes nothing to page
neighbours, and the shipped configuration confounds them with keyed joins.

Compiler arm, answerable page recall and quoted exact-quote recall:

| Config | 2K page | 4K page | 8K page | 16K page | 2K quote | 4K quote | 8K quote | 16K quote |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| D1 no expansion | 0.6366 | **0.7481** | **0.8133** | 0.8451 | 0.1019 | 0.2037 | 0.2315 | 0.3009 |
| D2 headings | 0.6367 | 0.7137 | 0.7993 | 0.8451 | 0.0833 | 0.1759 | 0.2454 | 0.3009 |
| D3 + siblings | 0.6187 | 0.7357 | 0.8083 | 0.8350 | 0.0972 | 0.2176 | 0.2593 | 0.3148 |
| D4 + tables | 0.6187 | 0.7357 | 0.8083 | 0.8350 | 0.0972 | 0.2176 | 0.2593 | 0.3148 |
| D4 + neighbours | 0.6187 | 0.7357 | 0.8083 | 0.8451 | 0.0972 | 0.2176 | 0.2593 | 0.3148 |
| D4 + joins | 0.6242 | 0.7413 | 0.8138 | 0.8406 | **0.1528** | **0.2731** | **0.3148** | **0.3704** |
| shipped | **0.6367** | 0.7248 | 0.8111 | **0.8749** | 0.1389 | 0.2315 | 0.3009 | **0.3704** |

### What the ladder says

**Structural expansion does not buy page recall.** D1, with no expansion at
all, has the best page recall at 4K and 8K of any rung, and every rung above
it on the ladder is worse at those budgets. The compiler's page-recall
advantage over the baselines is therefore not produced by structural
expansion. The factorial below says where it does come from.

**Table preservation is not measurable here.** D3 and D4 are identical to four
decimals on both metrics at all four budgets. At packet level they differ in
**1 of 96** compiler packets, and that one difference moves no metric. On this
development set, table preservation earns nothing.

**Page neighbours are a 16K-only effect and a small one.** D4 and D4+neighbours
differ in **5 of 96** packets, all at 16K, which is what a minimum budget of
16,384 requires. The effect is +0.0101 page recall at 16K and nothing
anywhere else. They are also the dominant cost at that budget: the
[latency record](../../docs/plans/2026-09-21-improvement-plan.md) work measured
16K compile at 628 ms against 127 to 161 ms elsewhere.

**Keyed joins are the largest single contributor to exact quote recall, and
they are one question.** D4 to D4+joins is +0.0556, +0.0555, +0.0555, +0.0556
— flat across every budget, which is the signature of exactly one question
moving from 0.0 to 1.0 on an 18-question set. Packet comparison confirms it:
**4 of 96** packets differ, all on `adubench_single_000703`. The effect is
real and it is one question. The
[preregistration](prereg-adaptive-packing.md) fixed 0.0556 as the value of one
question before any of this was run, which is why it can be said plainly now.

**The shipped configuration is not the best rung.** D4+joins beats it on both
metrics at 4K and 8K, and on quote recall at 2K. The shipped config wins page
recall at 2K and 16K. The two differ in three ways at once — shipped has the
sibling switches off, keyed joins on and page neighbours on — so this is a
finding to investigate, not a configuration change to make on four budgets and
18 questions.

## The content-unit × policy factorial

Run over all 24 development questions with the corrected code. No structural
expansion, joins, page neighbours or answer model participate, so this
isolates the content unit and the selection policy from everything else.

**Representation effect.** IR nodes beat the better chunk unit on page recall
in **7 of 8** matched cells, by +0.018 to +0.185; the exception is 16K under
faceted coverage at −0.003. On exact quote recall IR leads in **2 of 8**, by
+0.014 and +0.010, and trails in the rest by up to 0.024.

The Gate 0 factorial recorded 8 of 8 on page and 3 of 8 on quote. The
corrected run is slightly weaker on both and points the same way. The finding
stands: the IR unit reliably lands on the right page and does not reliably
carry the exact quoted evidence.

**Policy effect, and the replication that matters.** Faceted coverage minus
ranked, on the IR unit:

| Budget | page | quote |
| ---: | ---: | ---: |
| 2K | **+0.056** | **−0.066** |
| 4K | **+0.083** | **−0.052** |
| 8K | **+0.069** | **−0.021** |
| 16K | +0.023 | +0.010 |

Coverage buys page recall and costs exact quote recall. That is the same trade
the [packing-policy comparison](adaptive-packing-decision-3b77e75.md) found
across `coverage`, `adaptive` and `ranked` on the compiler arm — and this is
an independent design reaching it: different mechanism, different code path,
different experiment, same direction at the same budgets.

It is not confined to the IR unit. At 2K the quote cost of coverage is −0.056
for fixed windows and −0.056 for structural chunks as well. The policy does
this to every content unit.

**Interaction.** The IR unit's page advantage is *larger* under faceted
coverage than under ranked at the low budgets where the project's claim lives:
+0.157 and +0.185 at 2K and 4K, against +0.124 and +0.090 under ranked. And
the quote cost of coverage is largest for IR (−0.066 at 2K) of the three
units.

So the representation and the policy are not separable in the way the headline
suggests. **Part of what has been reported as an IR advantage is a policy
advantage that the IR unit amplifies — and the policy delivering it is the one
that costs exact evidence.**

## Decision

No configuration change is made on this evidence. The findings are recorded
and three of them should shape what follows:

1. Structural expansion is not what produces the page-recall advantage, so
   Phase 1's remaining effort should not go there.
2. Keyed joins are the one expansion operator with a visible quote-recall
   effect, and it rests on one question. Whether that generalises is a
   question for a larger population, not for `xldev24`.
3. The IR-versus-policy interaction means the benchmark's headline claim needs
   restating in Phase 2: the compiler's measured advantage is a
   page-selection advantage produced substantially by coverage packing, and
   coverage packing measurably costs exact evidence.

## Known weaknesses

- 24 questions, 18 eligible per metric, 9 source clusters. Several ladder
  effects here are one or four packets out of 96, and are reported as such.
- The spec ladder cannot attribute page neighbours; two configurations outside
  the series were needed, and the shipped configuration differs from D4 in
  three ways at once, so no single rung isolates it.
- `xlholdout6c` was not consulted and stays frozen.
- No answer-quality result exists. Everything here is evidence selection.
