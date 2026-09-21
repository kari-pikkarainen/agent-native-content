# Research Roadmap

## Current conclusion

The evidence supports a narrow claim: the selected deterministic compiler
pipeline can improve gold-page recall at low token budgets when the relevant
single-document scope is already known.

It does not yet show that the persistent IR causes the gain, that compiled
contexts produce better answers, that comparable evidence needs materially
fewer tokens, or that the approach generalizes or wins economically.

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

## Gate 4: Test the persistent representation directly

Run RAW versus IR on identical gold evidence before adding more enrichment.
The current two-question diagnostic makes IR about 49% larger than raw text, so
IR must improve answer or citation quality enough to justify that overhead.
Treat enriched and indexed conditions as later, separately reported treatments.

## Gate 5: Generalize without reusing tuned questions

Freeze a preregistered population from the untouched XL-DocBench remainder,
including cross-document questions. Record the analysis and stopping rules
before running it. If the result survives, add a second benchmark such as
T²-RAGBench before claiming technical validation.

## Gate 6: Compare realistic long context

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
