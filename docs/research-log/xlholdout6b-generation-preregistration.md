# XLHoldout6b guarded generation preregistration

## Status

Frozen before any provider call. The run is waiting for local API credentials.

## Purpose

Test whether the low-budget retrieval differences produce better answers and
semantically supported citations. This is a six-question diagnostic over a
previously inspected holdout, not a fresh confirmatory evaluation.

## Fixed inputs

- Retrieval run: `xlholdout6b-metric-audit-bc57f17`
- Retrieval commit: `bc57f17d9d1a4d3a25689c30f88ea2333bd2f525`
- Questions: all six registered XLHoldout6b questions
- Systems: `fixed`, `structural`, and `compiler`
- Budgets: 2,048 and 4,096 tokens
- Context cells: 36
- Saved context tokens: 109,794 before answer-prompt framing
- Prompt: repository `answer-json-v1`, identical across systems
- Answer model: `gpt-6-astra`
- Reasoning effort: `low`
- Maximum output: 512 tokens per call
- Citation judge: enabled, using the same model and frozen pricing
- Maximum calls: 72 (36 answers plus at most 36 citation judgments)

The judge sees the question, generated answer, and cited evidence only. It does
not see the gold answer. Missing citations score zero without a judge call;
invalid judge JSON also scores zero.

## Frozen pricing and spend envelope

Pricing is frozen from the official OpenAI model page as accessed on
2026-09-20:

- input: $10.00 per million tokens;
- cached input: $1.00 per million tokens; and
- output, including reasoning tokens: $50.00 per million tokens.

Source: <https://developers.openai.com/api/docs/models/gpt-6-astra>

If every judge repeats an entire source context, context text contributes at
most 219,588 input tokens before prompt framing. The absolute configured output
ceiling is 36,864 tokens across 72 calls. At the frozen uncached prices these
two components cost about $4.04. The operational authorization envelope is
$5.00 to allow for questions, instructions, evidence tags, and judge framing.
The CLI hard-enforces the 72-call ceiling; the $5 envelope is a conservative
pre-run estimate, not a provider-side spend lock.

## Primary metrics

1. relaxed benchmark accuracy;
2. same-model citation entailment;
3. dollars per correct answer; and
4. end-to-end latency per answer, including the judge where invoked.

Token F1, ANLS, citation-ID validity, gold-page alignment, provider token
usage, and response validity are secondary diagnostics.

## Decision rule

Proceed to the RAW-versus-IR gold-evidence generation experiment only if the
compiler shows a directional answer-accuracy or citation-entailment benefit at
2K or 4K, or comparable answer quality at lower realized cost. Do not add a
second answer model or higher budgets based on this six-question diagnostic
alone.

If the compiler's retrieval gains do not translate to answer or citation
benefits, pause algorithm expansion and inspect per-question failures first.

## Registered command

```shell
uv run --frozen --extra generation contextbench eval-generation \
  artifacts/runs/xlholdout6b-metric-audit-bc57f17 \
  --subset-file benchmarks/xl-docbench/subsets/xlholdout6b.json \
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
  --run-id xlholdout6b-generation-astra
```

`OPENAI_API_KEY` must be supplied through the local environment and must not be
committed to the repository.
