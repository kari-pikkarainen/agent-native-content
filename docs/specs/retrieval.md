# Retrieval Baselines Specification

Milestone 4 implements benchmark Arms A and B over the same retrieval stack.
Only the chunk construction differs.

## Arms

Arm A (`fixed`) concatenates source-node text in IR ordinal order and creates
512-token windows with a 64-token overlap. Each window retains every source node
and page it contains.

Arm B (`structural`) uses Docling's `HybridChunker` with a 512-token limit,
native heading metadata, and repeated table headers. Each chunk maps back to the
Docling source item references emitted by the chunker and then to IR nodes.

Both limits and all retrieval parameters are fields of `RetrievalConfig`; tests
use smaller values only to keep fixtures compact.

## Shared retrieval pipeline

Both arms run the same deterministic stages:

1. BM25 sparse retrieval with explicit `k1`, `b`, and candidate limit.
2. Dense brute-force cosine retrieval over the same candidate corpus.
3. Reciprocal Rank Fusion with explicit `rrf_k`.
4. A shared reranker over the fused top candidates.
5. Provenance-aware token-budget packing.

The returned `RankedEvidence` records dense, sparse, fused, and reranked scores.
Packed `ContextItem` values carry document IDs, pages, heading paths, IR node
IDs, Docling source item IDs, and an evidence ID suitable for answer citations.

## Models

The default `hash-256-v1` embedding and `lexical-overlap-v1` reranker are
deterministic, local fallbacks for tests and smoke runs. They avoid model
downloads and make repeated fixture runs byte-stable.

Benchmark runs can select SentenceTransformers models by setting
`RetrievalConfig.embedding_model` and `reranker_model` to model names and
installing the optional dependency. A model name alone names a moving Hugging
Face branch, so a hub-backed model must also be given a pinned revision
(`--embedding-revision` / `--reranker-revision`); loading one without a
revision fails rather than resolving whatever `main` points at.

```shell
uv sync --extra retrieval
```

The same selected model configuration must be used for Arms A and B. Model
loading is lazy; importing the retrieval package does not make network calls.

## Derived index artifacts

`HybridIndex.build(..., artifacts_root=Path("artifacts"))` writes:

```text
artifacts/indexes/<content-and-config-sha256>/index.json
```

The key includes the arm, IR document IDs, chunk IDs, retrieval configuration,
and resolved embedding, reranker, and tokenizer identities and implementation
versions. The serialized artifact includes the same provenance plus canonical
chunks and vectors, so a changed implementation selects a different derived
index path.

Benchmark evaluation may build a single index per arm over all subset source
documents. `retrieve(..., document_ids=...)` and `pack(..., document_ids=...)`
filter both sparse and dense candidates before fusion and reranking, preventing
evidence from outside a question's declared document scope.

## API

```python
from contextbench.retrieval import HybridIndex, RetrievalArm, RetrievalConfig

index = HybridIndex.build(
    [ir_document],
    arm=RetrievalArm.STRUCTURAL,
    config=RetrievalConfig(),
    source_documents={ir_document.id: docling_document},
    artifacts_root=Path("artifacts"),
)
ranked = index.retrieve("Which region grew?")
packet = index.pack("Which region grew?", token_budget=2048)
```

The packer rejects any output whose recorded token count exceeds the supplied
budget. No LLM call is made by either baseline.
