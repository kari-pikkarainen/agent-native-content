"""Acceptance tests for deterministic retrieval Arms A and B."""

from pathlib import Path

import pytest
from test_ir import FixtureTokenCounter, ingest_metadata, source_document

from contextbench.ir import project_document
from contextbench.retrieval import (
    HashEmbeddingModel,
    HybridIndex,
    RetrievalArm,
    RetrievalChunk,
    RetrievalConfig,
)


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
