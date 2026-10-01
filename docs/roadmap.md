# Research Roadmap

This page tracks the gates of the
[improvement plan](plans/2026-09-21-improvement-plan.md) and what comes after
them. It uses the plan's numbering. An earlier version of this page used its
own Gates 1 to 7; the mapping is given at the end so that old links still make
sense.

## Current conclusion

The evidence supports a narrow claim: the frozen deterministic compiler
improves gold-page recall at low token budgets when the relevant
single-document scope is already known.

It does not show that the persistent IR causes that gain, that compiled
contexts produce better answers, that comparable evidence needs materially
fewer tokens, or that the approach generalizes or wins economically. Presenting
the structured representation directly to an answer model did not help in a
controlled test. Document-format tuning has stopped under the preregistered
rule. The active step is a tabular-data pilot.

## Gates

| Gate | Question | Outcome |
| --- | --- | --- |
| Gate 0 | Is the low-budget page-recall advantage real after the measurement defects are fixed? | **Passed.** Survived nine fixes; the paired interval against both RAG baselines excludes zero at 2K and 4K on `xldev24`. [Record](research-log/gate0-rebaseline-67aef47.md). |
| Gate 1 | Does the frozen configuration hold on a fresh holdout? | **Passed on page recall**, on one run of `xlholdout6c`: positive point estimates at every budget, every interval including zero. Exact quote recall pointed the other way at every budget. Screening, not confirmation. [Record](research-log/gate1-xlholdout6c-60e5836.md). |
| Gate 2 | Does better evidence selection produce better answers? | **Failed at stage 1** under the preregistered rule, then shown by the [failure analysis](research-log/gate2-failure-analysis.md) to carry no signal about evidence quality in either direction. Four instrument defects were fixed. [Record](research-log/gate2-stage1-xlholdout6c-generation.md). |
| Gate 3, representation part | Does the IR communicate the same evidence better than raw text? | **No.** With identical gold pages, local Gemma-4-12B answered 6 of 18 from raw text, 5 from IR, 5 from enriched IR and 6 from indexed features, at 1.9 to 2.4 times the tokens. [Record](research-log/representation-xldev24-gemma-b3d53c0.md). |
| Gate 3, remainder | Stratified structured population, second benchmark, second model tier, long-context comparison | **Not opened.** Gate 2 did not pass, so the plan's Phase 3 retrieval work is paused. |
| Gate 4 | Validated or not? | **Not yet decidable.** The retrieval result is narrow and real; the answer-quality result is uninformative; the representation result is negative. |

Two later changes bear on every row above. Since commit `f916545` every arm
is charged for the prompt framing it renders, which costs the compiler up to 7
points of page recall at 2K on the development set and makes its
non-inferiority screen against fixed RAG fail at 16K. And both six-question
holdouts are spent: any further claim needs a new frozen population.

## Next step: agent-native tabular data

The next experiment moves to data where explicit machine-oriented structure
has a clearer potential advantage than markup around long document text. It
compares identical source rows under three conditions:

- compact CSV or plain table text;
- a typed schema with column meanings, units, keys and null semantics; and
- an agent-native representation adding formula dependencies, relationships,
  reusable summaries and cell-level provenance.

Tasks cover filtering, aggregation, joins, unit conversion, formula tracing
and provenance, with deterministic, executable ground truth wherever possible
and constrained JSON output so formatting failures do not pass as reasoning
failures. The representation conditions, task families, token comparisons and
stopping rule are preregistered before the measured run, on a small
development set, then checked once on an untouched holdout.

Until that test shows a gain, the conservative document pipeline is to use
the IR internally for organisation and selection while rendering compact text
to the answer model.

## After that

If the tabular pilot or a repaired generation instrument shows a directional
answer or citation benefit, the plan's Phase 3 reopens:

1. freeze a stratified population from the untouched XL-DocBench remainder,
   including cross-document questions, with its analysis plan;
2. check availability of T²-RAGBench or a substitute table-and-text
   benchmark, and add its adapter;
3. repeat the matched content-unit × policy factorial on that population;
4. repeat generation with a second, stronger answer-model tier; and
5. give a capable model the full relevant documents at 64K or 128K and
   compare answer quality, citation support, cost and latency.

Validation requires all of these, or an explicitly narrowed claim.

## Stop conditions

Pause the broader Content IR thesis if any of the following holds:

- enhanced fixed or structural RAG matches IR under the factorial control;
- stricter content coverage removes the low-budget advantage;
- better retrieval does not improve answers or citations;
- representation overhead outweighs any answer improvement; or
- the effect fails on an untouched cross-document population or second
  dataset.

The third and fourth conditions are the ones the current evidence comes
closest to; neither is settled, because the one generation run was
uninformative and the representation test used one local model.

## Mapping from the earlier numbering

| Earlier page | This page |
| --- | --- |
| Gate 1: isolate representation from policy | Done inside Phase 1; see the corrected factorial in Gate 0 and Gate 1 records |
| Gate 2: audit retrieval metrics | Done inside Phase 0 |
| Gate 3: test whether selected evidence improves answers | Gate 2 |
| Gate 4: test the persistent representation directly | Gate 3, representation part |
| Gate 5: agent-native tabular data | Next step |
| Gate 6: generalize without reusing tuned questions | After that, items 1 to 4 |
| Gate 7: compare realistic long context | After that, item 5 |
