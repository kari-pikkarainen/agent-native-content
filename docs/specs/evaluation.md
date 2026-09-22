# Evaluation Protocol

This protocol is fixed before inspecting the first XL100 retrieval results. It
tests evidence selection only: no answer-generation model, LLM planner, or
generated answer metric participates in this milestone.

## Development dataset

Milestone 1 pins the conservative XL-DocBench release as follows:

- dataset: `microsoft/XL-DocBench`
- release: `xldocbench_strict_1345_v1`
- revision: `72954bd70ffffe230f08b57c57fa9274ec14d7ea`
- evidence pages: one-based PDF/release indices

The tuning subset is the explicit ordered list in
`benchmarks/xl-docbench/subsets/xldev24.json`. It contains 24 questions selected only from
release metadata and source-availability checks: four single-document questions
per domain, including six unanswerable and six table/chart/image questions. It
is disjoint from XL100. The selection minimizes added source pages and bytes,
excludes documents over 300 pages, and requires every pinned source to pass PDF
availability and integrity preflight so development runs remain practical.
Cross-document questions remain in the held-out XL100 evaluation rather than
expanding the development corpus with dozens of additional and frequently
stale mirrors.

`benchmarks/xl-docbench/subsets/xl100.json` remains the held-out final retrieval evaluation:
100 questions balanced across all six domains, including 80 single-document
and 20 cross-document questions. The earlier XL10 smoke subset has already
informed implementation decisions and is therefore only a regression set, not
a final evaluation set. Benchmark commands load every committed list exactly
as stored and never regenerate one implicitly.

By default, the command downloads only the pinned metadata release and source
PDFs referenced by the selected evaluation subset. A diagnostic may instead
declare a parent retrieval-corpus subset while evaluating fewer contained
questions. In that mode, all parent-corpus documents are indexed so BM25
statistics and dense candidate competition match the parent run. Each PDF is
size-checked against the release record, content-addressed, parsed through the
local Docling pipeline, and projected to the deterministic IR. A manifest
records both subset hashes and ordered question lists plus each source and
parser identity.

## Systems and controlled variables

The comparison includes:

- `fixed` (Arm A): 512-token windows with 64-token overlap;
- `structural` (Arm B): Docling HybridChunker structural chunks;
- `long_context` (Arm C): relevant source documents in original node order,
  with no query-time retrieval or reranking;
- `compiler` (Arm D): IR-node retrieval, deterministic structural expansion,
  provenance-aware deduplication, and budget packing.

Arms A, B and D share the same tokenizer, BM25 parameters, brute-force dense
similarity, embedding model, reciprocal-rank fusion parameters, candidate
limits, and reranker. Arm C intentionally performs no retrieval: it uses the
same tokenizer and exact source-document scope, then packs source-derived body
nodes in their original order. The compiler's structural expansion and packing
policy is the treatment under test. Indexes and the Arm C source projection are
built once before query timing.

The selected compiler also applies deterministic lexical query faceting. Every
facet uses the same shared retrieval models and is fused back to the original
candidate capacity; no LLM query generation is used. Facet retrieval time is
included in compiler latency.
The full query and facet candidate pairs are scored in one cross-encoder batch;
this preserves the independently reranked facet lists and their fusion while
amortizing model invocation overhead.

For queries that explicitly name multiple tables, the selected compiler may
also construct bounded keyed-row joins. These use exact normalized identifiers
from source-derived model/dataset columns, preserve both tables' provenance,
and use the shared reranker. No LLM or fuzzy entity matcher participates.

The preregistered budgets are 2,048, 4,096, 8,192, and 16,384 tokens. The CLI
defaults to `BAAI/bge-small-en-v1.5` and
`cross-encoder/ms-marco-MiniLM-L-6-v2`; both model IDs are configurable and the
resolved IDs and implementation versions are recorded. The seed is recorded
even though the current evaluation path contains no randomized operation.

## Per-cell records

Every question × system × budget cell records:

- whether the question is answerable and its source-document scope;
- selected evidence IDs and the complete serialized context packet;
- selected, gold, and matched one-based PDF pages by dataset document ID;
- exact packed token count;
- retrieval/compilation latency in milliseconds;
- evidence-page recall and full-evidence coverage;
- content-verified page recall, which credits a referenced node's pages only
  when that node's full normalized source text is present in the context;
- exact normalized evidence-quote recall and full-quote coverage when quotes
  are supplied by the dataset;
- tokens to full evidence, when full coverage is reached;
- approximate context redundancy.

Evidence-page recall is `matched gold pages / gold pages`. Full coverage means
every required `(document ID, page)` pair occurs in the selected evidence. A
question with no annotated gold pages has vacuous recall `1.0`, full coverage
`true`, and tokens-to-full `0`; this convention applies identically to all
systems and must be disclosed when interpreting absolute averages.

Evidence-quote recall is the fraction of non-empty annotated quotes that occur
verbatim after case-folding and whitespace normalization in the packed context.
A question without annotated quotes has vacuous quote recall `1.0` and full
quote coverage `true`. Quote recall is intentionally strict and complements,
rather than replaces, page recall.

Content-verified page recall is a conservative provenance/content check. A
selected chunk does not inherit every page from a multi-page source node unless
the full normalized node text occurs in the emitted chunk. This prevents a
partial chunk from receiving page credit for absent portions of a large table
or paragraph. It can under-credit synthetic or selectively rendered evidence,
so it is reported with exact quote recall rather than treated as ground truth.

Summary artifacts retain the registered all-question metrics for continuity
and also report page metrics over questions that are marked answerable and
carry at least one annotated gold page, and quote metrics over questions with
at least one non-empty quote. A question with no annotated gold page is
excluded from those page columns and from the paired intervals below even when
it is marked answerable, because its vacuous `1.0` recall is identical in every
arm. Compiler deltas against each RAG baseline include descriptive paired 95%
bootstrap intervals. Resampling is clustered by the sorted source-document
scope, uses the registered seed, and defaults to 10,000 resamples. The
intervals describe uncertainty in the sampled benchmark population; they are
not a substitute for a larger holdout.

Tokens-to-full is the cumulative item-token count at the earliest ranked
context prefix covering every gold page. It is null when the budget never
achieves full coverage. Its reported median is over successful cells only and
must be read together with full-coverage rate.

Redundancy is the fraction of word-token positions covered by a repeated
four-token n-gram previously seen in another selected item. It is an
approximation, not semantic redundancy. Latency includes query embedding,
sparse/dense search, fusion, reranking, and packing or compilation. It excludes
dataset loading, PDF parsing, IR projection, model loading, and index building.
The runner computes one ranking per question and system at the largest declared
budget, then reuses it for every packing budget. Each cell's latency includes
the full shared retrieval cost plus that cell's packing or compilation cost.
Query-dependent page-window reranking is likewise cached across eligible
compiler budgets. Cache-hit cells add the measured preparation cost back to
their recorded latency, so reported cells remain comparable to independent
compilations even though the benchmark avoids repeated wall-clock work.

## Outputs and immutability

One run is atomically published under `artifacts/runs/<run-id>/` only after all
cells and files are complete. An existing run ID is never overwritten.

```text
manifest.json       dataset, evaluation and retrieval-corpus identities,
                    source/parser provenance, git SHA, full configs,
                    model/tokenizer identities, seed, budgets, question IDs
retrieval.jsonl     one metric record per question/system/budget cell
contexts.jsonl      the corresponding complete context packets
compiler-stages.jsonl
                    optional candidate recall at each compiler boundary and
                    against structural retrieval
summary.json        aggregate rows plus paired source-cluster intervals
report.md           registered and audited metrics, intervals, and deltas
```

Derived indexes live under `artifacts/indexes/<sha256>/`; their key includes
source/chunk identities, retrieval configuration, resolved model and tokenizer
versions, and the pinned embedding and reranker model revisions. Hub-backed
models must be loaded at an explicit revision, so an upstream weight change
rekeys the index and is recorded in the run manifest instead of silently
mixing weights.

Adding the revisions to that key invalidated the cache: all 31 indexes
currently under `artifacts/indexes/` predate the pin and are unreachable by
key, so the next run rebuilds every one of them and cannot be timed against a
warm-cache run.

Run the registered experiment with:

```shell
uv sync --extra retrieval
uv run --extra retrieval contextbench eval-retrieval
```

The command reuses verified source and ingestion caches. Use `--run-id` for an
explicit immutable identifier, `--docling-artifacts-dir` for pre-fetched parser
models, `--retrieval-corpus-subset-file` to hold parent-corpus index statistics
fixed during a smaller diagnostic, and the model options to override the
registered defaults. Progress is written to stderr; stdout contains a final
JSON object naming the run directory, Markdown report, and JSON summary.

Use `--compiler-stage-audit` for failure analysis. Each question and budget
then records candidate counts, aggregate candidate tokens, selected and matched
pages, recall, and full coverage for raw node retrieval, faceted node
retrieval, structural retrieval, their candidate union, structural expansion,
deduplication, and packing. Retrieval stages use the bounded ranking produced
at the run's largest declared budget; expansion and later stages remain
budget-specific. Aggregate candidate tokens before packing quantify search
space volume and may exceed the context budget.

## Generation evaluation

Generation is a separate experiment over the immutable context packets from a
completed retrieval run. It never repeats ingestion, index construction,
retrieval, or context compilation. All selected arms use the same answer
prompt, model, reasoning setting, maximum output, JSON response contract,
scoring functions, and pricing metadata.

The prompt requires a concise answer plus evidence-ID citations and requires
`INSUFFICIENT_EVIDENCE` when the context cannot support an answer. Invalid JSON
is not repaired and scores zero. Scoring *targets* the released XL-DocBench
deterministic evaluator — relaxed rule-based accuracy, normalized token F1, and
ANLS — but the mapping is **unverified** against it: the released evaluator has
never been executed or read here, and every difference below is an assumption
rather than a confirmed match. See "Released rule mapping and deviations".
Citation validity is the fraction of returned IDs present in the context.
The historical `citation_support` field measures overlap with registered gold
pages and is now labeled gold-page alignment; neither metric is semantic
entailment. An optional second call to the same frozen model judges whether the
cited evidence supports the generated answer without seeing the gold answer.
The judge uses only cited items, returns a strict boolean JSON decision, and
treats embedded evidence as data rather than instructions. Invalid judge
output scores zero.

Every cell records raw and parsed answer and judge responses, citations,
provider/model IDs, disaggregated judge usage, total
input/cached-input/output/reasoning tokens, end-to-end latency, accuracy,
similarity metrics, abstention correctness, and configured total cost.

Each cell also records whether the call succeeded, separately from whether the
answer was right:

- `response_valid`, true only when the provider reported a completed, readable
  response *and* that response satisfied the strict JSON answer contract. A
  truncated response is a failed call, not a wrong answer, and scores zero on
  every metric either way;
- `provider_status`, `provider_incomplete_reason`, and `provider_text_error`,
  the provider's own account of why a response was not usable. A null status
  means the provider reported none and is not read as a failure;
- `citation_entailment_judge_valid` with the same three provider fields for
  the judge call. `None` means no judge call was made for this cell, which is
  never aggregated as a judge failure.

The summary rows carry `response_valid_rate` and
`citation_entailment_judge_valid_rate` so an arm whose calls were truncated
cannot be read as an arm that answered badly. The judge rate is over the cells
that actually called the judge and is null when none did.

Pricing is explicit experiment metadata, never inferred from a mutable live
price table. The CLI requires a `--max-calls` authorization ceiling before
constructing the provider and counts the optional judge in that ceiling. Runs
are atomically published under
`artifacts/generation-runs/<run-id>/` and bind to hashes of the retrieval
manifest and contexts. The run manifest records the configured `temperature`
and `seed` alongside the frozen config; null means the setting was not sent
and the provider default applied.

### Paid-run safeguards and their limits

The valid-rate fields above are a *reporting* safeguard: they keep a
non-completed response from being scored as a wrong answer, and the run
continues so the calls already paid for are still recorded. They are not crash
safety. An exception raised by the provider call — a rate limit, a timeout, a
transport error — propagates out of the cell loop, and the run is published
only after that loop completes, so every response already paid for in that run
is lost and no artifact is written. The same is true of the representation
experiment. Durable partial artifacts are not implemented; until they are, a
paid run is all-or-nothing against provider failures and should be sized and
scheduled on that basis.

## Released rule mapping and deviations

### Why this mapping is unverified

The released XL-DocBench evaluator has never been compared against. The pinned
release on disk (`data/raw/xl-docbench`, `xldocbench_strict_1345_v1`) contains
only `manifest.json` and `data/documents.jsonl`, `data/qa_single_doc.jsonl`,
`data/qa_cross_doc.jsonl`. The manifest *names* evaluator artifacts —
`release_files.per_question_scores` (`results/scores.jsonl`),
`release_files.score_summary` (`results/summary.json`),
`score_evaluator_sha256`, and `scored_system_count` (13) — but none of them are
downloaded, no `results/` directory exists, and no evaluator code is vendored
anywhere in this repository. Reference semantics below are inferred from rule
*names* alone.

Every row is labelled **verified** (checked against the release data and
`src/contextbench/generation/scoring.py` in this repository) or **assumed,
pending evaluator fetch** (a guess at the reference evaluator that no artifact
on disk can confirm). A verified label never means "matches the reference"; it
means "this is what our implementation demonstrably does".

### Rule inventory

Counts over all 1345 released rows, both `qa_single_doc.jsonl` and
`qa_cross_doc.jsonl`:

| `verification_rule` | Rows | Released `answer.format` | Mapped `answer_type` |
|---|---|---|---|
| `casefold_exact_match` | 822 | `Str` (822) | `entity` |
| `numeric_tolerance` | 276 | `Int` (209), `Float` (67) | `numeric` |
| `exact_match` | 188 | `None` (188) | `unanswerable` |
| `percentage_exact` | 43 | `Float` (43) | `percentage` |
| `choice_exact_match` | 16 | `Str` (16) | `single_choice` |

Resulting `answer_type` distribution: entity 822, numeric 276, unanswerable
188, percentage 43, single_choice 16.

All 188 `exact_match` rows carry `format == "None"` **and**
`metadata.is_unanswerable == true`. `answer_type` returns `unanswerable` at its
first guard, before any rule dispatch, so `exact_match` never reaches the
relaxed entity path. The relaxed entity path affects exactly the 822
`casefold_exact_match` questions.

The set of released rules is pinned as `RELEASED_VERIFICATION_RULES` in
`src/contextbench/generation/scoring.py`. The test suite asserts only that this
constant and the parametrized mapping table in `tests/unit/test_generation.py`
name the same rules. Both are literals in this repository: **no test reads a
`verification_rule` from the pinned release, and none can**, because
`data/raw/**` is git-ignored and unit tests must not read `data/**`. A rule that
first appears in a future release therefore leaves the suite green and is scored
by whichever branch its name selects — for a name containing `numeric` or
`tolerance`, the numeric path at a 5% tolerance (row 5); otherwise the relaxed
entity path. The constant documents the closed set the mapping was written
against and detects an unreviewed edit to the mapping table; it is not a guard
against unseen data.

### Deviations and assumptions

| # | Rule / path | What the implementation does | Assumed released semantics | Assessment | Label |
|---|---|---|---|---|---|
| 1 | `casefold_exact_match` → `entity` (822 rows) | After normalization, scores 1.0 if the normalized gold is **non-empty and a substring** of the prediction (`gold_norm and gold_norm in prediction_norm`, `src/contextbench/generation/scoring.py:165`), else if the normalized Levenshtein ratio is **>= 0.8**. An empty normalized gold skips the substring branch entirely and is decided by Levenshtein alone, which scores 1.0 only against an equally empty prediction; `src/contextbench/generation/runner.py:170` maps a missing gold to `""`, so this path is reachable | Casefolded exact string equality | **Deliberate deviation, laxer.** Relaxed matching is intentional for free-text generation, but it is strictly more permissive than the rule name and inflates accuracy on the largest slice of the benchmark. Magnitude unquantified. | Deviation **verified**; released semantics **assumed, pending evaluator fetch** |
| 2 | `percentage_exact` → `percentage` (43 rows) | Shares `numeric`'s **5% relative** tolerance; the `percentage` and `numeric` kinds take the same branch | Exact match on the percentage value, as the name `percentage_exact` states | **Deliberate deviation, laxer.** A distinct `percentage` type exists but carries no distinct predicate. | Deviation **verified**; released semantics **assumed, pending evaluator fetch** |
| 3 | Tolerance value (`numeric` + `percentage`, 319 rows) | `NUMERIC_RELATIVE_TOLERANCE = 0.05`, applied as relative error; gold `0` is special-cased to an absolute `< 1e-6` | Unknown. The rule name `numeric_tolerance` implies a tolerance but does not state one | **Unsourced assumption.** Every released `answer` object contains exactly `format`, `value`, `verification_rule` — all 1345 rows, no exceptions — so there is no per-question tolerance parameter anywhere in the release. Whether the reference tolerance is relative or absolute, and its magnitude, are both unknown. The tolerance is applied to whatever number `_extract_number` returns; that extraction is at least as consequential and is row 7. | **Assumed, pending evaluator fetch** |
| 4 | `exact_match` → `unanswerable` (188 rows) | Substring match of the normalized prediction against a hardcoded phrase list: `not answerable`, `unanswerable`, `cannot be determined`, `cannot be answered`, `not enough information`, `insufficient_evidence` | A structured abstention check against the released answer. The release does not carry a null here: all 188 rows have `answer.format == "None"` and `answer.value == "Not answerable"`, so the runtime gold string is `Not answerable` | **Deliberate deviation.** Not equivalent in either direction: a prediction that confidently asserts a wrong answer *and* happens to contain one of these phrases scores 1.0, while a valid abstention phrased outside the list scores 0.0. The prompt mitigates this by mandating the literal `INSUFFICIENT_EVIDENCE` token, but nothing enforces it. The branch never reads gold, so the released `Not answerable` value is inert; test fixtures use it anyway so they mirror the release. | Behavior **verified**; released semantics **assumed, pending evaluator fetch** |
| 5 | Numeric routing | `numeric` is selected when `answer_format` is `Int`/`Float` **or** when the rule name *contains* `"numeric"` or `"tolerance"` (`any(marker in question.verification_rule ...)`), a substring test rather than equality | Exact dispatch on the rule identifier | **Latent fragility, not currently wrong.** For the five released rules the substring test gives the same result as equality, so no released row is misrouted. An unseen future rule containing either word — e.g. a hypothetical `numeric_exact` — would silently take the numeric path with its 5% tolerance and no error. **Nothing guards this at runtime or in the suite:** `RELEASED_VERIFICATION_RULES` is compared only against a literal table in the tests, never against release data, so such a rule would arrive green. See the rule inventory above. | Behavior **verified**; the risk is prospective |
| 6 | `choice_exact_match` → `single_choice` (16 rows) | `re.search(r"\b([A-D])\b", ...)` over the **raw, uppercased** prediction and gold (`src/contextbench/generation/scoring.py:159-164`); scores 1.0 when the **first** standalone `A`-`D` token on each side is equal. `normalize_answer` is not applied, everything after the first such token is ignored, and a missing token on either side scores 0.0 | Exact match of the selected option letter | **Deviation, wrong in both directions.** First-token-wins misreads free-text answers: `"Option A is ruled out, so the answer is C"` matches `A` and scores **0.0** against gold `C` (false negative), while `"Annex A shows X, so the answer is B"` matches `A` and scores **1.0** against gold `A` (false positive). An option letter beyond `D` never matches and scores 0.0 silently. All 16 released golds are bare `A`-`D` — **verified**: the 16 `choice_exact_match` values in `data/raw/xl-docbench/data/qa_*.jsonl` are exactly `A`, `B`, `C`, `D` — so the gold side is safe for this release; the prediction side is unconstrained model text and is not. Magnitude unquantified. | Behavior **verified** (`test_single_choice_matches_the_first_option_letter`); gold inventory **verified** against the release on disk; released *evaluator* semantics **assumed, pending evaluator fetch** |
| 7 | Numeric value extraction (`numeric` + `percentage`, 319 rows) | `_extract_number` (`src/contextbench/generation/scoring.py:229-270`) removes all spaces, then returns the **first** match of, in order: an `a^b` power (evaluated), an `a/b` fraction (evaluated), or a plain number found **anywhere** in the text. Magnitude words are ignored; a `%` sign is not part of the match, so it is dropped rather than converted; a comma followed by at most two digits is read as a decimal separator (`1,23` → `1.23`) and otherwise as a thousands separator (`1,234` → `1234`) | Unknown. The rule names `numeric_tolerance` and `percentage_exact` say nothing about how a number is recovered from free text | **Unsourced assumption with confirmed failure modes.** First-number-anywhere ignores sentence structure: gold `4.5` against `"In 2023, revenue was 4.5 billion"` extracts `2023` and scores **0.0**, and the dropped magnitude word means `4.5 billion` and `4.5` are indistinguishable. Because `%` is dropped on both sides, the released gold `5.4%` parses as `5.4`, so a prediction of `0.054` — the same quantity expressed as a fraction — scores **0.0**. The gold convention is not fixed: 33 of the 43 `percentage_exact` golds carry a `%` and 10 do not (see the secondary observations). The comma rule silently reinterprets locale-formatted numbers, and the release contains one such gold, `89,9`, which parses as `89.9`. All counts and gold examples in this row were read directly from `data/raw/xl-docbench/data/qa_*.jsonl`. This drives the same 319 rows as row 3 and is at least as consequential as the tolerance magnitude. | Extraction behavior **verified** (`test_numeric_extraction_takes_the_first_number_anywhere`); released extraction semantics **assumed, pending evaluator fetch** |

### Secondary observations

- The `boolean` path in `accuracy_score` is **dead for this release**: no
  released row has a `Bool` or `Boolean` format. It is retained for datasets
  that do, and is untouched by these deviations.
- An unrecognized `kind` falls through to the **entity** path rather than
  raising: the default is silent and permissive, not loud. Nothing detects an
  unreviewed rule, because `RELEASED_VERIFICATION_RULES` is only compared with a
  literal table in the tests and never with release data.
- The `percentage_exact` golds are annotated inconsistently **in the release
  itself**: 33 of the 43 carry a `%` (`5.4%`, `73.7%`, `66.7%`, `8.34%`,
  `5.96%`), 10 do not (`55.62`, `100`), and one uses a comma decimal separator
  (`89,9`). This implementation is insensitive to the difference, because
  `_extract_number` drops `%` and reads `89,9` as `89.9`, so only the numeric
  value is compared. A reference evaluator that honours the name
  `percentage_exact` as string equality would not be: it would reward or
  penalise a prediction for matching the formatting convention that its
  particular question happens to use, and that convention is not fixed across
  the 43 rows. Either way, `percentage_exact` does not denote one consistent
  gold convention. **Verified** by reading
  `data/raw/xl-docbench/data/qa_*.jsonl` directly; see rows 2 and 7.
- `token_f1_score` and `anls_score` are reported alongside accuracy and share
  `normalize_answer`, but neither is named by any released `verification_rule`;
  their correspondence to the released evaluator is equally unverified.

### Closing this gap

The only thing that converts these rows to a real comparison is fetching the
evaluator named by `score_evaluator_sha256` and the released
`results/scores.jsonl`, then diffing per-question scores for the 13 scored
systems. That fetch is network work and is out of scope here. Until it happens,
no claim of evaluator parity may be published; report accuracy as
"relaxed, locally defined" and cite this section.

## Gold-evidence representation experiment

The representation experiment fixes source-evidence retrieval. It selects the
same released gold-page IR nodes for `raw`, `ir`, `enriched`, and `indexed`.
Stable citation IDs and source content are held fixed; only the rendering
changes. Enrichment is computed once per document without access to questions
or answers, and a feature is eligible only when all its supporting nodes occur
inside the authorized gold-page set.

The run records deterministic enrichment preparation once per referenced
document, plus total and amortized milliseconds per evaluated question. This
keeps reusable document-conversion cost separate from per-query model latency.

All four conditions share the answer prompt, provider, requested model,
reasoning setting, output limit, deterministic scoring, and pricing. Record the
exact representation, local representation tokens, provider usage, accuracy,
token F1, ANLS, citation validity/support, latency, and cost. Questions without
gold pages are skipped and listed in the manifest and summary. Immutable runs
are published under `artifacts/representation-runs/<run-id>/`.

Known defect, recorded and not fixed: this runner derives its `response_valid`
from the answer parse alone and never consults the provider's completion
state, so a response the provider cut short is scored as a wrong answer rather
than as a failed call, and the summary has no valid-rate field to expose how
often that happened. This is the unfixed mirror of the fix already made in the
generation path, whose `response_valid` is the conjunction of the parse result
and `ProviderAnswer.provider_valid`. The experiment is paid (plan Phase 3
task 6), so a truncation episode would silently depress one condition's
accuracy and cost real money to discover. Fixing it moves this experiment's
numbers and therefore needs its own change and its own remeasurement.

The initial enriched condition contains deterministic outline, extractive
section previews, numeric/normative/date/exception facts, definitions,
explicit aliases, typed structural relationships, table schemas, and
calculation-ready rows. It does not test abstractive LLM enrichment. Any
accuracy gain must be reported alongside its token and one-time preprocessing
overhead.

The default answer prompt excludes calculation-ready row features because the
same source tables are already present, and caps the remaining inline agent
index at 128 features using fixed importance/page/ID ordering. The rows remain
available in the reusable bundle for addressable tool access. Treat the cap and
inline feature vocabulary as declared representation parameters, not hidden
retrieval.

The separate `indexed` condition intentionally adds bounded deterministic
feature retrieval over the already-authorized source nodes. It emits a compact
inventory, selects query-matching features, and includes the same canonical
source evidence. Its feature count and token ceiling are frozen in the run
configuration so it is not confused with the encoding-only comparison.

## First decision gate

Development stops before generation. Inspect page-recall and full-coverage
curves against actual packed tokens, plus redundancy and tokens-to-full. The
compiler should be materially up and left of both baselines: higher evidence
coverage at fixed budget or comparable coverage with fewer tokens.

If the compiler only matches structural RAG, the result supports better
chunking rather than a new IR/compiler layer. If it fails to beat fixed RAG,
diagnose retrieval, expansion, provenance mapping, and packing from the saved
contexts before changing algorithms. Do not add an LLM planner to rescue weak
retrieval results.
