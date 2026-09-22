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

This is recorded, not fixed.

#### It cannot fire on a benchmark run

An earlier version of this section claimed that fixing the dense channel moves
published numbers and so must precede any rerun. That claim was not measured,
and it is false. With `BAAI/bge-small-en-v1.5`, the embedder every published
run used, a non-positive similarity does not occur:

- Corpus side. All 31 cached indexes under `artifacts/indexes/` store
  384-dimension unit-normalized vectors. Their exhaustive pairwise cosines --
  3,715,675,587 distinct chunk pairs, including the three 36,294-chunk
  indexes -- contain no value at or below zero. Per-index minima run from
  `+0.1108` to `+0.5028`, and every chunk lies within 19.9 to 64.8 degrees of
  its corpus mean. The vectors occupy a narrow cone, not the whole sphere.
- Query side. The 24 `xldev24` questions, embedded at the pinned revision
  `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` with CLS pooling and L2
  normalization, scored against those stored vectors give 6,928,752
  query-chunk similarities. None is at or below zero; the minimum is `+0.1878`;
  none appears in any top-40. (The reproduction was checked against the stored
  vectors themselves, which it reproduces to within `6e-8`.)

A positivity guard on `_dense_search` is therefore inert under the production
embedder: it would discard nothing on any run the benchmark has published, and
so it cannot change a published number. This narrows the defect rather than
dismissing it. The guard is still a genuine correctness change -- the code
really does hand rank credit to zero-similarity chunks, and would do so for any
embedder whose vectors are not confined to a positive cone -- but the reachable
case today is the offline `hash-256-v1` model, whose sign-bit vectors leave
most chunks at exactly `0.0` against a short query.

#### What blocks the fix is an empty-candidate question

The guard is not blocked on the rerun. It is blocked on a policy question the
hash model exposes. BM25 already refuses zero-score chunks; if the dense
channel also refuses zero-similarity chunks, a query that matches nothing in
either channel yields no candidates at all, where it previously yielded
hash-ordered non-matches. Measured on the committed fixtures, a strict guard
empties 7 of the 20 fixture (arm, query) pairs -- `fixed`/`metrics`,
`fixed`/`growth conclusion`, and `structural` for `quarterly report`,
`metrics`, `methods`, `report highlights` and `growth conclusion` -- and drops
the `region 42` row of the pinned ranking table from four results to three,
because only three of those chunks carry any signal in either channel.

Whether an empty retrieval is the correct outcome for a query that matches
nothing, or whether the pipeline needs a floor, is a research decision and is
deliberately not taken here. Returning the top-k anyway would reinstate exactly
the hash-ordered credit the guard removes, so it is not a neutral default.

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
