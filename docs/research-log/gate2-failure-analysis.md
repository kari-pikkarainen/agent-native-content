# Gate 2 failure analysis: what the generation run did and did not measure

Date: 2026-09-23

Required by [the preregistration](prereg-xlholdout6c-generation.md) after
[Gate 2, stage 1](gate2-stage1-xlholdout6c-generation.md) failed. Read-only
over the saved artifacts: no API call, no code change. `xlholdout6c` is spent,
so nothing found here can be confirmed on it.

Per the owner's instruction, prompt framing is counted throughout: "prompt"
below means the answer model's recorded input tokens, not the packed content
budget.

## Summary

**The run carries no discriminating signal about evidence quality, in either
direction.** Both differences that decided the verdict come apart under
inspection: one is a question answerable from its own text, the other an
abstention credited as a supported citation. The verdict stands, because the
rule required a benefit and there is none, but the run does not show the
compiler's evidence is worse for answering either.

What survives is a concrete mechanism that is not specific to this run: on
documents whose parse breaks into very small units, the compiler packs
hundreds of fragments of a few tokens each. That empties its candidate pool,
leaves budget unspent, multiplies the prompt, and produces contexts the answer
model declines to answer from.

## The two deciding differences

**Accuracy: `adubench_single_000331`.** The question is *"…what total results
from 1000 to 1798 plus the 1581 transition year…"*, and the gold answer is
2379 = 1798 − 1000 + 1581. **Every operand is in the question.** Fixed RAG
answered correctly at 2K although `1798` appears nowhere in its 2K context, and
the judge scored its citations as not supporting the answer. The compiler's
context contained both `(1798)` and `(1581)`, and the model declined. The arms
differ in whether the model was willing to answer, not in whether their
evidence contained the answer.

**Citation entailment: `adubench_single_000255` at 2K.** Fixed RAG abstained
and cited two items; the judge scored entailment 1, reasoning that the evidence
established the premises but not the requested result. The citations did
entail that the evidence was insufficient. A metric meant to measure support
for an answer credited a correct abstention.

**Correction to the Gate 2 record.** It says that "in both cells where the arms
disagree, quote recall predicted the answer outcome and page recall predicted
the opposite". That alignment was coincidence: on `000331` fixed RAG's correct
answer did not come from its evidence. The record carries a dated note
pointing here.

## Every cell, by where it failed

Six questions, three arms, two budgets. 23 of the 36 answers are
`INSUFFICIENT_EVIDENCE`: 6 of 12 for fixed RAG, 8 of 12 for structural RAG and
8 of 12 for the compiler. The whole compiler–fixed abstention gap is `000331`.

| Question | Outcome | Where it failed |
| --- | --- | --- |
| `001173` | every arm correct | — |
| `001346` | every arm "wrong" | **Scoring.** Every arm answered "Open-ended steel pipe piles"; the gold is "Open-end pipe piles"; exact matching marked all of them wrong. Every arm's citations were judged entailed. |
| `000181` | every arm abstains | **Retrieval** for fixed RAG and the compiler: the answer is not in their contexts. Structural RAG had "Buy Now Pay Later" in its context and still abstained: **reading**. |
| `000255` | every arm abstains | **Composition.** The answer is a count ("five deep-flow regions"); the term is in every arm's context and no arm assembled it. |
| `000826` | every arm abstains | **Retrieval** for every arm: the answer is in no context. The question points at a figure. |
| `000331` | fixed correct, others abstain | **Not evidence.** The answer is computable from the question; see above. |

So of the six questions, one is answered by everyone, one is mis-scored for
everyone, three are abstained on by everyone, and one differs for a reason
unrelated to evidence.

## The instrument's own defects

Four were found, all independent of which arm is better, and all must be fixed
before another generation run can decide anything:

1. **Exact-match scoring rejects correct paraphrases.** `001346` scores 0 for
   every arm on a substantively correct answer.
2. **Citation entailment credits abstentions.** An `INSUFFICIENT_EVIDENCE`
   answer can score 1, so the metric does not measure support for an answer.
3. **Questions answerable from their own text do not measure evidence.**
   `000331` is one; nothing screened for them.
4. **Abstention dominates.** At 23 of 36 answers, most cells carry no answer to
   score, and the run discriminated on at most two questions.

## The mechanism that survives: shredded contexts

On `000331` the compiler packed **291 items at 2K and 500 at 4K, 8K and 16K**,
with a median of **6 tokens per item** and 61–65 per cent of items at 8 tokens
or fewer — `'order, using'`, `'PAGE'`, `'1.'`, `'(1581).'`, `'(1798)'`. The
document's parse is broken into word- and line-sized nodes, and the compiler's
node-level unit carries that straight into the context.

Three effects follow, and they explain findings recorded separately earlier:

- **The candidate pool empties.** 500 is `max_expanded_candidates`. At 4K and
  above the compiler packs all 500 candidates and still reaches only 3,772
  tokens. This is the budget under-fill the Gate 1 record found and could not
  explain.
- **The prompt multiplies.** About 45 tokens of framing per item turns 3,772
  packed tokens at 4K into a **28,954-token** prompt, seven times the nominal
  budget.
- **The model declines.** With both operands present, as isolated fragments,
  it abstained at both budgets.

**It is not one document.** Counting compiler packets whose median item is 10
tokens or fewer:

| Set | Shredded packets | Questions affected | Packets at the 500-item cap |
| --- | ---: | ---: | ---: |
| `xlholdout6c` | 4 of 24 | 1 of 6 | 4 |
| `xldev24`, frozen configuration | 8 of 96 | 5 of 24 | 6 |

On `xldev24`, `adubench_single_001102` hits the cap at 8K and 16K and packs
4,754 of 16,384 tokens. Several of the affected development questions are the
same scanned literary documents whose gold quotes the Phase 1 audit found
carrying OCR errors, which is consistent with parse quality driving the
fragmentation. That link is suggested here, not established.

The retrieval metrics reward this failure. Fragments land on the right pages,
so page recall rises; no fragment is long enough to hold a quote, so quote
recall falls. That is the page-versus-quote split Phase 1 recorded, with a
concrete cause for part of it.

## Recommendation

**Do not stop and document a negative result on this evidence.** The run that
would support it does not measure evidence quality. Stopping on it would be
drawing a conclusion from an instrument shown here to be broken.

**Do not run another generation experiment until the four instrument defects
are fixed.** Another run through the same instrument would spend money for the
same absence of signal.

**State the fragmentation mechanism as a hypothesis and test it on fresh
questions.** It is specific and measurable: shredded packets can be identified
from item size alone, before any answer is generated. Any remedy — merging
adjacent small nodes into a minimum unit size, or counting the rendered prompt
against the budget, which is the owner's open decision — is a change made after
seeing `xlholdout6c` and tuned against `xldev24`, so it can be confirmed only on
questions neither has touched. The unused remainder of XL100 is where the plan
already puts Phase 3's larger population.

The owner's pending budget decision bears directly on this. Counting framing
against the budget would make a shredded context expensive to the packer, not
just to the reader, and would remove the under-fill-plus-inflation combination
by construction.

## Known weaknesses

- Six questions, all answerable, one answer model, one prompt.
- The shredding counts use a 10-token median threshold chosen here; they are
  descriptive.
- The link between shredding and scanned or OCR-damaged documents rests on
  overlap with the Phase 1 quote audit, not on a parse-quality measurement.
