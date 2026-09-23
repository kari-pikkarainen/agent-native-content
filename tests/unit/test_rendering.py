"""Rendered-evidence budget accounting across every packer.

The answer prompt carries evidence as ``<evidence id="...">`` blocks, and the
budget now counts that rendered block rather than content alone. These tests
pin three things: the prompt a model sees is byte-for-byte what it was, every
arm stays inside the budget as rendered, and content accounting still
reproduces the old packets so the change can be measured.
"""

import hashlib
from pathlib import Path

import pytest
from test_compiler import compiler_config, compiler_source
from test_ir import FixtureTokenCounter, ingest_metadata

from contextbench.compiler import DocumentScope, compile_context
from contextbench.compiler.models import CompilerCandidate
from contextbench.compiler.pack import _coverage_selection, pack_candidates
from contextbench.generation.runner import render_answer_prompt
from contextbench.generation.runner import (
    render_grounded_prompt as _render_grounded_prompt,
)
from contextbench.ir import project_document
from contextbench.retrieval import (
    HybridIndex,
    RetrievalArm,
    RetrievalChunk,
    RetrievalConfig,
    RetrievalScores,
    long_context_chunks,
    pack_evidence,
    rank_long_context,
)
from contextbench.retrieval.chunking import fixed_chunks, structural_chunks
from contextbench.retrieval.models import (
    ContextItem,
    ContextPacket,
    RankedEvidence,
)
from contextbench.retrieval.rendering import (
    EVIDENCE_JOINER,
    EVIDENCE_RENDER_V1,
    EVIDENCE_RENDER_V2,
    evidence_label,
    render_evidence_block,
    render_evidence_item,
)


class CharacterCounter:
    """Counts characters, so the joiner and every tag character cost tokens.

    The word-count fixture tokenizer and ``o200k_base`` both make the joiner
    free, which would hide an accounting error of exactly one joiner. This one
    does not.
    """

    name = "fixture-characters"
    version = "1"

    def count(self, text: str) -> int:
        return len(text)


def _previous_render_answer_prompt(question: str, context: ContextPacket) -> str:
    """The inline rendering ``render_answer_prompt`` used before, verbatim."""
    evidence = "\n\n".join(
        f'<evidence id="{item.evidence_id}">\n{item.content}\n</evidence>'
        for item in context.items
    )
    return _render_grounded_prompt(question, evidence)


def _item(evidence_id: str, content: str) -> ContextItem:
    return ContextItem(
        evidence_id=evidence_id,
        document_id="doc",
        content=content,
        token_count=len(content.split()),
        source_node_ids=("node",),
        source_item_ids=("#/texts/0",),
        scores=RetrievalScores(),
    )


@pytest.mark.parametrize(
    "contents",
    [
        (),
        ("single line",),
        ("first\nsecond line", "  leading and trailing  ", "tabs\tand\ttabs"),
        ("unicode — dash, “quotes”, café",),
        ("an embedded </evidence> tag", '<evidence id="spoof">'),
        ("",),
    ],
)
def test_render_answer_prompt_is_byte_identical_to_the_previous_rendering(
    contents: tuple[str, ...],
) -> None:
    """The published Gate 2 prompts must stay reproducible from their packets."""
    packet = ContextPacket(
        query="q",
        token_budget=10_000,
        token_count=sum(len(content.split()) for content in contents),
        items=tuple(
            _item(f"evidence_{index:064x}", content)
            for index, content in enumerate(contents)
        ),
        metadata={},
    )
    question = "What is the “question”?\nSecond line."

    assert render_answer_prompt(question, packet) == _previous_render_answer_prompt(
        question, packet
    )


def _chunk(index: int, text: str) -> RetrievalChunk:
    return RetrievalChunk(
        id=f"chunk-{index:03d}",
        arm=RetrievalArm.FIXED,
        document_id="doc",
        text=text,
        token_count=len(text.split()),
        page_start=1,
        page_end=1,
        source_node_ids=(f"node-{index}",),
        source_item_ids=(f"#/texts/{index}",),
    )


def _ranked(texts: list[str]) -> tuple[RankedEvidence, ...]:
    return tuple(
        RankedEvidence(rank=rank, chunk=_chunk(rank, text), scores=RetrievalScores())
        for rank, text in enumerate(texts, 1)
    )


def _block_tokens(packet: ContextPacket, tokenizer) -> int:
    """Re-render a packet from scratch, in the version it says it was priced."""
    return tokenizer.count(
        render_evidence_block(
            ((item.evidence_id, item.content) for item in packet.items),
            version=packet.evidence_render_version or EVIDENCE_RENDER_V1,
        )
    )


def test_many_small_items_that_fit_by_content_are_cut_by_rendering() -> None:
    """The shredded-context case: framing, not content, is what overflows.

    Twenty two-word fragments are exactly 40 content tokens, so a 40-token
    budget takes all of them when only content is counted. Each fragment also
    carries three words of framing, so under rendered accounting the same
    budget holds only eight.
    """
    counter = FixtureTokenCounter()
    ranked = _ranked([f"fragment {index}" for index in range(20)])

    content = pack_evidence(
        "q", ranked, token_budget=40, tokenizer=counter, metadata={},
        budget_accounting="content",
    )
    rendered = pack_evidence(
        "q", ranked, token_budget=40, tokenizer=counter, metadata={},
        budget_accounting="rendered_evidence",
    )

    assert len(content.items) == 20
    assert content.token_count == 40
    # The content-accounted packet's own prompt would have been 100 tokens.
    assert content.rendered_token_count == 100
    assert len(rendered.items) == 8
    assert rendered.rendered_token_count == _block_tokens(rendered, counter) == 40
    assert rendered.budget_accounting == "rendered_evidence"


@pytest.mark.parametrize("counter", [FixtureTokenCounter(), CharacterCounter()])
def test_the_last_item_that_exactly_fits_is_packed(counter) -> None:
    """A budget equal to the finished block's cost must take every item.

    With the character counter the joiner costs two tokens, so an accountant
    that charged the joiner to the last item would refuse the final fragment
    here and silently leave budget it could have used.
    """
    ranked = _ranked(["alpha beta", "gamma", "delta epsilon zeta"])
    expected = pack_evidence(
        "q", ranked, token_budget=10_000, tokenizer=counter, metadata={}
    )
    exact = _block_tokens(expected, counter)

    packet = pack_evidence(
        "q", ranked, token_budget=exact, tokenizer=counter, metadata={}
    )

    assert len(packet.items) == 3
    assert packet.rendered_token_count == exact
    one_short = pack_evidence(
        "q", ranked, token_budget=exact - 1, tokenizer=counter, metadata={}
    )
    assert len(one_short.items) == 2


@pytest.mark.parametrize("counter", [FixtureTokenCounter(), CharacterCounter()])
def test_a_skipped_item_does_not_stop_a_smaller_later_one(counter) -> None:
    """Skip-and-continue survives the change: no early break, no stall."""
    long_text = " ".join(f"word{index}" for index in range(60))
    ranked = _ranked(["short one", long_text, "short two"])
    small = _block_tokens(
        pack_evidence("q", ranked[:1], token_budget=10_000, tokenizer=counter,
                      metadata={}),
        counter,
    )
    pair = pack_evidence(
        "q", (ranked[0], ranked[2]), token_budget=10_000, tokenizer=counter,
        metadata={},
    )

    packet = pack_evidence(
        "q", ranked, token_budget=_block_tokens(pair, counter), tokenizer=counter,
        metadata={},
    )

    assert small < _block_tokens(pair, counter)
    assert [item.content for item in packet.items] == ["short one", "short two"]


def _previous_pack_evidence(query, ranked, *, token_budget, tokenizer, metadata):
    """The content-only ``pack_evidence`` loop, verbatim, as a control."""
    items, used, total = [], set(), 0
    for evidence in ranked:
        chunk = evidence.chunk
        key = (chunk.document_id, *chunk.source_item_ids)
        if key in used:
            continue
        count = tokenizer.count(chunk.text)
        if total + count > token_budget:
            continue
        used.add(key)
        items.append(
            ContextItem(
                evidence_id="evidence_"
                + hashlib.sha256(chunk.id.encode()).hexdigest(),
                document_id=chunk.document_id,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                heading_path=chunk.heading_path,
                content=chunk.text,
                token_count=count,
                source_node_ids=chunk.source_node_ids,
                source_item_ids=chunk.source_item_ids,
                scores=evidence.scores,
            )
        )
        total += count
    return ContextPacket(
        query=query,
        token_budget=token_budget,
        token_count=total,
        items=tuple(items),
        metadata=metadata,
    )


def _without_new_fields(packet: ContextPacket) -> dict:
    return packet.model_dump(
        mode="json",
        exclude={
            "rendered_token_count",
            "budget_accounting",
            "evidence_render_version",
        },
    )


@pytest.mark.parametrize("budget", range(0, 45, 3))
def test_content_accounting_reproduces_the_previous_packets(budget: int) -> None:
    """Every field the old packer wrote is unchanged under content accounting."""
    counter = FixtureTokenCounter()
    ranked = _ranked(
        [f"fragment {index} " + "word " * (index % 5) for index in range(20)]
    )

    previous = _previous_pack_evidence(
        "q", ranked, token_budget=budget, tokenizer=counter, metadata={"arm": "x"}
    )
    current = pack_evidence(
        "q", ranked, token_budget=budget, tokenizer=counter, metadata={"arm": "x"},
        budget_accounting="content",
    )

    assert _without_new_fields(current) == _without_new_fields(previous)
    assert current.budget_accounting == "content"


def _arm_rankings(tmp_path: Path):
    """Real fixed, structural, long-context and compiler inputs, one fixture."""
    source = compiler_source()
    counter = FixtureTokenCounter()
    ir = project_document(source, ingest_metadata(tmp_path), tokenizer=counter)
    config = RetrievalConfig(
        fixed_chunk_tokens=12,
        fixed_overlap_tokens=3,
        structural_chunk_tokens=24,
        candidate_limit=20,
        rerank_limit=10,
    )
    query = "target revenue increased across alpha and beta markets"
    rankings = {}
    for arm, chunks in (
        ("fixed", fixed_chunks(ir, config=config, tokenizer=counter)),
        (
            "structural",
            structural_chunks(ir, source, config=config, tokenizer=counter),
        ),
    ):
        index = HybridIndex(chunks, config=config, tokenizer=counter)
        rankings[arm] = index.retrieve(query, token_budget=200)
    rankings["long_context"] = rank_long_context(
        long_context_chunks([ir], tokenizer=counter), document_ids={ir.id}
    )
    scope = DocumentScope.from_documents([ir], source_documents={ir.id: source})
    return rankings, scope, counter, query


@pytest.mark.parametrize("budget", [0, 1, 5, 9, 13, 17, 25, 33, 50, 80, 120])
def test_every_arm_stays_within_the_rendered_budget(
    tmp_path: Path, budget: int
) -> None:
    """Fixed, structural, long-context and compiler, over one budget sweep.

    The recorded rendered count is checked against a fresh rendering of the
    packet, not against the packer's own arithmetic, so this cannot pass by
    the accountant agreeing with itself.
    """
    rankings, scope, counter, query = _arm_rankings(tmp_path)
    packets = {
        arm: pack_evidence(
            query, ranked, token_budget=budget, tokenizer=counter, metadata={}
        )
        for arm, ranked in rankings.items()
    }
    packets["compiler"] = compile_context(
        query, scope, budget, compiler_config(), tokenizer=counter
    )

    for arm, packet in packets.items():
        assert packet.budget_accounting == "rendered_evidence", arm
        assert packet.rendered_token_count == _block_tokens(packet, counter), arm
        assert packet.rendered_token_count <= budget, arm
        assert packet.token_count <= packet.rendered_token_count, arm


def test_the_compiler_coverage_selector_is_charged_the_rendered_cost() -> None:
    """Coverage must not choose a set the emission loop then has to cut.

    Three single-word candidates: under content accounting a 3-token budget
    takes all three, under rendered accounting a single item already costs
    four words, so a 4-token budget takes exactly one.
    """
    counter = FixtureTokenCounter()

    def candidate(index: int) -> CompilerCandidate:
        return CompilerCandidate(
            chunk=RetrievalChunk(
                id=f"chunk-{index}",
                arm=RetrievalArm.COMPILER,
                document_id="doc",
                text=f"word{index}",
                token_count=1,
                page_start=index,
                page_end=index,
                source_node_ids=(f"node-{index}",),
                source_item_ids=(f"#/texts/{index}",),
            ),
            scores=RetrievalScores(reranked=1.0 / index),
            origin_rank=index,
            expansion_order=index,
        )

    candidates = [candidate(index) for index in range(1, 4)]
    for strategy in ("coverage", "ranked", "adaptive"):
        content = pack_candidates(
            "word1 word2 word3", candidates, token_budget=3, tokenizer=counter,
            strategy=strategy, metadata={}, budget_accounting="content",
        )
        rendered = pack_candidates(
            "word1 word2 word3", candidates, token_budget=4, tokenizer=counter,
            strategy=strategy, metadata={},
        )
        assert len(content.items) == 3, strategy
        assert len(rendered.items) == 1, strategy
        assert rendered.rendered_token_count == 4, strategy

    # The packet alone cannot show this: if the selector were charged content
    # it would choose all three and the emission loop would cut back to the
    # same one. The selection itself has to be priced correctly.
    selected, _leftover = _coverage_selection(
        "word1 word2 word3", candidates, token_budget=4, tokenizer=counter
    )
    assert len(selected) == 1


@pytest.mark.parametrize("version", [EVIDENCE_RENDER_V1, EVIDENCE_RENDER_V2])
def test_one_item_costs_its_rendering_and_the_joiner_between_items(
    version,
) -> None:
    """The accounting is defined by the renderer, not by a constant."""
    counter = CharacterCounter()
    ranked = _ranked(["one", "two"])

    packet = pack_evidence(
        "q", ranked, token_budget=10_000, tokenizer=counter, metadata={},
        evidence_render_version=version,
    )

    assert packet.evidence_render_version == version
    assert packet.rendered_token_count == _block_tokens(packet, counter)
    # Two items cost both renderings plus exactly one joiner.
    labels = [
        evidence_label(item.evidence_id, index, version)
        for index, item in enumerate(packet.items)
    ]
    assert packet.rendered_token_count == (
        len(render_evidence_item(labels[0], "one"))
        + len(EVIDENCE_JOINER)
        + len(render_evidence_item(labels[1], "two"))
    )


def test_v2_renders_positional_aliases_in_packet_order() -> None:
    block = render_evidence_block(
        [("evidence_aaa", "first"), ("evidence_bbb", "second")],
        version=EVIDENCE_RENDER_V2,
    )

    assert block == (
        '<evidence id="E1">\nfirst\n</evidence>\n\n'
        '<evidence id="E2">\nsecond\n</evidence>'
    )
    assert "evidence_aaa" not in block


def test_v2_budget_charges_the_aliased_cost_not_the_full_id() -> None:
    """The saving is real to the packer: more items fit the same budget."""
    counter = CharacterCounter()
    ranked = _ranked([f"fragment {index}" for index in range(12)])
    budget = 400

    v1 = pack_evidence(
        "q", ranked, token_budget=budget, tokenizer=counter, metadata={},
        evidence_render_version=EVIDENCE_RENDER_V1,
    )
    v2 = pack_evidence(
        "q", ranked, token_budget=budget, tokenizer=counter, metadata={},
        evidence_render_version=EVIDENCE_RENDER_V2,
    )

    assert v2.evidence_render_version == EVIDENCE_RENDER_V2
    assert v2.rendered_token_count == _block_tokens(v2, counter) <= budget
    assert v1.rendered_token_count == _block_tokens(v1, counter) <= budget
    assert len(v2.items) > len(v1.items)


@pytest.mark.parametrize("strategy", ["pack_evidence", "coverage", "ranked"])
def test_the_tenth_slot_is_priced_at_what_e10_actually_costs(strategy) -> None:
    """``E10`` is one character longer than ``E9``, and the budget must know.

    Ten items fit a budget equal to their finished block exactly; one token
    less, only nine do. A packer that priced every slot like ``E1`` would
    think the tenth still fits at one token less and would be refused by the
    finished-block check instead of simply leaving it out.
    """
    counter = CharacterCounter()
    texts = [f"t{index}" for index in range(10)]

    def pack(budget: int) -> ContextPacket:
        if strategy == "pack_evidence":
            return pack_evidence(
                "q", _ranked(texts), token_budget=budget, tokenizer=counter,
                metadata={}, evidence_render_version=EVIDENCE_RENDER_V2,
            )
        candidates = [
            CompilerCandidate(
                chunk=_chunk(index, text).model_copy(
                    update={"arm": RetrievalArm.COMPILER}
                ),
                scores=RetrievalScores(reranked=1.0 / (index + 1)),
                origin_rank=index + 1,
                expansion_order=index,
            )
            for index, text in enumerate(texts)
        ]
        return pack_candidates(
            "q", candidates, token_budget=budget, tokenizer=counter,
            strategy=strategy, metadata={},
            evidence_render_version=EVIDENCE_RENDER_V2,
        )

    full = pack(10_000)
    exact = _block_tokens(full, counter)
    assert len(full.items) == 10

    assert len(pack(exact).items) == 10
    assert pack(exact).rendered_token_count == exact
    assert len(pack(exact - 1).items) == 9

    if strategy == "coverage":
        # The packet alone cannot show the selector's pricing: a selector that
        # priced every slot as ``E1`` would choose ten and the correctly
        # priced emission loop would cut back to nine. Check the selection.
        candidates = [
            CompilerCandidate(
                chunk=_chunk(index, text).model_copy(
                    update={"arm": RetrievalArm.COMPILER}
                ),
                scores=RetrievalScores(reranked=1.0 / (index + 1)),
                origin_rank=index + 1,
                expansion_order=index,
            )
            for index, text in enumerate(texts)
        ]
        selected, _leftover = _coverage_selection(
            "q", candidates, token_budget=exact - 1, tokenizer=counter,
            evidence_render_version=EVIDENCE_RENDER_V2,
        )
        assert len(selected) == 9
