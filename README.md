# Context IR Benchmark

A research prototype for testing whether a persistent, structure-preserving
intermediate representation and deterministic query-time context compilation
can improve evidence selection or reduce context-token usage relative to strong
RAG baselines.

This repository is intended to falsify that hypothesis, not to serve as a
production platform. See [the benchmark specification](docs/benchmark-spec.md)
for the research questions, comparison arms, success criteria, and kill
conditions.

## Requirements

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)

## Development

```shell
uv sync
uv run contextbench --help
uv run ruff check .
uv run pytest
```

## XL-DocBench dataset

The adapter is pinned to Microsoft's conservative
`xldocbench_strict_1345_v1` release. Download its metadata, inspect a question,
or list the committed development subset with:

```shell
uv run contextbench dataset download xl-docbench
uv run contextbench dataset inspect xl-docbench <question-id>
uv run contextbench dataset list xl-docbench --subset-file configs/subsets/xl100.json
```

Add `--sources` to the download command to cache the referenced PDFs. Source
files are content-addressed after their release-recorded size is verified;
subsequent use rechecks SHA-256 and refuses silent replacement. Failed URLs are
recorded in `data/cache/xl-docbench/failures.jsonl`.

## Document ingestion

Convert a downloaded or other local PDF into the authoritative serialized
Docling representation with:

```shell
uv run contextbench ingest path/to/document.pdf
```

The command writes `document.json` and `metadata.json` beneath
`data/cache/ingest`. Entries are keyed by the source SHA-256 and the full parser
configuration fingerprint. Cache reuse verifies the serialized document hash,
parser versions, configuration, schema version, and structural counts before
loading it.

Docling may download local model weights on first use. For controlled or
offline runs, prefetch those weights and pass their directory with
`--artifacts-dir`. Remote inference services are always disabled by this
pipeline.

## Minimal IR

Project an ingested `DoclingDocument` into the validated, structure-preserving
IR through the Python API:

```python
from contextbench.ir import project_document, save_ir_document

ir = project_document(ingest_result.document, ingest_result.metadata)
save_ir_document(ir, output_path)
```

The projection has deterministic IDs and ordering, preserves hierarchy,
heading paths, tables, page provenance, and source hashes, and uses the fixed
`o200k_base` encoding for token counts. The authoritative parsed artifact
remains the serialized `DoclingDocument`; embeddings and other retrieval
indexes are deliberately excluded. See [the IR specification](docs/ir-spec.md)
for the full contract.

## Agent-ready document bundle

Decode a PDF once into a portable bundle containing canonical IR, semantic
HTML, source-grounded JSON-LD enrichment, a hash manifest, and the verified
source PDF:

```shell
uv run contextbench agentize path/to/document.pdf artifacts/agent-documents/example
```

The initial enrichment is deterministic and question-independent. It exposes
the outline, extractive section previews, numeric/normative key facts,
dates/exceptions, explicit aliases and typed relationships, table schemas, and
calculation-ready rows with confidence and node/item/page provenance. It does
not call an LLM or modify source truth. See
[the agent-document specification](docs/agent-document-spec.md).

The retrieval baselines are documented in
[docs/retrieval-spec.md](docs/retrieval-spec.md). Arms A and B share BM25,
dense retrieval, RRF, reranking, and token-budget packing; only their chunk
construction differs.

## Context compiler

Compile structure-aware evidence for benchmark Arm D with:

```python
from contextbench.compiler import CompilerConfig, DocumentScope, compile_context

scope = DocumentScope.from_documents(
    [ir],
    source_documents={ir.id: docling_document},
)
packet = compile_context(
    query,
    scope,
    token_budget=4096,
    config=CompilerConfig(),
)
```

The compiler performs shared hybrid retrieval, heading and configurable sibling
expansion, adjacent-list grouping, table preservation, provenance-aware
deduplication, and exact-token packing without an LLM call. See
[docs/compiler-spec.md](docs/compiler-spec.md) for the full contract.

Coverage-aware packing is the selected default after balanced XLDev24
confirmation. Use `--compiler-packing-strategy ranked` to reproduce the prior
greedy rank-order control.

## Evidence-only retrieval benchmark

Run the registered XL100 comparison for fixed RAG, structural RAG, source-order
long context, and the context compiler at 2K, 4K, 8K, and 16K token budgets
with one command:

```shell
uv sync --extra retrieval
uv run --extra retrieval contextbench eval-retrieval
```

For a real-data smoke run covering all six domains with 10 questions over only
6 PDFs (718 pages, about 29 MiB), use the committed `xl10` subset:

```shell
uv run --extra retrieval contextbench eval-retrieval \
  --subset-file configs/subsets/xl10.json \
  --run-id xl10-smoke
```

For a fast diagnostic that evaluates only a small question slice while keeping
the parent development set's BM25 statistics and index composition fixed, pass
a separate retrieval-corpus manifest:

```shell
uv run --extra retrieval contextbench eval-retrieval \
  --subset-file configs/subsets/xldev2-tables.json \
  --retrieval-corpus-subset-file configs/subsets/xldev24.json \
  --compiler-stage-audit \
  --run-id xldev2-fixed-corpus
```

The evaluation subset must be contained in the retrieval-corpus subset. The
run manifest records both names, hashes, ordered question lists, and every
indexed document.

`--compiler-stage-audit` adds `compiler-stages.jsonl`, with candidate counts,
candidate-token volume, page recall, and coverage at raw node retrieval,
faceted retrieval, structural retrieval, the compiler/structural union,
structural expansion, deduplication, and final packing. Candidate-stage token
counts describe the whole bounded pool and are not context budgets; only the
packing stage is budget constrained.

`xl10` deliberately contains only single-document questions and is suitable
for pipeline validation, not research claims. XL100 remains the registered
decision set.

The first run downloads the pinned dataset metadata, the source PDFs referenced
by XL100, Docling model artifacts when needed, and the configured local
SentenceTransformers models. Later runs reuse verified caches. Pass
`--docling-artifacts-dir` to use pre-downloaded Docling models or override
`--embedding-model`, `--reranker-model`, and `--run-id` as needed.

Completed runs are atomically written beneath `artifacts/runs/<run-id>` and are
never overwritten. Each contains raw evidence metrics and contexts for fixed,
structural, long-context, and compiler arms, a complete reproducibility
manifest, `summary.json`, and `report.md`. The milestone stops before answer
generation so the evidence-recall/token curve can be reviewed first. Metric
conventions and the decision gate are defined in
[the experiment protocol](docs/experiment-protocol.md).

## Answer-generation benchmark

Generation consumes a completed run's `contexts.jsonl`; it does not repeat PDF
parsing, indexing, retrieval, or compilation. The model, prompt, output limit,
scoring, and pricing policy are identical across selected systems. Install the
optional provider dependency and inspect the guarded command with:

```shell
uv sync --extra generation
uv run --extra generation contextbench eval-generation --help
```

The command requires an explicit model ID, uncached/cached input and output
prices, and `--max-calls`. It refuses a run whose question × system × budget
cell count exceeds that authorization ceiling. Provider usage, resolved model
ID, latency, benchmark accuracy, token F1, ANLS, citation validity, and cost are
written to a separate immutable generation run. No default command performs a
paid model call.

## Gold-evidence representation experiment

To test whether the encoding itself helps an answer model independently of
retrieval, compare the same annotated source pages in four conditions:

- `raw`: minimal source text with citation IDs;
- `ir`: the same nodes with document, page, kind, heading, and source identity;
- `enriched`: IR plus query-independent agent features grounded wholly in the
  same nodes;
- `indexed`: a compact document map plus a bounded query-selected feature view
  over the same reusable enrichment and canonical source nodes.

```shell
uv run --extra generation contextbench eval-representation \
  --subset-file configs/subsets/xldev2-tables.json \
  --model <model-id> \
  --input-usd-per-million <price> \
  --cached-input-usd-per-million <price> \
  --output-usd-per-million <price> \
  --max-calls 8
```

The command requires explicit current pricing and a hard provider-call ceiling.
It records representation and provider tokens, answer metrics, citations,
latency, cost, the exact rendered contexts, and the one-time enrichment
configuration. Questions without released gold pages are skipped and disclosed.
No retrieval algorithm participates.
