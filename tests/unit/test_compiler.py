"""Acceptance tests for deterministic context compiler v0."""

import hashlib
from pathlib import Path

import pytest
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.base import Size
from docling_core.types.doc.document import TableCell, TableData
from docling_core.types.doc.labels import DocItemLabel
from test_ir import (
    PAGE_HEADER,
    FixtureTokenCounter,
    hidden_layer_source,
    ingest_metadata,
    provenance,
)

import contextbench.compiler.expand as compiler_expand
from contextbench.compiler import (
    CompilerConfig,
    CompilerCorpusIndex,
    CompilerQueryCache,
    DocumentScope,
    compile_context,
    compile_context_with_trace,
)
from contextbench.compiler.candidates import node_chunks
from contextbench.compiler.expand import _penalize, expand_candidates
from contextbench.compiler.facets import query_facets
from contextbench.compiler.joins import (
    _key_columns,
    _row_keys,
    keyed_table_join_candidates,
)
from contextbench.compiler.models import (
    FALLBACK_CONTEXT_TIER,
    PRIMARY_EVIDENCE_TIER,
    CompilerCandidate,
)
from contextbench.compiler.pack import _backfill_order, pack_candidates
from contextbench.ir import project_document
from contextbench.ir.models import IRNodeKind
from contextbench.retrieval import (
    RetrievalArm,
    RetrievalChunk,
    RetrievalConfig,
    RetrievalScores,
)
from contextbench.retrieval.chunking import structural_chunks
from contextbench.retrieval.index import HybridIndex
from contextbench.retrieval.rerank import LexicalOverlapReranker


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


FACETED_QUERY = (
    "Which district reported the highest revenue, "
    "and how were the measurements audited?"
)
AUDIT_PARAGRAPH = "Measurements were audited across every district revenue return."


def faceted_oversized_table_source() -> DoclingDocument:
    """An oversized table beside prose that answers the query's other clause."""
    document = DoclingDocument(name="faceted-oversized-table")
    document.add_page(1, Size(width=612, height=792))
    heading = document.add_heading(
        "Results",
        level=1,
        prov=provenance(1, "Results", 750),
    )
    document.add_text(
        label=DocItemLabel.TEXT,
        text=AUDIT_PARAGRAPH,
        parent=heading,
        prov=provenance(1, AUDIT_PARAGRAPH, 730),
    )
    caption = document.add_text(
        label=DocItemLabel.CAPTION,
        text="District revenue",
        parent=heading,
        prov=provenance(1, "District revenue", 710),
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
        prov=provenance(1, "district table", 680),
    )
    return document


def joined_table_source() -> DoclingDocument:
    document = DoclingDocument(name="joined-tables")
    document.add_page(1, Size(width=612, height=792))
    document.add_page(2, Size(width=612, height=792))
    first_caption = document.add_text(
        label=DocItemLabel.CAPTION,
        text="Table A.1 | Model references",
        prov=provenance(1, "Table A.1", 740),
    )
    first_values = (
        ("Model", "Main References"),
        ("ALPHA-1", "Alpha et al."),
        ("BETA-2", ""),
    )
    first_cells = [
        TableCell(
            start_row_offset_idx=row,
            end_row_offset_idx=row + 1,
            start_col_offset_idx=column,
            end_col_offset_idx=column + 1,
            text=text,
            column_header=row == 0,
        )
        for row, values in enumerate(first_values)
        for column, text in enumerate(values)
    ]
    document.add_table(
        data=TableData(table_cells=first_cells, num_rows=3, num_cols=2),
        caption=first_caption,
        prov=provenance(1, "model references", 700),
    )
    second_caption = document.add_text(
        label=DocItemLabel.CAPTION,
        text="Table A.2 | Model datasets",
        prov=provenance(2, "Table A.2", 740),
    )
    second_values = (
        ("Institute: Model", "Dataset citation and DOI"),
        ("ORG:ALPHA-1", "Alpha dataset DOI"),
        ("ORG:BETA-2", "Beta dataset DOI"),
        ("ORG:BETA-2", "Beta scenario DOI"),
    )
    second_cells = [
        TableCell(
            start_row_offset_idx=row,
            end_row_offset_idx=row + 1,
            start_col_offset_idx=column,
            end_col_offset_idx=column + 1,
            text=text,
            column_header=row == 0,
        )
        for row, values in enumerate(second_values)
        for column, text in enumerate(values)
    ]
    document.add_table(
        data=TableData(table_cells=second_cells, num_rows=4, num_cols=2),
        caption=second_caption,
        prov=provenance(2, "model datasets", 700),
    )
    return document


PROSE_BESIDE_JOINED_TABLES = "Retention improved after the migration."


def joined_tables_and_prose_source() -> DoclingDocument:
    """Two joinable tables plus prose the same query also needs."""
    document = DoclingDocument(name="joined-tables-and-prose")
    document.add_page(1, Size(width=612, height=792))
    document.add_page(2, Size(width=612, height=792))
    heading = document.add_heading(
        "Findings",
        level=1,
        prov=provenance(1, "Findings", 760),
    )
    document.add_text(
        label=DocItemLabel.TEXT,
        text=PROSE_BESIDE_JOINED_TABLES,
        parent=heading,
        prov=provenance(1, PROSE_BESIDE_JOINED_TABLES, 735),
    )
    for page, caption_text, headers, rows in (
        (
            1,
            "Table C.1 | Model cohorts",
            ("Model", "Cohort"),
            (("ALPHA-1", "North"), ("BETA-2", "South"), ("GAMMA-3", "East")),
        ),
        (
            2,
            "Table C.2 | Model retention",
            ("Model", "Retention"),
            (
                ("ALPHA-1", "71 percent"),
                ("BETA-2", "64 percent"),
                ("GAMMA-3", "58 percent"),
            ),
        ),
    ):
        caption = document.add_text(
            label=DocItemLabel.CAPTION,
            text=caption_text,
            prov=provenance(page, caption_text, 700),
        )
        values = (headers, *rows)
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
                num_cols=len(headers),
            ),
            caption=caption,
            prov=provenance(page, caption_text, 680),
        )
    return document


def test_exact_table_keys_support_codes_dates_and_dataset_names() -> None:
    headers = ("Product code", "Effective date", "Dataset name", "Description")
    columns = _key_columns(headers)

    assert columns == (0, 1, 2)
    assert _row_keys(
        ("SKU-2048", "2026/09/20", "Climate Atlas", "ignored"),
        columns,
        headers,
    ) == (
        "identifier:sku-2048",
        "date:2026-09-20",
        "dataset:climate atlas",
    )


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


def test_precomputed_compiler_corpus_index_preserves_output(
    compiler_fixture,
) -> None:
    _source, ir, scope, counter = compiler_fixture
    config = compiler_config()
    index = CompilerCorpusIndex.build(
        [ir],
        retrieval_config=config.retrieval,
        tokenizer=counter,
    )

    direct = compile_context(
        "target revenue increased",
        scope,
        100,
        config,
        tokenizer=counter,
    )
    precomputed = compile_context(
        "target revenue increased",
        scope,
        100,
        config,
        tokenizer=counter,
        corpus_index=index,
    )

    assert precomputed == direct


def test_heading_context_can_be_compacted_to_trailing_levels(
    compiler_fixture,
) -> None:
    _source, _ir, scope, counter = compiler_fixture
    packet = compile_context(
        "target revenue increased",
        scope,
        40,
        compiler_config(heading_context_depth=1),
        tokenizer=counter,
    )

    target = next(
        item for item in packet.items if "Target revenue increased." in item.content
    )
    assert target.content.startswith("Results\n\n")
    assert "Annual Report" not in target.content


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


def test_node_candidate_ids_are_identical_across_heading_context(
    compiler_fixture,
) -> None:
    """The heading-context factor must not permute IR candidate ids.

    ``chunk.id`` is a deterministic tie-break sort key in ``retrieval/index``
    and in the coverage objective in ``compiler/pack``. While the node id
    payload embedded the *indexed* string, toggling
    ``compiler_node_heading_search_context`` permuted every IR id and moved IR
    results by a mechanism the structural unit does not have -- ``_chunk_from_nodes``
    omits ``search_text`` from its payload -- so an IR heading-on/off delta
    silently carried an arm-asymmetric id-permutation effect.

    Deriving the id from node text alone removes it. Cache isolation does not
    depend on it: each position gets its own ``RetrievalConfig`` and therefore
    its own derived-index key. What the factor must still change, and does, is
    ``search_text``.
    """
    source, ir, _scope, counter = compiler_fixture
    on_config = RetrievalConfig(compiler_node_heading_search_context=True)
    off_config = RetrievalConfig(compiler_node_heading_search_context=False)

    on = node_chunks([ir], tokenizer=counter, config=on_config)
    off = node_chunks([ir], tokenizer=counter, config=off_config)

    assert [chunk.id for chunk in on] == [chunk.id for chunk in off]
    # Everything a budget or a provenance check reads is identical too.
    assert [
        (chunk.text, chunk.token_count, chunk.source_node_ids, chunk.source_item_ids)
        for chunk in on
    ] == [
        (chunk.text, chunk.token_count, chunk.source_node_ids, chunk.source_item_ids)
        for chunk in off
    ]

    # The factor is not inert: what is indexed still differs.
    assert all(chunk.search_text is None for chunk in off)
    heading_bearing = [chunk for chunk in on if chunk.heading_path]
    assert heading_bearing
    assert any(chunk.search_text != chunk.text for chunk in heading_bearing)

    # The same property on the structural unit, which is what IR now matches.
    structural = {
        heading_context: structural_chunks(
            ir,
            source,
            config=RetrievalConfig(
                structural_heading_search_context=heading_context
            ),
            tokenizer=counter,
        )
        for heading_context in (True, False)
    }
    assert [chunk.id for chunk in structural[True]] == [
        chunk.id for chunk in structural[False]
    ]


def test_heading_search_context_fields_are_independent_per_content_unit(
    compiler_fixture,
) -> None:
    """Each unit must read only its own field, in both directions.

    The two units shared one ``heading_search_context`` until the development
    factorial measured the factor to be asymmetric -- heading context costs the
    IR-node unit page recall at every budget while helping structural chunks at
    2K and 4K -- which made the useful configuration, structural on and IR
    nodes off, unreachable. It is reachable only if turning one field off is
    genuinely inert on the other unit, so both directions are asserted against
    the all-on baseline rather than only against each other.
    """
    source, ir, _scope, counter = compiler_fixture

    def indexed(config: RetrievalConfig) -> tuple[list, list]:
        return (
            [chunk.search_text for chunk in structural_chunks(
                ir, source, config=config, tokenizer=counter
            )],
            [chunk.search_text for chunk in node_chunks(
                [ir], tokenizer=counter, config=config
            )],
        )

    both_on = RetrievalConfig()
    structural_on, nodes_on = indexed(both_on)
    # The baseline has to be heading-bearing on both units or the assertions
    # below would hold vacuously.
    assert any(text is not None for text in structural_on)
    assert any(text is not None for text in nodes_on)

    # Compiler field off: IR nodes stop indexing headings, structural chunks
    # are untouched.
    structural_text, node_text = indexed(
        both_on.model_copy(update={"compiler_node_heading_search_context": False})
    )
    assert structural_text == structural_on
    assert node_text == [None] * len(nodes_on)

    # And the reverse.
    structural_text, node_text = indexed(
        both_on.model_copy(update={"structural_heading_search_context": False})
    )
    assert structural_text == [None] * len(structural_on)
    assert node_text == nodes_on


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


def test_page_neighbor_candidates_are_bounded_before_reranking(
    compiler_fixture,
) -> None:
    _source, ir, scope, counter = compiler_fixture

    class CountingReranker(LexicalOverlapReranker):
        def __init__(self) -> None:
            self.batch_sizes = []

        def score(self, query, chunks):
            self.batch_sizes.append(len(chunks))
            return super().score(query, chunks)

    reranker = CountingReranker()
    config = compiler_config(
        retrieval=RetrievalConfig(
            fixed_chunk_tokens=4,
            fixed_overlap_tokens=1,
            candidate_limit=10,
            rerank_limit=1,
            max_candidate_limit=10,
            max_rerank_limit=1,
        ),
        page_neighbor_radius=1,
        page_neighbor_min_budget=50,
        page_neighbor_origin_limit=1,
        page_neighbor_prerank_limit=2,
        page_neighbor_candidate_limit=2,
    )
    index = HybridIndex(
        node_chunks([ir], tokenizer=counter),
        config=config.retrieval,
        tokenizer=counter,
        reranker=reranker,
    )
    ranked = index.retrieve("target revenue increased", token_budget=100)
    reranker.batch_sizes.clear()

    compile_context(
        "target revenue increased",
        scope,
        100,
        config,
        tokenizer=counter,
        hybrid_index=index,
        ranked_evidence=ranked,
    )

    assert reranker.batch_sizes == [2]


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


def _faceted_oversized_table_scope(tmp_path: Path):
    source = faceted_oversized_table_source()
    counter = FixtureTokenCounter()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=counter)
    scope = DocumentScope.from_documents([ir], source_documents={ir.id: source})
    return scope, counter


def test_faceted_core_scores_share_the_reranker_scale_with_fragments(
    tmp_path: Path,
) -> None:
    """Faceted core evidence must be ordered by the same quantity as fragments.

    Under the shipped defaults the facet stage fused candidates with RRF and
    wrote that sum into ``reranked`` as well as ``fused``, discarding the
    cross-encoder score it had just computed. Table fragments kept a raw
    reranker score, so an RRF value near 0.03 was compared against a reranker
    score, and every fragment sorted above every direct hit regardless of
    relevance.
    """
    scope, counter = _faceted_oversized_table_scope(tmp_path)
    config = compiler_config()
    reranker = LexicalOverlapReranker()
    budget = 18

    # Premise: the defect only exists under these two defaults together.
    assert config.query_faceting_enabled
    assert config.query_facet_rerank_strategy == "batched"
    assert query_facets(
        FACETED_QUERY,
        limit=config.query_facet_limit,
        min_terms=config.query_facet_min_terms,
    )

    _packet, trace = compile_context_with_trace(
        FACETED_QUERY,
        scope,
        budget,
        config,
        tokenizer=counter,
        reranker=reranker,
    )

    # ``reranked`` now holds the score the reranker actually produced for this
    # candidate against this query, and ``fused`` still holds the RRF sum.
    #
    # The equality below is NOT the general contract. It holds because this
    # candidate is in ranking 0, the full-query ranking, and
    # ``retrieve_faceted`` keeps the first ranking that produced a candidate.
    # A candidate reached only through a facet keeps that facet's score, and
    # comparing it to a full-query score would fail here by design. See
    # ``docs/specs/retrieval.md``, "What ``reranked`` holds, per class".
    evidence = next(
        candidate
        for candidate in trace.ranked_evidence
        if AUDIT_PARAGRAPH in candidate.chunk.retrieval_text
    )
    assert evidence.scores.reranked == pytest.approx(
        reranker.score(FACETED_QUERY, [evidence.chunk])[0]
    )
    assert evidence.scores.fused > 0
    assert evidence.scores.reranked != pytest.approx(evidence.scores.fused)

    fragments = [
        candidate
        for candidate in trace.expanded_candidates
        if candidate.operator == "table_fragment"
    ]
    core = [
        candidate
        for candidate in trace.expanded_candidates
        if candidate.operator == "retrieval"
    ]
    # Premise: the oversized table really did fragment.
    assert len(fragments) > 1
    paragraph = next(
        candidate for candidate in core if AUDIT_PARAGRAPH in candidate.chunk.text
    )

    # The paragraph answers a whole facet; no fragment matches the query as
    # well. On one scale that has to show up in the score and in the order.
    assert paragraph.scores.reranked > max(
        fragment.scores.reranked for fragment in fragments
    )
    positions = {
        candidate.chunk.id: index
        for index, candidate in enumerate(trace.expanded_candidates)
    }
    assert positions[paragraph.chunk.id] < min(
        positions[fragment.chunk.id] for fragment in fragments
    )


@pytest.mark.parametrize("strategy", ("coverage", "ranked"))
def test_table_fragments_stop_displacing_faceted_core_evidence(
    tmp_path: Path,
    strategy: str,
) -> None:
    """The scale mismatch cost core evidence its place in the packet."""
    scope, counter = _faceted_oversized_table_scope(tmp_path)
    config = compiler_config(packing_strategy=strategy)
    budget = 18

    packet, trace = compile_context_with_trace(
        FACETED_QUERY,
        scope,
        budget,
        config,
        tokenizer=counter,
        reranker=LexicalOverlapReranker(),
    )

    operator_by_content = {
        candidate.chunk.text: candidate.operator
        for candidate in trace.deduplicated_candidates
    }
    assert len(operator_by_content) == len(trace.deduplicated_candidates)
    operators = [operator_by_content[item.content] for item in packet.items]
    contents = [item.content for item in packet.items]

    assert packet.token_count <= budget
    assert operators
    # Direct hits lead, and the table's own caption node survives: when every
    # fragment sorted first it was dropped as a substring of one of them.
    assert operators[0] == "retrieval"
    assert AUDIT_PARAGRAPH in contents[0]
    assert any(content == "Results\n\nDistrict revenue" for content in contents)


def test_reranker_ties_fall_back_to_structure_not_to_fused_scores(
    tmp_path: Path,
) -> None:
    """``fused`` is class-local provenance and cannot order across classes.

    A keyed join's ``fused`` is a lexical overlap ratio; a retrieved node's is
    an RRF sum roughly a decimal order of magnitude smaller. Using it to break
    a reranker tie ranked joins first on units alone.

    The tie here is not manufactured by a stub: the real reranker gives the
    strongest direct hit and all three joins the same score, while the rest of
    the pool takes two other scores. Exact ties are ordinary -- every fragment
    of an oversized table scoring 0.0 against a heading query is another case,
    pinned by ``test_table_fragments_pin_structural_heading_search_context_off``.
    """
    source = joined_tables_and_prose_source()
    counter = FixtureTokenCounter()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=counter)
    scope = DocumentScope.from_documents([ir], source_documents={ir.id: source})

    _packet, trace = compile_context_with_trace(
        JOINED_TABLES_AND_PROSE_QUERY,
        scope,
        50,
        compiler_config(),
        tokenizer=counter,
        reranker=LexicalOverlapReranker(),
    )
    candidates = trace.expanded_candidates

    # Premise: a normally scored pool -- several distinct reranker scores --
    # in which exactly one score is shared, and shared across two classes
    # whose ``fused`` values are on different scales.
    scores = [candidate.scores.reranked for candidate in candidates]
    assert len(set(scores)) > 2
    tied_score = max(scores)
    tied = [
        candidate
        for candidate in candidates
        if candidate.scores.reranked == tied_score
    ]
    assert len(tied) > 1
    assert {candidate.operator for candidate in tied} == {"retrieval", "keyed_join"}
    core_tied = next(
        candidate for candidate in tied if candidate.operator == "retrieval"
    )
    join_tied = next(
        candidate for candidate in tied if candidate.operator == "keyed_join"
    )
    # Roughly 0.42 against roughly 0.05: this is the comparison that used to
    # decide the tie, and it decided it on units.
    assert join_tied.scores.fused > core_tied.scores.fused

    # The tie is broken by structure instead, so the direct hit keeps its place.
    keys = [
        (candidate.origin_rank, candidate.expansion_order, candidate.chunk.id)
        for candidate in tied
    ]
    assert keys == sorted(keys)
    assert candidates.index(core_tied) < candidates.index(join_tied)
    assert candidates[0].operator == "retrieval"


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


def test_table_fragments_pin_structural_heading_search_context_off(
    tmp_path: Path,
) -> None:
    """The pin at the table-fragment call site is load-bearing; keep it.

    ``expand_candidates`` builds table fragments with ``structural_chunks``,
    and pins ``structural_heading_search_context`` off there so that giving the
    structural arm heading context does not move the compiler. Delete the pin
    and this test fails on both assertions below.

    The pin is about table *fragments* and is independent of the compiler's
    node candidates, which read their own
    ``compiler_node_heading_search_context``. This call site stays pinned
    either way.

    Two distinct effects, both measured on this fixture with the query
    ``"Results"`` -- the heading the table sits under:

    1. The reranker scores the raw structural chunks *before* they are
       rendered, and it reads ``retrieval_text``. Without the pin the heading
       trail is in that string, so every fragment scores 1.0 instead of 0.0 and
       the fragment ordering inside the table changes for any query phrased in
       heading vocabulary.
    2. Worse, the rendered string replaces ``text`` through ``model_copy``,
       which carries ``search_text`` across unchanged. Without the pin the
       expanded candidate therefore keeps a **stale** ``search_text`` -- the
       heading trail above the *un-rendered* fragment body -- and since
       ``retrieval_text`` is ``search_text or text``, that stale string shadows
       the rendered text for everything downstream that reads it, including the
       coverage and table-reference terms in ``compiler/pack.py``. The rendered
       header row is in ``text`` and absent from the stale ``search_text``.

    The pin is not a no-op and is not cosmetic: it is what keeps a change
    scoped to Arm B out of the compiler arm.
    """
    source = oversized_table_source()
    counter = FixtureTokenCounter()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=counter)
    config = compiler_config(
        retrieval=RetrievalConfig(candidate_limit=5, rerank_limit=5),
        include_heading_context=False,
        table_chunk_tokens=12,
    )
    index = HybridIndex(
        node_chunks([ir], tokenizer=counter),
        config=config.retrieval,
        tokenizer=counter,
    )
    query = "Results"

    candidates = expand_candidates(
        query,
        index.retrieve(query),
        [ir],
        source_documents={ir.id: source},
        token_budget=17,
        config=config,
        tokenizer=counter,
        reranker=LexicalOverlapReranker(),
    )

    fragments = [
        candidate
        for candidate in candidates
        if candidate.operator == "table_fragment"
    ]
    assert len(fragments) > 1
    # No stale search_text: what the compiler reads downstream is the rendered
    # string and nothing else.
    assert all(fragment.chunk.search_text is None for fragment in fragments)
    assert all(
        fragment.chunk.retrieval_text == fragment.chunk.text
        for fragment in fragments
    )
    assert all("District | Revenue" in fragment.chunk.text for fragment in fragments)
    # The fragments carry no heading vocabulary, so the heading query scores
    # zero against every one of them. Without the pin these are all 1.0.
    assert [fragment.scores.reranked for fragment in fragments] == [0.0] * len(
        fragments
    )


def test_keyed_table_join_selects_constraint_row_and_preserves_provenance(
    tmp_path: Path,
) -> None:
    source = joined_table_source()
    counter = FixtureTokenCounter()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=counter)
    query = (
        "Which dataset in Table A.2 has a blank MainReferences entry "
        "in Table A.1?"
    )

    candidates = keyed_table_join_candidates(
        query,
        [ir],
        tokenizer=counter,
        reranker=LexicalOverlapReranker(),
        candidate_limit=4,
        empty_marker="[blank]",
    )

    assert candidates
    assert len(candidates) == 1
    best = candidates[0]
    assert "Joined table key: beta-2" in best.chunk.text
    assert "Table A.2" in best.chunk.text
    assert "Dataset citation and DOI: Beta" in best.chunk.text
    assert "Table A.1" in best.chunk.text
    assert "Main References: [blank]" in best.chunk.text
    table_nodes = tuple(node for node in ir.nodes if node.kind == IRNodeKind.TABLE)
    assert set(best.chunk.source_node_ids) == {node.id for node in table_nodes}
    assert set(best.chunk.source_item_ids) == {
        item_id for node in table_nodes for item_id in node.source_item_ids
    }
    assert best.chunk.page_start is None
    assert best.chunk.page_end is None


def test_keyed_table_join_is_prioritized_when_enabled(tmp_path: Path) -> None:
    source = joined_table_source()
    counter = FixtureTokenCounter()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=counter)
    scope = DocumentScope.from_documents(
        [ir],
        source_documents={ir.id: source},
    )
    query = (
        "Which dataset in Table A.2 has a blank MainReferences entry "
        "in Table A.1?"
    )

    packet = compile_context(
        query,
        scope,
        80,
        compiler_config(keyed_table_join_enabled=True),
        tokenizer=counter,
    )

    assert packet.items
    assert "Joined table key: beta-2" in packet.items[0].content
    assert "Main References: [blank]" in packet.items[0].content
    assert packet.token_count <= packet.token_budget
    assert "keyed_join" in packet.metadata["active_operators"]


JOINED_TABLES_AND_PROSE_QUERY = (
    "What retention did the migration reach in Table C.1 and Table C.2?"
)


def test_keyed_joins_do_not_gate_core_evidence_out_of_the_packet(
    tmp_path: Path,
) -> None:
    """Joins compete for budget; they must not make core evidence unselectable.

    ``_coverage_selection`` only ever looks at the lowest ``priority_tier``
    that still fits, so demoting core retrieval whenever a join fired kept
    direct hits out of the packet entirely while any join still fit. The
    budget here is chosen so the joins alone would consume it.
    """
    source = joined_tables_and_prose_source()
    counter = FixtureTokenCounter()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=counter)
    scope = DocumentScope.from_documents([ir], source_documents={ir.id: source})
    config = compiler_config()
    budget = 50

    packet, trace = compile_context_with_trace(
        JOINED_TABLES_AND_PROSE_QUERY,
        scope,
        budget,
        config,
        tokenizer=counter,
    )

    # Read the premise off the list packing actually sees: dedupe runs first,
    # and its result is truncated, so counting pre-dedupe candidates could
    # overstate how much budget the joins really consume.
    packed_pool = trace.deduplicated_candidates[: config.max_expanded_candidates]
    joins = [
        candidate for candidate in packed_pool if candidate.operator == "keyed_join"
    ]
    core = [
        candidate for candidate in packed_pool if candidate.operator != "keyed_join"
    ]
    # Guard the premise: without this the test would pass for the wrong reason.
    # Every join fits, and once they are all packed nothing else can be, so a
    # tier that ranks joins above core evidence leaves a packet of joins only.
    assert len(joins) > 1
    assert core
    join_tokens = sum(join.chunk.token_count for join in joins)
    assert join_tokens <= budget
    assert join_tokens + min(
        candidate.chunk.token_count for candidate in core
    ) > budget

    contents = [item.content for item in packet.items]
    assert packet.token_count <= budget
    # The joins keep their lead on merit: they cover both referenced tables.
    assert "Joined table key: alpha-1" in contents[0]
    assert "keyed_join" in packet.metadata["active_operators"]
    # ...but core retrieval evidence still reaches the packet.
    assert any(PROSE_BESIDE_JOINED_TABLES in content for content in contents)
    assert any("Model | Retention" in content for content in contents)


def test_priority_tier_does_not_depend_on_whether_joins_fired(
    tmp_path: Path,
) -> None:
    """A candidate's tier states its class, not what else the query produced."""
    source = joined_tables_and_prose_source()
    counter = FixtureTokenCounter()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=counter)
    scope = DocumentScope.from_documents([ir], source_documents={ir.id: source})

    tiers_by_chunk = {}
    for joins_enabled in (False, True):
        _packet, trace = compile_context_with_trace(
            JOINED_TABLES_AND_PROSE_QUERY,
            scope,
            50,
            compiler_config(keyed_table_join_enabled=joins_enabled),
            tokenizer=counter,
        )
        tiers_by_chunk[joins_enabled] = {
            candidate.chunk.id: candidate.priority_tier
            for candidate in trace.expanded_candidates
            if candidate.operator != "keyed_join"
        }
        if joins_enabled:
            assert any(
                candidate.operator == "keyed_join"
                for candidate in trace.expanded_candidates
            )
            assert all(
                candidate.priority_tier == PRIMARY_EVIDENCE_TIER
                for candidate in trace.expanded_candidates
                if candidate.operator == "keyed_join"
            )

    assert tiers_by_chunk[False]
    assert tiers_by_chunk[True] == tiers_by_chunk[False]
    assert set(tiers_by_chunk[True].values()) == {PRIMARY_EVIDENCE_TIER}
    assert PRIMARY_EVIDENCE_TIER < FALLBACK_CONTEXT_TIER


def test_page_neighbor_windows_rank_after_joins_and_core_evidence_at_16k(
    tmp_path: Path,
) -> None:
    """Fixed-window filler may spend leftover budget, never take precedence.

    This is the case the join tier bump broke: with core retrieval pushed to
    the page-neighbor tier, a window could be picked ahead of a direct hit.
    Joins, core retrieval, and page neighbors all have to materialise at once
    for the ordering between them to mean anything, so this runs at the real
    16K budget with the shipped gates rather than a lowered one.
    """
    source = joined_tables_and_prose_source()
    counter = FixtureTokenCounter()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=counter)
    scope = DocumentScope.from_documents([ir], source_documents={ir.id: source})
    config = compiler_config()
    budget = 16384

    # Pin the shipped gates this test depends on, so it cannot quietly drift
    # into testing a configuration the benchmark never runs.
    assert config.page_neighbor_min_budget == 16384
    assert config.page_neighbor_radius > 0
    assert config.keyed_table_join_enabled
    assert config.packing_strategy == "coverage"
    assert budget >= config.page_neighbor_min_budget

    packet, trace = compile_context_with_trace(
        JOINED_TABLES_AND_PROSE_QUERY,
        scope,
        budget,
        config,
        tokenizer=counter,
    )

    # Dedupe drops exact text duplicates, so text identifies a candidate.
    operator_by_content = {
        candidate.chunk.text: candidate.operator
        for candidate in trace.deduplicated_candidates
    }
    assert len(operator_by_content) == len(trace.deduplicated_candidates)
    operators = [operator_by_content[item.content] for item in packet.items]

    # Premise: all three classes really are competing in this packet.
    assert "keyed_join" in operators
    assert "retrieval" in operators
    assert "page_neighbor" in operators

    windows = [
        index
        for index, operator in enumerate(operators)
        if operator == "page_neighbor"
    ]
    primary = [
        index
        for index, operator in enumerate(operators)
        if operator != "page_neighbor"
    ]
    # Every window comes after every piece of primary evidence.
    assert min(windows) > max(primary)

    contents = [item.content for item in packet.items]
    assert any("Joined table key:" in content for content in contents)
    assert any(PROSE_BESIDE_JOINED_TABLES in content for content in contents)
    assert any("Model | Retention" in content for content in contents)
    assert packet.token_count <= budget


def test_page_neighbor_windows_carry_no_furniture(tmp_path: Path) -> None:
    """Page neighbours are fixed windows, so they inherit the window filter.

    Nothing in ``_page_neighbor_candidates`` filters content layers; it reranks
    whatever ``fixed_chunks`` produced. That is the whole of the guarantee, so
    the test runs end to end rather than against the chunker.
    """
    source = hidden_layer_source()
    counter = FixtureTokenCounter()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=counter)
    scope = DocumentScope.from_documents([ir], source_documents={ir.id: source})
    budget = 16384

    packet, trace = compile_context_with_trace(
        "page body sentence about revenue and costs",
        scope,
        budget,
        compiler_config(),
        tokenizer=counter,
        reranker=LexicalOverlapReranker(),
    )

    # Premise: page neighbours really were built for this query.
    assert "page_neighbor" in packet.metadata["active_operators"]
    windows = [
        candidate
        for candidate in trace.expanded_candidates
        if candidate.operator == "page_neighbor"
    ]
    assert windows

    assert all(PAGE_HEADER not in window.chunk.text for window in windows)
    assert all(PAGE_HEADER not in item.content for item in packet.items)
    assert packet.token_count <= budget


def test_simple_query_does_not_activate_specialized_operators(
    compiler_fixture,
) -> None:
    _source, _ir, scope, counter = compiler_fixture

    packet = compile_context(
        "revenue",
        scope,
        40,
        compiler_config(page_neighbor_radius=0),
        tokenizer=counter,
    )

    assert packet.metadata["active_operators"] == ""


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


def test_coverage_packing_prefers_uncovered_query_facets() -> None:
    counter = FixtureTokenCounter()

    def candidate(rank: int, text: str, page: int) -> CompilerCandidate:
        chunk = RetrievalChunk(
            id=f"chunk-{rank}",
            arm=RetrievalArm.COMPILER,
            document_id="document-1",
            text=text,
            token_count=counter.count(text),
            page_start=page,
            page_end=page,
            source_node_ids=(f"node-{rank}",),
            source_item_ids=(f"item-{rank}",),
        )
        return CompilerCandidate(
            chunk=chunk,
            scores=RetrievalScores(fused=1 / rank, reranked=1 / rank),
            origin_rank=rank,
            expansion_order=rank,
        )

    candidates = (
        candidate(1, "alpha measure details", 1),
        candidate(2, "alpha measure repeated", 1),
        candidate(3, "beta result details", 2),
    )
    metadata = {"arm": "compiler"}

    ranked = pack_candidates(
        "alpha measure and beta result",
        candidates,
        token_budget=6,
        tokenizer=counter,
        strategy="ranked",
        metadata=metadata,
    )
    coverage = pack_candidates(
        "alpha measure and beta result",
        candidates,
        token_budget=6,
        tokenizer=counter,
        strategy="coverage",
        metadata=metadata,
    )

    assert [item.page_start for item in ranked.items] == [1, 1]
    assert [item.page_start for item in coverage.items] == [1, 2]
    assert coverage.token_count == coverage.token_budget


ADAPTIVE_QUERY = "target revenue increased across alpha and beta markets"


def _adaptive_scope(tmp_path: Path):
    source = compiler_source()
    counter = FixtureTokenCounter()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=counter)
    return DocumentScope.from_documents([ir], source_documents={ir.id: source}), counter


def _packet_digest(packet) -> str:
    digest = hashlib.sha256()
    for item in packet.items:
        digest.update(item.evidence_id.encode())
        digest.update(b"\0")
    digest.update(str(packet.token_count).encode())
    return digest.hexdigest()


def _pool(query: str, scope, counter, budget: int, **config_updates):
    _packet, trace = compile_context_with_trace(
        query,
        scope,
        budget,
        compiler_config(**config_updates),
        tokenizer=counter,
    )
    return trace.deduplicated_candidates


@pytest.mark.parametrize(
    ("budget", "strategy", "expected"),
    [
        (20, "coverage",
         "9c32d6ae95c8203d43f4ed54d79541c5694502afe7a5772eeccdc8e584daed02"),
        (20, "ranked",
         "7d4b18cd6a728824d15d1c3f553e8033a7f33ac6bf7bfbebd4f2908d40596d8d"),
        (40, "coverage",
         "5c2468131aee91db28fe42822c70d115fbaa27d1949707e70e66cb5a5a6e0410"),
        (40, "ranked",
         "74963aecde08b02346fe5a7308ce8b929f411158b62b6cee3fd94ab33f14d013"),
        (60, "coverage",
         "953c61c5bc0dd4e67809766e675d689c2e04030e439d5dbe5c2823660aafd76d"),
        (60, "ranked",
         "54a8fba28e6ac1fb856abdc33320c78e6fbb1e0a0407d9c10ea124ec2d079dbd"),
    ],
)
def test_existing_packing_strategies_are_unchanged_by_adaptive(
    tmp_path: Path, budget: int, strategy: str, expected: str
) -> None:
    """Control. ``coverage`` and ``ranked`` are ablations and must not move.

    These six digests were produced by a verbatim copy of the pre-``adaptive``
    ``pack_candidates`` and ``_coverage_selection`` at ``9db9c5d``, run on this
    fixture, and they match what the shipped code returns. Adding a third
    strategy refactored ``_coverage_selection`` to return its leftovers as well
    as its selection, and this pins that the refactor changed nothing a
    control arm can see. If one of these moves, the ablation has stopped being
    a control and any comparison drawn against it is void.
    """
    scope, counter = _adaptive_scope(tmp_path)
    pool = _pool(ADAPTIVE_QUERY, scope, counter, budget)

    packet = pack_candidates(
        ADAPTIVE_QUERY,
        pool,
        token_budget=budget,
        tokenizer=counter,
        strategy=strategy,
        metadata={"arm": "compiler", "active_operators": ""},
    )

    assert _packet_digest(packet) == expected


@pytest.mark.parametrize(
    ("strategy", "expected"),
    [
        ("coverage",
         "fdef9448236b5d2a0ade7a8f59214eaa04c7ada7c84fda6edea520f01d069e52"),
        ("ranked",
         "36c9e0c9695d1b169a1e8cbbb3271ffdf7b32921862d8cbaee3962def20da516"),
    ],
)
def test_existing_strategies_are_unchanged_where_both_tiers_are_present(
    tmp_path: Path, strategy: str, expected: str
) -> None:
    """The control above cannot see the coverage tier gate; this one can.

    Page neighbours need a 16K budget, so the small fixture the other control
    uses contains tier 0 only and its digests survive removing the tier gate
    from ``_coverage_selection`` entirely. Verified by hand-mutation, which is
    why this case exists. Both digests were likewise produced by a verbatim
    copy of the pre-``adaptive`` implementation at ``9db9c5d``.
    """
    source = joined_tables_and_prose_source()
    counter = FixtureTokenCounter()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=counter)
    scope = DocumentScope.from_documents([ir], source_documents={ir.id: source})
    budget = 16384

    _packet, trace = compile_context_with_trace(
        JOINED_TABLES_AND_PROSE_QUERY,
        scope,
        budget,
        compiler_config(),
        tokenizer=counter,
    )
    pool = trace.deduplicated_candidates

    # Premise: this pool really does span both tiers.
    assert {candidate.priority_tier for candidate in pool} == {
        PRIMARY_EVIDENCE_TIER,
        FALLBACK_CONTEXT_TIER,
    }

    packet = pack_candidates(
        JOINED_TABLES_AND_PROSE_QUERY,
        pool,
        token_budget=budget,
        tokenizer=counter,
        strategy=strategy,
        metadata={"arm": "compiler", "active_operators": ""},
    )

    assert _packet_digest(packet) == expected


_SWITCH_QUERY = "alpha measure and beta result"


def _switch_candidates() -> tuple[CompilerCandidate, ...]:
    """Four candidates that make the switch point observable.

    ``alpha measure`` and ``beta result`` cover one facet each, so the facet
    clause fires once both are taken. ``gamma note`` and ``delta note`` cover
    no facet and no query term; they differ only in that coverage prefers
    ``gamma`` on marginal utility -- it has the better origin rank -- while a
    reranked backfill prefers ``delta``, which scores far higher. Exactly one
    of the two fits the budget, so the two strategies cannot both be right and
    the packet says which one ran.
    """
    counter = FixtureTokenCounter()

    def candidate(
        identifier: str, text: str, page: int, rank: int, reranked: float
    ) -> CompilerCandidate:
        return CompilerCandidate(
            chunk=RetrievalChunk(
                id=f"chunk-{identifier}",
                arm=RetrievalArm.COMPILER,
                document_id="document-1",
                text=text,
                token_count=counter.count(text),
                page_start=page,
                page_end=page,
                source_node_ids=(f"node-{identifier}",),
                source_item_ids=(f"item-{identifier}",),
            ),
            scores=RetrievalScores(reranked=reranked),
            origin_rank=rank,
            expansion_order=rank,
        )

    return (
        candidate("alpha", "alpha measure", 1, 1, 0.5),
        candidate("beta", "beta result", 2, 2, 0.4),
        candidate("gamma", "gamma note", 3, 3, 0.1),
        candidate("delta", "delta note", 4, 4, 0.9),
    )


def test_adaptive_backfills_evidence_coverage_alone_would_not_select() -> None:
    """The backfill must fire at the switch and change what is in the packet."""
    counter = FixtureTokenCounter()
    candidates = _switch_candidates()
    budget = 6
    metadata = {"arm": "compiler", "active_operators": ""}

    # Premise: two facets, and both are covered by the first two candidates.
    assert query_facets(_SWITCH_QUERY, limit=4, min_terms=2) == (
        "alpha measure",
        "beta result",
    )

    packed = {
        strategy: [
            item.content
            for item in pack_candidates(
                _SWITCH_QUERY,
                candidates,
                token_budget=budget,
                tokenizer=counter,
                strategy=strategy,
                metadata=dict(metadata),
            ).items
        ]
        for strategy in ("coverage", "ranked", "adaptive")
    }

    # Coverage keeps buying marginal breadth and takes ``gamma note``.
    assert packed["coverage"] == ["alpha measure", "beta result", "gamma note"]
    # The switch fires once both facets are covered, so the tail is reranked
    # order instead, which brings in evidence coverage never selected.
    assert packed["adaptive"] == ["alpha measure", "beta result", "delta note"]
    assert "delta note" not in packed["coverage"]
    # Adaptive is its own strategy, not a rename of either control.
    assert packed["adaptive"] != packed["coverage"]
    assert packed["adaptive"] != packed["ranked"]
    # The coverage phase's own picks survive the backfill, in its order.
    assert packed["adaptive"][:2] == packed["coverage"][:2]


def test_adaptive_without_facets_keeps_coverage_rather_than_becoming_ranked(
    tmp_path: Path,
) -> None:
    """An empty facet set is inapplicable, not vacuously satisfied.

    Reading "every facet is covered" as true when there are no facets would
    fire the switch before coverage selected anything, collapsing ``adaptive``
    into ``ranked`` for every simple query. The page clause governs instead,
    which is why this fixture's coverage and ranked packets differ and
    adaptive tracks coverage.
    """
    scope, counter = _adaptive_scope(tmp_path)
    budget = 40
    query = "revenue results market"
    metadata = {"arm": "compiler", "active_operators": ""}
    pool = _pool(query, scope, counter, budget)

    # Premise: this query really does produce no facets.
    assert query_facets(query, limit=4, min_terms=2) == ()

    coverage = pack_candidates(
        query, pool, token_budget=budget, tokenizer=counter,
        strategy="coverage", metadata=dict(metadata),
    )
    adaptive = pack_candidates(
        query, pool, token_budget=budget, tokenizer=counter,
        strategy="adaptive", metadata=dict(metadata),
    )
    ranked = pack_candidates(
        query, pool, token_budget=budget, tokenizer=counter,
        strategy="ranked", metadata=dict(metadata),
    )

    covered = [item.content for item in coverage.items]
    assert [item.content for item in adaptive.items] == covered
    assert covered != [item.content for item in ranked.items]


def test_adaptive_backfill_keeps_page_neighbors_behind_primary_evidence(
    tmp_path: Path,
) -> None:
    """Tier 1 is leftover-budget filler and the backfill must not promote it."""
    source = joined_tables_and_prose_source()
    counter = FixtureTokenCounter()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=counter)
    scope = DocumentScope.from_documents([ir], source_documents={ir.id: source})
    budget = 16384

    packet, trace = compile_context_with_trace(
        JOINED_TABLES_AND_PROSE_QUERY,
        scope,
        budget,
        compiler_config(packing_strategy="adaptive"),
        tokenizer=counter,
    )

    tier_by_content = {
        candidate.chunk.text: candidate.priority_tier
        for candidate in trace.deduplicated_candidates
    }
    tiers = [tier_by_content[item.content] for item in packet.items]

    # Premise: both tiers really are present in this packet.
    assert PRIMARY_EVIDENCE_TIER in tiers
    assert FALLBACK_CONTEXT_TIER in tiers
    assert tiers == sorted(tiers)
    assert packet.token_count <= budget


def test_adaptive_backfill_order_is_gated_by_priority_tier() -> None:
    """A high-scoring window must not overtake lower-scoring core evidence."""
    counter = FixtureTokenCounter()

    def candidate(identifier: str, score: float, tier: int) -> CompilerCandidate:
        text = f"evidence {identifier}"
        return CompilerCandidate(
            chunk=RetrievalChunk(
                id=f"chunk-{identifier}",
                arm=RetrievalArm.COMPILER,
                document_id="document-1",
                text=text,
                token_count=counter.count(text),
                source_node_ids=(f"node-{identifier}",),
                source_item_ids=(f"item-{identifier}",),
            ),
            scores=RetrievalScores(reranked=score),
            origin_rank=1,
            expansion_order=0,
            priority_tier=tier,
            operator="page_neighbor" if tier else "retrieval",
        )

    window = candidate("window", 9.0, FALLBACK_CONTEXT_TIER)
    core = candidate("core", 0.1, PRIMARY_EVIDENCE_TIER)

    ordered = _backfill_order((window, core))

    assert [item.chunk.id for item in ordered] == ["chunk-core", "chunk-window"]


@pytest.mark.parametrize("budget", range(0, 61, 4))
def test_adaptive_never_exceeds_the_token_budget(
    tmp_path: Path, budget: int
) -> None:
    scope, counter = _adaptive_scope(tmp_path)

    packet = compile_context(
        ADAPTIVE_QUERY,
        scope,
        budget,
        compiler_config(packing_strategy="adaptive"),
        tokenizer=counter,
    )

    assert packet.token_count <= budget
    assert sum(item.token_count for item in packet.items) == packet.token_count


def test_adaptive_compilation_is_repeatable(tmp_path: Path) -> None:
    scope, counter = _adaptive_scope(tmp_path)
    config = compiler_config(packing_strategy="adaptive")

    first = compile_context(ADAPTIVE_QUERY, scope, 40, config, tokenizer=counter)
    second = compile_context(ADAPTIVE_QUERY, scope, 40, config, tokenizer=counter)

    assert first.model_dump_json() == second.model_dump_json()
    assert first.metadata["packing_strategy"] == "adaptive"
