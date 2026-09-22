# Gate: Phase 0 re-baseline of the measurement

Date: 2026-09-22

Precommit: `e28b247`

Canonical runs: `xldev24-rebaseline-e28b247`,
`xlholdout6b-rebaseline-e28b247`, `xldev24-factorial-heading-e28b247`

Published under [`results/`](../../results/README.md) as `xldev24-rebaseline`,
`xlholdout6b-rebaseline`, and `xldev24-content-policy-heading`.

## Scope

Gate 0 of the [improvement plan](../plans/2026-09-21-improvement-plan.md). Its
condition: continuous integration green on `main`, new development and holdout
results published, and on `xldev24` the paired source-cluster bootstrap
interval for the compiler against the best RAG baseline excluding zero at both
2K and 4K. The plan states that if the low-budget advantage does not clear that
bar after the BM25 fix, the work stops and the result is written up.

Tasks 1 to 7 of Phase 0 were delivered first, across 29 commits. They fixed the
seven defects the 2026-09-21 review recorded, plus two the review did not
contain: the dense channel held a copy of the BM25 defect, and the structural
arm could not retrieve on its own heading vocabulary. Task 8 froze
[`xlholdout6c`](xlholdout6c-freeze.md), which was not run here.

All three runs were produced at `e28b247` on a clean worktree, with the
embedding model pinned to `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` and the
reranker to `233902d25c440f23af6f7d6e94d2946bac0bee0a`. Their manifests record
`git_dirty: false` and both revisions, so these are the first results in this
project reproducible from a config and a SHA rather than in principle.

## Result: the gate condition

`answerable_page_recall`, compiler minus baseline, paired source-cluster
bootstrap, 18 eligible questions of 24.

| Budget | vs fixed | vs structural |
| ---: | --- | --- |
| 2K | **+0.3375** [+0.1696, +0.5132] | **+0.2585** [+0.0514, +0.4427] |
| 4K | **+0.2134** [+0.0666, +0.3534] | **+0.2086** [+0.0342, +0.3681] |
| 8K | +0.1504 [−0.0063, +0.2740] | +0.1783 [+0.0099, +0.3224] |
| 16K | +0.1143 [+0.0267, +0.2034] | +0.1517 [+0.0424, +0.2879] |

Both intervals exclude zero at 2K and at 4K. **The gate condition is met.**

The margin decays monotonically with budget against fixed windows, from +0.34
to +0.11, which is what a selection advantage under scarcity should do: the
scarcity is what disappears.

The eligible count is 18 rather than 24 because answerable-only eligibility now
requires an annotated gold page. Six `xldev24` questions have none, and all six
are unanswerable, so they were already excluded before that change.

## Result: the holdout

Same metric, six questions.

| Budget | vs fixed | vs structural |
| ---: | --- | --- |
| 2K | **+0.1222** [+0.0333, +0.2333] | **+0.0875** [+0.0208, +0.1625] |
| 4K | **+0.1361** [+0.0611, +0.2111] | +0.0611 [−0.1111, +0.2000] |
| 8K | −0.0403 [−0.1986, +0.1875] | +0.0708 [0.0000, +0.1958] |
| 16K | **−0.0653** [−0.1208, −0.0167] | **+0.0819** [+0.0208, +0.1486] |

The published shape survives the fixes rather than being overturned by them.
The compiler leads fixed RAG at 2K and 4K and loses to it at 16K, and that loss
now carries an interval excluding zero rather than a point estimate. Against
structural chunks the compiler leads at 2K and at 16K, so the high-budget
problem is specifically fixed windows, not chunked retrieval in general.

The development set and the holdout disagree at 16K, where `xldev24` favours
the compiler and the holdout does not. That disagreement is the reason the plan
requires a holdout, and it is an argument against reading the gate result as
more than the screening check it is.

## Result: the matched factorial

The content-unit × policy factorial ran over all 24 development questions for
the first time, with heading search context crossed as a third factor. Earlier
factorial evidence came from two table-heavy questions.

IR nodes minus the better of the two chunk units, heading context on, the
shipped default:

| Budget | Policy | Page recall | Quote recall |
| ---: | --- | ---: | ---: |
| 2K | faceted_coverage | +0.2042 | −0.0174 |
| 2K | ranked | +0.1241 | +0.0139 |
| 4K | faceted_coverage | +0.1740 | −0.0243 |
| 4K | ranked | +0.0824 | +0.0139 |
| 8K | faceted_coverage | +0.1043 | −0.0208 |
| 8K | ranked | +0.0356 | +0.0000 |
| 16K | faceted_coverage | +0.0213 | +0.0208 |
| 16K | ranked | +0.0183 | −0.0104 |

On page recall IR nodes beat the best chunk unit in **8 of 8** matched cells.
On quote recall they do so in **3 of 8**, and never by more than 0.021.

This is the over-crediting the plan already suspected, now measured on the full
development set: the IR unit reliably lands on the right pages and does not
reliably carry the exact quoted evidence. A node boundary is not a quote
boundary. The gate is stated on page recall and passed on it; the plan promotes
quote recall to co-primary in Phase 2 for exactly this reason.

The two-question diagnostic recorded IR trailing the best chunk unit in 7 of 8
comparisons. That is not contradicted so much as superseded: two questions
could not support the inference either way.

## Result: the heading ablation

Heading search context on minus off, `ranked` policy, page recall. The `ranked`
policy is reported because it is the one clean of the coverage-term mechanism.

| Budget | fixed | structural | IR |
| ---: | ---: | ---: | ---: |
| 2K | +0.0000 | +0.0313 | **−0.0226** |
| 4K | +0.0000 | +0.0109 | **−0.0422** |
| 8K | +0.0000 | −0.0085 | **−0.0517** |
| 16K | +0.0000 | −0.0016 | **−0.0336** |

Heading context **costs** the IR unit between 2 and 5 points at every budget,
and helps structural chunks only at 2K and 4K. The fixed unit is unchanged
across the factor at every budget, which its construction requires and which
serves as a check that the factor is wired correctly.

This inverts the assumption that motivated the heading work. Phase 0 found the
structural baseline blind to heading vocabulary and expected that to flatter
the compiler. It did. But the compiler was simultaneously paying a heading tax
of its own, because it has always joined heading trails into its node search
text, and a trail repeated under every node in a section is a constant,
non-discriminative term. Both corrections narrow the same gap.

Read the delta with the caveat recorded in
[the retrieval specification](../specs/retrieval.md): the factor carries three
mechanisms, and even on `ranked` rows it carries two — heading-vocabulary
matchability and candidate dedupe scope. The coverage-selection mechanism is
excluded here only because `ranked` packing never reads `retrieval_text`.

## Decision

**Gate 0 passes.** All four conditions are met: CI is green on `main`, a fresh
holdout was frozen before any compiler change, the development and holdout
results are republished with the four earlier ones marked superseded, and the
paired interval excludes zero at 2K and 4K.

Phase 1 opens. Its target is now concrete rather than directional: the compiler
loses to fixed RAG at 16K on the holdout by a measured interval that excludes
zero, and Phase 1's goal is that it is never worse at any budget.

Two findings should shape it. The heading tax means one of Phase 1's cheapest
available improvements is to stop the compiler carrying heading trails into
node search text, which the ablation values at 2 to 5 points. The page-quote
divergence means a Phase 1 improvement measured only on page recall may not be
an improvement at all.

## Known weaknesses

- Everything here is page and quote recall over evidence selection. No
  answer-quality or economic result exists; task 10 is unrun.
- The holdout is six questions. It screens; it cannot bound a loss margin.
- The factorial's faceted-coverage rows carry a policy-side effect of the
  heading factor, so only the `ranked` rows are clean for that contrast.
- `xlholdout6c` was frozen but not run, and must not be run before Gate 1.
- The gate's own evidence is a development set plus a six-question holdout that
  disagree at 16K. Neither is a population that can support a validation claim.
