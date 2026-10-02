# Project Status and Decision History

This page is the detailed record that used to open the README. It is kept
verbatim, with its links adjusted and acronyms expanded on first use, so that the README can stay short. Read it
after the [README](../README.md) when you want the full account of what was
measured, what passed, what failed, and why.

The authoritative chain of decisions, each pinned to a commit, is the
"Start here" list in the [research log](research-log/README.md). The compact
published evidence is in [`results/`](../results/README.md).

## Status narrative

**Gate 1 passed on its one run of the `xlholdout6c` holdout — on page recall,
the metric it was preregistered on. On exact quote recall the same run points
the other way**: the compiler trails fixed retrieval-augmented generation (RAG) at every budget, with the
interval excluding zero at 4K and 16K. Both are in
[the Gate 1 decision](research-log/gate1-xlholdout6c-60e5836.md). The
frozen configuration and its development evidence are in the
[Phase 1 close-out](research-log/phase1-closeout-c7e56fa.md).

**The first answer-generation test then failed.** On the same six holdout
questions, with `gpt-6-astra` answering from each arm's saved contexts, the
compiler's answers were no better than fixed RAG's at either budget: accuracy
0.167 against 0.333 at 2K and 4K, citation entailment 0.333 against 0.500 at 2K
and level at 4K. Under the
[preregistered rule](research-log/prereg-xlholdout6c-generation.md) that
closes Gate 2 at its first stage: Phase 3 does not open and algorithm work
pauses for a per-question failure analysis. Each difference is one question.

**The failure analysis then showed the run carries no signal about evidence
quality in either direction.** The accuracy difference is a question
answerable from its own text, where the arms differed only in whether the
model was willing to answer; the citation difference is an abstention credited
as supported. The analysis also found four defects in the generation
instrument that must be fixed before another run, and one real mechanism: on
poorly parsed documents the compiler packs hundreds of fragments of a few
tokens each, which empties its candidate pool, multiplies the prompt, and
leaves the model declining to answer. It affects 5 of 24 development questions
and 1 of 6 holdout questions. See
[the Gate 2 decision](research-log/gate2-stage1-xlholdout6c-generation.md)
and [the failure analysis](research-log/gate2-failure-analysis.md).

The run also exposed a token-accounting problem. Although the compiler obeyed
the configured packed-content budget, its many small evidence items each added
prompt framing. Its nominal 2K context therefore produced an average 6,279-token
model input, larger than fixed RAG's 5,150-token input at a nominal 4K budget.
This overhead must be included in the failure analysis and in any future budget
comparison.

It now is. Since `f916545` every arm is charged for the evidence it renders
(tags, aliases and separators as well as content), with short `E1`-style
aliases. On the development set this costs the compiler 7 points of page
recall at 2K and at most 1.5 points above that. The non-inferiority screen
against fixed RAG now fails at 16K. The figures in the table below predate
that change and use content-only accounting. See
[the re-baseline record](research-log/stepc-rendered-budget-merge-f916545.md).

**The controlled representation experiment is also complete.** Gemma-4-12B
received the same annotated gold pages as compact text, Content IR (intermediate representation), enriched
IR, and query-selected agent features. Raw text answered 6 of 18 questions
correctly; IR and enriched answered 5, and indexed answered 6. The structured
conditions used 1.9–2.4 times the input tokens and 2.0–2.6 times the latency,
without meeting the preregistered improvement rule. This is evidence against
presenting the current document IR directly to this model, not against using
structure internally for selection. See the
[preregistration](research-log/prereg-xldev24-representation-gemma.md)
and [result](research-log/representation-xldev24-gemma-b3d53c0.md).

The frozen compiler leads the best RAG baseline on **page** recall on the
24-question development set at every tested budget. On **exact quote** recall
it leads at three of four budgets and trails at 2K, and the difference between
those two statements is the most important thing on this page.

| Budget | Dev compiler | Dev best RAG | Holdout compiler | Holdout best RAG |
| ---: | ---: | ---: | ---: | ---: |
| 2K | **0.718** | 0.533 | **0.513** | 0.425 |
| 4K | **0.806** | 0.634 | **0.626** | 0.565 |
| 8K | **0.860** | 0.739 | 0.815 | **0.856** |
| 16K | **0.888** | 0.843 | 0.935 | **1.000** |

Values are mean gold-evidence page recall at the stated context budget. The
development set has 24 questions over 11 documents; the directional holdout
has six questions over six previously unused documents. No answer model was
used for these results. The holdout columns are `xlholdout6b`, which predates
both the Phase 1 fixes and the freeze and was not re-run. The Gate 1 holdout,
`xlholdout6c`, is reported separately below, because it was run once at the
frozen configuration and is not comparable with these columns.

On `xlholdout6c`, answerable page recall, compiler against fixed RAG: +0.087
at 2K, +0.162 at 4K, +0.093 at 8K and +0.064 at 16K, every interval including
zero. Exact quote recall on the same run: −0.108, −0.192, −0.108 and −0.233,
excluding zero at 4K and 16K. Six questions; screening, not confirmation.

Exact quote recall over the same development run, on the 18 questions that
carry gold quotes:

| Budget | Dev compiler | Dev best RAG |
| ---: | ---: | ---: |
| 2K | 0.213 | **0.259** |
| 4K | **0.333** | 0.259 |
| 8K | **0.375** | 0.361 |
| 16K | **0.444** | 0.403 |

Against fixed RAG the compiler's exact-quote interval includes zero at 2K, 8K
and 16K and excludes it only at 4K. Against structural chunks at 2K the point
estimate is −0.046 with an interval of [−0.123, +0.018]: no longer measurably
worse, as it was before the freeze, but not shown better either. The
compiler's demonstrated advantage on this benchmark is a page-selection
advantage; an exact-evidence advantage has not been established.

Quote recall has a ceiling well below 1.0 that no arm can pass. Of 46
development gold quotes, 26 do not occur in their own document's parse, most
because the gold string is not a verbatim transcription — a heading and list
joined with a colon, a table read across cells — and three because the gold
quote itself contains optical character recognition (OCR) errors. Quote figures here are scored under match
policy `nfkc-unified-punctuation-ordered-elision-v3` and are not comparable
with figures scored under an earlier policy.

The frozen configuration turns sibling expansion on, which is worth +0.019
quote recall across budgets, and keeps page-neighbour expansion, which is
worth little quote recall but is what holds the compiler inside the
preregistered −3 percentage-point (pp) non-inferiority margin against fixed RAG at 16K. It holds
there by 0.0002, which is a pass under the rule and inside bootstrap noise.

The latest policy experiments explain much of that split. Coverage-aware
packing deliberately spreads the context across more potentially relevant
pages. That raises page recall but often lowers exact quote recall because the
selected node may touch the right page without containing the decisive span.
The effect appears across fixed chunks, structural chunks, and IR nodes, and is
strongest for the IR. A budget-adaptive alternative reduced the quote deficit
but lost page recall, so it was rejected under its preregistered rule.

The development figures come from the 2026-09-23 run at the frozen
configuration, after Phase 1's three correctness fixes; the holdout figures
predate both and were not re-run, because re-running a holdout to keep a table
tidy would spend it. The largest of those fixes repaired IR reading order, and it moved the fixed baseline
hardest: that arm had been building windows from a token stream in which 40.9
per cent of items were appended out of document order. Its page recall
*fell* when this was fixed, because a window splicing two distant pages was
credited with both, and its quote recall rose. The margin on this page is
therefore narrower than it was before the 2026-09-22 re-baseline, and the
reasons are recorded rather than absorbed. At 2K on the holdout the paired interval
against fixed RAG is [+0.033, +0.233], and at 16K it is [−0.121, −0.017],
so both the low-budget win and the high-budget loss exclude zero.

Read this table with the page-recall caveat under
[known limitations](#known-limitations): on the matched factorial the IR unit
leads on page recall far more consistently than on exact quote recall.

See the canonical
[frozen development report](../results/retrieval/xldev24-phase1-frozen/report.md),
[Phase 1 close-out](research-log/phase1-closeout-c7e56fa.md),
[holdout report](../results/retrieval/xlholdout6b-rebaseline/report.md),
[corrected content-unit factorial](../results/factorial/xldev24-content-policy-corrected/report.md),
[packing-policy decision](research-log/adaptive-packing-decision-3b77e75.md),
[expansion ablations](research-log/phase1-ablations-6cc7fd9.md), and
[results index](../results/README.md) for the full evidence and caveats. An
earlier six-question holdout mostly rejected the preceding compiler
configuration and remains published as superseded negative evidence.

**Decision:** retain the compiler as a credible low-budget page-selection
treatment, but do not claim that it replaces RAG or improves end-to-end answer
quality. Pause algorithm expansion and the larger XL100 run while the
per-question failure analysis examines missing exact evidence, budget
under-fill, context fragmentation, and prompt-framing overhead.

## Known limitations

- The current comparison supports the complete compiler pipeline, not the IR
  as an isolated cause. Query faceting, structural expansion, keyed joins, and
  coverage packing are also unique to the compiler treatment.
- Page recall can over-credit partial chunks from multi-page nodes, and the
  selected packer explicitly rewards new-page coverage. Exact quote evidence
  is substantially less favorable and should be treated as co-primary.
- The independent holdout is small and directional; the full XL100 has not
  been run with the selected compiler.
- Development and holdout questions are single-document tasks with the relevant
  document scope supplied. Cross-document routing and another dataset remain
  untested.
- Six development questions have no annotated gold pages and therefore receive
  the protocol's identical vacuous-success score in every arm. Answerable-only
  and quote-eligible summaries are now computed and rendered alongside the
  aggregate, and answerable-only eligibility now requires both the answerable
  flag and at least one annotated gold page, so a question with no gold pages
  is excluded from those columns and from the paired intervals even when it is
  marked answerable. No question in the current release is unanswerable with
  annotated gold pages, so the answerable-flag half of that conjunction moves
  no number today; it keeps the `answerable_*` fields meaning what they are
  named if a future release annotates such a question. The vacuous score is
  still recorded per question and still enters the all-questions aggregate,
  which this change deliberately leaves unchanged. The correction moves no
  `xldev24` number, where all six zero-gold-page questions are already excluded
  as unanswerable; one XL100 question (`adubench_single_001199`) is answerable
  with no gold pages and was previously counted. The canonical development and
  holdout reports predate both this reporting and this fix; only the
  [metric-audit rerun](../results/retrieval/xlholdout6b-metric-audit/report.md)
  publishes the answerable-only tables, and its numbers do not move:
  `xlholdout6b` contains no zero-gold-page and no unanswerable-with-gold-page
  question, so recomputing that run's `summary.json` from its own records under
  the new eligibility reproduces the published file byte for byte. Its
  `report.md` keeps the legend wording of the run that produced it.
- End-to-end answer quality has been measured only once, on six questions with
  one answer model. That preregistered run was negative: the compiler answered
  one question correctly at each budget while fixed RAG answered two, and the
  compiler did not improve citation entailment.
- Packed-content tokens are not the same as model-input tokens. On the Astra
  run, per-item evidence framing expanded the compiler's nominal 2K packet to
  6,279 input tokens on average and its nominal 4K packet to 11,657, versus
  3,052 and 5,150 for fixed RAG. Future comparisons must either budget the
  rendered prompt or report both quantities as co-primary resource measures.
- Compiler retrieval remains slower. A within-process measurement with caches
  cleared before each call put it at 2.29×, 2.32×, 2.40×, and 3.92× fixed RAG
  from 2K through 16K, missing Phase 1's 2× target. Pair-level score reuse can
  help a repeated direct-compilation workload, but it changes model batch
  composition and can change near-tied rankings, so it is off by default. The
  remaining 16K cost is dominated by page-neighbour reranking and is a
  selection tradeoff rather than a free caching optimization.
- The holdout still rejects high-budget dominance. After the re-baseline the
  compiler loses to fixed RAG at 16K by 0.065 page recall, with a paired
  interval of [−0.121, −0.017] that excludes zero, so this is now a measured
  loss rather than a directional one. Against structural chunks it still leads
  at 16K, so the problem is specifically fixed windows.
- Page recall over-credits the compiler, and the size is now measured. On the
  corrected full development factorial IR nodes beat the better chunk unit in
  seven of eight matched cells on page recall and two of eight on exact quote
  recall, never by more than 0.014 on the latter. Phase 1 sharpened this:
  before the freeze the compiler was measurably behind structural chunks on
  exact evidence at 2K while leading on pages. The frozen configuration's
  sibling expansion removes that — the 2K interval now includes zero — but it
  does not reverse it, and against fixed RAG the exact-quote interval still
  includes zero at 2K, 8K and 16K.
- Quote recall cannot reach 1.0 for any arm. Of 46 development gold quotes, 26
  do not occur in their own document's parse, mostly because the gold string
  is not a verbatim transcription, and three contain OCR errors of their own.
  Those are recorded, not repaired, because the gold data must not change. See
  [the Phase 1 close-out](research-log/phase1-closeout-c7e56fa.md).
- Page recall can also over-credit a *baseline*, which Phase 1 demonstrated
  directly. Before the IR reading-order repair the fixed arm's windows spliced
  distant pages together and were credited with all of them: identical window
  counts, but 2.43 distinct pages per window instead of 1.82. Fixing it lowered
  that arm's page recall and raised its quote recall. See
  [the Phase 1 record](research-log/phase1-correctness-fixes-9110e70.md).
- Agent enrichment is deterministic and mostly extractive. It is not a
  semantic knowledge graph or an abstractive document rewrite.
- On the two-question representation diagnostic, IR used about 49% more tokens
  than raw text and bounded enrichment about 91% more. Those costs require a
  meaningful answer or citation improvement to be justified.
- Charts, diagrams, and image-only evidence are not yet represented beyond
  what the parser exposes as text and structure.
- Current experiments use English PDFs, local retrieval models, and a single
  benchmark release; generalization is unknown.

## Decision history and next step

**Gates 0 and 1 have passed**, recorded in
[the Gate 0 decision](research-log/gate0-rebaseline-67aef47.md) and
[the Gate 1 decision](research-log/gate1-xlholdout6c-60e5836.md). The
gate after them, **Gate 2** of the
[improvement plan](plans/2026-09-21-improvement-plan.md), asked whether
better evidence selection produces better answers, and its first stage
**failed**: see
[the Gate 2 decision](research-log/gate2-stage1-xlholdout6c-generation.md).
The Gate 0 account below is kept as it was recorded.

Gate 0 asked whether the low-budget advantage on this page was real or an
artifact of broken measurement. It is real. It survived nine defect fixes,
including two the code review did not find: the dense channel held a copy of
the BM25 lexical-search zero-score defect, and the structural baseline could not retrieve on
its own heading vocabulary, which had been handicapping a baseline rather than
the treatment. On the remeasured `xldev24` the paired source-cluster interval
for the compiler against both RAG baselines excludes zero at 2K and at 4K,
which is the condition the gate was stated on.

The re-baselined results are published under
[`results/`](../results/README.md) and the four earlier ones are marked
superseded there, with the reason. Every figure on this page that predates
them has been replaced or removed. The new runs are the first in this project
reproducible from a config and a SHA: their manifests record a clean worktree
and both model weights pinned to a resolved commit.

The gate also narrowed the claim in three ways worth stating alongside it:

- **Page recall over-credits the compiler.** On the corrected full development
  factorial IR nodes beat the better chunk unit in seven of eight matched cells
  on page recall and two of eight on exact quote recall. Coverage packing raises
  page recall and lowers quote recall across all three content units. The gate
  was stated on page recall and passed on it; this is a screening result, not a
  validation.
- **The holdout loss at 16K is now measured.** The compiler loses to fixed RAG
  there by 0.065 page recall with an interval excluding zero. The development
  set and the holdout disagree at that budget, which is why a holdout exists.
- **The heading tax is real on page recall and was not worth taking.** Joining
  heading trails into node search text costs the IR unit between 2 and 5 points
  of page recall at every budget. Phase 1 tested removing it on the full
  pipeline and **rejected the change**: page recall improved at all four
  budgets, but exact quote recall did not, and the preregistered rule required
  both. The effect rests on two of eighteen questions, which `xldev24` cannot
  separate from noise. See
  [the ablation record](research-log/compiler-heading-free-edd196f.md).

**Phase 1 is complete and its configuration is frozen.** Its three correctness
fixes are
[delivered and measured](research-log/phase1-correctness-fixes-9110e70.md).
Heading-free retrieval and budget-adaptive packing were both tested and
rejected under rules written before their results were known. The corrected
factorial and D1–D4 expansion ladder are complete.

The node-boundary failure analysis found that most "right page, missing quote"
cases are not selection failures at all: the gold quote is not a verbatim
string in the parse. Of the remaining effect, sibling expansion is the
operator that recovers exact evidence, and the frozen configuration turns it
on. The latency target of at most twice fixed RAG was measured and **not met**;
the owner ruled that a documented limitation rather than a Gate 1 blocker,
because the Gate 1 rule was preregistered without a latency clause.

**Gate 1 has passed**, on one run of `xlholdout6c` against the commit,
configuration, quote policy and model revisions pinned in
[the close-out](research-log/phase1-closeout-c7e56fa.md) before it existed.
The compiler's page-recall point estimate against fixed RAG is positive at all
four budgets and no interval lies below the −3 pp margin, which is what the rule
asks. Every one of those intervals also includes zero, and on exact quote
recall the same run has the compiler behind fixed RAG at every budget. The
[Gate 1 decision](research-log/gate1-xlholdout6c-60e5836.md) records both,
and two mechanisms behind the second: the compiler reaches the right pages
while missing the quoted spans on them, and in some packets it stops filling
its budget where fixed RAG does not.

**Gate 2 failed at its first stage.** The
[preregistered](research-log/prereg-xlholdout6c-generation.md)
answer-generation run over the holdout's saved contexts found the compiler's
answers no better than fixed RAG's at 2K or 4K, and the hypothesis stated
before the run — that contexts with fewer exact quoted passages would not
produce better-supported citations — held. As preregistered, the larger
`xldev24` generation run is not made, Phase 3 does not open, and algorithm work
pauses.

**The failure analysis is done**, and it changes what Gate 2 can be taken to
show. [It found](research-log/gate2-failure-analysis.md) that the run
measured the answer model's willingness to answer rather than the quality of
the evidence: the deciding question was answerable from its own text, and the
deciding citation was an abstention scored as supported. It is therefore not
evidence for stopping, and not evidence for continuing.

The four instrument defects were fixed: semantic answer equivalence is scored
separately, citation entailment skips abstentions, question-only is an explicit
control, and valid answers and abstentions are reported separately. Rendered
prompt overhead is now charged to every retrieval arm. The fragmentation
mechanism remains a real compiler limitation, but the next controlled test
isolated a more fundamental question: whether the persistent document
representation itself helps an answer model.

It did not in the first controlled run. With identical gold pages, local
Gemma-4-12B produced 6 correct answers from raw text, 5 from IR, 5 from enriched
IR and 6 from indexed enrichment. Structured encodings used roughly twice the
tokens and latency. The answer judge's four audited errors all favoured the
structured conditions, and a generous manual regrade still left the best
structured condition tied with raw. Under the preregistered rule,
document-format tuning stops. The narrow retrieval result that remains is a
low-budget **gold-page-recall** advantage; exact-quote and answer-quality
superiority have not been established.

### Next experiment: agent-native tabular data

The active next step is a small, preregistered tabular-data pilot, where
explicit machine-oriented structure has a clearer potential advantage than
adding markup around long document text. It compares identical authorized
source rows under three conditions:

- compact CSV or plain table text;
- a typed schema with column meanings, units, keys and null semantics; and
- an agent-native representation adding formula dependencies, relationships,
  reusable summaries and cell-level provenance.

The task set covers filtering, aggregation, joins, unit conversion, formula
tracing and provenance. Answers use deterministic ground truth and constrained
JSON so formatting failures do not masquerade as reasoning failures. The run
reports both the natural cost of representing identical data and performance
under an equal input-token budget.

The implementation order was revised on 2026-10-01 to keep the next spend
experimental. First freeze the dataset, task oracle, renderers, model, metrics,
manual audit and paired stopping rule. Then implement only the preparation-cost
measurement and XLSX decoding required by the development pilot. Producer
metadata, cross-version identity, Markdown ingestion, the untouched tabular
holdout and the prepare-once break-even experiment are conditional on that
development gate showing a material benefit. See the
[device-side preparation plan](plans/2026-10-01-device-side-preparation-plan.md).

**Implementation status:** no tabular pilot code or measured tabular result
exists yet. The preparation ledger, XLSX decoder, producer-policy fields, v2
identity scheme and Markdown decoder are all planned, not implemented. The
first deliverable is the committed preregistration, not an infrastructure
phase.

Until the tabular development gate shows a gain, the conservative document
pipeline is to use IR internally for organization and selection while
rendering compact text to the answer model.

`xlholdout6c` was frozen and
[recorded](research-log/xlholdout6c-freeze.md) with all six sources
preflight-verified, and has now been run once, at Gate 1, with the
configuration chosen on `xldev24`. It is spent: it is not run again and is
never tuned on.

The earlier exploratory generation proposal for the already-inspected
`xlholdout6b` holdout remains intentionally unrun. The `xlholdout6c` Astra
failure analysis is complete, the generation instrument defects it exposed
have been fixed, and the subsequent controlled representation experiment was
negative. Neither spent document holdout is reused for the tabular decision.
