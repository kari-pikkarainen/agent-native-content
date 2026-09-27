# Controlled representation experiment on xldev24, local Gemma

Date: 2026-09-26

Run: `xldev24-representation-gemma4-12b`, published under
[`results/representation/xldev24-gemma4-12b`](../../results/representation/xldev24-gemma4-12b/report.md).
The run's `contexts.jsonl`, 11 MB of rendered source pages, is not published.

Judged against [the preregistration](prereg-xldev24-representation-gemma.md)
and its three dated notes. All of them were written before any answer of this
run existed.

## Provenance

The manifest records:
- commit `b3d53c0` with a clean worktree;
- served model `gemma-4-12b-it-mlx` only; weight hashes were checked against the
  preregistration before the run;
- `evidence-render-v3`, answer `prompt_sha256` `af70aa5e…`;
- temperature 0, timeout 3,600 s, 0 retries.

The run completed uninterrupted (`resumed: false`): 90 answer cells plus judge
calls. Every setting matches the corrected registered command.

## The verdict

**No directional support for the representation thesis on this data.** The
preregistered rule required a structured condition to win against `raw` on at
least two more questions than it loses, with citation entailment no lower. No
condition comes close.

| Condition | Semantic accuracy | vs `raw` (wins/losses) | Answer-input tokens | Answer latency |
| --- | --- | --- | --- | --- |
| `question_only` | 0/18 | — | 121 | 3 s |
| `raw` | **6/18** | — | 14,888 | 84 s |
| `ir` | 5/18 | 1 / 2 | 28,628 | 171 s |
| `enriched` | 5/18 | 0 / 1 | 36,023 | 218 s |
| `indexed` | 6/18 | 2 / 2 | 30,429 | 181 s |

Hypotheses:
- **H1** (`ir` beats `raw`): not supported.
- **H2** (enrichment beats `ir`): not supported. `enriched` against `ir` is 2–2;
  `indexed` against `ir` is 2–1.
- **H3** (structured citation entailment no worse than `raw`): fails for
  `indexed`. Where both answered, `indexed` loses 5 questions and wins none
  (mean −0.56); `enriched` −0.14; `ir` +0.17 on 6 questions.
- **H4** (structure costs tokens): confirmed. The structured conditions use
  1.9–2.4× `raw`'s input tokens and 2.0–2.6× its latency, for no accuracy gain.

As the preregistration directs: **document-format tuning stops, and the
tabular-data pilot is next.**

## Other preregistered reports

- **Question-only control.** All 18 `question_only` answers were invalid:
  Gemma replied in prose asking for the evidence. So no question is excluded
  as answerable without the document, and set (b) is all 18. The control
  measured instruction-following, not leakage.
- **Validity and abstention:**

  | Condition | Valid answers | Abstained | Answered |
  | --- | --- | --- | --- |
  | `raw` | 94% | 44% | 50% |
  | `ir` | 72% | 39% | 33% |
  | `enriched` | 89% | 33% | 56% |
  | `indexed` | 94% | 44% | 50% |

- **`N`/`F` citation diagnostic:** `indexed` cited 4 `N` or `F` refs, which
  score invalid. The other conditions cited none.
- **`xldev2` questions:**
  - `adubench_single_000324`: every condition wrong.
  - `adubench_single_000703`: `raw`, `ir` and `enriched` right; `indexed` wrong.
  - The enrichment's own development questions show no advantage for it.

## Judge audit

Hand-checked in the preregistered hash order.

- **Answer-equivalence judge: 16 of 20 agree (80%)**, exactly the threshold, so
  it is reported as reliable. All four disagreements are false positives, and
  all four favour structured conditions:
  - two hedged answers that deny knowing the answer (`enriched` and `ir`,
    `adubench_single_000505`);
  - one answer missing one of two required equations (`indexed`, `000283`);
  - one answer that never states the number asked for (`indexed`, `000282`).
- **Citation-entailment judge: 9 of 10 agree (90%).** The one disagreement
  credited `indexed` with support the cited table does not contain. Two of the
  agreements rest on excerpts of the cited text.

## Sensitivity, post hoc, not the decision

The invalid answers are Gemma format errors, and they are uneven across
conditions:
- JSON without a `citations` key;
- a malformed `citations(` field;
- a leaked `<|channel>thought` template token;
- text after the closing fence;
- one runaway answer to the output cap.

Hand-grading their readable answers, and applying the four judge corrections:

| Condition | Correct | Net vs `raw` |
| --- | --- | --- |
| `raw` | 6 | — |
| `ir` | 6 | 0 |
| `enriched` | 6 | 0 |
| `indexed` | 4 | −2 |

The conclusion does not change under the most generous reading.

## What this does and does not show

- **It shows:** for a 12B local model given the exact gold pages, encoding them
  as Content IR, with or without agent features, bought no accuracy over plain
  extracted text. It cost about twice the tokens and latency. The richest
  encoding (`indexed`) had the least well-supported citations.
- **It does not show** that structure never helps:
  - 18 development questions, one small model, one prompt;
  - a weak model may not exploit structure a frontier model could;
  - the structured encodings are longer, and that may itself hurt a small
    model's long-context reading.
- **For the compiler:** its selection advantage (more gold pages per budget)
  stands on retrieval evidence. This result says that rendering the selected
  evidence as IR is not, on this evidence, worth its tokens. A compiler that
  selects with IR but renders compact text is the conservative default until a
  stronger test says otherwise.

## Known weaknesses

- 18 questions, development-grade, and the enrichment was developed on two of
  them.
- One local 4-bit model answers and judges. The judge's four false positives
  all favoured structured conditions, so the reported numbers slightly flatter
  them.
- The question-only control was uninformative: every answer was invalid.
- Three dated pipeline fixes (seed, bare marker, short labels) were made after
  the pilot and before this run. Each is recorded in the preregistration.
