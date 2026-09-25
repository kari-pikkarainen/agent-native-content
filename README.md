# Agent-Native Content

> Persistent, structured, provenance-preserving content for AI agents.

## In plain English

Most content is stored either as pages designed for people or in a data model
built for one application. This project asks whether content should also carry
a reusable, **agent-ready layer**: explicit structure, relationships, tables as
data, navigation cues, and links back to the source. A person can still read
the original document, while an AI agent can read the prepared features
directly instead of reconstructing them from scratch for every task.

AI systems usually break a document into loose text snippets and search those
snippets again for every question. This project explores a different approach:
prepare the document once in a structured, trustworthy form that keeps its
sections, tables, and links back to the original pages. Then, for each question,
assemble a small package containing only the most useful evidence. We test
whether this reusable preparation helps agents find better-supported answers,
use less unnecessary context, and reuse the same content across different
tasks more effectively than conventional document search.

This repository explores whether source material can be prepared once into a
reusable intermediate representation, then assembled into task-specific,
token-budgeted context with better grounding and information efficiency than
conventional RAG.

The current reference implementation tests a narrower question:

> Can a persistent, structure-preserving document representation plus
> deterministic query-time compilation select better evidence—or use fewer
> context tokens—than strong RAG baselines?

It parses PDFs once, preserves their structure and provenance, and compiles a
query-specific evidence packet under a hard token budget. The broader goal is a
reusable content layer that can eventually support documents, web pages,
spreadsheets, presentations, transcripts, and multimodal sources. It also
explores packaging content with source-grounded, agent-usable features prepared
once and reused by many queries.

This is a **falsification-oriented research prototype**, not a production RAG
platform. The retrieval evidence is promising at low token budgets, but the
first answer-generation test did not translate that advantage into better
answers or citations. The project does not establish general superiority over
RAG.

## Current status

The complete evidence-only benchmark pipeline is implemented:

- content-addressed PDF ingestion with Docling;
- a deterministic, structure-preserving intermediate representation (IR);
- fixed-chunk RAG, structural RAG, source-order long context, and compiler arms;
- local BM25/dense retrieval, reciprocal-rank fusion, and cross-encoder
  reranking;
- query faceting, structural expansion, keyed table joins, deduplication, and
  coverage-aware packing;
- immutable, reproducible run artifacts and stage-level diagnostics;
- guarded answer-generation evaluation over already-saved contexts; and
- portable agent-document bundles plus a controlled representation experiment.

**Gate 1 passed on its one run of the `xlholdout6c` holdout — on page recall,
the metric it was preregistered on. On exact quote recall the same run points
the other way**: the compiler trails fixed RAG at every budget, with the
interval excluding zero at 4K and 16K. Both are in
[the Gate 1 decision](docs/research-log/gate1-xlholdout6c-60e5836.md). The
frozen configuration and its development evidence are in the
[Phase 1 close-out](docs/research-log/phase1-closeout-c7e56fa.md).

**The first answer-generation test then failed.** On the same six holdout
questions, with `gpt-6-astra` answering from each arm's saved contexts, the
compiler's answers were no better than fixed RAG's at either budget: accuracy
0.167 against 0.333 at 2K and 4K, citation entailment 0.333 against 0.500 at 2K
and level at 4K. Under the
[preregistered rule](docs/research-log/prereg-xlholdout6c-generation.md) that
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
[the Gate 2 decision](docs/research-log/gate2-stage1-xlholdout6c-generation.md)
and [the failure analysis](docs/research-log/gate2-failure-analysis.md).

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
[the re-baseline record](docs/research-log/stepc-rendered-budget-merge-f916545.md).

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
quote itself contains OCR errors. Quote figures here are scored under match
policy `nfkc-unified-punctuation-ordered-elision-v3` and are not comparable
with figures scored under an earlier policy.

The frozen configuration turns sibling expansion on, which is worth +0.019
quote recall across budgets, and keeps page-neighbour expansion, which is
worth little quote recall but is what holds the compiler inside the
preregistered −3pp non-inferiority margin against fixed RAG at 16K. It holds
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
[frozen development report](results/retrieval/xldev24-phase1-frozen/report.md),
[Phase 1 close-out](docs/research-log/phase1-closeout-c7e56fa.md),
[holdout report](results/retrieval/xlholdout6b-rebaseline/report.md),
[corrected content-unit factorial](results/factorial/xldev24-content-policy-corrected/report.md),
[packing-policy decision](docs/research-log/adaptive-packing-decision-3b77e75.md),
[expansion ablations](docs/research-log/phase1-ablations-6cc7fd9.md), and
[results index](results/README.md) for the full evidence and caveats. An
earlier six-question holdout mostly rejected the preceding compiler
configuration and remains published as superseded negative evidence.

**Decision:** retain the compiler as a credible low-budget page-selection
treatment, but do not claim that it replaces RAG or improves end-to-end answer
quality. Pause algorithm expansion and the larger XL100 run while the
per-question failure analysis examines missing exact evidence, budget
under-fill, context fragmentation, and prompt-framing overhead.

## How it works

```text
                         prepared once per document/corpus
PDF ──▶ Docling document ──▶ canonical IR ──▶ verified local indexes
                                  │                     │
                                  └──▶ agent bundle     │
                                       HTML + JSON-LD   │
                                                        ▼
query ──▶ hybrid retrieval ──▶ query facets ──▶ structural expansion
                                                    │
                                                    ▼
answer model ◀── evidence packet ◀── exact-token coverage packing
```

The IR preserves hierarchy, heading paths, tables, page locations, source
hashes, and stable provenance. It deliberately excludes embeddings, retrieval
scores, and generated annotations: those are replaceable derived state.

At query time, the compiler retrieves IR nodes with the same local models used
by the RAG baselines, expands useful document structure, optionally joins rows
across explicitly named tables, removes provenance-aware duplicates, and packs
the result without exceeding the token budget. Compiler v0 uses no LLM for
retrieval planning.

Coverage-aware packing is the selected default. The earlier greedy rank-order
policy and the rejected budget-adaptive policy remain available with
`--compiler-packing-strategy ranked` and
`--compiler-packing-strategy adaptive` as ablation controls.

## Compared systems

| Arm | System | Distinguishing behavior |
| --- | --- | --- |
| A | Fixed RAG | 512-token chunks with 64-token overlap |
| B | Structural RAG | Docling `HybridChunker` chunks |
| C | Long context | Source nodes in document order; no retrieval |
| D | Context compiler | IR-node retrieval plus deterministic compilation |

Arms A, B, and D share BM25, dense retrieval, fusion, reranking, tokenizer,
model configuration, and hard budget accounting. The treatment is document
representation and context construction—not a deliberately weak baseline.

## Requirements and setup

- Python 3.12 or newer
- [`uv`](https://docs.astral.sh/uv/)

Clone the repository and create the environment:

```shell
uv sync --extra retrieval
uv run contextbench --help
```

The first real-data run may download the pinned dataset metadata, referenced
PDFs, Docling artifacts, and the configured SentenceTransformers models. Later
runs reuse content- and configuration-verified caches. Remote inference is
disabled during PDF parsing.

### Parallel document parsing

The three XL commands that ingest documents accept `--parse-workers N`.
The default, `1`, preserves sequential parsing. A larger value parses only
uncached documents in spawned worker processes before the otherwise unchanged
run. Cache entries are published atomically, and a real-Docling integration
test checks that sequential and parallel parsing produce identical cached
documents.

On a 12-core Apple M3 Pro with 36 GB of memory, one cold-cache trial over the
six-document `xldev6-perf` subset took 17m 48.5s with one worker, 13m 53.3s
with two, and 14m 28.1s with four. Peak process-tree memory was 4.40, 6.24 and
7.82 GiB respectively. **Use two workers as the measured local default;** use
one when memory is constrained. Four workers did not improve this small run.
The comparison is directional, not a general throughput claim; see the
[complete measurement record](docs/research-log/parallel-parsing-performance-46c2a61.md).

Cache the Docling models before using multiple workers—by completing one
sequential parse or passing `--docling-artifacts-dir`—so the workers do not
attempt the same download concurrently. For example:

```shell
uv run --extra retrieval contextbench eval-retrieval \
  --subset-file benchmarks/xl-docbench/subsets/xldev2-tables.json \
  --retrieval-corpus-subset-file benchmarks/xl-docbench/subsets/xldev24.json \
  --parse-workers 2 \
  --run-id xldev2-local-parallel
```

For development:

```shell
uv run --frozen ruff check .
uv run --frozen pytest -q
```

## Recommended first experiment

Start with two questions while retaining the 24-question development corpus's
11 documents and index statistics:

```shell
uv run --extra retrieval contextbench eval-retrieval \
  --subset-file benchmarks/xl-docbench/subsets/xldev2-tables.json \
  --retrieval-corpus-subset-file benchmarks/xl-docbench/subsets/xldev24.json \
  --compiler-stage-audit \
  --run-id xldev2-local
```

This is a failure-selected table diagnostic, so use it to validate mechanics,
inspect contexts, and profile stages—not to make research claims. The command
evaluates all four systems at 2K, 4K, 8K, and 16K. It writes the final artifact
paths as JSON on stdout and progress on stderr.

After the models and indexes are warm, they can be forced offline:

```shell
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  uv run --extra retrieval contextbench eval-retrieval \
  --subset-file benchmarks/xl-docbench/subsets/xldev2-tables.json \
  --retrieval-corpus-subset-file benchmarks/xl-docbench/subsets/xldev24.json \
  --run-id xldev2-offline
```

Run IDs are immutable; choose a new ID for every run.

Every evaluation command refuses to run from a modified worktree, so that a
result is always reproducible from the recorded Git SHA; pass `--allow-dirty`
to run anyway and stamp the manifest with `git_dirty: true`.

## Causal factorial control

The primary benchmark changes both representation and selection behavior. Use
the controlled factorial command to cross fixed chunks, structural chunks, and
IR nodes with ranked single-query retrieval and faceted coverage-aware
retrieval:

```shell
uv run --extra retrieval contextbench eval-factorial \
  --subset-file benchmarks/xl-docbench/subsets/xldev2-tables.json \
  --retrieval-corpus-subset-file benchmarks/xl-docbench/subsets/xldev24.json \
  --run-id xldev2-factorial
```

Heading context is a third, crossed factor, single-valued by default; pass
`--heading-context on --heading-context off` to run the ablation, and read
[the decision history](#decision-history-and-next-step) before interpreting it.

The command deliberately excludes compiler-only structural expansion, table
joins, and page-neighbor backfill. Its defaults use this same two-question
diagnostic and fixed 11-document corpus. See the
[factorial specification](docs/specs/factorial.md).

## Common workflows

### Inspect the pinned dataset

The adapter is pinned to Microsoft's conservative
`xldocbench_strict_1345_v1` release.

```shell
uv run contextbench dataset download xl-docbench
uv run contextbench dataset list xl-docbench \
  --subset-file benchmarks/xl-docbench/subsets/xldev24.json
uv run contextbench dataset inspect xl-docbench <question-id>
```

Add `--sources` to the download command to prefetch source PDFs. The benchmark
runner otherwise fetches only the sources needed by the selected corpus.
Downloads are size-checked, content-addressed, and revalidated before reuse.

### Ingest one PDF

```shell
uv run contextbench ingest path/to/document.pdf
```

This writes an authoritative serialized `DoclingDocument` and metadata beneath
`data/cache/ingest/`. The cache key includes the source hash, parser versions,
and complete parser configuration; cache hits revalidate artifact integrity
and structural counts.

### Create an agent-ready document

```shell
uv run contextbench agentize \
  path/to/document.pdf \
  artifacts/agent-documents/example
```

The new immutable directory contains:

```text
source.pdf            hash-verified original (optional)
content.json          canonical Context Compiler IR
enrichments.jsonld    source-grounded agent features
agent.html            semantic HTML with embedded JSON-LD
manifest.json         identities, configuration, and file hashes
```

Enrichment is deterministic and question-independent. It exposes the outline,
extractive section previews, key facts, definitions, aliases, typed
relationships, dates, exceptions, quantities, table schemas, and
calculation-ready rows. Every feature retains confidence and node/item/page
provenance; source truth remains in the canonical IR.

This is a portable companion bundle, not a new PDF or DOCX standard. Existing
document formats can carry some metadata, but HTML plus JSON-LD provides a
practical, inspectable encoding without requiring reader-specific extensions.
See the [agent-ready content specification](docs/specs/agent-document.md).

### Run a larger retrieval subset

The balanced development set is the largest set currently recommended for
iteration:

```shell
uv run --extra retrieval contextbench eval-retrieval \
  --subset-file benchmarks/xl-docbench/subsets/xldev24.json \
  --compiler-stage-audit \
  --run-id xldev24-local
```

`benchmarks/xl-docbench/subsets/xl100.json` remains the registered full evaluation set, but
the current holdout result does not justify spending the time to run it yet.
Subset intent and contamination status are recorded inside every manifest.

### Evaluate answers from saved contexts

Answer generation is a separate, opt-in experiment. It consumes a completed
retrieval run and does **not** repeat parsing, indexing, retrieval, or context
compilation:

```shell
uv sync --extra generation
uv run --extra generation contextbench eval-generation \
  artifacts/runs/<retrieval-run-id> \
  --subset-file benchmarks/xl-docbench/subsets/xldev2-tables.json \
  --model <model-id> \
  --input-usd-per-million <price> \
  --cached-input-usd-per-million <price> \
  --output-usd-per-million <price> \
  --max-calls <limit> \
  --run-id <generation-run-id>
```

The command requires explicit pricing and a hard provider-call ceiling. It
refuses to start if the requested question × system × budget cells exceed
`--max-calls`. No default command makes a paid model call.

### Isolate the value of document encoding

The gold-evidence representation experiment bypasses retrieval and gives each
condition the same annotated source pages:

- `raw`: minimal source text and citation IDs;
- `ir`: canonical content plus structure and provenance;
- `enriched`: IR plus bounded, question-independent agent features; and
- `indexed`: IR plus a compact query-selected view of reusable features; and
- `question_only`: an opt-in control with no evidence at all, requested with
  `--condition question_only` (the default remains the four conditions above).
  The prompt still demands evidence-only answers, so this measures answers
  given despite no evidence, not what the model knows; compliant abstentions
  are counted separately.

Two optional judges use the same model for every condition:
`--answer-equivalence-judge` records a representation-blind semantic accuracy
beside the unchanged deterministic accuracy, and `--citation-entailment-judge`
checks whether cited source nodes support the answer. Neither judge is sent an
exact `INSUFFICIENT_EVIDENCE` abstention, and an invalid judge response scores
zero. `--max-calls` must cover questions x conditions x (1 + enabled judges);
it bounds logical calls, not SDK-level retries. Judge calls are evaluation
overhead, so representations are compared on answer-call-only tokens,
latency and cost, reported separately from all-call totals.
This is implemented and unit-tested only; no live run with the judges or the
question-only control has been made.

```shell
uv run --extra generation contextbench eval-representation \
  --subset-file benchmarks/xl-docbench/subsets/xldev2-tables.json \
  --model <model-id> \
  --input-usd-per-million <price> \
  --cached-input-usd-per-million <price> \
  --output-usd-per-million <price> \
  --max-calls 8 \
  --run-id xldev2-representation
```

A no-call preparation smoke test found these mean local token counts on the
two table-heavy questions:

| Representation | Mean tokens |
| --- | ---: |
| Raw | 33,515.5 |
| IR | 49,940.5 |
| Bounded enriched | 64,012.0 |
| Indexed | 53,453.5 |

The indexed view is 16.5% smaller than bounded enriched, but still 7.1% larger
than IR. This only measures representation volume; it is not evidence of an
answer-quality improvement. Preparation took about 81 ms for two cached
documents on one development machine and is reusable across queries. See the
canonical [representation result](results/representation/xldev2-no-call/README.md).

## Reproducibility and artifacts

Benchmark state is separated by lifecycle:

```text
data/raw/xl-docbench/                 pinned release metadata
data/cache/xl-docbench/               hash-verified source PDFs
data/cache/ingest/<source>/<config>/  authoritative parsed documents
artifacts/indexes/<sha256>/           verified derived retrieval indexes
artifacts/runs/<run-id>/              evidence-only retrieval runs
artifacts/factorial-runs/<run-id>/    controlled causal-factor runs
artifacts/generation-runs/<run-id>/   answer-generation runs
artifacts/representation-runs/<id>/   representation runs
results/                              compact canonical evidence committed to Git
```

Retrieval runs are assembled in a temporary directory and published atomically;
an existing run ID is never overwritten. A completed run contains:

| File | Contents |
| --- | --- |
| `manifest.json` | Git SHA, dataset/subset hashes, source/parser identities, full configs, model/tokenizer versions, seed, and question IDs |
| `retrieval.jsonl` | Per-question/system/budget evidence metrics |
| `contexts.jsonl` | Complete rendered context packets |
| `compiler-stages.jsonl` | Optional candidate and recall snapshots at compiler boundaries |
| `summary.json` | Aggregate metrics by system and budget |
| `report.md` | Human-readable evidence-only report |

Indexes and corpus structures are built once and reused after verification.
The runner also computes one ranking per question/system at the largest budget
and repacks it for smaller budgets. These changes reduced a repeated local
two-question command from roughly eight minutes with index rebuilding to about
90 seconds with warm indexes; machine and thermal variance make this a
directional measurement, not a benchmark claim.

## Metrics

The primary retrieval metric is **gold-evidence page recall at a fixed packed
token budget**. Runs also record:

- full evidence-page coverage;
- exact evidence-quote recall and full quote coverage, under a recorded quote
  match policy (see [the evaluation spec](docs/specs/evaluation.md));
- tokens required to reach full evidence;
- packed context tokens and approximate redundancy; and
- query-time retrieval/compilation latency.

Latency excludes dataset loading, PDF parsing, model loading, IR projection,
and index construction. The exact conventions, including treatment of missing
gold pages or quotes, are defined in the
[experiment protocol](docs/specs/evaluation.md).

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
  [metric-audit rerun](results/retrieval/xlholdout6b-metric-audit/report.md)
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
  [the Phase 1 close-out](docs/research-log/phase1-closeout-c7e56fa.md).
- Page recall can also over-credit a *baseline*, which Phase 1 demonstrated
  directly. Before the IR reading-order repair the fixed arm's windows spliced
  distant pages together and were credited with all of them: identical window
  counts, but 2.43 distinct pages per window instead of 1.82. Fixing it lowered
  that arm's page recall and raised its quote recall. See
  [the Phase 1 record](docs/research-log/phase1-correctness-fixes-9110e70.md).
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
[the Gate 0 decision](docs/research-log/gate0-rebaseline-67aef47.md) and
[the Gate 1 decision](docs/research-log/gate1-xlholdout6c-60e5836.md). The
gate after them, **Gate 2** of the
[improvement plan](docs/plans/2026-09-21-improvement-plan.md), asked whether
better evidence selection produces better answers, and its first stage
**failed**: see
[the Gate 2 decision](docs/research-log/gate2-stage1-xlholdout6c-generation.md).
The Gate 0 account below is kept as it was recorded.

Gate 0 asked whether the low-budget advantage on this page was real or an
artifact of broken measurement. It is real. It survived nine defect fixes,
including two the code review did not find: the dense channel held a copy of
the BM25 zero-score defect, and the structural baseline could not retrieve on
its own heading vocabulary, which had been handicapping a baseline rather than
the treatment. On the remeasured `xldev24` the paired source-cluster interval
for the compiler against both RAG baselines excludes zero at 2K and at 4K,
which is the condition the gate was stated on.

The re-baselined results are published under
[`results/`](results/README.md) and the four earlier ones are marked
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
  [the ablation record](docs/research-log/compiler-heading-free-edd196f.md).

**Phase 1 is complete and its configuration is frozen.** Its three correctness
fixes are
[delivered and measured](docs/research-log/phase1-correctness-fixes-9110e70.md).
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
[the close-out](docs/research-log/phase1-closeout-c7e56fa.md) before it existed.
The compiler's page-recall point estimate against fixed RAG is positive at all
four budgets and no interval lies below the −3pp margin, which is what the rule
asks. Every one of those intervals also includes zero, and on exact quote
recall the same run has the compiler behind fixed RAG at every budget. The
[Gate 1 decision](docs/research-log/gate1-xlholdout6c-60e5836.md) records both,
and two mechanisms behind the second: the compiler reaches the right pages
while missing the quoted spans on them, and in some packets it stops filling
its budget where fixed RAG does not.

**Gate 2 failed at its first stage.** The
[preregistered](docs/research-log/prereg-xlholdout6c-generation.md)
answer-generation run over the holdout's saved contexts found the compiler's
answers no better than fixed RAG's at 2K or 4K, and the hypothesis stated
before the run — that contexts with fewer exact quoted passages would not
produce better-supported citations — held. As preregistered, the larger
`xldev24` generation run is not made, Phase 3 does not open, and algorithm work
pauses.

**The failure analysis is done**, and it changes what Gate 2 can be taken to
show. [It found](docs/research-log/gate2-failure-analysis.md) that the run
measured the answer model's willingness to answer rather than the quality of
the evidence: the deciding question was answerable from its own text, and the
deciding citation was an abstention scored as supported. It is therefore not
evidence for stopping, and not evidence for continuing.

It found two things that are. The generation instrument has four defects —
exact matching rejects correct paraphrases, citation entailment credits
abstentions, nothing screens out questions answerable without evidence, and
abstentions dominate — which must be fixed before another generation run can
decide anything. And the compiler has a concrete failure: on poorly parsed
documents it packs hundreds of fragments of a few tokens each, which empties
its candidate pool, leaves budget unspent, and multiplies the prompt, up to
28,954 tokens for a nominal 4K budget.

**The active step is to fix the instrument and state the fragmentation
mechanism as a hypothesis, to be tested only on questions neither holdout nor
`xldev24` has touched.** Whether the token budget should cover the rendered
prompt rather than packed content remains an open decision for the owner, and
bears directly on the fragmentation remedy.

`xlholdout6c` was frozen and
[recorded](docs/research-log/xlholdout6c-freeze.md) with all six sources
preflight-verified, and has now been run once, at Gate 1, with the
configuration chosen on `xldev24`. It is spent: it is not run again and is
never tuned on.

The earlier exploratory generation proposal for the already-inspected
`xlholdout6b` holdout is intentionally not run. The preregistered
`xlholdout6c` Astra experiment now provides the answer-quality and economic
result that matters for the active decision, and the next work is its
per-question failure analysis rather than another small generation run.

## Repository map

```text
src/contextbench/
  agentdoc/        portable document enrichment and bundles
  compiler/        query facets, joins, expansion, dedupe, and packing
  datasets/        pinned XL-DocBench adapter and source cache
  evaluation/      retrieval benchmark, metrics, reports, and stage audit
  generation/      provider-neutral answer evaluation
  ingest/          Docling conversion and verified cache
  ir/              canonical models, projection, serialization, tokenization
  representation/  controlled document-encoding experiment
  retrieval/       chunks, BM25, dense search, fusion, and reranking
benchmarks/        committed benchmark definitions and subsets
docs/              vision, architecture, specifications, ADRs, and research log
results/           compact canonical reports, summaries, and manifests
artifacts/         ignored local indexes and complete experiment outputs
tests/             offline unit tests and fixtures
```

Start with the [project vision](docs/vision.md) and
[research roadmap](docs/roadmap.md), then read the
[benchmark specification](docs/specs/benchmark.md) for the research questions
and kill conditions. The
[architecture](docs/architecture.md), [IR specification](docs/specs/content-ir.md),
[retrieval specification](docs/specs/retrieval.md), and
[compiler specification](docs/specs/context-compiler.md) define the implemented
boundaries in more detail.

## License

Agent-Native Content is available under the
[Apache License 2.0](LICENSE).
