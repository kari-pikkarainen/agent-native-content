# Preregistration: generation over xlholdout6c (Gate 2, stage 1)

## Status

**Frozen 2026-09-23, before any provider call.** Every decision in it was made
by the owner before any answer existed: `gpt-6-astra`, the two-stage gate,
skipping the `xlholdout6b` run, and accepting the provider-failure risk for
this run only. It is not edited after the run; if it proves wrong, a later note
says so.

The pin is enforced, not just recorded. Before freezing, the registered command
was run with a deliberately wrong expected hash and refused before any provider
call, writing nothing, and reported the artifact's actual hash as exactly the
value pinned below.

## Purpose

Phase 1 task 10 and Gate 2 of the
[improvement plan](../plans/2026-09-21-improvement-plan.md): decide whether the
compiler's retrieval differences produce better answers and better-supported
citations, at the two budgets where it claims an advantage.

The run uses the saved contexts of the one Gate 1 holdout run. These six
questions were not inspected before their retrieval run, and that retrieval
result is recorded in [the Gate 1 decision](gate1-xlholdout6c-60e5836.md)
before any answer exists.

This is **stage 1 of a two-stage gate**. A positive result here does not open
Phase 3. It authorises a larger, separately preregistered generation run, and
only that run can open Phase 3. See the decision rule below.

## What is already known, and predicted from it

Stated now because the retrieval result is in hand and would otherwise be
available to explain an answer result after the fact.

On these six questions and these contexts, compiler minus fixed RAG:

| | 2K | 4K |
| --- | ---: | ---: |
| answerable page recall | +0.087 | +0.162 |
| exact quote recall | −0.108 | −0.192 [−0.358, −0.042] |

**H1 (directional prediction).** The compiler's citation-entailment score will
be **no higher** than fixed RAG's at 2K and at 4K. Its contexts reached more of
the gold pages and carried fewer of the exact quoted passages on them, and a
citation is judged against the passage cited, not against the page.

**H2 (no directional prediction).** Relaxed answer accuracy. The page-recall
advantage predicts the compiler ahead; the quote-recall deficit predicts it
behind. The record does not know which dominates, and this run is how to find
out.

H1 is reported whatever the decision rule concludes. If H1 fails — the
compiler's citations are better supported despite the quote deficit — that is
recorded as evidence against exact quote recall as a proxy for answer support.

## Fixed inputs

- Retrieval run: `xlholdout6c-gate1-60e5836`, at commit `60e5836`
- **Retrieval artifact sha256**, as the runner computes it over `manifest.json`
  then `contexts.jsonl`:
  `02aef5206febbc4c3811e8caf9aad9a0a9da92729e7105aa3fd2c3e810b1aab0`.
  This is the enforced pin: the registered command passes it, and the runner
  refuses to start, before any provider call, if the artifact differs.
- For reference, the two files separately: `contexts.jsonl`
  `4a19f84e5c48ae1ec1942deda7b1095dccd8b67a95622d76232a071533e20b6e`,
  `manifest.json`
  `db511ca2a92ee473edc4c91e1180e12b29b44b29521dcfe2b078c1387f5f941f`
- Questions: all six `xlholdout6c` questions, all answerable
- Systems: `fixed`, `structural`, `compiler`
- Budgets: 2,048 and 4,096 tokens
- Context cells: 36
- Saved context tokens: 109,143 before answer-prompt framing

Generation settings are those of the original preregistration, as the plan
requires — the same model, prompt and call ceiling:

- Prompt: repository `answer-json-v1`, identical across systems
- Answer model: `gpt-6-astra`
- Reasoning effort: `low`
- Maximum output: 512 tokens per call, including reasoning tokens
- Citation judge: enabled, same model, frozen pricing
- Maximum calls: 72 (36 answers plus at most 36 citation judgments)

The judge sees the question, the generated answer and the cited evidence only,
never the gold answer. Missing citations score zero without a judge call.
Invalid judge JSON, or a provider response that is incomplete or not
`completed`, scores zero.

## Frozen pricing and spend envelope

Re-frozen from the official OpenAI model page for `gpt-6-astra` as accessed on
**2026-09-23**: $10.00 per million input tokens, $1.00 cached input, $50.00
output including reasoning tokens. The page names no successor or deprecation.
The figures are unchanged from the 2026-09-20 freeze, and are recorded as
re-checked rather than carried over.

If every judge repeats an entire source context, context text contributes at
most 218,286 input tokens before prompt framing. The output ceiling is 36,864
tokens across 72 calls. At the frozen uncached prices these two components cost
about $4.03. The operational envelope is $5.00. The CLI hard-enforces the
72-call ceiling; the envelope is a pre-run estimate, not a provider-side lock.

## Provider failures: risk accepted

The generation runner is all-or-nothing: a provider exception aborts the run
before anything is published, so responses already paid for are lost. For a
run of at most 72 calls and about $4, that risk is **accepted** rather than
engineered away. If the run aborts, the lost spend is recorded, the cause is
recorded, and the same preregistration is re-run from the start; nothing seen
in an aborted run may change it.

This acceptance is limited to this run. **Resumable per-cell persistence is
required before the stage 2 run**, where a late failure would cost more.

## Metrics

Primary, as in the original:

1. relaxed benchmark accuracy;
2. same-model citation entailment;
3. dollars per correct answer;
4. end-to-end latency per answer, including the judge where invoked.

Secondary diagnostics: token F1, ANLS, citation-ID validity, gold-page
alignment, provider token usage and response validity.

**Abstention correctness is not testable here.** The plan lists it among the
Phase 2 metrics, but all six questions are answerable. It is recorded as
untested rather than reported as perfect.

## Resolution of the instrument

Six questions per system per budget. Accuracy moves in steps of one question,
**0.167**. Every comparison below is a comparison of point estimates on six
questions; no interval computed from them bounds anything. The result is
directional by construction.

## Decision rule: a two-stage gate

### Stage 1 — this run, a screening gate

Against **fixed RAG**, the baseline Gate 1 was stated on, at 2K or at 4K:

- **(a)** compiler relaxed accuracy is higher; or
- **(b)** compiler citation entailment is higher; or
- **(c)** compiler relaxed accuracy is equal or higher **and** its dollars per
  correct answer are lower.

If any of (a), (b) or (c) holds at either budget, stage 1 **passes**. A stage 1
pass **authorises the stage 2 run and nothing else**. It does not open
Phase 3.

If none holds, stage 1 **fails**: Phase 3 does not open, stage 2 is not run,
algorithm work pauses, and the per-question failure analysis comes first, as
the plan's Gate 2 requires.

"Higher" and "lower" compare point estimates with no margin. The structural
baseline is reported beside every figure and does not gate. A stage 1 pass
carried by one question at one budget is reported as exactly that. Condition (c)
is unlikely to discriminate on its own, because the contexts are budget-bound
and near-equal in size — 24,246 compiler tokens against 24,100 fixed at 4K —
so a cost difference would come from answer and judge length.

### Stage 2 — the corroborating run, preregistered separately

Stage 2 is the plan's Phase 2 task 3: generation over `xldev24` at 2K and 4K.
It gets its own preregistration, committed before it runs, and **Phase 3 opens
only if stage 2 corroborates stage 1**.

Fixed now, so stage 2's preregistration cannot relax them:

- **Same model, prompt, reasoning effort and output cap as this run.** A
  different model could not corroborate this result.
- **Corroboration means the same metric, in the same direction, at the same
  budget** as the condition that passed stage 1, against fixed RAG. A benefit
  that appears on a different metric or budget is a new finding, not a
  corroboration, and does not open Phase 3.
- Resumable per-cell persistence is in place.

One weakness is stated in advance. `xldev24` is the set the compiler
configuration was selected on. The selection used retrieval metrics, not
answers, so an answer-level result there is not circular, but it is weaker
corroboration than a fresh population would be. Stage 2's preregistration must
say so, and a Phase 3 decision resting on it must too.

## Departures from the plan, recorded

- **Phase 2 task 1** analyses "both guarded generation runs together". The
  earlier `xlholdout6b` run is **not** made. That holdout was inspected before
  its generation preregistration, so its result could inform but never confirm,
  and running it only to satisfy the plan's wording would spend money for a
  weaker answer. Phase 2 is analysed on this run, then on stage 2.
- **Gate 2** as the plan states it opens Phase 3 on a single six-question run.
  It is tightened here into two stages, before any answer exists.

## Registered command

```shell
uv run --frozen --extra generation contextbench eval-generation \
  artifacts/runs/xlholdout6c-gate1-60e5836 \
  --subset-file benchmarks/xl-docbench/subsets/xlholdout6c.json \
  --system fixed --system structural --system compiler \
  --budget 2048 --budget 4096 \
  --model gpt-6-astra \
  --reasoning-effort low \
  --max-output-tokens 512 \
  --citation-entailment-judge \
  --input-usd-per-million 10 \
  --cached-input-usd-per-million 1 \
  --output-usd-per-million 50 \
  --max-calls 72 \
  --expected-retrieval-artifact-sha256 02aef5206febbc4c3811e8caf9aad9a0a9da92729e7105aa3fd2c3e810b1aab0 \
  --run-id xlholdout6c-generation-astra
```

Run from a clean worktree, without `--allow-dirty`. `OPENAI_API_KEY` is supplied
through the local environment and is never committed.
