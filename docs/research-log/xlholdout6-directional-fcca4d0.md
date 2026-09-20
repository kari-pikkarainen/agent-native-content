# Experiment: XLHoldout6 directional confirmation

Date: 2026-09-20

## Decision

Do not run the full XL100 yet and do not select or tune another compiler change
on XLHoldout6. The selected compiler does not consistently beat the baselines
on this small, fresh slice, so the XLDev24 improvements are not yet sufficient
evidence that the approach generalizes.

Return to development-only diagnosis on XLDev24. Preserve the remaining
untouched XL100 questions for another precommitted directional confirmation
after a new approach wins on the development set.

## Holdout construction

The `xlholdout6` manifest was committed as `b676330` before any retrieval
results were produced. It contains six answerable, single-document XL100
questions: one from each domain. All six source documents are absent from both
XL10 and XLDev24. Selection used only metadata and pinned-source availability,
not retrieval results.

This is a directional holdout, not a claims set. Its six documents contain 646
pages. Four questions require table, chart, or image evidence and two are
text-only.

## Result

Canonical run: `xlholdout6-faceted-fcca4d0`.

| Budget | Compiler recall | Best baseline | Baseline system | Recall delta | Compiler coverage | Best coverage |
| ---: | ---: | ---: | --- | ---: | ---: | ---: |
| 2,048 | 0.230 | 0.264 | fixed | -0.034 | 0.000 | 0.000 |
| 4,096 | 0.395 | 0.390 | fixed | +0.005 | 0.000 | 0.000 |
| 8,192 | 0.488 | 0.578 | structural | -0.090 | 0.000 | 0.000 |
| 16,384 | 0.697 | 0.767 | structural | -0.070 | 0.167 | 0.333 |

The compiler narrowly leads mean recall at 4K, but loses at the other three
budgets. At 16K it fully covers one of six questions while the structural
baseline covers two. Compiler latency is approximately 3.5-3.7 times fixed at
2K-4K and 2.7 times structural at 8K-16K.

The 16K per-question pattern is heterogeneous. The compiler leads the best
baseline on the medical and legal questions, ties on finance, and trails on
narrative, scientific, and technical questions. The aggregate loss is therefore
not evidence that every compiler mechanism is harmful, but it is sufficient to
reject a general superiority claim from the current configuration.

## Reproducibility and reporting correction

The initial run `xlholdout6-faceted-b676330` exposed a report-only bug: when
baseline coverage tied, the report selected the fixed baseline without using
recall as a tie-breaker while labeling it the best baseline. Commit `fcca4d0`
adds the recall tie-breaker and a regression test. The canonical rerun produced
identical contexts and evidence metrics to the initial run; only measured
latencies differ.

No answer-generation model was used. No compiler setting was changed in
response to holdout results.

## Next validation rule

A future candidate should first show a consistent advantage over both fixed and
structural baselines on XLDev24, including the failure modes represented by the
narrative, scientific, and technical questions. Its next confirmation subset
must be selected and committed before evaluation, exclude all documents used so
far, and remain small. Run the full XL100 only after that directional check
succeeds.
