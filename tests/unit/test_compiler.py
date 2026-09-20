"""Acceptance tests for deterministic context compiler v0."""

from pathlib import Path

import pytest
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.base import Size
from docling_core.types.doc.document import TableCell, TableData
from docling_core.types.doc.labels import DocItemLabel
from test_ir import FixtureTokenCounter, ingest_metadata, provenance

import contextbench.compiler.expand as compiler_expand
from contextbench.compiler import (
    CompilerConfig,
    CompilerQueryCache,
    DocumentScope,
    compile_context,
    compile_context_with_trace,
)
from contextbench.compiler.candidates import node_chunks
from contextbench.compiler.expand import _penalize
from contextbench.ir import project_document
from contextbench.ir.models import IRNodeKind
from contextbench.retrieval import RetrievalConfig, RetrievalScores
from contextbench.retrieval.index import HybridIndex


def compiler_source() -> DoclingDocument:
    document = DoclingDocument(name="compiler-fixture")
    document.add_page(1, Size(width=612, height=792))
    document.add_page(2, Size(width=612, height=792))
    title = document.add_title(
        "Annual Report",
        prov=provenance(1, "Annual Report", 760),
    )
    results = document.add_heading(
        "Results",
        level=1,
        parent=title,
        prov=provenance(1, "Results", 730),
    )
    for index, text in enumerate(
        (
            "Context before target.",
            "Target revenue increased.",
            "Context after target.",
        )
    ):
        document.add_text(
            label=DocItemLabel.TEXT,
            text=text,
            parent=results,
            prov=provenance(1, text, 700 - index * 25),
        )

    list_group = document.add_list_group(name="Markets", parent=results)
    for index, text in enumerate(
        ("Alpha market grew.", "Beta market declined.", "Gamma market held.")
    ):
        document.add_list_item(
            text=text,
            parent=list_group,
            prov=provenance(1, text, 610 - index * 20),
        )

    caption = document.add_text(
        label=DocItemLabel.CAPTION,
        text="Revenue table",
        parent=results,
        prov=provenance(1, "Revenue table", 540),
    )
    cells = [
        TableCell(
            start_row_offset_idx=row,
            end_row_offset_idx=row + 1,
            start_col_offset_idx=column,
            end_col_offset_idx=column + 1,
            text=text,
            column_header=row == 0,
        )
        for row, values in enumerate((("Region", "Revenue"), ("North", "42")))
        for column, text in enumerate(values)
    ]
    document.add_table(
        data=TableData(table_cells=cells, num_rows=2, num_cols=2),
        caption=caption,
        parent=results,
        prov=provenance(1, "Region Revenue North 42", 510),
    )
    duplicate = "Repeated duplicate phrase."
    document.add_text(
        label=DocItemLabel.TEXT,
        text=duplicate,
        parent=results,
        prov=provenance(1, duplicate, 470),
    )
    document.add_text(
        label=DocItemLabel.TEXT,
        text=duplicate,
        parent=results,
        prov=provenance(1, duplicate, 445),
    )
    methods = document.add_heading(
        "Methods",
        level=1,
        parent=title,
        prov=provenance(2, "Methods", 760),
    )
    document.add_text(
        label=DocItemLabel.TEXT,
        text="Measurements were audited.",
        parent=methods,
        prov=provenance(2, "Measurements were audited.", 730),
    )
    return document


def oversized_table_source() -> DoclingDocument:
    document = DoclingDocument(name="oversized-table")
    document.add_page(1, Size(width=612, height=792))
    heading = document.add_heading(
        "Results",
        level=1,
        prov=provenance(1, "Results", 750),
    )
    caption = document.add_text(
        label=DocItemLabel.CAPTION,
        text="District revenue",
        parent=heading,
        prov=provenance(1, "District revenue", 720),
    )
    values = [("District", "Revenue")] + [
        (f"District{index}", str(100 + index)) for index in range(12)
    ]
    cells = [
        TableCell(
            start_row_offset_idx=row,
            end_row_offset_idx=row + 1,
            start_col_offset_idx=column,
            end_col_offset_idx=column + 1,
            text=text,
            column_header=row == 0,
        )
        for row, row_values in enumerate(values)
        for column, text in enumerate(row_values)
    ]
    document.add_table(
        data=TableData(
            table_cells=cells,
            num_rows=len(values),
            num_cols=2,
        ),
        caption=caption,
        parent=heading,
        prov=provenance(1, "district table", 690),
    )
    return document


@pytest.fixture
def compiler_fixture(tmp_path: Path):
    source = compiler_source()
    counter = FixtureTokenCounter()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=counter)
    scope = DocumentScope.from_documents(
        [ir],
        source_documents={ir.id: source},
    )
    return source, ir, scope, counter


def compiler_config(**updates) -> CompilerConfig:
    base = CompilerConfig(
        retrieval=RetrievalConfig(candidate_limit=20, rerank_limit=10),
    )
    return base.model_copy(update=updates)


def test_prebuilt_global_index_matches_per_scope_index(compiler_fixture) -> None:
    _source, ir, scope, counter = compiler_fixture
    config = compiler_config()
    index = HybridIndex(
        node_chunks([ir], tokenizer=counter),
        config=config.retrieval,
        tokenizer=counter,
    )

    direct = compile_context(
        "target revenue increased",
        scope,
        40,
        config,
        tokenizer=counter,
    )
    reused = compile_context(
        "target revenue increased",
        scope,
        40,
        config,
        tokenizer=counter,
        hybrid_index=index,
    )
    ranked = index.retrieve("target revenue increased", token_budget=40)
    pre_ranked = compile_context(
        "target revenue increased",
        scope,
        40,
        config,
        tokenizer=counter,
        hybrid_index=index,
        ranked_evidence=ranked,
    )

    assert reused == direct
    assert pre_ranked == direct


def test_compiler_trace_preserves_output_and_candidate_boundaries(
    compiler_fixture,
) -> None:
    _source, _ir, scope, counter = compiler_fixture
    config = compiler_config(
        include_previous_sibling=True,
        include_next_sibling=True,
    )

    packet, trace = compile_context_with_trace(
        "target revenue increased",
        scope,
        40,
        config,
        tokenizer=counter,
    )

    assert packet == compile_context(
        "target revenue increased",
        scope,
        40,
        config,
        tokenizer=counter,
    )
    assert trace.ranked_evidence
    assert len(trace.expanded_candidates) >= len(trace.ranked_evidence)
    assert len(trace.deduplicated_candidates) <= len(trace.expanded_candidates)


def test_pre_ranked_evidence_rejects_documents_outside_scope(
    compiler_fixture,
) -> None:
    _source, ir, scope, counter = compiler_fixture
    config = compiler_config()
    index = HybridIndex(
        node_chunks([ir], tokenizer=counter),
        config=config.retrieval,
        tokenizer=counter,
    )
    ranked = index.retrieve("target revenue increased", token_budget=40)
    foreign = ranked[0].model_copy(
        update={
            "chunk": ranked[0].chunk.model_copy(
                update={"document_id": "foreign-document"}
            )
        }
    )

    with pytest.raises(ValueError, match="outside document_scope"):
        compile_context(
            "target revenue increased",
            scope,
            40,
            config,
            tokenizer=counter,
            hybrid_index=index,
            ranked_evidence=(foreign,),
        )


def test_node_candidates_exclude_furniture_and_search_with_headings(
    compiler_fixture,
) -> None:
    _source, ir, _scope, counter = compiler_fixture
    target = next(node for node in ir.nodes if node.text == "Target revenue increased.")
    repeated = next(
        node for node in ir.nodes if node.text == "Repeated duplicate phrase."
    )
    furniture = repeated.model_copy(update={"content_layer": "furniture"})
    nodes = tuple(furniture if node.id == repeated.id else node for node in ir.nodes)
    document = ir.model_copy(update={"nodes": nodes})

    chunks = node_chunks([document], tokenizer=counter)

    target_chunk = next(chunk for chunk in chunks if target.id in chunk.source_node_ids)
    assert target_chunk.text == "Target revenue increased."
    assert target_chunk.search_text == (
        "Annual Report\nResults\nTarget revenue increased."
    )
    assert all(furniture.id not in chunk.source_node_ids for chunk in chunks)


def test_table_row_candidates_repeat_headers_and_mark_blank_cells(
    compiler_fixture,
) -> None:
    _source, ir, _scope, counter = compiler_fixture
    table_node = next(node for node in ir.nodes if node.kind == IRNodeKind.TABLE)
    assert table_node.table is not None
    table = table_node.table.model_copy(
        update={
            "column_headers": ("Region", "Main References"),
            "rows": (
                ("Region", "Main References"),
                ("North", "42"),
                ("South", ""),
            )
        }
    )
    replacement = table_node.model_copy(update={"table": table})
    document = ir.model_copy(
        update={
            "nodes": tuple(
                replacement if node.id == table_node.id else node
                for node in ir.nodes
            )
        }
    )

    chunks = node_chunks(
        [document],
        tokenizer=counter,
        table_rows=True,
    )
    rows = [chunk for chunk in chunks if table_node.id in chunk.source_node_ids]

    assert [chunk.text for chunk in rows] == [
        "Revenue table\nRegion: North | Main References: 42",
        "Revenue table\nRegion: South | Main References: [blank]",
    ]
    assert all("MainReferences" in chunk.search_text for chunk in rows)
    assert all(chunk.source_item_ids == table_node.source_item_ids for chunk in rows)


def test_compiler_packs_retrieved_table_row_instead_of_whole_table(
    compiler_fixture,
) -> None:
    _source, ir, scope, counter = compiler_fixture
    config = compiler_config(
        retrieval=RetrievalConfig(candidate_limit=10, rerank_limit=1),
        table_row_retrieval_enabled=True,
    )
    index = HybridIndex(
        node_chunks([ir], tokenizer=counter, table_rows=True),
        config=config.retrieval,
        tokenizer=counter,
    )

    packet = compile_context(
        "north revenue 42",
        scope,
        40,
        config,
        tokenizer=counter,
        hybrid_index=index,
    )

    assert "Region: North | Revenue: 42" in packet.items[0].content
    assert "Region | Revenue\nNorth | 42" not in packet.items[0].content


def test_prebuilt_index_must_share_compiler_retrieval_config(
    compiler_fixture,
) -> None:
    _source, ir, scope, counter = compiler_fixture
    config = compiler_config()
    different = RetrievalConfig(candidate_limit=2, rerank_limit=1)
    index = HybridIndex(
        node_chunks([ir], tokenizer=counter),
        config=different,
        tokenizer=counter,
    )

    with pytest.raises(ValueError, match="configuration differs"):
        compile_context(
            "target revenue increased",
            scope,
            40,
            config,
            tokenizer=counter,
            hybrid_index=index,
        )


def test_heading_ancestry_is_metadata_and_rendered_context(compiler_fixture) -> None:
    _source, _ir, scope, counter = compiler_fixture

    packet = compile_context(
        "target revenue increased",
        scope,
        30,
        compiler_config(retrieval=RetrievalConfig(candidate_limit=10, rerank_limit=1)),
        tokenizer=counter,
    )

    item = packet.items[0]
    assert item.heading_path == ("Annual Report", "Results")
    assert item.content == ("Annual Report\n> Results\n\nTarget revenue increased.")


def test_configurable_paragraph_siblings_receive_score_penalty(
    compiler_fixture,
) -> None:
    _source, _ir, scope, counter = compiler_fixture
    config = compiler_config(
        retrieval=RetrievalConfig(
            candidate_limit=10,
            rerank_limit=1,
            max_candidate_limit=10,
            max_rerank_limit=1,
        ),
        include_previous_sibling=True,
        include_next_sibling=True,
        sibling_neighbor_limit=1,
        sibling_score_penalty=0.5,
    )

    packet = compile_context(
        "target revenue increased",
        scope,
        50,
        config,
        tokenizer=counter,
    )

    assert len(packet.items) == 3
    assert "Context before target." in packet.items[1].content
    assert "Context after target." in packet.items[2].content
    assert packet.items[1].scores.fused < packet.items[0].scores.fused
    assert packet.items[2].scores.fused < packet.items[0].scores.fused


def test_paragraph_neighbor_penalty_increases_with_distance(
    compiler_fixture,
) -> None:
    _source, _ir, scope, counter = compiler_fixture
    config = compiler_config(
        retrieval=RetrievalConfig(
            candidate_limit=10,
            rerank_limit=1,
            max_candidate_limit=10,
            max_rerank_limit=1,
        ),
        include_previous_sibling=True,
        include_next_sibling=False,
        sibling_neighbor_limit=2,
        sibling_score_penalty=0.5,
    )

    packet = compile_context(
        "context after target",
        scope,
        50,
        config,
        tokenizer=counter,
    )

    target = next(
        item for item in packet.items if "Context after target" in item.content
    )
    immediate = next(
        item for item in packet.items if "Target revenue increased" in item.content
    )
    distant = next(
        item for item in packet.items if "Context before target" in item.content
    )
    assert immediate.scores.reranked == pytest.approx(target.scores.reranked * 0.5)
    assert distant.scores.reranked == pytest.approx(target.scores.reranked * 0.25)


@pytest.mark.parametrize(
    ("score", "expected"),
    ((2.0, 1.0), (-2.0, -4.0), (0.0, -0.5)),
)
def test_penalty_always_lowers_signed_reranker_score(
    score: float,
    expected: float,
) -> None:
    penalized = _penalize(RetrievalScores(fused=1.0, reranked=score), 0.5)

    assert penalized.fused == 0.5
    assert penalized.reranked == expected
    assert penalized.reranked < score


def test_adjacent_list_items_stay_together(compiler_fixture) -> None:
    _source, _ir, scope, counter = compiler_fixture
    config = compiler_config(
        retrieval=RetrievalConfig(candidate_limit=10, rerank_limit=1),
        list_neighbor_limit=1,
    )

    packet = compile_context(
        "beta market declined",
        scope,
        50,
        config,
        tokenizer=counter,
    )

    contents = [item.content for item in packet.items]
    assert any("Alpha market grew." in content for content in contents)
    assert any("Beta market declined." in content for content in contents)
    assert any("Gamma market held." in content for content in contents)


def test_page_neighbor_expansion_adds_bounded_multiscale_context(
    compiler_fixture,
) -> None:
    _source, _ir, scope, counter = compiler_fixture
    config = compiler_config(
        retrieval=RetrievalConfig(
            fixed_chunk_tokens=12,
            fixed_overlap_tokens=3,
            candidate_limit=10,
            rerank_limit=1,
            max_candidate_limit=10,
            max_rerank_limit=1,
        ),
        page_neighbor_radius=1,
        page_neighbor_min_budget=50,
        page_neighbor_origin_limit=1,
        page_neighbor_candidate_limit=10,
    )

    small = compile_context(
        "target revenue increased",
        scope,
        49,
        config,
        tokenizer=counter,
    )
    expanded = compile_context(
        "target revenue increased",
        scope,
        100,
        config,
        tokenizer=counter,
    )

    assert all(item.page_start != 2 for item in small.items)
    assert "Target revenue increased" in expanded.items[0].content
    assert any(item.page_end == 2 for item in expanded.items)
    assert any("Measurements were audited" in item.content for item in expanded.items)
    assert expanded.token_count <= expanded.token_budget


def test_query_cache_reuses_page_neighbor_ranking_across_budgets(
    compiler_fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source, ir, scope, counter = compiler_fixture
    config = compiler_config(
        retrieval=RetrievalConfig(
            fixed_chunk_tokens=12,
            fixed_overlap_tokens=3,
            candidate_limit=10,
            rerank_limit=1,
            max_candidate_limit=10,
            max_rerank_limit=1,
        ),
        page_neighbor_radius=1,
        page_neighbor_min_budget=50,
        page_neighbor_origin_limit=1,
        page_neighbor_candidate_limit=10,
    )
    index = HybridIndex(
        node_chunks([ir], tokenizer=counter),
        config=config.retrieval,
        tokenizer=counter,
    )
    ranked = index.retrieve("target revenue increased", token_budget=120)
    calls = 0
    original = compiler_expand._page_neighbor_candidates

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(compiler_expand, "_page_neighbor_candidates", counted)
    cache = CompilerQueryCache()
    compile_context(
        "target revenue increased",
        scope,
        100,
        config,
        tokenizer=counter,
        hybrid_index=index,
        ranked_evidence=ranked,
        query_cache=cache,
    )
    cached = compile_context(
        "target revenue increased",
        scope,
        120,
        config,
        tokenizer=counter,
        hybrid_index=index,
        ranked_evidence=ranked,
        query_cache=cache,
    )
    uncached = compile_context(
        "target revenue increased",
        scope,
        120,
        config,
        tokenizer=counter,
        hybrid_index=index,
        ranked_evidence=ranked,
    )

    assert calls == 2
    assert cached == uncached
    assert cache.page_neighbors_used
    assert cache.page_neighbor_cache_hit
    assert cache.page_neighbor_prepare_ms >= 0


def test_query_cache_rejects_page_ranking_for_another_query(
    compiler_fixture,
) -> None:
    _source, ir, scope, counter = compiler_fixture
    config = compiler_config(
        retrieval=RetrievalConfig(
            fixed_chunk_tokens=12,
            fixed_overlap_tokens=3,
            candidate_limit=10,
            rerank_limit=1,
            max_candidate_limit=10,
            max_rerank_limit=1,
        ),
        page_neighbor_radius=1,
        page_neighbor_min_budget=50,
        page_neighbor_origin_limit=1,
    )
    index = HybridIndex(
        node_chunks([ir], tokenizer=counter),
        config=config.retrieval,
        tokenizer=counter,
    )
    ranked = index.retrieve("target revenue increased", token_budget=120)
    cache = CompilerQueryCache()
    compile_context(
        "target revenue increased",
        scope,
        120,
        config,
        tokenizer=counter,
        hybrid_index=index,
        ranked_evidence=ranked,
        query_cache=cache,
    )

    with pytest.raises(ValueError, match="another query"):
        compile_context(
            "different question",
            scope,
            120,
            config,
            tokenizer=counter,
            hybrid_index=index,
            ranked_evidence=ranked,
            query_cache=cache,
        )


def test_duplicate_source_text_is_emitted_once(compiler_fixture) -> None:
    _source, _ir, scope, counter = compiler_fixture

    packet = compile_context(
        "repeated duplicate phrase",
        scope,
        100,
        compiler_config(),
        tokenizer=counter,
    )

    matching = [
        item for item in packet.items if "Repeated duplicate phrase." in item.content
    ]
    assert len(matching) == 1


def test_table_is_preserved_with_caption_headers_and_rows(compiler_fixture) -> None:
    _source, ir, scope, counter = compiler_fixture
    config = compiler_config(
        retrieval=RetrievalConfig(candidate_limit=10, rerank_limit=1)
    )

    packet = compile_context("north revenue 42", scope, 40, config, tokenizer=counter)

    item = packet.items[0]
    table_node = next(node for node in ir.nodes if node.kind == IRNodeKind.TABLE)
    assert "Revenue table" in item.content
    assert "Region | Revenue" in item.content
    assert "North | 42" in item.content
    assert item.source_node_ids == (table_node.id,)
    assert item.source_item_ids == table_node.source_item_ids


def test_oversized_table_uses_reranked_docling_chunks(tmp_path: Path) -> None:
    source = oversized_table_source()
    counter = FixtureTokenCounter()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=counter)
    scope = DocumentScope.from_documents(
        [ir],
        source_documents={ir.id: source},
    )
    config = compiler_config(
        retrieval=RetrievalConfig(candidate_limit=5, rerank_limit=1),
        include_heading_context=False,
        table_chunk_tokens=12,
    )

    packet = compile_context(
        "District9 109",
        scope,
        17,
        config,
        tokenizer=counter,
    )

    assert packet.items
    assert packet.token_count <= 17
    assert "District" in packet.items[0].content
    assert "Revenue" in packet.items[0].content
    assert "District9" in packet.items[0].content
    assert "109" in packet.items[0].content


@pytest.mark.parametrize("budget", range(0, 21))
def test_compiler_never_exceeds_token_boundary(compiler_fixture, budget: int) -> None:
    _source, _ir, scope, counter = compiler_fixture

    packet = compile_context(
        "revenue results market",
        scope,
        budget,
        compiler_config(),
        tokenizer=counter,
    )

    assert packet.token_count <= budget
    assert packet.token_count == sum(item.token_count for item in packet.items)


def test_every_item_resolves_to_exact_ir_provenance(compiler_fixture) -> None:
    _source, ir, scope, counter = compiler_fixture

    packet = compile_context(
        "revenue results market methods",
        scope,
        200,
        compiler_config(),
        tokenizer=counter,
    )

    assert packet.items
    for item in packet.items:
        assert item.document_id == ir.id
        assert item.page_start is not None
        assert item.page_end is not None
        assert item.source_node_ids
        assert item.source_item_ids
        for node_id in item.source_node_ids:
            node = ir.node_by_id[node_id]
            assert set(node.source_item_ids).intersection(item.source_item_ids)


def test_repeated_compilation_is_identical(compiler_fixture) -> None:
    _source, _ir, scope, counter = compiler_fixture
    config = compiler_config(include_next_sibling=True)

    first = compile_context(
        "target revenue",
        scope,
        80,
        config,
        tokenizer=counter,
    )
    second = compile_context(
        "target revenue",
        scope,
        80,
        config,
        tokenizer=counter,
    )

    assert first == second
