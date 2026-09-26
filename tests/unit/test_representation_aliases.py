"""Evidence aliases and short references in the representation experiment.

A 12B local model could not copy ``evidence_`` + 64-hex IDs, and looped on
the 64-hex ``node_`` IDs of the structured conditions, so citation metrics
measured ID copying and the structured conditions paid for hex the raw
condition never saw. Under ``evidence-render-v3`` (the default) evidence items
are shown as ``E1``, ``E2``, ..., IR nodes as ``N1``, ``N2``, ... and indexed
features as ``F1``, ``F2``, ...; aliases and node references are assigned once
per question in gold-evidence order and are the same in every condition.
Cited aliases are mapped back to full IDs before scoring. v1 and v2 stay
selectable and render exactly as before. Every provider here is an in-memory
fake; nothing touches the network.
"""

import hashlib
import html
import json
import re
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest
from test_evaluation import _corpus
from test_ir import FixtureTokenCounter
from test_representation import (
    CITATION_JUDGE,
    EVIDENCE_CONDITIONS,
    JudgedRepresentationProvider,
    _config,
    _invoke_eval_representation,
    _run_judged,
)

from contextbench.agentdoc import (
    AgentFeatureKind,
    enrich_document,
    feature_type_counts,
    features_for_nodes,
    select_agent_features,
)
from contextbench.generation.runner import (
    ANSWER_PROMPT_INSTRUCTIONS,
    ANSWER_PROMPT_INSTRUCTIONS_ALIASED,
)
from contextbench.representation import (
    RepresentationCondition,
    RepresentationError,
    render_representation,
)
from contextbench.representation.runner import (
    QuestionLabels,
    _gold_evidence_nodes,
    map_citations,
    question_labels,
)

FULL_ID = re.compile(r"evidence_[0-9a-f]{64}")
# Any identifier-like hex run; a v3 prompt must contain none.
LONG_HEX = re.compile(r"[0-9a-fA-F]{12,}")
EVIDENCE_TAG = re.compile(
    r'<evidence id="([^"]+)"[^>]*>\n(?:Heading: [^\n]*\n)?(.*?)\n</evidence>',
    re.DOTALL,
)
EVIDENCE_AND_NODE = re.compile(r'<evidence id="([^"]+)"[^>]*source_node="([^"]+)"')
V1 = "evidence-render-v1"
V2 = "evidence-render-v2"
V3 = "evidence-render-v3"
STRUCTURED = (
    RepresentationCondition.IR,
    RepresentationCondition.ENRICHED,
    RepresentationCondition.INDEXED,
)


class CitingProvider(JudgedRepresentationProvider):
    """Answers every evidence-bearing cell with a fixed citation list.

    ``cite`` receives the answer request and returns what the model cites, so
    a test can cite aliases, full IDs, or labels no prompt showed.
    """

    def __init__(self, cite) -> None:
        super().__init__()
        self.cite = cite

    def generate(self, request, *, config):
        response = super().generate(request, config=config)
        if ":" in request.system or not request.evidence_ids:
            return response
        return response.model_copy(
            update={
                "text": json.dumps(
                    {"answer": "turnover", "citations": self.cite(request)}
                )
            }
        )


def _contexts(run_path: Path) -> dict[str, dict]:
    return {
        row["condition"]: row
        for row in (
            json.loads(line)
            for line in (run_path / "contexts.jsonl").read_text().splitlines()
        )
    }


def _answer_requests(provider) -> dict[str, object]:
    return {
        request.system: request
        for request in provider.requests
        if ":" not in request.system
    }


def _judge_prompts(provider) -> dict[str, str]:
    return {
        request.system.removesuffix(CITATION_JUDGE): request.prompt
        for request in provider.requests
        if request.system.endswith(CITATION_JUDGE)
    }


def _labelled_text(prompt: str) -> dict[str, str]:
    """Label -> the source text rendered under it, in prompt order."""
    return dict(EVIDENCE_TAG.findall(prompt))


# --- frozen pre-change renderer ------------------------------------------
#
# A verbatim copy of ``render_representation``, ``_raw_block`` and
# ``_ir_block`` as of 49b218d, before any labelling scheme existed, with one
# addition: ``label`` names an evidence item. The identity reproduces 49b218d
# exactly (v1); an alias lookup is what v2 is specified to change, and nothing
# else. Do not edit it to make a test pass: a difference is a regression.


def _frozen_render(
    condition,
    evidence_nodes,
    *,
    query,
    enrichments,
    inline_feature_kinds,
    max_inline_features,
    indexed_max_features,
    indexed_feature_token_budget,
    tokenizer,
    label: Callable[[str], str] = lambda evidence_id: evidence_id,
):
    if condition == RepresentationCondition.QUESTION_ONLY:
        if evidence_nodes:
            raise RepresentationError("question-only condition received evidence")
        return "", 0
    if condition == RepresentationCondition.RAW:
        return "\n\n".join(_frozen_raw(item, label) for item in evidence_nodes), 0
    source = "\n\n".join(_frozen_ir(item, label) for item in evidence_nodes)
    if condition == RepresentationCondition.IR:
        return source, 0
    ids_by_node = {item.node.id: label(item.evidence_id) for item in evidence_nodes}
    nodes_by_document: dict[str, set[str]] = defaultdict(set)
    for item in evidence_nodes:
        nodes_by_document[item.node.document_id].add(item.node.id)
    if condition == RepresentationCondition.INDEXED:
        selected = select_agent_features(
            query,
            enrichments,
            nodes_by_document,
            tokenizer=tokenizer,
            kinds=inline_feature_kinds | {AgentFeatureKind.TABLE_ROW},
            max_features=indexed_max_features,
            token_budget=indexed_feature_token_budget,
        )
        counts = feature_type_counts(
            enrichments,
            nodes_by_document,
            kinds=inline_feature_kinds | {AgentFeatureKind.TABLE_ROW},
        )
        count_value = ",".join(f"{kind}:{count}" for kind, count in counts.items())
        blocks = []
        for item in selected:
            feature = item.feature
            source_ids = [ids_by_node[node_id] for node_id in feature.source_node_ids]
            blocks.append(
                f'<feature ref="{feature.id[-12:]}" type="{feature.kind.value}" '
                f'src="{",".join(source_ids)}">'
                f"{html.escape(item.feature.text)}</feature>"
            )
        rendered_index = "\n".join(blocks)
        return (
            f'<agent_map available="{html.escape(count_value)}" '
            f'selected="{len(selected)}">\n{rendered_index}\n</agent_map>\n\n'
            f"<source_evidence>\n{source}\n</source_evidence>",
            len(selected),
        )
    selected_features = []
    for document_id, node_ids in nodes_by_document.items():
        selected_features.extend(
            feature
            for feature in features_for_nodes(enrichments[document_id], node_ids)
            if feature.kind in inline_feature_kinds
        )
    selected_features.sort(
        key=lambda feature: (
            -feature.importance,
            feature.page_start or 0,
            feature.id,
        )
    )
    selected_features = selected_features[:max_inline_features]
    feature_blocks = []
    for feature in selected_features:
        source_ids = [ids_by_node[node_id] for node_id in feature.source_node_ids]
        feature_blocks.append(
            f'<agent_feature type="{feature.kind.value}" '
            f'importance="{feature.importance:.2f}" '
            f'confidence="{feature.confidence:.2f}" '
            f'source_evidence_ids="{",".join(source_ids)}">\n'
            f"{html.escape(feature.text)}\n</agent_feature>"
        )
    rendered_features = "\n\n".join(feature_blocks)
    return (
        f"<agent_features>\n{rendered_features}\n</agent_features>\n\n"
        f"<source_evidence>\n{source}\n</source_evidence>",
        len(selected_features),
    )


def _frozen_raw(item, label) -> str:
    return (
        f'<evidence id="{label(item.evidence_id)}">\n'
        f"{html.escape(item.node.text)}\n</evidence>"
    )


def _frozen_ir(item, label) -> str:
    node = item.node
    heading = " > ".join(node.heading_path)
    return (
        f'<evidence id="{label(item.evidence_id)}" '
        f'document="{html.escape(item.dataset_document_id)}" '
        f'kind="{node.kind.value}" pages="{node.page_start}-{node.page_end}" '
        f'source_node="{node.id}">\n'
        f"Heading: {html.escape(heading or '[root]')}\n"
        f"{html.escape(node.text)}\n</evidence>"
    )


def _render_inputs(tmp_path: Path):
    corpus = _corpus(tmp_path)
    question = corpus.questions[0]
    config = _config()
    nodes = _gold_evidence_nodes(question, corpus)
    enrichments = {
        document.id: enrich_document(document, config=config.enrichment)
        for document in corpus.documents.values()
    }
    kwargs = {
        "query": question.question,
        "enrichments": enrichments,
        "inline_feature_kinds": set(config.inline_feature_kinds),
        "max_inline_features": config.max_inline_features,
        "indexed_max_features": config.indexed_max_features,
        "indexed_feature_token_budget": config.indexed_feature_token_budget,
        "tokenizer": FixtureTokenCounter(),
    }
    return nodes, kwargs


@pytest.mark.parametrize("condition", EVIDENCE_CONDITIONS)
def test_v1_renders_byte_identically_to_the_pre_change_renderer(
    tmp_path: Path, condition: RepresentationCondition
) -> None:
    nodes, kwargs = _render_inputs(tmp_path)
    assert len(nodes) >= 2

    rendered = render_representation(
        condition, nodes, labels=question_labels(nodes, V1), **kwargs
    )

    assert rendered == _frozen_render(condition, nodes, **kwargs)


@pytest.mark.parametrize("condition", EVIDENCE_CONDITIONS)
def test_v2_changes_only_the_evidence_label(
    tmp_path: Path, condition: RepresentationCondition
) -> None:
    nodes, kwargs = _render_inputs(tmp_path)
    aliases = {item.evidence_id: f"E{i + 1}" for i, item in enumerate(nodes)}

    rendered = render_representation(
        condition, nodes, labels=question_labels(nodes, V2), **kwargs
    )

    assert rendered == _frozen_render(
        condition, nodes, label=aliases.__getitem__, **kwargs
    )


# --- label guards ----------------------------------------------------------


def _drop_first(mapping: Mapping[str, str]) -> dict[str, str]:
    return dict(list(mapping.items())[1:])


def _all_same(mapping: Mapping[str, str]) -> dict[str, str]:
    return dict.fromkeys(mapping, "X1")


@pytest.mark.parametrize(
    ("field", "change", "message"),
    [
        ("evidence", _drop_first, "evidence items have no label"),
        ("evidence", _all_same, "evidence labels must be unique"),
        ("nodes", _drop_first, "node items have no label"),
        ("nodes", _all_same, "node labels must be unique"),
    ],
)
@pytest.mark.parametrize("condition", EVIDENCE_CONDITIONS)
def test_missing_or_duplicate_labels_are_refused(
    tmp_path: Path,
    condition: RepresentationCondition,
    field: str,
    change: Callable[[Mapping[str, str]], dict[str, str]],
    message: str,
) -> None:
    nodes, kwargs = _render_inputs(tmp_path)
    base = question_labels(nodes, V3)
    labels = QuestionLabels(
        version=V3,
        evidence=change(base.evidence) if field == "evidence" else base.evidence,
        nodes=change(base.nodes) if field == "nodes" else base.nodes,
    )

    with pytest.raises(RepresentationError, match=message):
        render_representation(condition, nodes, labels=labels, **kwargs)


# --- runs -----------------------------------------------------------------


def test_every_evidence_condition_shows_the_same_alias_for_the_same_item(
    tmp_path: Path,
) -> None:
    provider = JudgedRepresentationProvider()
    result = _run_judged(tmp_path, provider, "aliases-consistent")

    contexts = _contexts(result.path)
    evidence_ids = contexts["raw"]["evidence_ids"]
    assert len(evidence_ids) >= 2, "the fixture must show more than one item"
    expected = {f"E{index + 1}": value for index, value in enumerate(evidence_ids)}
    # Assigned in gold-evidence order, once per question.
    for condition in EVIDENCE_CONDITIONS:
        assert contexts[condition.value]["evidence_ids"] == evidence_ids
        assert contexts[condition.value]["evidence_labels"] == expected
    assert contexts["question_only"]["evidence_labels"] == {}
    assert contexts["question_only"]["node_labels"] == {}
    assert contexts["question_only"]["representation"] == ""

    requests = _answer_requests(provider)
    shown = {
        condition.value: _labelled_text(requests[condition.value].prompt)
        for condition in EVIDENCE_CONDITIONS
    }
    for condition, labelled in shown.items():
        # Every item, in order, under its alias ...
        assert list(labelled) == list(expected), condition
    # ... and each alias names the same source text in every condition.
    for label in expected:
        assert len({shown[c][label] for c in shown}) == 1, label

    # Feature source references use the same aliases.
    enriched = requests["enriched"].prompt
    indexed = requests["indexed"].prompt
    feature_refs = re.findall(r'source_evidence_ids="([^"]*)"', enriched)
    index_refs = re.findall(r' src="([^"]*)"', indexed)
    assert feature_refs and index_refs
    for refs in (*feature_refs, *index_refs):
        assert set(refs.split(",")) <= set(expected), refs


def test_structured_conditions_share_short_node_refs(tmp_path: Path) -> None:
    provider = JudgedRepresentationProvider()
    result = _run_judged(tmp_path, provider, "node-refs-consistent")

    contexts = _contexts(result.path)
    corpus = _corpus(tmp_path / "check")
    question = corpus.questions[0]
    gold_nodes = _gold_evidence_nodes(question, corpus)
    expected = {f"N{i + 1}": item.node.id for i, item in enumerate(gold_nodes)}
    assert all(node_id.startswith("node_") for node_id in expected.values())
    # Mapped back to the real node IDs, identically for every condition.
    for condition in EVIDENCE_CONDITIONS:
        assert contexts[condition.value]["node_labels"] == expected

    requests = _answer_requests(provider)
    pairs = {
        condition.value: EVIDENCE_AND_NODE.findall(requests[condition.value].prompt)
        for condition in STRUCTURED
    }
    # Each evidence alias sits beside the same node ref in ir, enriched and
    # indexed, in gold order.
    expected_pairs = [(f"E{i + 1}", f"N{i + 1}") for i in range(len(gold_nodes))]
    for condition, found in pairs.items():
        assert found == expected_pairs, condition
    # raw shows no structure, so no node refs.
    assert "source_node=" not in requests["raw"].prompt


def test_indexed_features_get_short_refs_in_map_order(tmp_path: Path) -> None:
    provider = JudgedRepresentationProvider()
    _run_judged(tmp_path, provider, "feature-refs")

    indexed = _answer_requests(provider)["indexed"].prompt
    refs = re.findall(r'<feature ref="([^"]+)"', indexed)
    assert refs
    assert refs == [f"F{i + 1}" for i in range(len(refs))]


@pytest.mark.parametrize("condition", tuple(RepresentationCondition))
def test_a_v3_prompt_contains_no_long_hex_run(
    tmp_path: Path, condition: RepresentationCondition
) -> None:
    provider = JudgedRepresentationProvider()
    result = _run_judged(
        tmp_path, provider, f"no-hex-{condition.value}", conditions=(condition,)
    )

    assert provider.requests
    for request in provider.requests:
        # The answer prompt and both judges' prompts of this condition.
        assert not LONG_HEX.search(request.prompt), (
            request.system,
            LONG_HEX.findall(request.prompt)[:3],
        )
    for row in _contexts(result.path).values():
        assert not LONG_HEX.search(row["representation"])


def test_v2_keeps_hex_node_ids_and_feature_refs(tmp_path: Path) -> None:
    provider = JudgedRepresentationProvider()
    _run_judged(tmp_path, provider, "v2-hex", evidence_render_version=V2)

    requests = _answer_requests(provider)
    for condition in EVIDENCE_CONDITIONS:
        assert not FULL_ID.search(requests[condition.value].prompt)
    for condition in STRUCTURED:
        assert re.search(
            r'source_node="node_[0-9a-f]{64}"', requests[condition.value].prompt
        )
    assert re.search(
        r'<feature ref="[0-9a-f]{12}"', requests["indexed"].prompt
    )


def test_no_full_evidence_id_reaches_any_prompt_under_aliases(
    tmp_path: Path,
) -> None:
    provider = JudgedRepresentationProvider()
    result = _run_judged(tmp_path, provider, "aliases-no-hex")

    evidence_ids = _contexts(result.path)["raw"]["evidence_ids"]
    assert provider.requests
    for request in provider.requests:
        assert not FULL_ID.search(request.prompt), request.system
        for evidence_id in evidence_ids:
            assert evidence_id not in request.prompt


def test_v1_still_renders_full_ids_and_records_the_scheme(tmp_path: Path) -> None:
    provider = JudgedRepresentationProvider()
    result = _run_judged(
        tmp_path, provider, "aliases-v1", evidence_render_version=V1
    )

    requests = _answer_requests(provider)
    for condition in EVIDENCE_CONDITIONS:
        prompt = requests[condition.value].prompt
        assert FULL_ID.search(prompt)
        assert not re.search(r'id="E\d+"', prompt)
        assert prompt.startswith(ANSWER_PROMPT_INSTRUCTIONS)
    manifest = json.loads((result.path / "manifest.json").read_text())
    assert manifest["evidence_render_version"] == V1
    assert manifest["config"]["evidence_render_version"] == V1
    assert manifest["prompt_sha256"] == hashlib.sha256(
        ANSWER_PROMPT_INSTRUCTIONS.encode()
    ).hexdigest()
    for record in result.records:
        if record.condition != RepresentationCondition.QUESTION_ONLY:
            assert record.citation_validity == 1
            assert record.citation_entailment == 1


@pytest.mark.parametrize("version", [V2, V3])
def test_aliased_schemes_are_recorded_with_the_aliased_instructions(
    tmp_path: Path, version: str
) -> None:
    result = _run_judged(
        tmp_path,
        JudgedRepresentationProvider(),
        f"aliases-{version}",
        evidence_render_version=version,
    )
    manifest = json.loads((result.path / "manifest.json").read_text())
    assert manifest["evidence_render_version"] == version
    assert manifest["config"]["evidence_render_version"] == version
    assert manifest["prompt_sha256"] == hashlib.sha256(
        ANSWER_PROMPT_INSTRUCTIONS_ALIASED.encode()
    ).hexdigest()


def test_default_scheme_is_v3() -> None:
    assert _config().evidence_render_version == V3
    # The aliased instructions ask for aliases, not IDs.
    assert '"citations":["E1"]' in ANSWER_PROMPT_INSTRUCTIONS_ALIASED


def test_cited_aliases_map_to_their_full_ids_before_scoring(
    tmp_path: Path,
) -> None:
    provider = CitingProvider(lambda _request: ["E2", "E1"])
    result = _run_judged(tmp_path, provider, "aliases-mapped")

    evidence_ids = _contexts(result.path)["raw"]["evidence_ids"]
    judged = {
        request.system.removesuffix(CITATION_JUDGE): request
        for request in provider.requests
        if request.system.endswith(CITATION_JUDGE)
    }
    for record in result.records:
        if record.condition == RepresentationCondition.QUESTION_ONLY:
            continue
        # Recorded citations are full, provenance-bearing IDs.
        assert record.citations == (evidence_ids[1], evidence_ids[0])
        assert record.citation_validity == 1
        assert record.citation_support == 1
        assert record.citation_entailment == 1
        # The judge sees exactly the mapped nodes, under their aliases.
        judge = judged[record.condition.value]
        assert judge.evidence_ids == (evidence_ids[1], evidence_ids[0])
        # In citation order, each under the alias the answer prompt showed.
        assert list(_labelled_text(judge.prompt)) == ["E2", "E1"]


@pytest.mark.parametrize("version", [V1, V2, V3])
def test_the_citation_judge_prompt_is_identical_across_conditions(
    tmp_path: Path, version: str
) -> None:
    provider = CitingProvider(
        lambda request: [request.evidence_ids[1], request.evidence_ids[0]]
        if version == V1
        else ["E2", "E1"]
    )
    _run_judged(
        tmp_path, provider, f"judge-identical-{version}",
        evidence_render_version=version,
    )

    prompts = _judge_prompts(provider)
    assert set(prompts) == {condition.value for condition in EVIDENCE_CONDITIONS}
    assert len(set(prompts.values())) == 1
    prompt = next(iter(prompts.values()))
    # Canonical node text only: no encoding reaches the judge.
    for marker in ("<agent_features>", "<agent_map", "source_node=", "Heading:"):
        assert marker not in prompt


def test_an_unknown_alias_is_an_invalid_citation(tmp_path: Path) -> None:
    provider = CitingProvider(lambda _request: ["E1", "E999"])
    result = _run_judged(tmp_path, provider, "aliases-unknown")

    evidence_ids = _contexts(result.path)["raw"]["evidence_ids"]
    for record in result.records:
        if record.condition == RepresentationCondition.QUESTION_ONLY:
            continue
        # Kept as written, so the artifact shows what the model cited.
        assert record.citations == (evidence_ids[0], "E999")
        assert record.citation_validity == 0.5


def test_node_refs_and_garbled_ids_are_invalid_citations_and_skip_the_judge(
    tmp_path: Path,
) -> None:
    garbled = "evidence_" + "ab" * 30  # 60 hex digits: a truncated copy
    # N1 is a node reference, not a citation label.
    provider = CitingProvider(lambda _request: ["E0", "e1", "N1", garbled])
    result = _run_judged(tmp_path, provider, "aliases-garbled")

    assert not any(r.system.endswith(CITATION_JUDGE) for r in provider.requests)
    for record in result.records:
        if record.condition == RepresentationCondition.QUESTION_ONLY:
            continue
        assert record.citations == ("E0", "e1", "N1", garbled)
        assert record.citation_validity == 0
        assert record.citation_entailment == 0


def test_a_full_id_cited_verbatim_is_still_accepted(tmp_path: Path) -> None:
    provider = CitingProvider(
        lambda request: [request.evidence_ids[1], "E1"]
    )
    result = _run_judged(tmp_path, provider, "aliases-verbatim")

    evidence_ids = _contexts(result.path)["raw"]["evidence_ids"]
    for record in result.records:
        if record.condition == RepresentationCondition.QUESTION_ONLY:
            continue
        assert record.citations == (evidence_ids[1], evidence_ids[0])
        assert record.citation_validity == 1
        assert record.citation_entailment == 1


def test_map_citations_maps_aliases_first_and_keeps_anything_else() -> None:
    labels = {"evidence_a": "E1", "evidence_b": "E2"}
    assert map_citations(("E2", "evidence_a", "E3", ""), labels) == (
        "evidence_b",
        "evidence_a",
        "E3",
        "",
    )
    # Without labels (question_only) nothing maps.
    assert map_citations(("E1",), {}) == ("E1",)


def test_question_labels_follow_gold_order(tmp_path: Path) -> None:
    nodes: Sequence = _render_inputs(tmp_path)[0]
    labels = question_labels(nodes, V3)
    assert list(labels.evidence.values()) == [f"E{i + 1}" for i in range(len(nodes))]
    assert list(labels.nodes.values()) == [f"N{i + 1}" for i in range(len(nodes))]
    assert list(labels.evidence) == [item.evidence_id for item in nodes]
    assert list(labels.nodes) == [item.node.id for item in nodes]
    for version in (V1, V2):
        assert question_labels(nodes, version).nodes == {
            item.node.id: item.node.id for item in nodes
        }
    assert question_labels(nodes, V1).evidence == {
        item.evidence_id: item.evidence_id for item in nodes
    }


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ((), V3),
        (("--evidence-render-version", V2), V2),
        (("--evidence-render-version", V1), V1),
    ],
)
def test_eval_representation_passes_the_render_scheme(
    monkeypatch, args: tuple[str, ...], expected: str
) -> None:
    result, captured, _ = _invoke_eval_representation(
        monkeypatch, "--max-calls", "8", *args
    )
    config = captured.get("config")
    assert config is not None, result.output
    assert config.evidence_render_version == expected


def test_eval_representation_refuses_an_unknown_render_scheme(monkeypatch) -> None:
    result, captured, constructions = _invoke_eval_representation(
        monkeypatch, "--max-calls", "8", "--evidence-render-version", "v4"
    )
    assert result.exit_code != 0
    assert captured == {}
    assert constructions == []
