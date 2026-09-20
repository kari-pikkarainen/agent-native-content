"""Acceptance tests for deterministic retrieval Arms A and B."""

from pathlib import Path

import pytest
from test_ir import FixtureTokenCounter, ingest_metadata, source_document

from contextbench.ir import project_document
from contextbench.retrieval import (
    HashEmbeddingModel,
    HybridIndex,
    RetrievalArm,
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
