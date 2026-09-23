# Gate 1: xlholdout6c, run once

Date: 2026-09-23

Run: `xlholdout6c-gate1-60e5836`, published under
[`results/`](../../results/README.md) as `xlholdout6c-gate1`.

This is the one run of the Gate 1 holdout. It was made against the pins fixed
in [the Phase 1 close-out](phase1-closeout-c7e56fa.md) before it existed, and
it is recorded here whatever it shows. The configuration is not revised after
it, and the holdout is not run again.

## Provenance

Six checks passed before the run: a clean worktree; no change to `src/`,
`benchmarks/`, `pyproject.toml` or `uv.lock` since `c7e56fa`; the subset file's
sha256; no earlier run of this subset; the compiler config hash; and the quote
match policy.

Nine checks passed on the run's own record afterwards: `git_dirty` false,
commit `60e5836`, subset sha256
`f8bee8e5038cab2c92868b108ebf160114d2c82633662e475f6760006e0c7adc`, run config
hash `b2b8bbaa3eee2d52…`, compiler config hash `104b14de5974064f` on all 24
compiler packets, quote policy `nfkc-unified-punctuation-ordered-elision-v3`,
and both model revisions and the dataset revision as pinned.

## The verdict

**Gate 1 passes**, under the rule as preregistered in
[the plan](../plans/2026-09-21-improvement-plan.md):

> It passes when, on `xlholdout6c`, the compiler's paired point estimate
> against fixed RAG is positive at 2K and 4K and its interval at 8K and 16K
> does not lie entirely below the −3 pp margin.

Compiler minus fixed RAG, answerable page recall, 6 questions over 6 source
clusters:

| Budget | point estimate | interval | rule | |
| ---: | ---: | --- | --- | --- |
| 2K | +0.0870 | [−0.1065, +0.2457] | point estimate > 0 | pass |
| 4K | +0.1617 | [−0.0069, +0.3254] | point estimate > 0 | pass |
| 8K | +0.0933 | [−0.0694, +0.2460] | upper bound > −0.03 | pass |
| 16K | +0.0636 | [−0.0833, +0.1899] | upper bound > −0.03 | pass |

## What the pass does and does not establish

**Every one of those four intervals includes zero.** The rule asks only for a
positive point estimate at 2K and 4K, and at 8K and 16K asks only that the
interval not lie entirely below the margin. Six questions cannot do more, and
the plan says so: Gate 1 is a screening check, not a non-inferiority result.
The non-inferiority check, which asks the lower bound to clear −0.03, is
satisfied at 5 of 8 cells here and is confirmatory at none.

The development set and the previous holdout disagreed at 16K, where
`xlholdout6b` measured a loss to fixed RAG with an interval excluding zero.
That loss does not recur here: the 16K point estimate is +0.0636. Six fresh
questions cannot settle which holdout was representative.

Against structural chunks the page-recall result is stronger: the interval
excludes zero at 2K, 4K and 8K and touches it at 16K.

## Exact quote recall points the other way

This is not a gating metric, and it is the most important thing in this
record.

Compiler minus fixed RAG, exact quote recall, the same 6 questions:

| Budget | point estimate | interval |
| ---: | ---: | --- |
| 2K | −0.108 | [−0.358, +0.167] |
| 4K | **−0.192** | [−0.358, −0.042] |
| 8K | −0.108 | [−0.317, +0.083] |
| 16K | **−0.233** | [−0.417, −0.067] |

On the holdout the compiler trails fixed RAG on exact quotes at every budget,
with the interval excluding zero at 4K and 16K. Against structural chunks it
trails at every budget with intervals that include zero.

This is the divergence Phase 1 recorded on the development set — page recall
rewarding the compiler while exact quote recall does not — and on the holdout
it is larger and in the compiler's disfavour. Gate 1 was stated on page recall
and passed on it. It would be wrong to read the pass as evidence that the
compiler selects better evidence in the sense an answer needs.

### Two mechanisms, from the per-question record

**Right pages, missing spans.** `adubench_single_000331` scores 0.53 page
recall against fixed RAG's 0.20 at every budget, and 0.20 quote recall against
fixed RAG's 0.60. The compiler reaches more of the gold pages and fewer of the
quoted passages on them. This is the node-granularity failure recorded
throughout Phase 1.

**The compiler leaves budget unspent.** On that same question the compiler
packs 3,772 tokens at 4K, 8K and 16K alike, while fixed RAG fills 16,245 of
16,384. `adubench_single_000255` stops at 13,405 at 16K. Across the holdout 3
of 24 compiler packets fill less than 90 per cent of their budget, one of them
23 per cent; fixed RAG never falls below 96 per cent.

The under-fill is not a holdout finding. At the frozen configuration on
`xldev24` the compiler under-fills 6 of 96 packets, down to 29 per cent, and
fixed RAG none. It was present in the development evidence and was not
examined there. It is recorded as a finding for Phase 2, not acted on: the
configuration is frozen and is not changed after the gate.

## Decision

**Gate 1 passes. Phase 1 is closed. Task 10, the confirmatory answer-generation
run at 2K and 4K, is the next step**, and it needs its own preregistration
before anything is generated.

This result should shape that preregistration. The question the generation
run exists to answer is whether better page selection produces better answers
and better-supported citations. The holdout supplies a specific reason to
doubt it: the compiler's contexts carry fewer of the exact quoted passages than
fixed RAG's at both budgets the run will use. A preregistration that did not
state this as a hypothesis in advance would be written with the answer to its
most likely failure already in hand.

## Known weaknesses

- Six questions over six source clusters. No interval here bounds a loss
  margin, and several per-budget effects rest on one or two questions.
- Gate 1 is a screening rule. Its pass is compatible with a true effect
  anywhere from a small loss to a large gain.
- Quote recall on six questions is coarse: one gold quote on one question is
  worth several points.
- The quote-recall ceiling is set by gold-quote construction, as recorded at
  the close-out; the holdout's gold quotes were not audited, because auditing
  them would mean inspecting the holdout.
- No answer-quality result exists.
