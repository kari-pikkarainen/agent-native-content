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

### Known defect: the dense channel ranks non-matches

Stage 1 returns only chunks that match at least one query term: a chunk scoring
zero under BM25 carries no lexical evidence, so giving it a rank gave it
reciprocal-rank-fusion credit ordered by chunk ID, which is a hash rather than
relevance.

Stage 2 still has that defect. `HybridIndex._dense_search` applies no
positivity guard: it sorts every similarity, including exactly `0.0` and
negative values, truncates to the candidate limit, and breaks ties by chunk ID.
A chunk with zero similarity to the query therefore receives a dense rank in
hash order and the full `1 / (rrf_k + rank)` credit that rank is worth, exactly
as zero-score chunks once did on the sparse side. Short queries against the
default 256-dimension hash embedding leave most chunks at similarity exactly
`0.0`, so this is the common case rather than a corner.

This is recorded, not fixed. Fixing it moves published numbers, so it must be
its own change with its own re-measurement, not a rider on the BM25 fix. Any
rerun that republishes a baseline should decide this first: if the dense mirror
is fixed after a baseline is republished, every number in that baseline moves
again and the rerun is wasted.

### How much the sparse defect cost each arm

The share of the sparse channel that was noise was measured before the fix,
and it is not the same share in every arm: 6 of 35 sparse ranks were unearned
on the ranking corpus, 15 of 30 on the fixed retrieval fixture, and 15 of 20
on the structural one, where five queries matched no chunk at all and their
whole sparse channel was noise. The arms therefore did not pay equally for the
defect, which is why a rerun has to remeasure the paired deltas rather than
carry the published ones over. These counts come from the committed fixture
corpora, which are small: they establish that the effect differs by arm, not
how large it is on the benchmark subsets.

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

The revision is not part of `RetrievalConfig`, so a programmatic caller
constructs the adapters itself and passes them to `HybridIndex.build`:

```python
from contextbench.retrieval import (
    RetrievalConfig,
    SentenceTransformerCrossEncoderReranker,
    SentenceTransformerEmbeddingModel,
)

config = RetrievalConfig(
    embedding_model="BAAI/bge-small-en-v1.5",
    reranker_model="cross-encoder/ms-marco-MiniLM-L-6-v2",
)
embedder = SentenceTransformerEmbeddingModel(
    config.embedding_model,
    revision="5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
)
reranker = SentenceTransformerCrossEncoderReranker(
    config.reranker_model,
    revision="233902d25c440f23af6f7d6e94d2946bac0bee0a",
)
```

Each revision must be the commit its own model ID resolved to; both adapters
refuse an empty or missing revision.

The same selected model configuration must be used for Arms A and B. Model
loading is lazy; importing the retrieval package does not make network calls.

## Derived index artifacts

`HybridIndex.build(..., artifacts_root=Path("artifacts"))` writes:

```text
artifacts/indexes/<content-and-config-sha256>/index.json
```

The key includes the arm, IR document IDs, chunk IDs, retrieval configuration,
resolved embedding, reranker, and tokenizer identities and implementation
versions, and the pinned embedding and reranker model revisions. The serialized
artifact includes the same provenance plus canonical chunks and vectors, so a
changed implementation, or the same model ID repinned to different weights,
selects a different derived index path.

Adding the revisions to the key invalidated the existing cache. All 31
indexes under `artifacts/indexes/` were written before the pin, record the two
hub models without a revision, and are now unreachable by key: they must be
rebuilt. That is cache invalidation, not a change in results, but it means the
next run pays full index construction for every arm rather than reusing a warm
cache.

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
    # Omit both to get the offline `hash-256-v1` and `lexical-overlap-v1`
    # fallbacks; hub-backed models are passed in already pinned, as above.
    embedder=embedder,
    reranker=reranker,
)
ranked = index.retrieve("Which region grew?")
packet = index.pack("Which region grew?", token_budget=2048)
```

The packer rejects any output whose recorded token count exceeds the supplied
budget. No LLM call is made by either baseline.
