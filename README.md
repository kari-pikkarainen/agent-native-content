# Agent-Native Content

> Persistent, structured, provenance-preserving content for AI agents.

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
platform. The current evidence is promising at low token budgets, but it does
not establish general superiority over RAG.

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

The selected compiler beats the best RAG baseline on the 24-question
development set at every tested budget. A fresh six-question holdout confirms
the advantage at 2K and 4K tokens, but fixed RAG wins at 8K and 16K:

| Budget | Dev compiler | Dev best RAG | Holdout compiler | Holdout best RAG |
| ---: | ---: | ---: | ---: | ---: |
| 2K | **0.727** | 0.502 | **0.513** | 0.390 |
| 4K | **0.791** | 0.631 | **0.626** | 0.546 |
| 8K | **0.864** | 0.755 | 0.815 | **0.856** |
| 16K | **0.922** | 0.836 | 0.935 | **1.000** |

Values are mean gold-evidence page recall at the stated context budget. The
development set has 24 questions over 11 documents; the directional holdout
has six questions over six previously unused documents. No answer model was
used for these results. An earlier six-question holdout mostly rejected the
preceding compiler configuration and remains published as negative evidence.
See the canonical
[development report](results/retrieval/xldev24-coverage/report.md),
[first holdout report](results/retrieval/xlholdout6/report.md),
[holdout report](results/retrieval/xlholdout6b/report.md), and
[results index](results/README.md) for the full evidence and caveats.

**Decision:** keep the compiler as a credible low-budget treatment, do not
claim that it replaces RAG, and postpone the full XL100 run until answer-quality
validation shows that the extra retrieval work is worthwhile.

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
policy remains available with `--compiler-packing-strategy ranked` as an
ablation control.

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
- `indexed`: IR plus a compact query-selected view of reusable features.

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
- exact normalized evidence-quote recall and full quote coverage;
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
  aggregate, but eligibility keys on a question's answerable flag rather than
  on it having annotated gold pages, so an answerable question with no gold
  pages still contributes a vacuous score. No such question occurs in
  `xldev24`, where all six zero-gold-page questions are unanswerable; one
  XL100 question is affected. The canonical development and
  holdout reports predate this reporting; only the
  [metric-audit rerun](results/retrieval/xlholdout6b-metric-audit/report.md)
  publishes the answerable-only tables.
- Evidence retrieval has been measured more thoroughly than end-to-end answer
  quality. No answer-generation or economic result exists yet.
- Compiler retrieval is currently slower: about 4.7–5.4 seconds per holdout
  query versus 1.4 seconds for fixed RAG and 2.2 seconds for structural RAG on
  the same development machine.
- The holdout rejects high-budget dominance: fixed RAG wins at 8K and 16K.
- Agent enrichment is deterministic and mostly extractive. It is not a
  semantic knowledge graph or an abstractive document rewrite.
- On the two-question representation diagnostic, IR used about 49% more tokens
  than raw text and bounded enrichment about 91% more. Those costs require a
  meaningful answer or citation improvement to be justified.
- Charts, diagrams, and image-only evidence are not yet represented beyond
  what the parser exposes as text and structure.
- Current experiments use English PDFs, local retrieval models, and a single
  benchmark release; generalization is unknown.

## Next decision gate

The active gate is Gate 0 of the
[improvement plan](docs/plans/2026-09-21-improvement-plan.md): re-baseline the
measurement. A 2026-09-21 code review found shared retrieval and reporting
defects that are still present, including BM25 returning every chunk with a
zero score into rank fusion, embedding and reranker models loaded without a
pinned revision, and run manifests that do not record whether the worktree was
dirty. Those defects affect every arm, but not necessarily by the same amount,
so the absolute figures and paired deltas published on this page should be
treated as provisional until the affected runs are repeated.

That re-baselining is in progress and not complete. It ends with continuous
integration green on `main`, a fresh `xlholdout6c` holdout frozen before any
compiler change, and republished `xldev24` and `xlholdout6b` results. The gate
closes only if, on the remeasured `xldev24`, the paired source-cluster
bootstrap interval for the compiler against the best RAG baseline excludes zero
at both 2K and 4K. If it does not, the plan is to stop and write that up.

Only after that does the plan harden the compiler and then run the content-unit
by policy factorial on the full development set. That factorial is the
comparison that can separate representation from retrieval policy; the existing
factorial evidence is a two-question diagnostic. Guarded answer generation at
2K and 4K is implemented and preregistered but has produced no result, so no
answer-quality or economic claim is available yet, and expansion to an
untouched cross-document set, a second benchmark, and realistic 64K/128K long
context stays behind that. See the [research roadmap](docs/roadmap.md).

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
