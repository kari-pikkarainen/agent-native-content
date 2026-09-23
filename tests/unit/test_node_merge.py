"""Retrieval-unit merging of source-adjacent tiny IR nodes (compiler only)."""

import hashlib
import json
from pathlib import Path

import pytest
from merge_fixtures import run_source, shredded_source
from test_compiler import compiler_source
from test_ir import FixtureTokenCounter, ingest_metadata

from contextbench.compiler import (
    CompilerConfig,
    DocumentScope,
    compile_context,
    compile_context_with_trace,
)
from contextbench.compiler.candidates import (
    merged_unit_id,
    node_chunks,
)
from contextbench.compiler.compiler import cap_candidate_pool
from contextbench.compiler.dedupe import deduplicate_candidates
from contextbench.compiler.expand import expand_candidates
from contextbench.compiler.models import CompilerCandidate, NodeMergePolicy
from contextbench.evaluation import FactorialConfig
from contextbench.ir import project_document
from contextbench.ir.models import IRBoundingBox, IRDocument, IRNode, IRNodeKind
from contextbench.retrieval import RetrievalConfig
from contextbench.retrieval.models import (
    RankedEvidence,
    RetrievalArm,
    RetrievalChunk,
    RetrievalScores,
)
from contextbench.retrieval.rendering import evidence_item_overhead
from contextbench.retrieval.rerank import LexicalOverlapReranker

COUNTER = FixtureTokenCounter()
# Word counts: every fixture paragraph below is two words unless stated.
POLICY = NodeMergePolicy(min_tokens=4, target_tokens=6, max_tokens=8, max_page_span=1)


def _node(
    ordinal: int,
    text: str,
    *,
    heading: tuple[str, ...] = ("Alpha",),
    page: int = 1,
    page_end: int | None = None,
    kind: IRNodeKind = IRNodeKind.PARAGRAPH,
    items: tuple[str, ...] | None = None,
) -> IRNode:
    end = page_end or page
    return IRNode(
        id=f"node{ordinal}",
        document_id="doc",
        kind=kind,
        content_layer="body",
        ordinal=ordinal,
        text=text,
        heading_path=heading,
        page_start=page,
        page_end=end,
        bounding_boxes=(
            IRBoundingBox(
                page_no=page, left=10, top=700 - ordinal, right=200, bottom=690,
                coord_origin="BOTTOMLEFT",
            ),
            *(
                (
                    IRBoundingBox(
                        page_no=end, left=10, top=90, right=200, bottom=80,
                        coord_origin="BOTTOMLEFT",
                    ),
                )
                if end != page
                else ()
            ),
        ),
        source_item_ids=items or (f"#/texts/{ordinal}",),
        token_count=len(text.split()),
    )


def _document(*nodes: IRNode) -> IRDocument:
    return IRDocument(
        id="doc",
        source_uri="file:///doc.pdf",
        source_sha256="a" * 64,
        parser_name="fixture",
        parser_version="1",
        parser_core_version="1",
        tokenizer_name=COUNTER.name,
        tokenizer_version=COUNTER.version,
        page_count=3,
        page_numbers=(1, 2, 3),
        nodes=nodes,
    )


def _units(document: IRDocument, policy: NodeMergePolicy = POLICY):
    return node_chunks([document], tokenizer=COUNTER, merge=policy)


def _groups(chunks) -> list[tuple[str, ...]]:
    return [chunk.source_node_ids for chunk in chunks]


def _one_node_id(document_id: str, node: IRNode) -> str:
    """The 7a9726b one-node id derivation, verbatim."""
    payload = f"compiler-node-v3\0{document_id}\0{node.id}\0{node.text}".encode()
    return f"chunk_{hashlib.sha256(payload).hexdigest()}"


# --- the merge rule -------------------------------------------------------


def test_merging_never_crosses_a_heading_path_boundary() -> None:
    """Adjacent, same page, all tiny: only the heading path separates them."""
    document = _document(
        _node(0, "a0 b0"),
        _node(1, "a1 b1"),
        _node(2, "a2 b2", heading=("Beta",)),
        _node(3, "a3 b3", heading=("Beta",)),
    )
    wide = POLICY.model_copy(update={"target_tokens": 8})

    assert _groups(_units(document, wide)) == [
        ("node0", "node1"),
        ("node2", "node3"),
    ]
    # A deeper trail is a different path too, not a prefix match.
    nested = _document(
        _node(0, "a0 b0"),
        _node(1, "a1 b1", heading=("Alpha", "Sub")),
    )
    assert _groups(_units(nested, wide)) == [("node0",), ("node1",)]


def test_merging_never_crosses_the_page_span_limit() -> None:
    document = _document(
        _node(0, "a0 b0", page=1),
        _node(1, "a1 b1", page=1),
        _node(2, "a2 b2", page=2),
        _node(3, "a3 b3", page=2),
    )
    wide = POLICY.model_copy(update={"target_tokens": 8})

    assert _groups(_units(document, wide)) == [
        ("node0", "node1"),
        ("node2", "node3"),
    ]
    # The limit is the whole unit's span, not the gap to the previous node:
    # a node that itself runs onto page 2 cannot join a page-1 run at span 1.
    straddling = _document(
        _node(0, "a0 b0", page=1),
        _node(1, "a1 b1", page=1, page_end=2),
    )
    assert _groups(_units(straddling, wide)) == [("node0",), ("node1",)]
    # And the limit is a parameter: two pages admits both documents whole.
    two_pages = wide.model_copy(update={"max_page_span": 2})
    assert _groups(_units(document, two_pages)) == [
        ("node0", "node1", "node2", "node3")
    ]
    assert _groups(_units(straddling, two_pages)) == [("node0", "node1")]


def test_units_grow_to_target_and_never_past_max() -> None:
    document = _document(*(_node(i, f"a{i} b{i} c{i}") for i in range(4)))

    # Three-word nodes, target 6: each unit closes at exactly 6.
    assert _groups(_units(document)) == [("node0", "node1"), ("node2", "node3")]
    # Target 8, max 8: a third node would make 9, so the unit stops at 6.
    capped = POLICY.model_copy(update={"target_tokens": 8, "max_tokens": 8})
    units = _units(document, capped)
    assert _groups(units) == [("node0", "node1"), ("node2", "node3")]
    assert all(unit.token_count <= 8 for unit in units)
    # Max 9 admits the third node.
    roomy = POLICY.model_copy(update={"target_tokens": 9, "max_tokens": 9})
    assert _groups(_units(document, roomy)) == [
        ("node0", "node1", "node2"),
        ("node3",),
    ]
    # The target closes a unit even with room to spare under the max.
    spare = POLICY.model_copy(update={"max_tokens": 100})
    assert _groups(_units(document, spare)) == [
        ("node0", "node1"),
        ("node2", "node3"),
    ]


def test_a_node_at_the_minimum_stays_alone_and_ends_the_run() -> None:
    document = _document(
        _node(0, "a0 b0"),
        _node(1, "w x y z"),  # exactly min_tokens
        _node(2, "a2 b2"),
    )

    assert _groups(_units(document)) == [("node0",), ("node1",), ("node2",)]


def test_non_prose_kinds_end_a_run_and_are_never_merged() -> None:
    document = _document(
        _node(0, "a0 b0"),
        _node(1, "Figure one", kind=IRNodeKind.CAPTION),
        _node(2, "a2 b2"),
        _node(3, "a3 b3", kind=IRNodeKind.LIST_ITEM),
    )
    wide = POLICY.model_copy(update={"target_tokens": 8})

    assert _groups(_units(document, wide)) == [
        ("node0",),
        ("node1",),
        ("node2", "node3"),
    ]


def test_a_tiny_node_with_no_mergeable_neighbour_is_unchanged() -> None:
    document = _document(
        _node(0, "a0 b0"),
        _node(1, "a1 b1", heading=("Beta",)),
    )
    unmerged = node_chunks([document], tokenizer=COUNTER)

    assert _units(document) == unmerged


# --- identity and provenance ----------------------------------------------


def test_merged_provenance_is_the_full_union_in_reading_order() -> None:
    document = _document(
        _node(0, "a0 b0", page=1, items=("#/texts/9", "#/texts/2")),
        _node(1, "a1 b1", page=2, items=("#/texts/2", "#/texts/5")),
        _node(2, "a2 b2", page=2, items=("#/texts/1",)),
    )
    policy = POLICY.model_copy(update={"max_page_span": 2})

    (unit,) = _units(document, policy)

    assert unit.source_node_ids == ("node0", "node1", "node2")
    # Reading order, first occurrence, nothing dropped and nothing sorted.
    assert unit.source_item_ids == ("#/texts/9", "#/texts/2", "#/texts/5", "#/texts/1")
    assert (unit.page_start, unit.page_end) == (1, 2)
    assert unit.text == "a0 b0\na1 b1\na2 b2"
    assert unit.token_count == 6
    assert unit.heading_path == ("Alpha",)
    assert unit.search_text is not None and "Alpha" in unit.search_text
    # Every contributing bounding box stays reachable through the node ids.
    boxes = [
        box
        for node_id in unit.source_node_ids
        for box in document.node_by_id[node_id].bounding_boxes
    ]
    assert boxes == [box for node in document.nodes for box in node.bounding_boxes]


def test_merged_ids_cannot_collide_with_one_node_ids() -> None:
    document = _document(*(_node(i, f"a{i} b{i}") for i in range(3)))
    single_ids = {_one_node_id("doc", node) for node in document.nodes}

    (unit,) = _units(document)

    assert unit.id == merged_unit_id("doc", unit.source_node_ids, unit.text)
    assert unit.id not in single_ids
    # The domains are disjoint even for a degenerate one-node run with the
    # one-node id's exact inputs.
    for node in document.nodes:
        assert merged_unit_id("doc", (node.id,), node.text) != _one_node_id(
            "doc", node
        )
    # Deterministic and pinned: the derivation, domain marker included, is a
    # recorded format, so changing it must be a visible decision.
    assert merged_unit_id("doc", ("node0", "node1"), "x") == (
        "chunk_"
        + hashlib.sha256(
            b'compiler-merged-v1\0["doc",["node0","node1"],"x"]'
        ).hexdigest()
    )
    # Sensitive to membership, not just to the concatenated ids.
    assert merged_unit_id("doc", ("node0", "node1"), "x") != merged_unit_id(
        "doc", ("node0node1",), "x"
    )


def test_unmerged_ids_are_unchanged() -> None:
    document = _document(
        _node(0, "a0 b0"),
        _node(1, "a1 b1"),
        _node(2, "w x y z"),
        _node(3, "a3 b3", heading=("Beta",)),
    )

    off = node_chunks([document], tokenizer=COUNTER)
    on = _units(document)

    assert [chunk.id for chunk in off] == [
        _one_node_id("doc", node) for node in document.nodes
    ]
    singles = [chunk for chunk in on if len(chunk.source_node_ids) == 1]
    assert singles == [off[2], off[3]]


def test_merging_leaves_the_ir_node_set_untouched(tmp_path: Path) -> None:
    source = run_source()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=COUNTER)
    before = ir.model_dump(mode="json")

    units = _units(ir)

    assert ir.model_dump(mode="json") == before
    covered = [node_id for unit in units for node_id in unit.source_node_ids]
    off = node_chunks([ir], tokenizer=COUNTER)
    # Every node candidate is in exactly one unit, in reading order.
    assert covered == [node_id for chunk in off for node_id in chunk.source_node_ids]


# The packets ``compile_context`` produced at 7a9726b with the default
# configuration, on these three fixtures, for eight query/budget pairs each.
# Computed by running the same loop against ``git archive 7a9726b src``; the
# ``compiler_config`` hash is excluded because adding config fields changes
# it for every configuration, as ``COMPILER_VERSION``'s comment records.
PRE_MERGING_PACKETS_SHA256 = (
    "ee05bcc6dfeb3a2f3694f86ff2bf10003fb131b8007eb2a61eb6f3baeedff9d8"
)


def test_merging_off_reproduces_the_pre_merging_packets(tmp_path: Path) -> None:
    config = CompilerConfig(
        retrieval=RetrievalConfig(candidate_limit=20, rerank_limit=10)
    )
    assert config.node_merge_policy is None
    cases = [
        (compiler_source, ("target revenue increased", "Beta market declined")),
        (run_source, ("entry4 value4", "entry0 value8")),
        (shredded_source, ("row 12 amount", "amount 301 row 43")),
    ]
    packets = []
    for builder, queries in cases:
        source = builder()
        ir = project_document(
            source, ingest_metadata(Path("/tmp/golden")), tokenizer=COUNTER
        )
        scope = DocumentScope.from_documents([ir], source_documents={ir.id: source})
        for query in queries:
            for budget in (12, 40, 120, 400):
                dump = compile_context(
                    query, scope, budget, config, tokenizer=COUNTER
                ).model_dump(mode="json")
                dump["metadata"].pop("compiler_config")
                packets.append(dump)
    payload = json.dumps(packets, sort_keys=True, separators=(",", ":"))

    assert hashlib.sha256(payload.encode()).hexdigest() == PRE_MERGING_PACKETS_SHA256


# --- expansion and deduplication ------------------------------------------


def _run_scope(tmp_path: Path, count: int = 9):
    source = run_source(count)
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=COUNTER)
    scope = DocumentScope.from_documents([ir], source_documents={ir.id: source})
    units = [
        unit
        for unit in _units(ir)
        if len(unit.source_node_ids) > 1
    ]
    return ir, scope, units


def _evidence(chunk: RetrievalChunk, rank: int, score: float) -> RankedEvidence:
    return RankedEvidence(
        rank=rank,
        chunk=chunk,
        scores=RetrievalScores(fused=score, reranked=score),
    )


def _expand(ir, scope, ranked, **updates):
    config = CompilerConfig(
        retrieval=RetrievalConfig(candidate_limit=20, rerank_limit=10),
        node_merge_enabled=True,
        node_merge_min_tokens=4,
        node_merge_target_tokens=6,
        node_merge_max_tokens=8,
        keyed_table_join_enabled=False,
        page_neighbor_radius=0,
        **updates,
    )
    return expand_candidates(
        "entry",
        ranked,
        scope.documents,
        source_documents=scope.source_documents,
        token_budget=400,
        config=config,
        tokenizer=COUNTER,
        reranker=LexicalOverlapReranker(),
    )


def _text_node_ids(ir: IRDocument) -> list[str]:
    return [node.id for node in ir.nodes if node.kind == IRNodeKind.PARAGRAPH]


def test_expansion_never_re_adds_a_node_inside_a_merged_unit(tmp_path: Path) -> None:
    ir, scope, units = _run_scope(tmp_path)
    paragraphs = _text_node_ids(ir)
    assert [unit.source_node_ids for unit in units] == [
        tuple(paragraphs[0:3]),
        tuple(paragraphs[3:6]),
        tuple(paragraphs[6:9]),
    ]
    middle = units[1]

    # A reach of three is the unit's length: without the outward-only rule the
    # first member would reach the last member's neighbour a second time.
    expanded = _expand(ir, scope, [_evidence(middle, 1, 1.0)], sibling_neighbor_limit=3)

    assert expanded[0].operator == "retrieval"
    assert expanded[0].chunk.source_node_ids == middle.source_node_ids
    assert expanded[0].chunk.text.endswith(middle.text)
    related = [candidate.chunk.source_node_ids[0] for candidate in expanded[1:]]
    assert sorted(related) == sorted(paragraphs[0:3] + paragraphs[6:9])
    assert len(related) == len(set(related))
    assert not set(related) & set(middle.source_node_ids)


def test_deduplication_never_emits_a_node_twice(tmp_path: Path) -> None:
    ir, scope, units = _run_scope(tmp_path)
    first, second, _third = units
    # The first unit's next sibling is the second unit's first member, and it
    # outranks the second unit, so it is kept before the unit containing it.
    expanded = _expand(
        ir,
        scope,
        [_evidence(first, 1, 1.0), _evidence(second, 2, 0.5)],
    )
    sibling = second.source_node_ids[0]
    order = [candidate.chunk.source_node_ids for candidate in expanded]
    assert order.index((sibling,)) < order.index(second.source_node_ids)

    unique = deduplicate_candidates(expanded, scope.documents)

    emitted = [
        node_id
        for candidate in unique
        for node_id in candidate.chunk.source_node_ids
    ]
    assert len(emitted) == len(set(emitted))
    assert sibling in emitted


def test_deduplication_is_unchanged_without_a_merged_unit(tmp_path: Path) -> None:
    """The node-overlap rule is gated on a merged unit being present."""
    ir, scope, _units_ = _run_scope(tmp_path)
    node = ir.node_by_id[_text_node_ids(ir)[0]]
    chunk = node_chunks([ir], tokenizer=COUNTER)[2]
    assert chunk.source_node_ids == (node.id,)
    shared = CompilerCandidate(
        chunk=chunk,
        scores=RetrievalScores(),
        origin_rank=1,
        expansion_order=0,
        allow_shared_source=True,
    )
    renamed = CompilerCandidate(
        chunk=chunk.model_copy(update={"id": "other", "text": "different text"}),
        scores=RetrievalScores(),
        origin_rank=2,
        expansion_order=1,
        allow_shared_source=True,
    )

    # Two candidates on one node, both allowed to share a source: kept as
    # before, because no merged unit is in the pool.
    assert deduplicate_candidates([shared, renamed], scope.documents) == (
        shared,
        renamed,
    )


# --- the token-mass floor under the count cap ------------------------------


def _pool(sizes: list[int]) -> list[CompilerCandidate]:
    return [
        CompilerCandidate(
            chunk=RetrievalChunk(
                id=f"c{index}",
                arm=RetrievalArm.COMPILER,
                document_id="doc",
                text="x",
                token_count=size,
                source_node_ids=(f"n{index}",),
                source_item_ids=(f"#/texts/{index}",),
            ),
            scores=RetrievalScores(),
            origin_rank=index + 1,
            expansion_order=0,
        )
        for index, size in enumerate(sizes)
    ]


def test_candidate_pool_cap_is_unchanged_without_a_mass_multiple() -> None:
    pool = _pool([1] * 10)

    assert cap_candidate_pool(
        pool, max_count=3, token_mass_multiple=None, token_budget=100, item_overhead=5
    ) == tuple(pool[:3])


def test_token_mass_floor_extends_the_count_cap_until_the_budget_is_covered() -> None:
    pool = _pool([2] * 20)

    # Rendered cost 2 + 3 = 5 per candidate; the floor 1.0 * 30 needs six.
    capped = cap_candidate_pool(
        pool, max_count=3, token_mass_multiple=1.0, token_budget=30, item_overhead=3
    )
    assert capped == tuple(pool[:6])
    # Framing is part of the mass: without it the floor would need fifteen.
    content_only = cap_candidate_pool(
        pool, max_count=3, token_mass_multiple=1.0, token_budget=30, item_overhead=0
    )
    assert content_only == tuple(pool[:15])
    # Never fewer than the count cap keeps, even once the floor is met.
    large = _pool([50] * 10)
    assert cap_candidate_pool(
        large, max_count=4, token_mass_multiple=1.0, token_budget=30, item_overhead=0
    ) == tuple(large[:4])


def test_a_shredded_pool_no_longer_runs_out_before_the_budget(
    tmp_path: Path,
) -> None:
    source = shredded_source()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=COUNTER)
    scope = DocumentScope.from_documents([ir], source_documents={ir.id: source})
    budget = 200
    base = CompilerConfig(
        retrieval=RetrievalConfig(candidate_limit=20, rerank_limit=10),
        # Scaled down with the fixture: 500 against tens of thousands of
        # four-word nodes is what the count cap does at corpus scale.
        max_expanded_candidates=8,
        page_neighbor_radius=0,
    )
    floored = base.model_copy(update={"expanded_candidate_token_mass_multiple": 1.0})
    overhead = evidence_item_overhead(
        COUNTER, base.budget_accounting, base.evidence_render_version
    )

    def pool_mass(config):
        packet, trace = compile_context_with_trace(
            "row amount", scope, budget, config, tokenizer=COUNTER
        )
        # Rendered cost, as the packer prices it.
        mass = sum(
            candidate.chunk.token_count + overhead
            for candidate in trace.deduplicated_candidates
        )
        return packet, trace, mass

    count_packet, count_trace, count_mass = pool_mass(base)
    mass_packet, mass_trace, mass_mass = pool_mass(floored)

    # The count cap empties the pool well short of the budget.
    assert len(count_trace.deduplicated_candidates) == 8
    assert count_mass < budget
    assert count_packet.token_count < budget // 2
    # The floor keeps candidates until their mass covers the budget, and the
    # packet spends it -- without ever exceeding it.
    assert len(mass_trace.deduplicated_candidates) > 8
    assert mass_mass >= budget
    assert mass_packet.token_count > count_packet.token_count
    assert mass_packet.token_count <= budget
    # The floor only extends the count cap's prefix.
    assert (
        mass_trace.deduplicated_candidates[:8] == count_trace.deduplicated_candidates
    )


def test_merged_compilation_packs_each_node_once_within_budget(
    tmp_path: Path,
) -> None:
    source = shredded_source()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=COUNTER)
    scope = DocumentScope.from_documents([ir], source_documents={ir.id: source})
    config = CompilerConfig(
        retrieval=RetrievalConfig(candidate_limit=20, rerank_limit=10),
        node_merge_enabled=True,
        node_merge_min_tokens=8,
        node_merge_target_tokens=16,
        node_merge_max_tokens=24,
    )

    for budget in (40, 120, 400):
        packet = compile_context(
            "row 12 amount", scope, budget, config, tokenizer=COUNTER
        )
        nodes = [
            node_id for item in packet.items for node_id in item.source_node_ids
        ]
        assert len(nodes) == len(set(nodes))
        assert packet.token_count <= budget
        assert any(len(item.source_node_ids) > 1 for item in packet.items)


# --- configuration ---------------------------------------------------------


def _merge_corpus(tmp_path: Path):
    source = run_source()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=COUNTER)
    return ir, {ir.id: source}


def test_the_benchmark_runner_builds_the_compiler_index_from_merged_units(
    tmp_path: Path,
) -> None:
    from contextbench.evaluation import BenchmarkSystem, RetrievalBenchmarkConfig
    from contextbench.evaluation import runner as benchmark_runner
    from contextbench.retrieval import HashEmbeddingModel

    ir, sources = _merge_corpus(tmp_path)
    retrieval = RetrievalConfig(candidate_limit=20, rerank_limit=10)

    def compiler_chunks(compiler: CompilerConfig):
        config = RetrievalBenchmarkConfig(
            systems=(BenchmarkSystem.FIXED, BenchmarkSystem.COMPILER),
            retrieval=retrieval,
            compiler=compiler,
        )
        indexes = benchmark_runner._build_indexes(
            [ir],
            sources_by_ir_id=sources,
            systems=config.systems,
            config=config,
            artifacts_root=tmp_path / "artifacts",
            tokenizer=COUNTER,
            embedder=HashEmbeddingModel(),
            reranker=LexicalOverlapReranker(),
        )
        return indexes

    off = compiler_chunks(CompilerConfig(retrieval=retrieval))
    on = compiler_chunks(
        CompilerConfig(
            retrieval=retrieval,
            node_merge_enabled=True,
            node_merge_min_tokens=4,
            node_merge_target_tokens=6,
            node_merge_max_tokens=8,
        )
    )

    assert on[BenchmarkSystem.COMPILER].chunks == _units(ir)
    assert off[BenchmarkSystem.COMPILER].chunks == node_chunks(
        [ir], tokenizer=COUNTER, config=retrieval
    )
    # The other arms read none of it.
    assert on[BenchmarkSystem.FIXED].chunks == off[BenchmarkSystem.FIXED].chunks


def test_the_factorial_merges_only_the_ir_content_unit(tmp_path: Path) -> None:
    from contextbench.evaluation import ContentUnit, SelectionPolicy
    from contextbench.evaluation import factorial as factorial_runner
    from contextbench.retrieval import HashEmbeddingModel

    ir, sources = _merge_corpus(tmp_path)

    def indexes(**updates):
        return factorial_runner._build_factorial_indexes(
            [ir],
            sources_by_ir_id=sources,
            config=FactorialConfig(**updates),
            artifacts_root=tmp_path / "factorial-artifacts",
            tokenizer=COUNTER,
            embedder=HashEmbeddingModel(),
            reranker=LexicalOverlapReranker(),
        )

    off = indexes()
    on = indexes(
        node_merge_enabled=True,
        node_merge_min_tokens=4,
        node_merge_target_tokens=6,
        node_merge_max_tokens=8,
    )

    for unit in ContentUnit:
        key = (unit, SelectionPolicy.RANKED, True)
        if unit == ContentUnit.IR:
            assert on[key].chunks == _units(ir)
            assert on[key].chunks != off[key].chunks
        else:
            assert on[key].chunks == off[key].chunks


def test_merging_is_off_by_default_and_bounds_must_be_ordered() -> None:
    assert CompilerConfig().node_merge_policy is None
    assert FactorialConfig().node_merge_policy is None
    assert CompilerConfig().expanded_candidate_token_mass_multiple is None
    assert CompilerConfig(node_merge_enabled=True).node_merge_policy == NodeMergePolicy(
        min_tokens=64, target_tokens=128, max_tokens=256, max_page_span=1
    )
    with pytest.raises(ValueError, match="min <= target <= max"):
        CompilerConfig(node_merge_target_tokens=300)
    with pytest.raises(ValueError, match="min <= target <= max"):
        FactorialConfig(node_merge_min_tokens=200)


def test_merged_units_change_the_compiler_index_key(tmp_path: Path) -> None:
    from contextbench.retrieval.index import _index_key

    source = run_source()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=COUNTER)
    retrieval = RetrievalConfig()

    def key(chunks):
        return _index_key(
            [ir],
            arm=RetrievalArm.COMPILER,
            config=retrieval,
            chunks=chunks,
            embedding_model="e",
            embedding_version="1",
            embedding_revision=None,
            reranker_model="r",
            reranker_version="1",
            reranker_revision=None,
            tokenizer=COUNTER.name,
            tokenizer_version=COUNTER.version,
        )

    off = node_chunks([ir], tokenizer=COUNTER, config=retrieval)
    on = node_chunks([ir], tokenizer=COUNTER, config=retrieval, merge=POLICY)
    # Enabled but with nothing small enough to merge: same chunks, same key,
    # which is correct -- the index really is reusable.
    inert = node_chunks(
        [ir],
        tokenizer=COUNTER,
        config=retrieval,
        merge=NodeMergePolicy(
            min_tokens=1, target_tokens=1, max_tokens=1, max_page_span=1
        ),
    )

    assert on != off
    assert key(on) != key(off)
    assert inert == off
    assert key(inert) == key(off)
