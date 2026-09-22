"""Acceptance tests for deterministic retrieval Arms A and B."""

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from test_ir import FixtureTokenCounter, ingest_metadata, source_document

from contextbench.ir import project_document
from contextbench.ir.models import IRNodeKind
from contextbench.retrieval import (
    HashEmbeddingModel,
    HybridIndex,
    LexicalOverlapReranker,
    RetrievalArm,
    RetrievalChunk,
    RetrievalConfig,
    SentenceTransformerCrossEncoderReranker,
    SentenceTransformerEmbeddingModel,
    long_context_chunks,
    pack_evidence,
    rank_long_context,
)
from contextbench.retrieval.index import _index_key


@pytest.fixture
def retrieval_fixture(tmp_path: Path):
    document = source_document()
    ir = project_document(
        document,
        ingest_metadata(tmp_path),
        tokenizer=FixtureTokenCounter(),
    )
    config = RetrievalConfig(
        fixed_chunk_tokens=12,
        fixed_overlap_tokens=3,
        structural_chunk_tokens=24,
        candidate_limit=10,
        rerank_limit=5,
    )
    return document, ir, config


@pytest.mark.parametrize(
    "query",
    (
        "quarterly report",
        "results revenue",
        "north america",
        "revenue by region",
        "region 42",
        "metrics",
        "methods",
        "measured",
        "report highlights",
        "growth conclusion",
    ),
)
@pytest.mark.parametrize("arm", (RetrievalArm.FIXED, RetrievalArm.STRUCTURAL))
def test_fixture_queries_return_ranked_traceable_evidence(
    tmp_path: Path,
    retrieval_fixture,
    query: str,
    arm: RetrievalArm,
) -> None:
    source, ir, config = retrieval_fixture
    index = HybridIndex.build(
        [ir],
        arm=arm,
        config=config,
        source_documents={ir.id: source},
        tokenizer=FixtureTokenCounter(),
        embedder=HashEmbeddingModel(config.embedding_dimensions),
        artifacts_root=tmp_path / "artifacts",
    )

    ranked = index.retrieve(query)
    packet = index.pack(query, token_budget=12)

    assert ranked
    assert ranked[0].rank == 1
    assert ranked[0].chunk.document_id == ir.id
    assert ranked[0].chunk.source_node_ids
    assert ranked[0].chunk.source_item_ids
    assert ranked[0].scores.dense >= -1
    assert ranked[0].scores.sparse >= 0
    assert ranked[0].scores.fused > 0
    assert packet.token_count <= 12
    assert packet.metadata["arm"] == arm.value
    assert all(item.document_id == ir.id for item in packet.items)
    assert list((tmp_path / "artifacts" / "indexes").glob("*/index.json"))


def test_fixed_chunks_overlap_and_packing_deduplicates_source_material(
    tmp_path: Path,
) -> None:
    document = source_document()
    long_text = " ".join(f"term{index}" for index in range(40))
    document.add_text(label="text", text=long_text)
    counter = FixtureTokenCounter()
    ir = project_document(document, ingest_metadata(tmp_path), tokenizer=counter)
    config = RetrievalConfig(
        fixed_chunk_tokens=10,
        fixed_overlap_tokens=3,
        candidate_limit=20,
        rerank_limit=20,
    )

    index = HybridIndex.build(
        [ir],
        arm=RetrievalArm.FIXED,
        config=config,
        tokenizer=counter,
    )
    long_chunks = [chunk for chunk in index.chunks if "term" in chunk.text]
    assert len(long_chunks) >= 5
    assert all(chunk.token_count <= 10 for chunk in long_chunks)
    assert set(long_chunks[0].source_node_ids) & set(long_chunks[1].source_node_ids)

    packet = index.pack("term20", token_budget=30)
    assert packet.token_count <= 30
    assert len(packet.items) == len({item.source_item_ids for item in packet.items})


def test_long_context_preserves_body_source_order_without_retrieval(
    tmp_path: Path,
) -> None:
    source = source_document()
    counter = FixtureTokenCounter()
    document = project_document(
        source,
        ingest_metadata(tmp_path),
        tokenizer=counter,
    )
    expected = [
        node
        for node in document.nodes
        if node.text.strip()
        and node.content_layer == "body"
        and node.kind != IRNodeKind.LIST
    ]

    chunks = long_context_chunks([document], tokenizer=counter)
    ranked = rank_long_context(chunks, document_ids={document.id})
    packet = pack_evidence(
        "question",
        ranked,
        token_budget=sum(chunk.token_count for chunk in chunks),
        tokenizer=counter,
        metadata={"arm": RetrievalArm.LONG_CONTEXT.value},
    )

    assert [chunk.source_node_ids[0] for chunk in chunks] == [
        node.id for node in expected
    ]
    assert [item.content for item in packet.items] == [node.text for node in expected]
    assert packet.metadata == {"arm": "long_context"}
    assert all(item.scores.reranked == 0 for item in packet.items)


def test_search_text_drives_retrieval_but_emitted_text_stays_exact() -> None:
    config = RetrievalConfig(
        candidate_limit=2,
        rerank_limit=1,
        max_candidate_limit=2,
        max_rerank_limit=1,
    )
    chunks = (
        RetrievalChunk(
            id="chunk-wrong",
            arm=RetrievalArm.COMPILER,
            document_id="doc",
            text="Visible distractor",
            search_text="Visible distractor",
            token_count=2,
            source_node_ids=("node-wrong",),
            source_item_ids=("item-wrong",),
        ),
        RetrievalChunk(
            id="chunk-right",
            arm=RetrievalArm.COMPILER,
            document_id="doc",
            text="Precise emitted evidence",
            search_text="Hidden heading keyword Precise emitted evidence",
            token_count=3,
            source_node_ids=("node-right",),
            source_item_ids=("item-right",),
        ),
    )
    index = HybridIndex(chunks, config=config, tokenizer=FixtureTokenCounter())

    packet = index.pack("hidden keyword", token_budget=10)

    assert len(packet.items) == 1
    assert packet.items[0].content == "Precise emitted evidence"


def test_token_budget_expands_rerank_pool_by_candidate_token_mass() -> None:
    chunks = tuple(
        RetrievalChunk(
            id=f"chunk-{index:02d}",
            arm=RetrievalArm.COMPILER,
            document_id="doc",
            text=f"evidence {index}",
            search_text=f"shared query evidence {index}",
            token_count=1,
            source_node_ids=(f"node-{index}",),
            source_item_ids=(f"item-{index}",),
        )
        for index in range(20)
    )
    config = RetrievalConfig(
        candidate_limit=2,
        rerank_limit=2,
        candidate_token_multiplier=3,
        rerank_token_multiplier=2,
        max_candidate_limit=20,
        max_rerank_limit=20,
    )
    index = HybridIndex(chunks, config=config, tokenizer=FixtureTokenCounter())

    fixed_count = index.retrieve("shared query")
    token_aware = index.retrieve("shared query", token_budget=5)

    assert len(fixed_count) == 2
    assert len(token_aware) == 10
    assert sum(item.chunk.token_count for item in token_aware) >= 10


def test_candidate_retrieval_defers_reranking() -> None:
    class CountingReranker:
        name = "counting"
        version = "1"

        def __init__(self) -> None:
            self.calls = 0

        def score(self, _query, chunks):
            self.calls += 1
            return [float(index) for index, _chunk in enumerate(chunks)]

    chunks = tuple(
        RetrievalChunk(
            id=f"chunk-{index}",
            arm=RetrievalArm.COMPILER,
            document_id="doc",
            text=f"shared evidence {index}",
            token_count=1,
            source_node_ids=(f"node-{index}",),
            source_item_ids=(f"item-{index}",),
        )
        for index in range(3)
    )
    config = RetrievalConfig(candidate_limit=3, rerank_limit=3)
    reranker = CountingReranker()
    index = HybridIndex(
        chunks,
        config=config,
        tokenizer=FixtureTokenCounter(),
        reranker=reranker,
    )

    candidates = index.retrieve_candidates("shared evidence")

    assert reranker.calls == 0
    assert [candidate.scores.reranked for candidate in candidates] == [
        candidate.scores.fused for candidate in candidates
    ]
    ranked = index.rerank("shared evidence", candidates)
    assert reranker.calls == 1
    assert [evidence.chunk.id for evidence in ranked] == [
        "chunk-2",
        "chunk-1",
        "chunk-0",
    ]


def test_candidate_retrieval_honors_an_explicit_rerank_cap() -> None:
    chunks = tuple(
        RetrievalChunk(
            id=f"chunk-{index}",
            arm=RetrievalArm.COMPILER,
            document_id="doc",
            text=f"shared evidence {index}",
            token_count=1,
            source_node_ids=(f"node-{index}",),
            source_item_ids=(f"item-{index}",),
        )
        for index in range(20)
    )
    config = RetrievalConfig(
        candidate_limit=2,
        rerank_limit=2,
        max_candidate_limit=20,
        max_rerank_limit=20,
    )
    index = HybridIndex(chunks, config=config, tokenizer=FixtureTokenCounter())

    candidates = index.retrieve_candidates(
        "shared evidence",
        token_budget=20,
        maximum_rerank_limit=7,
    )

    assert len(candidates) == 7


def test_rerank_many_batches_query_candidate_pairs() -> None:
    class PairReranker:
        name = "pair"
        version = "1"

        def __init__(self) -> None:
            self.pair_calls = 0

        def score(self, _query, _chunks):
            raise AssertionError("individual scoring should not be used")

        def score_pairs(self, pairs):
            self.pair_calls += 1
            return [
                float(len(query) + index)
                for index, (query, _chunk) in enumerate(pairs)
            ]

    chunks = tuple(
        RetrievalChunk(
            id=f"chunk-{index}",
            arm=RetrievalArm.COMPILER,
            document_id="doc",
            text=f"evidence {index}",
            token_count=1,
            source_node_ids=(f"node-{index}",),
            source_item_ids=(f"item-{index}",),
        )
        for index in range(3)
    )
    config = RetrievalConfig(candidate_limit=3, rerank_limit=3)
    reranker = PairReranker()
    index = HybridIndex(
        chunks,
        config=config,
        tokenizer=FixtureTokenCounter(),
        reranker=reranker,
    )
    candidates = index.retrieve_candidates("evidence")

    first, second = index.rerank_many(
        (("one", candidates[:2]), ("longer", candidates[2:])),
    )

    assert reranker.pair_calls == 1
    assert len(first) == 2
    assert len(second) == 1


def test_repeated_retrieval_reuses_query_reranking() -> None:
    class CountingReranker:
        name = "counting"
        version = "1"

        def __init__(self) -> None:
            self.calls = 0

        def score(self, _query, chunks):
            self.calls += 1
            return [1.0] * len(chunks)

    chunks = (
        RetrievalChunk(
            id="chunk",
            arm=RetrievalArm.COMPILER,
            document_id="doc",
            text="cached evidence",
            token_count=2,
            source_node_ids=("node",),
            source_item_ids=("item",),
        ),
    )
    reranker = CountingReranker()
    index = HybridIndex(
        chunks,
        config=RetrievalConfig(candidate_limit=1, rerank_limit=1),
        tokenizer=FixtureTokenCounter(),
        reranker=reranker,
    )

    first = index.retrieve("cached evidence", document_ids={"doc"})
    second = index.retrieve("cached evidence", document_ids={"doc"})

    assert second is first
    assert reranker.calls == 1


def test_duplicate_search_text_does_not_consume_rerank_capacity() -> None:
    chunks = tuple(
        RetrievalChunk(
            id=f"duplicate-{index}",
            arm=RetrievalArm.COMPILER,
            document_id="doc",
            text=f"duplicate occurrence {index}",
            search_text="same repeated boilerplate",
            token_count=1,
            source_node_ids=(f"duplicate-node-{index}",),
            source_item_ids=(f"duplicate-item-{index}",),
        )
        for index in range(5)
    ) + (
        RetrievalChunk(
            id="unique",
            arm=RetrievalArm.COMPILER,
            document_id="doc",
            text="unique evidence",
            search_text="unique evidence",
            token_count=1,
            source_node_ids=("unique-node",),
            source_item_ids=("unique-item",),
        ),
    )
    config = RetrievalConfig(
        candidate_limit=6,
        rerank_limit=2,
        max_candidate_limit=6,
        max_rerank_limit=2,
    )
    index = HybridIndex(chunks, config=config, tokenizer=FixtureTokenCounter())

    ranked = index.retrieve("same repeated boilerplate")

    assert len(ranked) == 2
    assert {item.chunk.retrieval_text for item in ranked} == {
        "same repeated boilerplate",
        "unique evidence",
    }


def test_fixed_retrieval_capacity_keeps_budget_contexts_nested() -> None:
    chunks = tuple(
        RetrievalChunk(
            id=f"chunk-{index:02d}",
            arm=RetrievalArm.COMPILER,
            document_id="doc",
            text=f"evidence{index}",
            token_count=1,
            source_node_ids=(f"node-{index}",),
            source_item_ids=(f"item-{index}",),
        )
        for index in range(20)
    )
    config = RetrievalConfig(
        candidate_limit=2,
        rerank_limit=2,
        candidate_token_multiplier=3,
        rerank_token_multiplier=2,
        max_candidate_limit=20,
        max_rerank_limit=20,
    )
    index = HybridIndex(chunks, config=config, tokenizer=FixtureTokenCounter())

    small = index.pack(
        "evidence",
        token_budget=2,
        retrieval_token_budget=10,
    )
    large = index.pack(
        "evidence",
        token_budget=10,
        retrieval_token_budget=10,
    )

    assert small.items == large.items[: len(small.items)]
    assert small.token_count == 2
    assert large.token_count == 10


def test_repeated_builds_have_identical_rankings_and_artifact_keys(
    tmp_path: Path, retrieval_fixture
) -> None:
    source, ir, config = retrieval_fixture
    first = HybridIndex.build(
        [ir],
        arm=RetrievalArm.STRUCTURAL,
        config=config,
        source_documents={ir.id: source},
        tokenizer=FixtureTokenCounter(),
        artifacts_root=tmp_path / "one",
    )
    second = HybridIndex.build(
        [ir],
        arm=RetrievalArm.STRUCTURAL,
        config=config,
        source_documents={ir.id: source},
        tokenizer=FixtureTokenCounter(),
        artifacts_root=tmp_path / "two",
    )

    first_results = first.retrieve("revenue results")
    second_results = second.retrieve("revenue results")
    assert first_results == second_results
    first_artifact = next((tmp_path / "one" / "indexes").iterdir())
    second_artifact = next((tmp_path / "two" / "indexes").iterdir())
    assert first_artifact.name == second_artifact.name
    assert (first_artifact / "index.json").read_bytes() == (
        second_artifact / "index.json"
    ).read_bytes()


def test_repeated_build_loads_verified_vectors_without_reembedding(
    tmp_path: Path,
    retrieval_fixture,
) -> None:
    source, ir, config = retrieval_fixture

    class CountingEmbedder(HashEmbeddingModel):
        def __init__(self) -> None:
            super().__init__(config.embedding_dimensions)
            self.calls = 0

        def embed(self, texts):
            self.calls += 1
            return super().embed(texts)

    first_embedder = CountingEmbedder()
    first = HybridIndex.build(
        [ir],
        arm=RetrievalArm.STRUCTURAL,
        config=config,
        source_documents={ir.id: source},
        tokenizer=FixtureTokenCounter(),
        embedder=first_embedder,
        artifacts_root=tmp_path / "artifacts",
    )
    second_embedder = CountingEmbedder()
    second = HybridIndex.build(
        [ir],
        arm=RetrievalArm.STRUCTURAL,
        config=config,
        source_documents={ir.id: source},
        tokenizer=FixtureTokenCounter(),
        embedder=second_embedder,
        artifacts_root=tmp_path / "artifacts",
    )

    assert first_embedder.calls == 1
    assert second_embedder.calls == 0
    assert second.retrieve("revenue results") == first.retrieve("revenue results")


def test_global_index_respects_per_question_document_scope(tmp_path: Path) -> None:
    counter = FixtureTokenCounter()
    allowed_source = source_document()
    excluded_source = source_document()
    excluded_source.add_text(label="text", text="exclusive scope leak phrase")
    allowed = project_document(
        allowed_source,
        ingest_metadata(tmp_path),
        tokenizer=counter,
    )
    excluded_metadata = ingest_metadata(tmp_path).model_copy(
        update={"source_sha256": "d" * 64}
    )
    excluded = project_document(
        excluded_source,
        excluded_metadata,
        tokenizer=counter,
    )
    config = RetrievalConfig(candidate_limit=20, rerank_limit=20)
    index = HybridIndex.build(
        [allowed, excluded],
        arm=RetrievalArm.FIXED,
        config=config,
        tokenizer=counter,
    )

    packet = index.pack(
        "exclusive scope leak phrase",
        token_budget=100,
        document_ids={allowed.id},
    )

    assert packet.items
    assert {item.document_id for item in packet.items} == {allowed.id}


@dataclass(frozen=True)
class _Identified:
    """Stand-in for a document or chunk: the index key reads only the id."""

    id: str


_KEY_DOCUMENTS = (_Identified("ir-doc-a"), _Identified("ir-doc-b"))
_KEY_CHUNKS = (_Identified("chunk-a"), _Identified("chunk-b"))


def _key(**overrides: object) -> str:
    arguments: dict[str, object] = {
        "arm": RetrievalArm.FIXED,
        "config": RetrievalConfig(),
        "chunks": _KEY_CHUNKS,
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "embedding_version": "5.7.0",
        "embedding_revision": "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
        "reranker_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
        "reranker_version": "5.7.0",
        "reranker_revision": "233902d25c440f23af6f7d6e94d2946bac0bee0a",
        "tokenizer": "o200k_base",
        "tokenizer_version": "0.12.0",
    }
    arguments.update(overrides)
    return _index_key(_KEY_DOCUMENTS, **arguments)


def test_index_key_changes_with_model_revision() -> None:
    """A moved hub branch must rekey even when every other input is identical."""
    pinned = _key()

    assert _key(embedding_revision="0" * 40) != pinned
    assert _key(reranker_revision="0" * 40) != pinned
    assert _key(embedding_revision=None) != pinned
    assert _key() == pinned


def test_index_key_is_stable_for_a_fixed_revision() -> None:
    """Pin the key for one fixed input so a payload change cannot pass silently.

    The literal was produced by this payload and nothing else. Any accidental
    change to the key payload, its field names, or the retrieval config
    defaults would strand every cached index under a new key, so that change
    has to be made deliberately.
    """
    assert _key(
        embedding_model="hash-256-v1",
        embedding_version="1",
        embedding_revision=None,
        reranker_model="lexical-overlap-v1",
        reranker_version="1",
        reranker_revision=None,
    ) == "09fca44765c922c8ba0b5a1812ae172ab0a578842a7e52ff1887a14e40bdf99e"

    assert _key() == "fcafc11e9de5b97151c6b0bb473435f3fd6196e6e7fe3d247403fdb7b5c2e927"


def test_configured_hub_model_requires_a_revision() -> None:
    """Hub-backed adapters must refuse to resolve the moving default branch.

    An injected loader keeps ``sentence_transformers`` out of the test run;
    the refusal has to happen before any weights are touched, so the loader
    must never be called.
    """
    calls: list[tuple[str, object]] = []

    def loader(model_name: str, *, revision: str) -> object:
        calls.append((model_name, revision))
        return object()

    for revision in (None, "", "   "):
        with pytest.raises(ValueError, match="pinned model revision is required"):
            SentenceTransformerEmbeddingModel(
                "BAAI/bge-small-en-v1.5",
                revision=revision,
                loader=loader,
            )
        with pytest.raises(ValueError, match="pinned model revision is required"):
            SentenceTransformerCrossEncoderReranker(
                "cross-encoder/ms-marco-MiniLM-L-6-v2",
                revision=revision,
                loader=loader,
            )
    assert calls == []

    embedder = SentenceTransformerEmbeddingModel(
        "BAAI/bge-small-en-v1.5",
        revision="5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
        loader=loader,
    )
    reranker = SentenceTransformerCrossEncoderReranker(
        "cross-encoder/ms-marco-MiniLM-L-6-v2",
        revision="233902d25c440f23af6f7d6e94d2946bac0bee0a",
        loader=loader,
    )

    assert calls == [
        ("BAAI/bge-small-en-v1.5", "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"),
        (
            "cross-encoder/ms-marco-MiniLM-L-6-v2",
            "233902d25c440f23af6f7d6e94d2946bac0bee0a",
        ),
    ]
    assert embedder.revision == "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
    assert reranker.revision == "233902d25c440f23af6f7d6e94d2946bac0bee0a"


def test_offline_hash_models_report_no_revision() -> None:
    """Deterministic offline models have no hub identity to pin."""
    assert HashEmbeddingModel(256).revision is None
    assert LexicalOverlapReranker().revision is None


_RANKING_CORPUS_TEXTS = (
    "Revenue increased strongly across every reported region this quarter.",
    "Revenue in North America grew by eleven percent year over year.",
    "Revenue in Europe declined slightly against the prior quarter.",
    "Operating margin improved once the restructuring charge cleared.",
    "The regional revenue table lists North America, Europe, and Asia.",
    "North America headcount grew faster than any other region.",
    "Asia revenue remained flat while regional costs rose.",
    "Quarterly highlights cover revenue, margin, and regional growth.",
    "The methodology section explains how reporting regions are defined.",
    "Costs rose across Europe because of higher energy prices.",
    "Growth in this quarterly report is measured year over year.",
    "The conclusion notes revenue growth and margin recovery.",
    "Region 42 is an internal identifier and not a reporting region.",
    "Reported metrics include revenue, margin, headcount, and growth.",
)

_UNCHANGED_RANKING_QUERIES = (
    "revenue by region",
    "north america growth",
    "europe costs",
    "margin recovery",
    "quarterly metrics",
    "region 42",
    # The only query whose reranked order differs from the fused order, which
    # is what makes reranker and BM25 scoring changes observable here.
    "europe costs identifier",
)


def _ranking_corpus() -> tuple[RetrievalChunk, ...]:
    """Build the fixed offline corpus the pre-pin ranking table was captured from."""
    return tuple(
        RetrievalChunk(
            id=f"ranking-chunk-{position:02d}",
            arm=RetrievalArm.FIXED,
            document_id="ranking-doc",
            text=chunk_text,
            token_count=len(chunk_text.split()),
            source_node_ids=(f"ranking-node-{position:02d}",),
            source_item_ids=(f"ranking-item-{position:02d}",),
        )
        for position, chunk_text in enumerate(_RANKING_CORPUS_TEXTS)
    )


def _ranking_config() -> RetrievalConfig:
    return RetrievalConfig(candidate_limit=5, rerank_limit=4)


def _observed_rankings(index: HybridIndex) -> dict[str, tuple[tuple[str, int], ...]]:
    return {
        query: tuple((item.chunk.id, item.rank) for item in index.retrieve(query))
        for query in _UNCHANGED_RANKING_QUERIES
    }


# Captured by running the pre-pin implementation at d7f427e against this exact
# corpus, before the embedding and reranker revisions entered the index key, so
# the rekey is provably a cache invalidation rather than a change in results.
# Recapture the same way, from an extracted d7f427e tree, if the corpus or the
# queries change; never by recording what the current code prints.
_RANKINGS_BEFORE_THE_REVISION_PIN = {
    "revenue by region": (
        ("ranking-chunk-00", 1),
        ("ranking-chunk-01", 2),
        ("ranking-chunk-12", 3),
        ("ranking-chunk-06", 4),
    ),
    "north america growth": (
        ("ranking-chunk-05", 1),
        ("ranking-chunk-04", 2),
        ("ranking-chunk-01", 3),
        ("ranking-chunk-07", 4),
    ),
    "europe costs": (
        ("ranking-chunk-09", 1),
        ("ranking-chunk-06", 2),
        ("ranking-chunk-02", 3),
        ("ranking-chunk-04", 4),
    ),
    "margin recovery": (
        ("ranking-chunk-11", 1),
        ("ranking-chunk-03", 2),
        ("ranking-chunk-07", 3),
        ("ranking-chunk-13", 4),
    ),
    "quarterly metrics": (
        ("ranking-chunk-07", 1),
        ("ranking-chunk-13", 2),
        ("ranking-chunk-10", 3),
        ("ranking-chunk-00", 4),
    ),
    "region 42": (
        ("ranking-chunk-12", 1),
        ("ranking-chunk-00", 2),
        ("ranking-chunk-05", 3),
        ("ranking-chunk-01", 4),
    ),
    # Fusion ranks these 09, 06, 03, 12; the reranker swaps the last two.
    "europe costs identifier": (
        ("ranking-chunk-09", 1),
        ("ranking-chunk-06", 2),
        ("ranking-chunk-12", 3),
        ("ranking-chunk-03", 4),
    ),
}


def test_offline_index_rankings_are_unchanged_by_the_revision_pin() -> None:
    """Threading revisions through must invalidate caches, not reorder evidence.

    Every cached index rekeys because the key payload gained two fields, so a
    key assertion alone cannot tell a cache invalidation from a regression.
    This compares the ranking itself: for each query the ordered
    ``(chunk.id, rank)`` pairs must equal what the pre-pin code at d7f427e
    produced from the same corpus.

    Scope, measured by mutation rather than asserted. Dropping the dense
    contribution from RRF, negating or flattening the reranker score,
    reversing or unscaling BM25, removing BM25 length normalization, and
    dropping the ``HashEmbeddingModel`` sign bit each change at least one row
    and fail elementwise. Only ``europe costs identifier`` has a reranked
    order that differs from its fused order (fusion gives 09, 06, 03, 12; the
    reranker swaps the last two), so it alone catches a constant reranker
    score, and it alone catches dropping the BM25 idf factor. The other six
    queries absorb BM25 score-scaling changes in RRF fusion and the top-four
    rerank cut even when the sparse top-five genuinely changes.

    So this is a cache-invalidation check over one small offline corpus, not a
    general scoring guard. A regression that preserves relative order at every
    stage, or one confined to score magnitudes these seven queries absorb,
    passes here: changing ``rrf_k`` from 60 to 1, for instance, leaves the
    fused order identical. Any change to chunking, BM25, fusion, or reranking
    needs its own evidence; a green run of this table is not that evidence.
    """
    index = HybridIndex(
        _ranking_corpus(),
        config=_ranking_config(),
        embedder=HashEmbeddingModel(256),
        reranker=LexicalOverlapReranker(),
        tokenizer=FixtureTokenCounter(),
    )

    assert index.embedder.revision is None
    assert index.reranker.revision is None
    assert _observed_rankings(index) == _RANKINGS_BEFORE_THE_REVISION_PIN


def test_rekeyed_index_artifacts_still_round_trip(
    tmp_path: Path, retrieval_fixture
) -> None:
    """The index saved under the revision-aware key must load back unchanged."""
    source, ir, config = retrieval_fixture
    artifacts_root = tmp_path / "artifacts"
    built = HybridIndex.build(
        [ir],
        arm=RetrievalArm.FIXED,
        config=config,
        source_documents={ir.id: source},
        tokenizer=FixtureTokenCounter(),
        artifacts_root=artifacts_root,
    )
    reloaded = HybridIndex.build(
        [ir],
        arm=RetrievalArm.FIXED,
        config=config,
        source_documents={ir.id: source},
        tokenizer=FixtureTokenCounter(),
        artifacts_root=artifacts_root,
    )

    artifact = next((artifacts_root / "indexes").iterdir()) / "index.json"
    stored = json.loads(artifact.read_text(encoding="utf-8"))
    assert stored["embedding_revision"] is None
    assert stored["reranker_revision"] is None
    assert built.retrieve("revenue results") == reloaded.retrieve("revenue results")
