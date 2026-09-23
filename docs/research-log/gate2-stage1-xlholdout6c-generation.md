# Gate 2, stage 1: generation over xlholdout6c

Date: 2026-09-23

Run: `xlholdout6c-generation-astra`, published under
[`results/`](../../results/README.md) as
`generation/xlholdout6c-generation-astra`, with raw model and judge responses
removed.

Judged against [the preregistration](prereg-xlholdout6c-generation.md),
frozen at `6768f8d` before any provider call.

## Provenance

The run was made by the owner in their own terminal, so the API key never
passed through the session. Its manifest records commit `6768f8d` with a clean
worktree, `gpt-6-astra` at reasoning effort `low`, a 512-token output cap, the
`answer-json-v1` prompt, the frozen pricing, and
`retrieval_artifact_verified: true` against the pinned hash `02aef520…`.
Every setting matches the preregistration.

Answer and judge responses were valid in **every** cell, so the scores measure
answers rather than failed calls. The published files and the raw artifacts
were scanned for key-shaped strings before anything was committed; none was
found.

## The verdict

**Stage 1 fails.** Compiler against fixed RAG:

| Condition | 2K | 4K |
| --- | --- | --- |
| (a) relaxed accuracy higher | 0.167 against 0.333 — no | 0.167 against 0.333 — no |
| (b) citation entailment higher | 0.333 against 0.500 — no | 0.333 against 0.333 — equal, not higher |
| (c) accuracy equal or higher and $/correct lower | accuracy lower — no | accuracy lower — no |

No condition holds at either budget. As preregistered: Phase 3 does not open,
the stage 2 `xldev24` run is not made, algorithm work pauses, and the
per-question failure analysis comes first.

**H1 holds.** It predicted, before the run, that the compiler's citation
entailment would be no higher than fixed RAG's at either budget. It is lower at
2K and equal at 4K.

**H2**, on accuracy, carried no prediction. The compiler is behind fixed RAG at
both budgets and level with structural RAG.

## What the difference is made of

Six questions. On four of them every arm is wrong, and on one every arm is
right, so the whole comparison rests on two:

- **`adubench_single_000331`** (gold answer `2379`) carries the entire accuracy
  difference. Fixed RAG answers it correctly at both budgets; the compiler does
  not. On this question the compiler reached **more** of the gold pages — page
  recall 0.53 against 0.20 — and **fewer** of the quoted passages, 0.20 against
  0.60. It is also the question on which the compiler stopped filling its
  budget, at 3,772 tokens. The Gate 1 record named it as the example of both
  failure mechanisms.
- **`adubench_single_000255`** at 2K carries the citation difference. The
  compiler's quote recall there was 0.00 against fixed RAG's 0.50.

In both cells where the arms disagree, **quote recall predicted the answer
outcome and page recall predicted the opposite.** That is two cells, which is
directional and nothing more. It is the pattern Phase 1 recorded on retrieval
metrics alone, now seen at the level of answers, and it points in the direction
the preregistration predicted.

## The token budget is not the budget the model reads

This was found in the run and was not anticipated by the preregistration.

Budgets are enforced on packed content tokens, and those are matched: 2,047
compiler tokens against 2,006 for fixed RAG at 2K. But the answer prompt adds
framing to every packed item — an evidence tag and its metadata — and the
compiler packs far more items: **79 at 2K and 148 at 4K, against fixed RAG's 4
and 8**. The framing costs about 45 tokens per item, consistently at both
budgets: (6,279 − 3,052) / (79 − 4) ≈ 43 and (11,657 − 5,150) / (147.7 − 8) ≈
47.

So the compiler's answer prompt at 2K averaged **6,279** input tokens, larger
than fixed RAG's at 4K (5,150). At 2K its packed items average about 26 content
tokens each, so the framing around each fragment is longer than the fragment.

Two consequences:

- **It did not favour fixed RAG.** The compiler's answer model read about twice
  the prompt and still answered worse, so the result is not explained by the
  compiler being starved of input.
- **It changes the cost comparison.** The compiler's dollars per correct answer
  are 3.5 times fixed RAG's at 2K and 4.2 times at 4K. At equal accuracy
  condition (c) could not have passed on this evidence.

Whether a heavily fragmented context — dozens of short tagged extracts — is
harder for an answer model to use than a few coherent windows is a hypothesis
this raises and does not test. It belongs to the failure analysis.

## For the owner

**Should the token budget be enforced on the rendered prompt rather than on
packed content?** As defined, the budget excludes the per-item framing, so a
packer that emits many small items spends a prompt far beyond its nominal
budget without breaching anything. `AGENTS.md` requires that a configured token
budget is never silently exceeded. Whether that is breached here depends on
what the budget is taken to mean, which is a definition only the owner should
set. It is not changed here.

## Next

The per-question failure analysis, as the preregistration requires, before any
further algorithm work. The questions it should start from are recorded above:
why coverage packing's extra gold pages did not produce correct answers on
`adubench_single_000331`, why the compiler under-fills its budget on that same
question, and whether fragmentation itself degrades answers.

## Known weaknesses

- Six questions. Each difference between the arms is one question.
- Four of the six questions are answered wrongly by every arm, and one
  correctly by every arm, so the run discriminates on two.
- One model, one prompt, one reasoning effort.
- Abstention correctness was not testable: all six questions are answerable.
