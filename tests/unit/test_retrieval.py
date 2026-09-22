"""Acceptance tests for deterministic retrieval Arms A and B."""

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.base import Size
from docling_core.types.doc.labels import DocItemLabel
from test_ir import (
    PAGE_HEADER,
    FixtureTokenCounter,
    hidden_layer_source,
    ingest_metadata,
    provenance,
    source_document,
)

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
from contextbench.retrieval.chunking import (
    contextual_search_text,
    fixed_chunks,
    structural_chunks,
)
from contextbench.retrieval.index import _index_key
from contextbench.retrieval.sparse import BM25Index


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


# The (arm, query) pairs that retrieve nothing now that both channels refuse
# non-matches. Every one of these ranked a chunk first with sparse and dense
# both exactly 0.0 before the dense positivity guard landed: rank 1 was awarded
# on hash-ordered dense rank credit alone, over a chunk sharing no query term
# and no vector direction with the query. Empty is the honest answer for all
# four, and it is what BM25 alone has returned for the sparse channel since
# its own guard.
#
# This set used to hold seven pairs, and the three it lost were lost to a fix,
# not to a weakened assertion. ``RetrievalConfig.structural_heading_search_
# context`` now defaults to ``True``, so ``structural_chunks`` sets each chunk's
# ``search_text`` to its heading trail joined above its own text, exactly as the
# compiler's candidates do. Both channels read ``chunk.retrieval_text``, which
# is ``search_text or text``, so headings are now indexed for the structural arm
# too. Emitted ``text`` and ``token_count`` are untouched in either position of
# the flag; this is a search-only change.
#
# Measured by building both indexes over the fixture, with the flag on and then
# off, the indexed vocabularies are:
#
#   fixed (either position):  42 america by grew highlights increased measured
#                             methods north print quarterly region report
#                             results revenue strongly
#   structural, flag on:      the same list minus "highlights"
#   structural, flag off:     42 america by grew increased measured north print
#                             region revenue strongly
#
# The fixed arm windows over *every* node carrying text, title and headings
# included (``chunking.fixed_chunks``), so its indexed vocabulary equals the
# document's. With the flag off, ``structural_chunks`` indexes ``raw_chunk.text``
# alone and ``Quarterly Report``, ``Results`` and ``Methods`` are unreachable --
# that was the defect. With it on, the only term the fixed arm indexes and the
# structural arm does not is ``highlights``, and that one is not a heading at
# all: it is an ``IRNodeKind.LIST`` group name, which Docling's chunker renders
# as "- North America grew." while dropping the name, so it never enters a
# heading trail. The compiler arm cannot reach it either, for its own reason
# (it skips ``IRNodeKind.LIST`` groups as non-evidence). Per remaining pair:
#
#   fixed/metrics                 vocabulary genuinely absent: neither
#                                 "metrics" nor any casefold match of it
#                                 appears anywhere in the fixture.
#   fixed/growth conclusion       genuinely absent: no "growth", no
#                                 "conclusion".
#   structural/metrics            genuinely absent, as above.
#   structural/growth conclusion  genuinely absent, as above.
#
# All four are honest misses, and every one of them is an honest miss on *both*
# arms. That symmetry is the point of the fix: the set no longer contains a
# single pair that is empty only because of which arm asked. The three that
# left -- ``structural``/``quarterly report``, ``structural``/``methods`` and
# ``structural``/``report highlights`` -- now retrieve on heading vocabulary
# their chunk text still does not contain. ``report highlights`` retrieves on
# "report" from the title heading only; "highlights" remains unindexed for the
# reason above, the same way ``structural``/``results revenue`` used to return a
# hit on "revenue" alone. Published pre-fix structural numbers were measured in
# the flag-off state and carry the defect; see ``docs/specs/retrieval.md``.
#
# This list is the measured result, not a target: it is reachable only under
# the offline ``hash-256-v1`` embedding, whose 256-dimension sign-bit vectors
# leave most chunks at exactly 0.0 against a short query. Under the production
# embedder no non-positive similarity occurs at all, so nothing is dropped
# there (see ``docs/specs/retrieval.md``). If chunking, the fixture document,
# or the embedding model changes, re-measure this list rather than editing it
# to make the test pass.
_FIXTURE_QUERIES_WITHOUT_EVIDENCE = frozenset(
    {
        (RetrievalArm.FIXED, "metrics"),
        (RetrievalArm.FIXED, "growth conclusion"),
        (RetrievalArm.STRUCTURAL, "metrics"),
        (RetrievalArm.STRUCTURAL, "growth conclusion"),
    }
)


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

    # Invariants that hold for both halves of the split, including the empty
    # one: the index is still built and saved, the packet is still a valid
    # packet, and it still stays inside its budget. An empty retrieval must
    # produce an empty packet rather than an error or a malformed one.
    assert packet.token_count <= 12
    assert packet.metadata["arm"] == arm.value
    assert all(item.document_id == ir.id for item in packet.items)
    assert list((tmp_path / "artifacts" / "indexes").glob("*/index.json"))

    if (arm, query) in _FIXTURE_QUERIES_WITHOUT_EVIDENCE:
        assert ranked == ()
        assert packet.items == ()
        assert packet.token_count == 0
        return

    assert ranked
    assert ranked[0].rank == 1
    assert ranked[0].chunk.document_id == ir.id
    assert ranked[0].chunk.source_node_ids
    assert ranked[0].chunk.source_item_ids
    # Now tightened to ``> 0`` on both channels, which the comment this
    # replaced said to do once the dense channel filtered non-matches too.
    # The pairs that made the weaker ``>= 0`` necessary were exactly the
    # ones reaching rank 1 on a zero score in both channels; they are the
    # split above, and none of them lands here. For the 16 that remain --
    # 13 before heading context reached the structural arm -- the top hit
    # shares a query term and a vector direction with the query. The three
    # newcomers are scored hits, not empty rows relabelled: measured, they
    # are structural/quarterly report at sparse 0.4705 dense 0.6325,
    # structural/methods at 0.8944/0.4472, and structural/report highlights
    # at 0.2353/0.3162, each clearing this assertion on its own.
    assert ranked[0].scores.sparse > 0
    assert ranked[0].scores.dense > 0
    assert ranked[0].scores.fused > 0
    # No candidate survives on hash-ordered filler: every returned chunk owes
    # its rank to at least one channel that actually scored it.
    assert all(
        evidence.scores.sparse > 0 or evidence.scores.dense > 0
        for evidence in ranked
    )


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


def test_fixed_windows_follow_source_page_order(tmp_path: Path) -> None:
    """A window stream over source-ordered text cannot walk back a page.

    ``fixed_chunks`` concatenates node text in ordinal order and reports
    ``page_start``/``page_end`` as the min and max page of the nodes a window
    touches. So if ordinals put page 1 content behind page 2 content, a window
    splices unrelated pages and claims a span covering both. ``_page_range_distance``
    in ``compiler/expand.py`` reads exactly those two fields, which is how an
    over-wide span turns a window into a page neighbour of every anchor.
    """
    counter = FixtureTokenCounter()
    ir = project_document(
        hidden_layer_source(),
        ingest_metadata(tmp_path),
        tokenizer=counter,
    )
    config = RetrievalConfig(fixed_chunk_tokens=8, fixed_overlap_tokens=0)

    chunks = fixed_chunks(ir, config=config, tokenizer=counter)

    assert len(chunks) > 1
    starts = [chunk.page_start for chunk in chunks]
    ends = [chunk.page_end for chunk in chunks]
    assert all(page is not None for page in (*starts, *ends))
    assert starts == sorted(starts)
    assert ends == sorted(ends)
    # No window claims more of the document than it actually crosses.
    assert all(end - start <= 1 for start, end in zip(starts, ends, strict=True))


def test_fixed_windows_exclude_furniture_without_dropping_it_from_the_ir(
    tmp_path: Path,
) -> None:
    """Running headers are a retrieval-surface exclusion, not an ingest one."""
    counter = FixtureTokenCounter()
    ir = project_document(
        hidden_layer_source(),
        ingest_metadata(tmp_path),
        tokenizer=counter,
    )
    config = RetrievalConfig(fixed_chunk_tokens=8, fixed_overlap_tokens=0)
    furniture = next(node for node in ir.nodes if node.content_layer == "furniture")

    chunks = fixed_chunks(ir, config=config, tokenizer=counter)

    assert chunks
    assert all(PAGE_HEADER not in chunk.text for chunk in chunks)
    assert all(furniture.id not in chunk.source_node_ids for chunk in chunks)
    # Body text on the same page is still there, so this is a filter and not a
    # truncation of the stream.
    assert any("First page body sentence" in chunk.text for chunk in chunks)
    # And the node itself survives projection with its provenance intact.
    assert furniture.text == PAGE_HEADER
    assert furniture.bounding_boxes


def test_structural_chunks_exclude_furniture(tmp_path: Path) -> None:
    """Docling's chunker is body-only; pin it so that cannot drift silently.

    This surface was already clean -- measured across the 28 cached benchmark
    documents, ``structural_chunks`` emitted 7,570 chunks and not one of them
    referenced a furniture node. Nothing in this repository enforced it.
    """
    counter = FixtureTokenCounter()
    source = hidden_layer_source()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=counter)
    config = RetrievalConfig(structural_chunk_tokens=64)
    furniture = next(node for node in ir.nodes if node.content_layer == "furniture")

    chunks = structural_chunks(ir, source, config=config, tokenizer=counter)

    assert chunks
    assert all(PAGE_HEADER not in chunk.text for chunk in chunks)
    assert all(furniture.id not in chunk.source_node_ids for chunk in chunks)


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


def _structural_index(
    tmp_path: Path, retrieval_fixture, *, heading_context: bool
) -> HybridIndex:
    source, ir, config = retrieval_fixture
    return HybridIndex.build(
        [ir],
        arm=RetrievalArm.STRUCTURAL,
        config=config.model_copy(
            update={"structural_heading_search_context": heading_context}
        ),
        source_documents={ir.id: source},
        tokenizer=FixtureTokenCounter(),
        embedder=HashEmbeddingModel(config.embedding_dimensions),
        artifacts_root=tmp_path / f"artifacts-{heading_context}",
    )


def test_structural_chunks_index_heading_vocabulary_when_enabled(
    tmp_path: Path, retrieval_fixture
) -> None:
    """A term that exists only in a heading must reach the structural indexes.

    ``methods`` appears in the fixture as a level-1 heading and nowhere in any
    chunk body: the chunk under it carries only ``print('measured')``. So a hit
    here can only have come from ``search_text`` carrying the heading trail,
    which is what ``structural_heading_search_context`` turns on.
    """
    index = _structural_index(tmp_path, retrieval_fixture, heading_context=True)

    ranked = index.retrieve("methods")

    assert ranked
    chunk = ranked[0].chunk
    assert "methods" not in chunk.text.casefold()
    assert chunk.heading_path == ("Quarterly Report", "Methods")
    assert chunk.search_text == "Quarterly Report\nMethods\n" + chunk.text
    # Retrieved on the heading in both channels, not on rank credit alone.
    assert ranked[0].scores.sparse > 0
    assert ranked[0].scores.dense > 0


def test_structural_heading_context_off_leaves_headings_unindexed(
    tmp_path: Path, retrieval_fixture
) -> None:
    """The off position must reproduce the pre-fix behaviour exactly.

    Pre-fix, ``search_text`` was ``None`` on every structural chunk and heading
    vocabulary was unreachable. Both halves are asserted, so the ablation arm
    of the Phase C comparison is a real reproduction and not merely a weaker
    version of the fix.
    """
    index = _structural_index(tmp_path, retrieval_fixture, heading_context=False)

    assert all(chunk.search_text is None for chunk in index.chunks)
    assert all(
        chunk.retrieval_text == chunk.text for chunk in index.chunks
    )
    assert index.retrieve("methods") == ()
    assert index.retrieve("quarterly report") == ()
    # A body term is unaffected by the flag in either position.
    assert index.retrieve("measured")


def test_structural_heading_context_changes_no_emitted_text_or_token_count(
    tmp_path: Path, retrieval_fixture
) -> None:
    """Search-only means search-only: output bytes and budgets cannot move.

    ``search_text`` is read by the indexes; ``text`` and ``token_count`` are
    what a model sees and what every budget is charged against. The flag must
    leave chunk identity, emitted text, token counts and provenance identical
    in both positions, and a packed context for a query that both positions
    retrieve must be byte-identical.
    """
    on = _structural_index(tmp_path, retrieval_fixture, heading_context=True)
    off = _structural_index(tmp_path, retrieval_fixture, heading_context=False)

    def emitted(index: HybridIndex):
        return tuple(
            (
                chunk.id,
                chunk.text,
                chunk.token_count,
                chunk.heading_path,
                chunk.page_start,
                chunk.page_end,
                chunk.source_node_ids,
                chunk.source_item_ids,
            )
            for chunk in index.chunks
        )

    assert emitted(on) == emitted(off)
    assert [chunk.search_text for chunk in off.chunks] == [None] * len(off.chunks)
    # Stated as the exact per-chunk expectation rather than ``is not None``.
    # ``chunking.py`` guards on ``and heading_path``, so a chunk with an empty
    # trail correctly keeps ``search_text is None`` even with the flag on; a
    # blanket ``is not None`` would hold here only because every chunk of this
    # fixture happens to sit under a heading, and would fail spuriously the day
    # one does not. This form is strictly stronger -- it pins the string, not
    # just its presence -- while staying true for a heading-less chunk.
    assert [chunk.search_text for chunk in on.chunks] == [
        contextual_search_text(chunk.text, chunk.heading_path)
        if chunk.heading_path
        else None
        for chunk in on.chunks
    ]
    # ...and not vacuous: at least one chunk must actually gain a trail, or the
    # comparison above would pass against two lists of ``None``.
    assert any(chunk.search_text is not None for chunk in on.chunks)

    packed_on = on.pack("measured", token_budget=12)
    packed_off = off.pack("measured", token_budget=12)
    assert [item.content for item in packed_on.items] == [
        item.content for item in packed_off.items
    ]
    assert packed_on.token_count == packed_off.token_count


def duplicate_body_source() -> DoclingDocument:
    """Two identical paragraph bodies under two different level-1 headings."""
    document = DoclingDocument(name="duplicate-body")
    document.add_page(1, Size(width=612, height=792))
    title = document.add_title(
        "Annual Review",
        prov=provenance(1, "Annual Review", 750),
    )
    body = "Revenue increased strongly."
    for name, top in (("North", 700), ("South", 600)):
        heading = document.add_heading(
            name,
            level=1,
            parent=title,
            prov=provenance(1, name, top),
        )
        document.add_text(
            label=DocItemLabel.TEXT,
            text=body,
            parent=heading,
            prov=provenance(1, body, top - 20),
        )
    return document


def test_heading_context_widens_candidate_dedupe_scope(tmp_path: Path) -> None:
    """Heading context also widens the dedupe key, for queries with no headings.

    ``HybridIndex._unique_by_search_text`` dedupes on ``retrieval_text``, and it
    runs on the sorted fused candidate list *before* ``rerank_limit`` is
    applied. With the flag off, two chunks whose bodies are identical under
    different headings share a dedupe key and collapse to one candidate: the
    second is dropped, and with it its heading and its provenance. With the flag
    on, the key is the heading trail above the body, so both survive into the
    rerank pool and both consume a rerank slot.

    This is a **second, independent mechanism** by which the flag moves
    structural numbers. It is not heading-vocabulary matching: the query
    asserted below shares no term with any heading in the fixture, and the
    result still differs between the two positions of the flag. An ablation
    that toggles this one flag therefore measures heading matching *and* dedupe
    scope together, which is why the difference is recorded in
    ``docs/specs/retrieval.md`` rather than left to be attributed to matching.

    The widening is the correct behaviour and is not being changed here: two
    passages under different headings are different evidence with different
    provenance, and it makes the structural arm consistent with the compiler
    arm, whose candidates have always carried heading-bearing ``search_text``.
    """
    source = duplicate_body_source()
    counter = FixtureTokenCounter()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=counter)
    config = RetrievalConfig(
        structural_chunk_tokens=24,
        candidate_limit=10,
        rerank_limit=5,
    )

    def index(heading_context: bool) -> HybridIndex:
        return HybridIndex.build(
            [ir],
            arm=RetrievalArm.STRUCTURAL,
            config=config.model_copy(
                update={"structural_heading_search_context": heading_context}
            ),
            source_documents={ir.id: source},
            tokenizer=counter,
            embedder=HashEmbeddingModel(config.embedding_dimensions),
            artifacts_root=tmp_path / f"dedupe-artifacts-{heading_context}",
        )

    on = index(heading_context=True)
    off = index(heading_context=False)

    # Same chunks, same emitted text, in both positions: only the key differs.
    assert [chunk.text for chunk in on.chunks] == [chunk.text for chunk in off.chunks]
    assert len(on.chunks) == 2
    assert on.chunks[0].text == on.chunks[1].text
    assert on.chunks[0].heading_path != on.chunks[1].heading_path

    # The query carries no heading vocabulary at all, which is the point.
    query = "revenue"
    headings = {
        term
        for chunk in on.chunks
        for heading in chunk.heading_path
        for term in heading.casefold().split()
    }
    assert not headings & set(query.casefold().split())

    on_candidates = on.retrieve_candidates(query)
    off_candidates = off.retrieve_candidates(query)

    assert len(on_candidates) == 2
    assert {evidence.chunk.heading_path for evidence in on_candidates} == {
        ("Annual Review", "North"),
        ("Annual Review", "South"),
    }
    assert len(off_candidates) == 1
    assert len(on.retrieve(query)) == 2
    assert len(off.retrieve(query)) == 1


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
    """Collapsing duplicates must free a rerank slot for a different chunk.

    The query gained the term ``evidence`` when the dense channel started
    refusing non-matches. It had been ``same repeated boilerplate``, which the
    ``unique`` chunk matches in neither channel: sparse 0.0, and dense exactly
    0.0 against the hash embedding. That chunk was therefore filling the
    second rerank slot on hash-ordered dense rank credit, so the test was
    demonstrating its property with a candidate that had earned nothing. With
    ``evidence`` in the query the same two chunks fill the same two slots,
    both on genuine sparse matches, and the assertions below are unchanged.
    """
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

    ranked = index.retrieve("same repeated boilerplate evidence")

    assert len(ranked) == 2
    assert {item.chunk.retrieval_text for item in ranked} == {
        "same repeated boilerplate",
        "unique evidence",
    }


def test_fixed_retrieval_capacity_keeps_budget_contexts_nested() -> None:
    """A smaller budget must yield a prefix of the larger budget's packet.

    The chunk text gained a hyphen when the dense channel started refusing
    non-matches. It had been ``evidence0``, which BM25 tokenizes as the single
    term ``evidence0`` -- so the query ``evidence`` matched no chunk at all,
    and every one of these twenty candidates reached the pool on a dense rank
    over a similarity of exactly 0.0, ordered by chunk id. The nesting
    property was being demonstrated over a ranking that was entirely hash
    order. ``evidence-0`` tokenizes as ``evidence`` and ``0``, so the query
    now matches all twenty on the sparse side, while
    ``FixtureTokenCounter`` still counts one whitespace-delimited token per
    chunk, leaving the budget arithmetic below exactly as it was.
    """
    chunks = tuple(
        RetrievalChunk(
            id=f"chunk-{index:02d}",
            arm=RetrievalArm.COMPILER,
            document_id="doc",
            text=f"evidence-{index}",
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
    """Scoping must exclude another document's chunks from a shared index.

    The query gained the term ``revenue`` when the dense channel started
    refusing non-matches. It had been ``exclusive scope leak phrase``, a
    phrase that appears only in the excluded document, so inside the allowed
    scope it matched nothing in either channel and the packet is now empty.
    An empty packet excludes the leak trivially, which would make this test
    vacuous rather than failing. ``revenue`` appears in the allowed document,
    so the scoped packet is non-empty and the exclusion is doing real work.
    The unscoped packet below is checked too: it must surface the leak chunk,
    which proves the scoped packet's silence comes from the document filter
    and not from the query simply matching nothing anywhere.
    """
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

    query = "exclusive scope leak phrase revenue"
    packet = index.pack(query, token_budget=100, document_ids={allowed.id})
    unscoped = index.pack(query, token_budget=100)

    assert packet.items
    assert {item.document_id for item in packet.items} == {allowed.id}
    assert not any("exclusive scope leak" in item.content for item in packet.items)
    assert any("exclusive scope leak" in item.content for item in unscoped.items)


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


def test_index_key_separates_both_heading_search_context_fields() -> None:
    """Each heading field must rekey on its own, and not collide with the other.

    Derived indexes are cached under this key, and both fields change what a
    unit indexes, so a run with either one off must never reuse an index built
    with it on. Turning them off produces three distinct configurations --
    structural only, compiler only, both -- and all four keys have to differ:
    if only one field reached the key, two of these would collide and a cached
    index would silently be reused across the setting the run was made to
    change.
    """
    both_on = _key()
    structural_off = _key(
        config=RetrievalConfig(structural_heading_search_context=False)
    )
    nodes_off = _key(
        config=RetrievalConfig(compiler_node_heading_search_context=False)
    )
    both_off = _key(
        config=RetrievalConfig(
            structural_heading_search_context=False,
            compiler_node_heading_search_context=False,
        )
    )

    assert len({both_on, structural_off, nodes_off, both_off}) == 4


def test_index_key_is_stable_for_a_fixed_revision() -> None:
    """Pin the key for one fixed input so a payload change cannot pass silently.

    The literal was produced by this payload and nothing else. Any accidental
    change to the key payload, its field names, or the retrieval config
    defaults would strand every cached index under a new key, so that change
    has to be made deliberately.

    Both literals have moved three times, each time because
    ``RetrievalConfig`` changed shape: when it gained
    ``structural_heading_search_context``; when that field was renamed to
    ``heading_search_context`` so both heading-bearing content units read it;
    and now that the one field is split back into
    ``structural_heading_search_context`` and
    ``compiler_node_heading_search_context``, one per unit. The key payload
    embeds ``config.model_dump(mode="json")``, so any config field change
    rekeys every cached index -- which is correct here, because these fields
    change what the structural and IR units index and a stale index must not be
    reused across either of them. That is the property the split has to
    preserve: each field reaches the key on its own, so a run that turns one
    off cannot reuse the index of a run that left it on.

    Derived rather than re-recorded, at every step. For the split: rebuilding
    this exact payload with the two config keys collapsed back into the single
    ``heading_search_context`` they replace, value unchanged, and hashing it
    the same way reproduces the previous literals byte for byte --
    ``1df0d2dc8403e51f8e109387922e7a4fabafc38abd5787b174b726addf17d449``
    offline and ``5d6ebb7ee0a00513a67ad06516d9ab2e1215a55df13389fc66442d5e9841
    baf6`` hub-backed -- and the symmetric difference of the two config dumps is
    exactly those three key names, with no shared key differing in value. The
    split is therefore the whole of the difference.

    For the rename before it: renaming the one key back to
    ``structural_heading_search_context`` reproduced
    ``3dff8843ce030b48bd9ff9ca59eec5826e2be6c9d62409dfc9ae1b7f9e15d105``
    offline and ``8bc92172223a345ab003704cf6081998ac06d393fadf012cd30eb285f44
    17b23`` hub-backed. For the field's introduction before that: deleting the
    key entirely reproduced
    ``09fca44765c922c8ba0b5a1812ae172ab0a578842a7e52ff1887a14e40bdf99e``
    offline and ``fcafc11e9de5b97151c6b0bb473435f3fd6196e6e7fe3d247403fdb7b5
    c2e927`` hub-backed.
    """
    assert _key(
        embedding_model="hash-256-v1",
        embedding_version="1",
        embedding_revision=None,
        reranker_model="lexical-overlap-v1",
        reranker_version="1",
        reranker_revision=None,
    ) == "f7d25a102c55a27ea2cd7eae004c2adcf1448b4e327c4a4c34495169282ff4d3"

    assert _key() == "034f7f527f5a306b5ebce87cc4c61edabc0917e15ac0d9642632487b8881388b"


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


def _sparse_probe_corpus() -> tuple[RetrievalChunk, ...]:
    """Ten chunks of which exactly five contain the probe term ``zirconium``."""
    texts = (
        "zirconium alloys resist corrosion in reactor cladding.",
        "The bridge deck was poured in three continuous sections.",
        "Cold-worked zirconium keeps its strength at temperature.",
        "Rainfall totals for the catchment fell for a fourth year.",
        "Trace hafnium is separated from zirconium before use.",
        "The orchestra rehearsed the second movement twice.",
        "Welding zirconium demands an inert shielding atmosphere.",
        "Ferry timetables change on the first Monday of the month.",
        "Neutron transparency is why zirconium is chosen at all.",
        "The bakery opens before dawn on market days.",
    )
    return tuple(
        RetrievalChunk(
            id=f"sparse-chunk-{position:02d}",
            arm=RetrievalArm.FIXED,
            document_id="sparse-doc",
            text=chunk_text,
            token_count=len(chunk_text.split()),
            source_node_ids=(f"sparse-node-{position:02d}",),
            source_item_ids=(f"sparse-item-{position:02d}",),
        )
        for position, chunk_text in enumerate(texts)
    )


def test_bm25_returns_only_chunks_that_match_a_query_term() -> None:
    """A chunk sharing no term with the query is not a sparse hit.

    Five of these ten chunks contain ``zirconium`` and five share no token
    with the query at all. Asking for ten results must still yield five: a
    zero-score chunk carries no lexical evidence, and returning it gave it a
    rank, ordered among its fellow zeros by chunk id, which is a hash.
    """
    chunks = _sparse_probe_corpus()
    config = RetrievalConfig()
    index = BM25Index(chunks, k1=config.sparse_k1, b=config.sparse_b)

    hits = index.search("zirconium", limit=10)

    assert len(hits) == 5
    assert all(score > 0.0 for _position, score in hits)
    assert {chunks[position].id for position, _score in hits} == {
        "sparse-chunk-00",
        "sparse-chunk-02",
        "sparse-chunk-04",
        "sparse-chunk-06",
        "sparse-chunk-08",
    }


def test_fusion_credit_equals_the_ranks_each_channel_actually_awarded() -> None:
    """Every fused candidate is paid for ranks a channel genuinely gave it.

    This test previously asserted the opposite shape: that a chunk BM25 had
    refused still reached fusion on a dense term alone, scoring exactly
    ``1 / (rrf_k + dense_rank)``. Its docstring recorded why that was a defect
    rather than a design -- ``_dense_search`` had no positivity guard, so it
    ranked zero-similarity chunks in ``chunk.id`` order and paid them full
    reciprocal-rank credit -- and predicted this rewrite once the guard
    landed. It has landed, so the one-sided case it described no longer
    exists in this corpus, and asserting it would now assert a bug.

    What replaces it is the positive claim. Both channels refuse non-matches,
    so both return exactly the five ``zirconium`` chunks, and each candidate's
    fused score is the sum of the two reciprocal-rank terms its own ranks
    earned. No candidate is carried by a rank awarded on a hash.
    """
    chunks = _sparse_probe_corpus()
    config = RetrievalConfig(candidate_limit=10, rerank_limit=10)
    index = HybridIndex(
        chunks,
        config=config,
        embedder=HashEmbeddingModel(config.embedding_dimensions),
        reranker=LexicalOverlapReranker(),
        tokenizer=FixtureTokenCounter(),
    )
    sparse_ranks = {
        chunks[position].id: rank
        for rank, (position, _score) in enumerate(
            index.sparse.search("zirconium", limit=10), 1
        )
    }
    dense_ranks = {
        chunks[position].id: rank
        for rank, (position, _score) in enumerate(
            index._dense_search("zirconium", 10, allowed_indices=None), 1
        )
    }

    candidates = index.retrieve_candidates("zirconium")

    matching = {
        "sparse-chunk-00",
        "sparse-chunk-02",
        "sparse-chunk-04",
        "sparse-chunk-06",
        "sparse-chunk-08",
    }
    assert set(sparse_ranks) == matching
    assert set(dense_ranks) == matching
    assert {item.chunk.id for item in candidates} == matching
    for item in candidates:
        assert item.scores.sparse > 0.0
        assert item.scores.dense > 0.0
        assert item.scores.fused == pytest.approx(
            1 / (config.rrf_k + sparse_ranks[item.chunk.id])
            + 1 / (config.rrf_k + dense_ranks[item.chunk.id])
        )


def test_dense_search_returns_only_chunks_with_positive_similarity() -> None:
    """A chunk with no positive similarity to the query is not a dense hit.

    The dense analogue of the BM25 test above, over the same corpus and the
    same query. Under the offline hash embedding the five
    chunks with no ``zirconium`` token also share no sign-bit direction with
    the query, leaving them at similarity exactly 0.0. Asking for ten results
    must still yield five: returning the zeros gave them a dense rank ordered
    among themselves by chunk id, which is a hash rather than relevance.
    """
    chunks = _sparse_probe_corpus()
    config = RetrievalConfig(candidate_limit=10, rerank_limit=10)
    index = HybridIndex(
        chunks,
        config=config,
        embedder=HashEmbeddingModel(config.embedding_dimensions),
        reranker=LexicalOverlapReranker(),
        tokenizer=FixtureTokenCounter(),
    )

    hits = index._dense_search("zirconium", 10, allowed_indices=None)

    assert len(hits) == 5
    assert all(score > 0.0 for _position, score in hits)
    assert {chunks[position].id for position, _score in hits} == {
        "sparse-chunk-00",
        "sparse-chunk-02",
        "sparse-chunk-04",
        "sparse-chunk-06",
        "sparse-chunk-08",
    }


def test_chunks_absent_from_both_channels_earn_no_fusion_credit() -> None:
    """A chunk neither channel scored must not reach fusion at all.

    The five non-``zirconium`` chunks score 0.0 under BM25 and 0.0 under the
    dense channel. With both guards in place neither channel ranks them, so
    they earn no reciprocal-rank term from either side and must be absent
    from the candidate pool entirely -- not present with a fused score of
    0.0, which would still let them occupy a rerank slot and, at a smaller
    ``rerank_limit``, displace a chunk that was genuinely scored.
    """
    chunks = _sparse_probe_corpus()
    config = RetrievalConfig(candidate_limit=10, rerank_limit=10)
    index = HybridIndex(
        chunks,
        config=config,
        embedder=HashEmbeddingModel(config.embedding_dimensions),
        reranker=LexicalOverlapReranker(),
        tokenizer=FixtureTokenCounter(),
    )
    unscored = {
        "sparse-chunk-01",
        "sparse-chunk-03",
        "sparse-chunk-05",
        "sparse-chunk-07",
        "sparse-chunk-09",
    }

    candidates = index.retrieve_candidates("zirconium")
    ranked = index.retrieve("zirconium")
    packet = index.pack("zirconium", token_budget=200)

    assert not {item.chunk.id for item in candidates}.intersection(unscored)
    assert not {item.chunk.id for item in ranked}.intersection(unscored)
    assert not {
        chunks[position].id
        for position, _score in index.sparse.search("zirconium", limit=10)
    }.intersection(unscored)
    assert not {
        chunks[position].id
        for position, _score in index._dense_search(
            "zirconium", 10, allowed_indices=None
        )
    }.intersection(unscored)
    unscored_texts = {chunks[position].text for position in (1, 3, 5, 7, 9)}
    assert not {item.content for item in packet.items}.intersection(unscored_texts)


def test_a_query_matching_nothing_retrieves_nothing() -> None:
    """When both channels refuse, retrieval and packing are empty, not filled.

    This is the semantics the dense guard commits to: a channel with no
    evidence returns nothing, so a query with no evidence in either channel
    returns nothing. It previously returned a full pool of chunks ordered by
    a hash of their ids. An empty packet must still be a valid packet -- zero
    items, zero tokens, inside its budget, carrying its metadata -- because
    every downstream consumer receives it.
    """
    chunks = _sparse_probe_corpus()
    config = RetrievalConfig(candidate_limit=10, rerank_limit=10)
    index = HybridIndex(
        chunks,
        config=config,
        embedder=HashEmbeddingModel(config.embedding_dimensions),
        reranker=LexicalOverlapReranker(),
        tokenizer=FixtureTokenCounter(),
    )

    assert index.sparse.search("gallium", limit=10) == []
    assert index._dense_search("gallium", 10, allowed_indices=None) == []
    assert index.retrieve_candidates("gallium") == ()
    assert index.retrieve("gallium") == ()

    packet = index.pack("gallium", token_budget=200)

    assert packet.items == ()
    assert packet.token_count == 0
    assert packet.token_budget == 200
    assert packet.metadata["arm"] == RetrievalArm.FIXED.value


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
#
# Two rows are no longer pure d7f427e captures. Stopping BM25 from returning
# zero-score chunks moved ``quarterly metrics``; adding the matching positivity
# guard to the dense channel shortened ``region 42`` from four results to
# three. Both were re-derived from the reciprocal-rank arithmetic, not
# re-recorded, and each derivation sits on its own row.
#
# The other five rows still hold their d7f427e *values*. Four of them --
# ``revenue by region``, ``north america growth``, ``margin recovery`` and
# ``europe costs identifier`` -- have no non-positive similarity anywhere in
# their dense top-five, so the *dense* guard discards nothing from them. That
# is a statement about the dense guard only, not about the row being untouched:
# ``margin recovery`` did lose zero-score sparse padding to the earlier BM25
# guard. Its value survives because the padding sat below the top-four rerank
# cut, so removing it changed no returned entry -- the same way ``europe
# costs`` survived losing chunk-00 from dense rank 5 at similarity exactly 0.0,
# also below the cut. Read these four as "the dense guard changed nothing
# here", and ``margin recovery`` and ``europe costs`` as additionally "an input
# did change, below the cut".
#
# Treat an unchanged value as evidence about the value only. If one of these
# rows later flips, the first place to look is the derivation recorded beside
# it, not a regression in a subsystem the row never depended on.
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
    # Re-derived, not re-recorded, when BM25 stopped returning zero-score
    # chunks. Only 13, 07 and 10 contain "quarterly" or "metrics", so the
    # pre-fix sparse top-five padded itself with 00 and 01 at score 0.0, in
    # chunk-id order. That paid chunk-00 sparse rank 4, worth 1/64, lifting it
    # to fused 1/64 + 1/65 = 0.031010 and into the fourth rerank slot. Without
    # the padding chunk-00 keeps only dense rank 5, 1/65 = 0.015385, and loses
    # the slot to chunk-04, which earns 1/63 = 0.015873 from dense rank 3 on
    # its own. The first three places are sparse-and-dense hits and do not move.
    #
    # The dense guard then took chunk-00's remaining rank too: its similarity
    # to this query is exactly 0.0, so it is no longer a dense hit and the
    # pool is 07, 13, 10, 04 with no fifth entry to cut. The value is
    # unchanged because chunk-00 had already lost the slot on the arithmetic
    # above; what changed is that it now has no credit left at all. Chunk-04
    # keeps dense rank 3 on a genuine 0.2236 similarity.
    "quarterly metrics": (
        ("ranking-chunk-07", 1),
        ("ranking-chunk-13", 2),
        ("ranking-chunk-10", 3),
        ("ranking-chunk-04", 4),
    ),
    # Re-derived, not re-recorded, when the dense channel gained the same
    # positivity guard BM25 has. This is the deletion the previous note on
    # this row predicted: it said slot 4 survived only on "a one-rank margin
    # on a hash-ordered tie", and the guard removes exactly that.
    #
    # Only 12, 00 and 05 contain "region" or "42" -- 08 has "regions" and 06
    # has "regional", both different tokens -- so sparse returns three hits:
    # 12 at 4.0475, then 00 and 05 tied at 1.4605 and separated by chunk id,
    # giving sparse ranks 12=1, 00=2, 05=3. Dense similarities are 12=0.5883,
    # 05=0.2357, 00=0.2132 and exactly 0.0 for the other eleven chunks, so
    # dense ranks are 12=1, 05=2, 00=3.
    #
    # Pre-guard, dense sliced its top five from the full sort, so the two
    # lowest-id zeros took the remaining slots: chunk-01 at dense rank 4 and
    # chunk-02 at dense rank 5, in chunk-id order. Neither matched a query
    # term, so each held only its dense term: chunk-01 at 1/64 = 0.015625 and
    # chunk-02 at 1/65 = 0.015385. That was enough for chunk-01 to take the
    # fourth rerank slot ahead of chunk-02.
    #
    # Post-guard both are discarded before ranking and earn nothing, because
    # 0.0 is not a positive similarity. Three candidates remain and rerank_limit
    # of 4 cuts nothing:
    #   12: 1/61 + 1/61 = 0.032787
    #   00: 1/62 + 1/63 = 0.032002  (sparse rank 2, dense rank 3)
    #   05: 1/63 + 1/62 = 0.032002  (sparse rank 3, dense rank 2)
    # 00 and 05 tie exactly -- the same two reciprocal-rank terms swapped
    # between channels -- and the tie breaks on chunk id, so 00 takes 2 and 05
    # takes 3. The reranker leaves that order. The row is three entries, and
    # every one of them is a hit in both channels.
    "region 42": (
        ("ranking-chunk-12", 1),
        ("ranking-chunk-00", 2),
        ("ranking-chunk-05", 3),
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

    Absorbing score-scaling is not absorbing everything. A change to which
    chunks a channel returns at all moves ranks rather than magnitudes, and
    those the table does see: dropping zero-score chunks from the sparse hits
    left ``europe costs identifier`` untouched, since all five of its hits
    score above zero, and moved ``quarterly metrics`` instead; dropping
    non-positive similarities from the dense hits then shortened ``region 42``
    from four results to three, because only three chunks in this corpus carry
    any signal for that query in either channel.

    A shorter row is a legitimate result, not a truncation. Both channels now
    refuse to rank what they did not score, so a query with three hits yields
    three results rather than padding to the rerank limit with chunks ordered
    by a hash of their ids.

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
