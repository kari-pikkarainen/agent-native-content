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
