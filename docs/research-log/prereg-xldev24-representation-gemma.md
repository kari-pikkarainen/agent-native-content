# Preregistration: controlled representation experiment on xldev24, local Gemma

## Status

**Frozen 2026-09-26, before any answer of the registered run exists.** Every
decision below was made by the owner before the run:
- a free local model instead of a paid API;
- Gemma-4-12B after Qwen3.6-35B-A3B could not hold the largest prompts;
- all 18 questions rather than dropping the largest documents;
- a resumable run over two nights.

This record is not edited after the run. If something in it proves wrong, a
dated note below says so.

A two-question pilot (`xldev24-pilot2`) runs first, **after** this record is
committed. It is a pipeline check, not evidence; see "Pilot".

## Purpose

This is the first controlled test of the project's representation thesis:
content stored once in a structure-preserving Content IR, with agent-oriented
features, is more useful to an answering model than the same content as
extracted text.

Retrieval is removed from the comparison. Every evidence condition receives
the same annotated gold pages. The conditions differ only in how those pages
are encoded:

| Condition | What the model receives |
| --- | --- |
| `question_only` | No evidence. A control for questions answerable without the document |
| `raw` | Extracted source text of the gold pages |
| `ir` | The same pages as canonical Content IR |
| `enriched` | IR plus inline, bounded, query-independent agent features |
| `indexed` | IR plus a selectively retrieved view of the same features |

The comparison is between encodings of the same evidence, not between
equal-token contexts. The representations differ in size (raw is smallest,
enriched largest), and that difference is part of what is measured.

## Data

- **Subset:** `xldev24`, the 18 answerable questions with annotated gold pages.
  The 6 unanswerable questions have no gold pages and are not eligible.
- **Grade:** development data, so this result is **exploratory, not
  confirmatory**. `xldev24` was used to tune retrieval. The agent enrichment was
  developed on `xldev2-tables`, whose two questions (`adubench_single_000324`
  and `adubench_single_000703`) are among these 18. They are reported
  separately as well as in the totals.
- **Measured volume** (a no-call dry run at `72c7da1`, answer prompts only):
  - by the Gemma tokenizer: 4,387,866 input tokens across 90 answer calls;
  - largest single prompt: 190,772 tokens (`adubench_single_001102`, `enriched`).

## Model and serving, pinned

- **Model:** `lmstudio-community/gemma-4-12B-it-MLX-4bit`, Hugging Face revision
  `f45bda5639cf187cd5f127a5484813f5f1e3a6ad`.
- **Weight files (sha256):**
  - `model-00001-of-00002.safetensors`
    `47e8c872523dbdcd80f2fdca4953f3b1d027c9fca69f7c05338232732a3b5101`
  - `model-00002-of-00002.safetensors`
    `dd6fff693520d3e89ad07b9cf3db2369659485146ce13fda0bd7ad087c6acc7d`
- **Server:** LM Studio 0.4.25+1, engine `mlx-llm-mac-arm64-apple-metal-advsimd@1.11.0`.
  - Served model id: `gemma-4-12b-it-mlx`.
  - Loaded with a requested context of 200,000. The server's auto-fit made the
    effective context **214,272**, which holds every prompt plus the output cap.
  - Parallel 1.
- **Hardware:** Apple M3 Pro, 36 GB.
- **Enforcement:** the run records the served model id per call and refuses to
  resume against a different id. A different quantization served under the same
  id cannot be detected by the run. The weight hashes above are the pin, and
  they are re-checked before each night's session.

## Generation settings

Identical for every condition and both judges:

| Setting | Value |
| --- | --- |
| Endpoint | `--provider-base-url http://127.0.0.1:1234/v1`. Only a placeholder key is ever sent |
| Timeout | `--provider-timeout 3600`. The longest measured call took 1,889 s |
| Retries | `--provider-max-retries 0`. A failure is resumed, not retried |
| Temperature | `--temperature 0` |
| Seed | `--seed 20260926` |
| Maximum output | `--max-output-tokens 1024`. Gemma does not think by default, and measured answers took 102–126 output tokens |
| Reasoning effort | not set |
| Answer prompt | repository `answer-json-v1`, `prompt_sha256` `050d25fb1c866b01e732d09c67215c4f4c8cc4fa10a22b74174abec7c7d39bf4` |
| Judges | `--answer-equivalence-judge` and `--citation-entailment-judge`, the same model. Judge prompt hashes are recorded in the manifest |
| Pricing | 0 / 0 / 0 USD per million tokens. Local. Cost fields are therefore zero, and efficiency is read from tokens and latency |
| Call ceiling | `--max-calls 270` (18 × 5 × 3), checked before any call |

## Registered commands

The pilot runs first:

```text
uv run contextbench eval-representation \
  --subset-file benchmarks/xl-docbench/subsets/xldev24-pilot2.json \
  --condition question_only --condition raw --condition ir \
  --condition enriched --condition indexed \
  --model gemma-4-12b-it-mlx \
  --provider-base-url http://127.0.0.1:1234/v1 \
  --provider-timeout 3600 --provider-max-retries 0 \
  --temperature 0 --seed 20260926 --max-output-tokens 1024 \
  --answer-equivalence-judge --citation-entailment-judge \
  --input-usd-per-million 0 --cached-input-usd-per-million 0 \
  --output-usd-per-million 0 \
  --max-calls 30 \
  --run-id xldev24-pilot2-gemma4-12b
```

Then the registered run. The command is the same apart from the subset file,
`--max-calls 270` and the run ID. It is rerun unchanged to resume after an
interruption:

```text
uv run contextbench eval-representation \
  --subset-file benchmarks/xl-docbench/subsets/xldev24.json \
  --condition question_only --condition raw --condition ir \
  --condition enriched --condition indexed \
  --model gemma-4-12b-it-mlx \
  --provider-base-url http://127.0.0.1:1234/v1 \
  --provider-timeout 3600 --provider-max-retries 0 \
  --temperature 0 --seed 20260926 --max-output-tokens 1024 \
  --answer-equivalence-judge --citation-entailment-judge \
  --input-usd-per-million 0 --cached-input-usd-per-million 0 \
  --output-usd-per-million 0 \
  --max-calls 270 \
  --run-id xldev24-representation-gemma4-12b
```

Before each session, the worktree must be clean at the commit that adds this
record, or at a later commit that changes nothing under `src/`. The run records
its commit, and it refuses to resume across code changes.

## Pilot

The pilot is the two questions with the smallest and the largest
representation: `adubench_single_000266` and `adubench_single_001102`. Its
purpose is only to exercise the pipeline end to end:
- the long timeout;
- both judges on this model, and whether they return parseable output;
- memory on the largest prompt;
- one deliberate interruption and resume.

**What the pilot may change:** only defects in the pipeline, such as a crash, a
parse failure caused by output formatting, or a timeout. Any such fix is
committed and recorded as a dated note here before the registered run.

**What it may not change:** no setting above (model, sampling, prompt, output
cap, conditions, judges, questions) may change because of the pilot's answers or
scores. Its two questions are answered again in the registered run, and only
those answers count.

## Metrics

All come from the run's `summary.json` and records, per condition:

1. **Semantic accuracy.** The answer-equivalence judge sees only the question,
   the reference answer and the candidate answer, never the condition or the
   evidence. Deterministic exact accuracy is reported beside it.
2. **Citation entailment.** Measured over non-abstaining answers with valid
   citations, and read together with the answer rate.
3. **Abstention rate** (the exact `INSUFFICIENT_EVIDENCE` marker), and answer
   rate.
4. **Answer and judge validity rates.**
5. **Answer-only input tokens and latency.** This is the efficiency comparison.
   Judge calls are excluded from it.

### Question-only control

Before any comparison between representations, each question is classified by
`question_only`'s answer: correct, incorrect, abstained or invalid. Every
comparison below is reported twice:
- (a) on all 18 questions;
- (b) on the questions that `question_only` did **not** answer correctly.

Claims about representation quality rest on (b).

## Hypotheses and decision rule

Stated before the run. With 18 questions or fewer, every difference is a count
of questions, and it is reported as per-question wins and losses against `raw`
(semantic accuracy, and citation entailment where both answered). No
significance claim is made.

- **H1.** `ir` has a higher semantic accuracy than `raw` on set (b).
- **H2.** `enriched` or `indexed` has a higher semantic accuracy than `ir` on
  set (b).
- **H3.** On citation entailment, the structured conditions are no worse than
  `raw`.
- **H4, cost.** The structured conditions spend more answer-input tokens than
  `raw`. Any accuracy gain is reported per extra 1,000 input tokens.

**Directional support** for the thesis requires both of these:
- at least one of `ir`, `enriched` or `indexed` wins against `raw` on at least
  **2 more questions than it loses**, on set (b), by semantic accuracy;
- that condition's citation entailment is not lower than `raw`'s.

**If there is directional support:** the next step is a new, untouched document
subset, run before any expansion to other formats.

**If there is not:** document-format tuning stops, and the tabular-data pilot
comes next, as set out in the agent-native thesis plan. There, explicit
machine-oriented structure has a stronger theoretical advantage.

Either outcome is recorded as development evidence, not as a claim about unseen
documents.

## Judge audit

The judges are a 12B local model, weaker than a frontier judge, so they are
checked before the results are interpreted.

- **Answer-equivalence judge:** from the registered run, 20 of its verdicts are
  drawn by `sha256("20260926:" + question_id + ":" + condition)` order, and each
  is checked by hand against the reference answer.
- **Citation-entailment judge:** 10 of its verdicts are checked the same way.

Agreement is reported. If agreement with the hand check is below 80% for either
judge, that judge's metric is reported as unreliable. The decision rule then
falls back to deterministic accuracy, with the reason recorded.

## Known limitations

- 18 questions, one model, one prompt, one sampling setting. Development data.
- The same weak model answers and judges. Its errors affect every condition,
  but not necessarily equally.
- A local 4-bit quantization. Results may not transfer to frontier models.
- Representations differ in length, so a gain may come from length rather than
  structure.
