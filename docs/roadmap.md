# Research Roadmap

## Current conclusion

The evidence supports a narrow claim: the selected deterministic compiler
pipeline can improve gold-page recall at low token budgets when the relevant
single-document scope is already known.

It does not yet show that the persistent IR causes the gain, that compiled
contexts produce better answers, that comparable evidence needs materially
fewer tokens, or that the approach generalizes or wins economically.

The controlled gold-evidence experiment found no benefit from presenting the
current document IR or agent features directly to local Gemma-4-12B: the best
structured condition tied raw text while using roughly twice the tokens and
latency. Under its preregistered rule, document-format tuning has stopped. The
active research step is the tabular-data pilot summarized in the README.

## Gate 1: Isolate representation from retrieval policy

**Implementation status:** initial small-subset diagnostic complete.

Run a representation-by-policy factorial comparison on development data. The
exact contract is defined in the [factorial specification](specs/factorial.md).

| Content unit | Control policy | Enhanced policy |
| --- | --- | --- |
| Fixed 512/64 chunks | Single query + ranked packing | Faceted retrieval + coverage packing |
| Structural chunks | Single query + ranked packing | Faceted retrieval + coverage packing |
| IR nodes | Single query + ranked packing | Faceted retrieval + coverage packing |

Hold document scope, sparse and dense models, fusion, reranker, candidate
limits, budgets, and token accounting fixed. This separates three effects:

- IR versus chunk representation under the same policy;
- faceting and diversified packing within each representation; and
- any interaction between representation and policy.

The two-question table-heavy diagnostic found that IR trailed the best chunk
unit in seven of eight matched policy/budget comparisons. Faceting plus
coverage-aware packing improved page recall in 10 of 12 within-unit
comparisons, at a substantial latency cost. This rejects an IR-specific claim
at this gate and points to selection policy as the stronger mechanism. See the
[decision note](research-log/xldev2-content-policy-factorial.md).

## Gate 2: Audit retrieval metrics

**Status:** complete on the six-question XLHoldout6b diagnostic.

Before paid generation:

- report answerable-only metrics alongside the registered aggregate;
- make exact quote recall and full quote coverage co-primary;
- add exact content-span or provenance-span coverage that cannot credit absent
  text merely because a selected node references the same page;
- report paired uncertainty intervals clustered by source document; and
- manually inspect the largest compiler wins and losses at 2K and 4K.

Preserve the existing page metrics for continuity, but do not use them alone
for the next decision.

The audit added answerable-only and quote-eligible summaries, conservative
content-verified page coverage, and paired source-cluster bootstrap intervals.
The low-budget page effect survives, but manual inspection found both false
positive and false negative retrieval signals. See the
[metric-audit decision note](research-log/xlholdout6b-metric-audit.md). This
meets the gate for a small guarded answer-generation run, not for a broader
retrieval claim.

## Gate 3: Test whether selected evidence improves answers

**Status:** the first preregistered provider run and its failure analysis are
complete. The run did not establish an answer-quality benefit because its
outcome was driven by abstention behavior; the evaluation defects it exposed
have since been corrected.

Use already-saved contexts first. Compare fixed, structural, and compiler
systems at 2K and 4K with one answer model, one prompt, and explicit pricing and
call limits. Measure:

- benchmark accuracy and similarity metrics;
- citation entailment or evidence support, not only citation-ID validity;
- abstention correctness;
- provider tokens, latency, and dollars; and
- cost and latency per correct answer.

Expand budgets or add a second model only if the first guarded run shows a
directional answer-quality or economic benefit.

The first run is frozen in the
[XLHoldout6b generation preregistration](research-log/xlholdout6b-generation-preregistration.md):
36 answer cells at 2K/4K, the same model for answer and semantic citation
judging, a 72-call hard ceiling, and an approximately $5 authorization
envelope.

## Gate 4: Test the persistent representation directly

**Status:** complete as a development experiment. The preregistered run gave
identical gold-page evidence to raw, IR, enriched and indexed conditions. Raw
and indexed each answered 6 of 18 questions correctly; IR and enriched each
answered 5. Structured conditions used 1.9–2.4 times raw's answer-input tokens
and did not meet the directional rule. See the
[result](research-log/representation-xldev24-gemma-b3d53c0.md).

## Gate 5: Test agent-native tabular data

Run the bounded tabular pilot described in the README. Prefer executable
ground truth and cell-level provenance so the central comparison does not
depend on a model judging itself. Preregister the representation conditions,
task families, token comparisons and stopping rule before the measured run.

## Gate 6: Generalize without reusing tuned questions

Freeze a preregistered population from the untouched XL-DocBench remainder,
including cross-document questions. Record the analysis and stopping rules
before running it. If the result survives, add a second benchmark such as
T²-RAGBench before claiming technical validation.

## Gate 7: Compare realistic long context

Finally, give a capable answer model the full relevant documents at 64K or 128K
where they fit. Compare answer quality, total input cost, latency, and citation
support—not retrieval recall alone.

## Stop conditions

Pause the broader Content IR thesis if any of the following holds:

- enhanced fixed or structural RAG matches IR under the factorial control;
- stricter content coverage removes the low-budget advantage;
- better retrieval does not improve answers or citations;
- representation overhead outweighs any answer improvement; or
- the effect fails on an untouched cross-document population or second dataset.
