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

### Both channels refuse non-matches

Stage 1 returns only chunks that match at least one query term: a chunk scoring
zero under BM25 carries no lexical evidence, so giving it a rank gave it
reciprocal-rank-fusion credit ordered by chunk ID, which is a hash rather than
relevance.

Stage 2 now applies the same rule. `HybridIndex._dense_search` drops any chunk
whose similarity to the query is not strictly positive before ranking. Vectors
are L2-normalized, so the similarity is a cosine and `<= 0.0` means at or
beyond orthogonal: there is no shared direction to rank on. Previously the
stage sorted every similarity including exactly `0.0` and negative values,
truncated to the candidate limit, and broke ties by chunk ID, so a chunk with
zero similarity collected a dense rank in hash order and the full
`1 / (rrf_k + rank)` credit that rank is worth. Short queries against the
default 256-dimension hash embedding leave most chunks at similarity exactly
`0.0`, so that was the common case rather than a corner.

This was previously recorded here as a known defect held open by a research
question about empty results. That question has been decided, and the
subsections below record both the decision and the measurements it rests on.

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
  vectors themselves, which it reproduces to approximately `5e-7` -- float32
  precision. An earlier version of this page said `6e-8`; independent
  reproduction reached `4.47e-07`, about seven times looser, which is
  consistent with float32 batch nondeterminism rather than with a disagreement
  about the vectors. The positivity conclusion is unaffected -- the smallest
  similarity involved is `+0.1878`, five orders of magnitude above the
  discrepancy -- but a reader reproducing the work will not hit `6e-8` and
  should not treat missing it as a failure. Read the agreement as float32
  precision, not as a fixed constant.)

The positivity guard on `_dense_search` is therefore inert under the production
embedder: it discards nothing on any run the benchmark has published, and so it
cannot change a published number. This narrows the guard's reach rather than
dismissing it. It is a genuine correctness change -- the code really did hand
rank credit to zero-similarity chunks, and would do so for any embedder whose
vectors are not confined to a positive cone -- but the reachable case today is
the offline `hash-256-v1` model, whose sign-bit vectors leave most chunks at
exactly `0.0` against a short query.

#### Empty retrieval is a legitimate outcome

The guard raises a policy question that only the hash model exposes. BM25
already refuses zero-score chunks; now that the dense channel also refuses
zero-similarity chunks, a query matching nothing in either channel yields no
candidates at all, where it previously yielded hash-ordered non-matches.

**The decision is that empty is correct.** A channel holding no evidence
returns nothing. That is exactly the semantics BM25 has had since its own
guard landed, and the asymmetry between the two channels was the defect, not
the emptiness. No floor is applied. Returning the top-k anyway would reinstate
precisely the hash-ordered credit the guard removes, so it is not a neutral
default; it is the old behavior under a new name. A downstream consumer that
needs a non-empty context must widen its query or its scope, not be handed
chunks the retrieval stack could not justify.

Measured on the committed fixtures, the guard empties 7 of the 20 fixture
(arm, query) pairs -- `fixed`/`metrics`, `fixed`/`growth conclusion`, and
`structural` for `quarterly report`, `metrics`, `methods`, `report highlights`
and `growth conclusion` -- and shortens the `region 42` row of the pinned
ranking table from four results to three, because only three of those chunks
carry any signal in either channel. Each of those 7 pairs previously ranked a
chunk first with sparse and dense scores both exactly `0.0`.

Consequences, audited across the consumers of `retrieve()` and `pack()`:

- `pack()` on an empty ranking yields a valid packet with zero items, zero
  tokens, and its metadata intact. `ContextPacket` permits an empty `items`
  tuple and its budget invariant holds trivially.
- Evidence-page recall for an empty context is `0.0` against annotated gold
  pages, not a vacuous `1.0`. The `1.0` branch in `evaluation/evidence.py` is
  reached only when a question annotates no gold pages at all, which is a
  property of the question and independent of retrieval.
- `tokens_to_full_evidence` is `None` for an empty context, meaning full
  evidence was never reached, and the summary's median skips it.
- Redundancy over zero items is `0.0` by an explicit guard, not a division by
  zero.
- Reports render an empty cell numerically; `n/a` appears only where a metric
  is genuinely undefined for every question in the cell.
- Answer generation receives a prompt with an empty evidence section. A
  grounded answer has nothing it may cite, so its citation validity and
  citation support are `0.0`. This is the existing rule for an empty citation
  list and is the intended reading: an uncited claim is ungrounded whatever
  the reason.

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
