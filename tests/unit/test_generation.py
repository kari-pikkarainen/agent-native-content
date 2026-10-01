"""Generation prompt, provider, scoring, and artifact acceptance tests."""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_evaluation import _config, _corpus, _run

from agent_native_content.datasets.base import BenchmarkQuestion
from agent_native_content.evaluation import BenchmarkSystem
from agent_native_content.experiments import manifest
from agent_native_content.generation import (
    GenerationConfig,
    GenerationError,
    GenerationEvaluationRecord,
    OpenAIAnswerProvider,
    PricingMetadata,
    ProviderAnswer,
    is_abstention,
    parse_answer_equivalence_response,
    parse_answer_response,
    parse_citation_entailment_response,
    render_answer_equivalence_prompt,
    run_generation_benchmark,
)
from agent_native_content.generation.models import AnswerRequest
from agent_native_content.generation.providers import (
    ProviderConfigurationError,
    responses_create_kwargs,
)
from agent_native_content.generation.runner import (
    ANSWER_PROMPT_INSTRUCTIONS,
    ANSWER_PROMPT_INSTRUCTIONS_ALIASED,
    CITATION_ENTAILMENT_PROMPT_INSTRUCTIONS,
    _artifact_hash,
    _markdown_report,
    _summarize,
    render_citation_entailment_prompt,
)
from agent_native_content.generation.scoring import (
    NUMERIC_RELATIVE_TOLERANCE,
    RELEASED_VERIFICATION_RULES,
    accuracy_score,
    anls_score,
    answer_type,
    token_f1_score,
)
from agent_native_content.retrieval import ContextItem, ContextPacket, RetrievalScores


class FixtureProvider:
    name = "fixture"
    version = "1"

    def __init__(self) -> None:
        self.requests: list[AnswerRequest] = []

    def generate(self, request: AnswerRequest, *, config: GenerationConfig):
        self.requests.append(request)
        if request.system.endswith(":citation_entailment_judge"):
            return ProviderAnswer(
                text=json.dumps(
                    {
                        "entailed": True,
                        "reason": "The cited passage states the answer.",
                    }
                ),
                model_id=config.model,
                response_id=f"response-{len(self.requests)}",
                input_tokens=100,
                cached_input_tokens=20,
                output_tokens=10,
                reasoning_tokens=2,
                provider_usage={"total_tokens": 110},
            )
        return ProviderAnswer(
            # Cite the first evidence item when there is one, and cite nothing
            # when the packet is empty. Retrieval can legitimately return no
            # evidence now that both channels refuse non-matches, so a packet
            # with zero items reaches generation; this stub used to index
            # ``evidence_ids[0]`` unconditionally and raised IndexError, which
            # the runner converts into a whole-run GenerationError. A grounded
            # model handed no evidence has nothing it may cite, so citing
            # nothing is the behavior being modeled, not a workaround.
            text=json.dumps(
                {
                    "answer": "revenue",
                    "citations": list(request.evidence_ids[:1]),
                }
            ),
            model_id=config.model,
            response_id=f"response-{len(self.requests)}",
            input_tokens=100,
            cached_input_tokens=20,
            output_tokens=10,
            reasoning_tokens=2,
            provider_usage={"total_tokens": 110},
        )


def _generation_config() -> GenerationConfig:
    return GenerationConfig(
        model="fixture-model",
        systems=tuple(BenchmarkSystem),
        budgets=(12,),
        pricing=PricingMetadata(
            input_usd_per_million=1,
            cached_input_usd_per_million=0.5,
            output_usd_per_million=2,
        ),
    )


def _content_accounted_retrieval_config():
    """The shared retrieval fixture's config, with content budget accounting.

    Used where a test's premise is sized in content tokens -- here, which arm
    packs nothing at a 12-token budget.
    """
    config = _config()
    return config.model_copy(
        update={
            "compiler": config.compiler.model_copy(
                update={"budget_accounting": "content"}
            )
        }
    )


def test_generation_runner_reuses_immutable_contexts_and_writes_costs(
    tmp_path: Path,
) -> None:
    # The assertions below name the one arm that packs nothing at 12 tokens,
    # which is a content-token premise; content accounting is pinned for it.
    retrieval = _run(
        tmp_path,
        run_id="retrieval-fixture",
        config=_content_accounted_retrieval_config(),
    )
    provider = FixtureProvider()

    result = run_generation_benchmark(
        retrieval.path,
        _corpus(tmp_path).questions,
        config=_generation_config(),
        provider=provider,
        artifacts_root=tmp_path / "artifacts",
        run_id="generation-fixture",
        git_commit="b" * 40,
        git_dirty=False,
        clock=lambda: datetime(2026, 9, 20, tzinfo=UTC),
    )

    assert len(result.records) == len(BenchmarkSystem)
    assert len(provider.requests) == len(BenchmarkSystem)
    assert {record.system for record in result.records} == set(BenchmarkSystem)
    assert all(record.accuracy == 1 for record in result.records)
    # Split by whether the cell had anything to cite. The structural arm packs
    # nothing at this 12-token budget: its one genuine chunk is 21 tokens, and
    # the smaller chunks that used to fill the gap were non-matches the
    # retrieval channels no longer rank. An answer that cites nothing scores
    # zero on both citation metrics, which is the runner's existing rule for
    # an empty citation list and is the right one -- an uncited claim is
    # ungrounded whatever the reason. The cells that do carry evidence must
    # still score a perfect 1, so this stays a real assertion rather than a
    # relaxation to ">= 0".
    cited = [record for record in result.records if record.citations]
    uncited = [record for record in result.records if not record.citations]
    assert {record.system for record in uncited} == {BenchmarkSystem.STRUCTURAL}
    assert len(cited) == len(BenchmarkSystem) - 1
    assert all(record.citation_validity == 1 for record in cited)
    assert all(record.citation_support == 1 for record in cited)
    assert all(record.citation_validity == 0 for record in uncited)
    assert all(record.citation_support == 0 for record in uncited)
    assert all(not record.citation_present for record in uncited)
    assert all(record.cost_usd == pytest.approx(0.00011) for record in result.records)
    assert len(result.summary.rows) == len(BenchmarkSystem)
    assert {path.name for path in result.path.iterdir()} == {
        "generation.jsonl",
        "manifest.json",
        "report.md",
        "summary.json",
    }
    manifest = json.loads((result.path / "manifest.json").read_text())
    assert manifest["retrieval_run_id"] == "retrieval-fixture"
    assert manifest["provider"] == "fixture"
    assert manifest["git_commit"] == "b" * 40
    assert len(manifest["retrieval_artifact_sha256"]) == 64

    with pytest.raises(GenerationError, match="completed run already exists"):
        run_generation_benchmark(
            retrieval.path,
            _corpus(tmp_path).questions,
            config=_generation_config(),
            provider=provider,
            artifacts_root=tmp_path / "artifacts",
            run_id="generation-fixture",
        )


def test_generation_manifest_separates_offline_models_from_unpinned_ones(
    tmp_path: Path,
) -> None:
    """A null carried revision must not read the same in both upstream cases.

    Copying only the revisions made an offline upstream run, which has no hub
    identity to record, indistinguishable from a run made before revisions
    were pinned, which has a hub identity and no record of which commit it
    resolved to. The model name carried beside each revision separates them
    without opening the upstream run, which is the whole point of the copy.
    """
    retrieval = _run(tmp_path, run_id="retrieval-offline")

    offline_run = run_generation_benchmark(
        retrieval.path,
        _corpus(tmp_path).questions,
        config=_generation_config(),
        provider=FixtureProvider(),
        artifacts_root=tmp_path / "artifacts",
        run_id="generation-offline",
        git_commit="b" * 40,
        git_dirty=False,
        clock=lambda: datetime(2026, 9, 20, tzinfo=UTC),
    )
    offline = json.loads(
        (offline_run.path / "manifest.json").read_text(encoding="utf-8")
    )

    assert offline["embedding_model"] == "hash-256-v1"
    assert offline["embedding_revision"] is None
    assert offline["reranker_model"] == "lexical-overlap-v1"
    assert offline["reranker_revision"] is None

    upstream_path = retrieval.path / "manifest.json"
    upstream = json.loads(upstream_path.read_text(encoding="utf-8"))
    upstream["embedding_model"] = "BAAI/bge-small-en-v1.5"
    upstream["reranker_model"] = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    upstream["embedding_revision"] = None
    upstream["reranker_revision"] = None
    upstream_path.write_text(json.dumps(upstream), encoding="utf-8")

    unpinned_run = run_generation_benchmark(
        retrieval.path,
        _corpus(tmp_path).questions,
        config=_generation_config(),
        provider=FixtureProvider(),
        artifacts_root=tmp_path / "artifacts",
        run_id="generation-unpinned",
        git_commit="b" * 40,
        git_dirty=False,
        clock=lambda: datetime(2026, 9, 20, tzinfo=UTC),
    )
    unpinned = json.loads(
        (unpinned_run.path / "manifest.json").read_text(encoding="utf-8")
    )

    assert unpinned["embedding_model"] == "BAAI/bge-small-en-v1.5"
    assert unpinned["embedding_revision"] is None
    assert unpinned["reranker_model"] == "cross-encoder/ms-marco-MiniLM-L-6-v2"
    assert unpinned["reranker_revision"] is None
    carried = ("embedding_model", "embedding_revision", "reranker_model")
    assert [offline[field] for field in carried] != [
        unpinned[field] for field in carried
    ]


def test_answer_parser_is_strict_but_accepts_json_fences() -> None:
    answer, citations, valid = parse_answer_response(
        '```json\n{"answer":"42","citations":["evidence_1"]}\n```'
    )

    assert (answer, citations, valid) == ("42", ("evidence_1",), True)
    assert parse_answer_response("Answer: 42") == ("", (), False)
    assert parse_answer_response('{"answer":"42","citations":"evidence_1"}') == (
        "",
        (),
        False,
    )


def test_optional_same_model_citation_entailment_is_costed(tmp_path: Path) -> None:
    retrieval = _run(tmp_path, run_id="retrieval-entailment")
    provider = FixtureProvider()
    config = _generation_config().model_copy(
        update={
            "systems": (BenchmarkSystem.COMPILER,),
            "citation_entailment_judge": True,
        }
    )

    result = run_generation_benchmark(
        retrieval.path,
        _corpus(tmp_path).questions,
        config=config,
        provider=provider,
        artifacts_root=tmp_path / "artifacts",
        run_id="generation-entailment",
        git_commit="b" * 40,
        git_dirty=False,
    )

    record = result.records[0]
    assert len(provider.requests) == 2
    assert provider.requests[1].system.endswith(":citation_entailment_judge")
    assert record.citation_entailment == 1.0
    assert record.citation_entailment_judge_valid is True
    assert record.calls == 2
    assert record.input_tokens == 200
    assert record.judge_input_tokens == 100
    assert record.cost_usd == pytest.approx(0.00022)
    assert result.summary.rows[0].mean_citation_entailment == 1.0
    manifest = json.loads((result.path / "manifest.json").read_text())
    assert len(manifest["citation_entailment_prompt_sha256"]) == 64


def test_citation_entailment_parser_is_strict() -> None:
    assert parse_citation_entailment_response(
        '{"entailed":true,"reason":"Direct support."}'
    ) == (True, "Direct support.", True)
    assert parse_citation_entailment_response(
        '{"entailed":"yes","reason":"Direct support."}'
    ) == (False, "", False)
    assert parse_citation_entailment_response("yes") == (False, "", False)


def test_answer_equivalence_prompt_is_blind_to_representation() -> None:
    prompt = render_answer_equivalence_prompt(
        "Which piles are used?",
        "Open-end pipe piles",
        "Open-ended steel pipe piles",
    )

    assert "Open-end pipe piles" in prompt
    assert "Open-ended steel pipe piles" in prompt
    assert "system" not in prompt.casefold()
    assert "condition" not in prompt.casefold()


def test_answer_equivalence_parser_is_strict() -> None:
    assert parse_answer_equivalence_response(
        '{"equivalent":true,"reason":"Same pile type."}'
    ) == (True, "Same pile type.", True)
    assert parse_answer_equivalence_response(
        '{"equivalent":"yes","reason":"Same."}'
    ) == (False, "", False)
    assert parse_answer_equivalence_response("yes") == (False, "", False)


def _legacy_parse_answer_response(text: str) -> tuple[str, tuple[str, ...], bool]:
    """Frozen copy of the answer parser before fence handling was shared."""
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            value = "\n".join(lines[1:-1])
            if value.lstrip().startswith("json"):
                value = value.lstrip()[4:].lstrip()
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return "", (), False
    if not isinstance(payload, dict):
        return "", (), False
    answer = payload.get("answer")
    citations = payload.get("citations")
    if not isinstance(answer, str) or not isinstance(citations, list):
        return "", (), False
    if any(not isinstance(citation, str) for citation in citations):
        return "", (), False
    return answer.strip(), tuple(citations), True


_ANSWER_JSON = '{"answer":" 42 ","citations":["E1","E2"]}'
_ANSWER_PARSER_CASES = (
    _ANSWER_JSON,
    f"  \n{_ANSWER_JSON}\n\t",
    f"```json\n{_ANSWER_JSON}\n```",
    f"```\n{_ANSWER_JSON}\n```",
    f"  ```json  \n{_ANSWER_JSON}\n  ```  \n",
    f"```JSON\n{_ANSWER_JSON}\n```",
    f"```python\n{_ANSWER_JSON}\n```",
    f"```\njson\n{_ANSWER_JSON}\n```",
    f"```\njson{_ANSWER_JSON}\n```",
    f"```json\n{_ANSWER_JSON}```",
    f"```json\n{_ANSWER_JSON}",
    f"```json {_ANSWER_JSON} ```",
    f"```json\n{_ANSWER_JSON}\n```\n```",
    f"```json\n```json\n{_ANSWER_JSON}\n```\n```",
    f"Here you go:\n```json\n{_ANSWER_JSON}\n```",
    f"```json\n{_ANSWER_JSON}\n```\nHope that helps.",
    f"Answer: {_ANSWER_JSON}",
    '```json\n{"answer":"42","citations":["E1"\n```',
    '{"answer":"42","citations":["E1"],}',
    '{"answer":"42","citations":"E1"}',
    '{"answer":42,"citations":[]}',
    '{"answer":"42","citations":[1]}',
    '["42"]',
    "",
    "```",
    "```\n```",
    "```json\n\n```",
    "Answer: 42",
    '{"answer":"INSUFFICIENT_EVIDENCE","citations":[]}',
    # Near-misses around the bare abstention marker stay invalid.
    '"INSUFFICIENT_EVIDENCE"',
    "INSUFFICIENT_EVIDENCE.",
    "INSUFFICIENT EVIDENCE",
    "INSUFFICIENT_EVIDENCE\nThe evidence does not say.",
    "INSUFFICIENT_EVIDENCE {}",
    "The answer is INSUFFICIENT_EVIDENCE",
    "Answer: INSUFFICIENT_EVIDENCE",
    "INSUFFICIENT_EVIDENCE\n```",
    "```json\nINSUFFICIENT_EVIDENCE",
    "INSUFFICIENT_EVIDENC",
    '{"answer":"INSUFFICIENT_EVIDENCE","citations":[]',
)

# The only intentional differences from the legacy parser: a response that is
# nothing but the abstention marker (case as ``is_abstention`` matches it,
# after whitespace and one enclosing fence are removed) is a valid abstention.
_BARE_ABSTENTION_CASES = (
    "INSUFFICIENT_EVIDENCE",
    "  \nINSUFFICIENT_EVIDENCE\n\t",
    "insufficient_evidence",
    "Insufficient_Evidence",
    "```\nINSUFFICIENT_EVIDENCE\n```",
    "```json\nINSUFFICIENT_EVIDENCE\n```",
    "```\n  INSUFFICIENT_EVIDENCE  \n```",
)


@pytest.mark.parametrize("text", _ANSWER_PARSER_CASES)
def test_answer_parser_is_unchanged_by_shared_fence_helper(text: str) -> None:
    assert parse_answer_response(text) == _legacy_parse_answer_response(text)


@pytest.mark.parametrize("text", _BARE_ABSTENTION_CASES)
def test_bare_abstention_marker_is_a_valid_abstention(text: str) -> None:
    assert _legacy_parse_answer_response(text) == ("", (), False)
    assert parse_answer_response(text) == ("INSUFFICIENT_EVIDENCE", (), True)
    assert is_abstention(parse_answer_response(text)[0])


@pytest.mark.parametrize(
    ("parser", "payload", "expected"),
    (
        (
            parse_citation_entailment_response,
            '{"entailed":true,"reason":"Direct support."}',
            (True, "Direct support.", True),
        ),
        (
            parse_answer_equivalence_response,
            '{"equivalent":false,"reason":"Different pile type."}',
            (False, "Different pile type.", True),
        ),
    ),
)
def test_judge_parsers_accept_only_an_enclosing_code_fence(
    parser: Callable[[str], tuple[bool, str, bool]],
    payload: str,
    expected: tuple[bool, str, bool],
) -> None:
    invalid = (False, "", False)
    # A fence around otherwise valid JSON is the only tolerated wrapper.
    assert parser(f"```json\n{payload}\n```") == expected
    assert parser(f"```\n{payload}\n```") == expected
    assert parser(f"\n  ```json\n{payload}\n```  \n") == expected
    # Truncated output stays invalid, fenced or not.
    assert parser(f"```json\n{payload[:-5]}\n```") == invalid
    assert parser(f"```json\n{payload}") == invalid
    assert parser(payload[:-1]) == invalid
    # Prose around the JSON is not extracted.
    assert parser(f"Sure:\n```json\n{payload}\n```") == invalid
    assert parser(f"```json\n{payload}\n```\nDone.") == invalid
    assert parser(f"The judgment is {payload}") == invalid
    # No other repair, such as dropping trailing commas.
    assert parser(payload[:-1] + ",}") == invalid


@pytest.mark.parametrize(
    ("answer", "expected"),
    (
        ("INSUFFICIENT_EVIDENCE", True),
        (" insufficient_evidence ", True),
        ("There is insufficient evidence.", False),
        ("Revenue rose, though evidence is insufficient.", False),
        ("", False),
    ),
)
def test_abstention_is_the_exact_prompt_marker(answer: str, expected: bool) -> None:
    assert is_abstention(answer) is expected


class AbstainingProvider(FixtureProvider):
    def generate(self, request: AnswerRequest, *, config: GenerationConfig):
        if request.system.endswith(":citation_entailment_judge"):
            raise AssertionError("an abstention must not call the entailment judge")
        self.requests.append(request)
        return ProviderAnswer(
            text=json.dumps(
                {
                    "answer": "INSUFFICIENT_EVIDENCE",
                    "citations": list(request.evidence_ids[:1]),
                }
            ),
            model_id=config.model,
            input_tokens=100,
            output_tokens=10,
        )


def test_citation_entailment_is_not_applicable_to_abstentions(tmp_path: Path) -> None:
    retrieval = _run(tmp_path, run_id="retrieval-abstention")
    provider = AbstainingProvider()
    config = _generation_config().model_copy(
        update={
            "systems": (BenchmarkSystem.COMPILER,),
            "citation_entailment_judge": True,
        }
    )

    result = run_generation_benchmark(
        retrieval.path,
        _corpus(tmp_path).questions,
        config=config,
        provider=provider,
        artifacts_root=tmp_path / "artifacts",
        run_id="generation-abstention",
        git_commit="b" * 40,
        git_dirty=False,
    )

    assert len(provider.requests) == 1
    record = result.records[0]
    assert record.abstained is True
    assert record.citation_entailment is None
    assert record.citation_entailment_judge_valid is None
    assert record.calls == 1
    row = result.summary.rows[0]
    assert row.answer_rate == 0.0
    assert row.mean_citation_entailment is None
    assert row.citation_entailment_judge_valid_rate is None


@pytest.mark.parametrize(
    ("prediction", "gold", "kind", "expected"),
    (
        ("25.9", "25", "numeric", 1.0),
        ("27", "25", "numeric", 0.0),
        ("Option B", "B", "single_choice", 1.0),
        ("INSUFFICIENT_EVIDENCE", "Not answerable", "unanswerable", 1.0),
        ("The answer is revenue increased", "revenue", "entity", 1.0),
    ),
)
def test_native_accuracy_rules(
    prediction: str,
    gold: str,
    kind: str,
    expected: float,
) -> None:
    assert accuracy_score(prediction, gold, kind) == expected


def test_native_similarity_metrics() -> None:
    assert token_f1_score("red red blue", "red green") == pytest.approx(0.5)
    assert anls_score("revenue", "revenve") > 0.5
    assert anls_score("x", "revenue") == 0


def test_openai_provider_maps_responses_usage_without_importing_sdk() -> None:
    calls: list[dict[str, object]] = []

    class Responses:
        @staticmethod
        def create(**kwargs):
            calls.append(kwargs)
            usage = SimpleNamespace(
                input_tokens=120,
                output_tokens=20,
                total_tokens=140,
                input_tokens_details=SimpleNamespace(cached_tokens=40),
                output_tokens_details=SimpleNamespace(reasoning_tokens=5),
                model_dump=lambda **_kwargs: {"total_tokens": 140},
            )
            return SimpleNamespace(
                id="response-1",
                model="resolved-model",
                output_text='{"answer":"yes","citations":[]}',
                usage=usage,
            )

    provider = OpenAIAnswerProvider(
        client=SimpleNamespace(responses=Responses()),
    )
    config = _generation_config().model_copy(
        update={"reasoning_effort": "low"}
    )
    result = provider.generate(
        AnswerRequest(
            question_id="question-1",
            system=BenchmarkSystem.COMPILER,
            token_budget=12,
            prompt="prompt",
            evidence_ids=("evidence-1",),
        ),
        config=config,
    )

    assert calls == [
        {
            "model": "fixture-model",
            "input": "prompt",
            "max_output_tokens": 256,
            "store": False,
            "reasoning": {"effort": "low"},
        }
    ]
    assert result.model_id == "resolved-model"
    assert result.cached_input_tokens == 40
    assert result.reasoning_tokens == 5


def test_generation_dirty_worktree_is_refused_before_any_provider_call(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A refused generation run must not spend money on a provider call."""
    retrieval = _run(tmp_path, run_id="retrieval-dirty-gate")
    provider = FixtureProvider()
    artifacts_root = tmp_path / "generation-artifacts"

    monkeypatch.setattr(manifest, "current_git_commit", lambda: "d" * 40)
    monkeypatch.setattr(manifest, "current_git_dirty", lambda: True)

    with pytest.raises(GenerationError, match="modified worktree"):
        run_generation_benchmark(
            retrieval.path,
            _corpus(tmp_path).questions,
            config=_generation_config(),
            provider=provider,
            artifacts_root=artifacts_root,
            run_id="generation-dirty",
            git_commit=None,
            allow_dirty=False,
            clock=lambda: datetime(2026, 9, 20, tzinfo=UTC),
        )

    assert provider.requests == []
    assert not artifacts_root.exists()


class TruncatedFirstCallProvider(FixtureProvider):
    """Answers normally but reports the first response as non-completed.

    The text stays a correct, parseable answer, so a run that ignored the
    provider status would score this cell 1.0 instead of recording a failure.
    """

    def generate(self, request: AnswerRequest, *, config: GenerationConfig):
        answer = super().generate(request, config=config)
        if len(self.requests) == 1:
            return answer.model_copy(
                update={
                    "status": "incomplete",
                    "incomplete_reason": "max_output_tokens",
                }
            )
        return answer


def _provider_request() -> AnswerRequest:
    return AnswerRequest(
        question_id="question-1",
        system=BenchmarkSystem.COMPILER,
        token_budget=12,
        prompt="prompt",
        evidence_ids=("evidence-1",),
    )


def _generation_record(**overrides) -> GenerationEvaluationRecord:
    values: dict[str, object] = {
        "retrieval_run_id": "retrieval-fixture",
        "question_id": "question-1",
        "system": BenchmarkSystem.COMPILER,
        "token_budget": 12,
        "answerable": True,
        "gold_answer": "revenue",
        "raw_response": '{"answer":"revenue","citations":[]}',
        "parsed_answer": "revenue",
        "citations": (),
        "response_valid": True,
        "accuracy": 1.0,
        "token_f1": 1.0,
        "anls": 1.0,
        "citation_validity": 0.0,
        "citation_support": None,
        "citation_present": False,
        "abstained": False,
        "insufficient_evidence_correct": False,
        "input_tokens": 100,
        "cached_input_tokens": 20,
        "output_tokens": 10,
        "reasoning_tokens": 2,
        "latency_ms": 1.0,
        "model_id": "fixture-model",
        "provider_usage": {},
        "cost_usd": 0.0001,
    }
    values.update(overrides)
    return GenerationEvaluationRecord(**values)


def test_non_completed_response_scores_zero_and_does_not_abort_the_run(
    tmp_path: Path,
) -> None:
    """A truncated answer must be a recorded failure, not a wrong answer.

    Aborting would throw away the provider calls already paid for, so the run
    continues and the failed cell is recorded, costed, and scored zero.
    """
    retrieval = _run(tmp_path, run_id="retrieval-truncated")
    provider = TruncatedFirstCallProvider()

    result = run_generation_benchmark(
        retrieval.path,
        _corpus(tmp_path).questions,
        config=_generation_config(),
        provider=provider,
        artifacts_root=tmp_path / "artifacts",
        run_id="generation-truncated",
        git_commit="b" * 40,
        git_dirty=False,
        clock=lambda: datetime(2026, 9, 20, tzinfo=UTC),
    )

    failed = [record for record in result.records if not record.response_valid]
    assert len(failed) == 1
    record = failed[0]
    assert record.provider_status == "incomplete"
    assert record.provider_incomplete_reason == "max_output_tokens"
    assert (record.accuracy, record.token_f1, record.anls) == (0.0, 0.0, 0.0)
    # The answer text itself was correct and parseable: only the provider
    # status distinguishes this failure from a right answer.
    assert record.parsed_answer == "revenue"
    assert record.cost_usd == pytest.approx(0.00011)

    assert len(provider.requests) == len(BenchmarkSystem)
    assert len(result.records) == len(BenchmarkSystem)
    assert all(
        other.accuracy == 1.0
        for other in result.records
        if other.response_valid
    )
    assert (result.path / "summary.json").is_file()
    rates = {row.system: row.response_valid_rate for row in result.summary.rows}
    assert rates[record.system] == 0.0
    assert sum(rates.values()) == len(BenchmarkSystem) - 1
    written = [
        json.loads(line)
        for line in (result.path / "generation.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(written) == len(BenchmarkSystem)
    assert sum(not row["response_valid"] for row in written) == 1


def test_response_valid_rate_separates_failed_calls_from_wrong_answers() -> None:
    summary = _summarize(
        "generation-rate",
        "retrieval-fixture",
        (
            _generation_record(question_id="question-1"),
            _generation_record(
                question_id="question-2",
                response_valid=False,
                provider_status="incomplete",
                provider_incomplete_reason="max_output_tokens",
                accuracy=0.0,
                token_f1=0.0,
                anls=0.0,
            ),
        ),
    )

    assert len(summary.rows) == 1
    assert summary.rows[0].response_valid_rate == 0.5
    assert summary.rows[0].answer_rate == 0.5
    assert summary.rows[0].question_count == 2


def test_generation_manifest_records_configured_temperature(
    tmp_path: Path,
) -> None:
    retrieval = _run(tmp_path, run_id="retrieval-sampling")
    unset = run_generation_benchmark(
        retrieval.path,
        _corpus(tmp_path).questions,
        config=_generation_config(),
        provider=FixtureProvider(),
        artifacts_root=tmp_path / "artifacts",
        run_id="generation-sampling-default",
        git_commit="b" * 40,
        git_dirty=False,
        clock=lambda: datetime(2026, 9, 20, tzinfo=UTC),
    )
    configured = run_generation_benchmark(
        retrieval.path,
        _corpus(tmp_path).questions,
        config=_generation_config().model_copy(update={"temperature": 0.0}),
        provider=FixtureProvider(),
        artifacts_root=tmp_path / "artifacts",
        run_id="generation-sampling-configured",
        git_commit="b" * 40,
        git_dirty=False,
        clock=lambda: datetime(2026, 9, 20, tzinfo=UTC),
    )

    # null records "not sent, provider default", which is a stated setting
    # rather than a missing one.
    unset_manifest = json.loads(
        (unset.path / "manifest.json").read_text(encoding="utf-8")
    )
    assert unset_manifest["temperature"] is None
    assert unset_manifest["seed"] is None
    configured_manifest = json.loads(
        (configured.path / "manifest.json").read_text(encoding="utf-8")
    )
    assert configured_manifest["temperature"] == 0.0
    assert configured_manifest["seed"] is None
    assert configured_manifest["config"]["temperature"] == 0.0
    assert configured_manifest["config"]["seed"] is None


class _RecordingResponses:
    """Fake ``client.responses``; like every fake, it accepts any keyword."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            id="response-1",
            model="resolved-model",
            output_text='{"answer":"yes","citations":[]}',
            status="completed",
            incomplete_details=None,
            usage=SimpleNamespace(
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
                input_tokens_details=None,
                output_tokens_details=None,
            ),
        )


def test_openai_provider_sends_sampling_settings_only_when_configured() -> None:
    responses = _RecordingResponses()
    calls = responses.calls
    provider = OpenAIAnswerProvider(client=SimpleNamespace(responses=responses))
    request = _provider_request()

    unset = provider.generate(request, config=_generation_config())
    provider.generate(
        request,
        config=_generation_config().model_copy(update={"temperature": 0.0}),
    )

    assert "temperature" not in calls[0]
    # 0.0 is a configured temperature, not an unset one.
    assert calls[1]["temperature"] == 0.0
    assert all("seed" not in call for call in calls)
    assert unset.provider_valid is True


def test_openai_provider_refuses_a_seed_before_any_call() -> None:
    # The Responses API has no seed parameter, so a configured seed could only
    # be recorded, never applied. Old configs with seed unset still parse.
    seeded = _generation_config().model_copy(update={"temperature": 0.0, "seed": 7})
    assert GenerationConfig.model_validate(
        _generation_config().model_dump(mode="json")
    ).seed is None
    with pytest.raises(ProviderConfigurationError, match="no seed parameter"):
        OpenAIAnswerProvider.from_config(seeded, environ={})

    responses = _RecordingResponses()
    provider = OpenAIAnswerProvider(client=SimpleNamespace(responses=responses))
    with pytest.raises(ProviderConfigurationError, match="--temperature 0"):
        provider.generate(_provider_request(), config=seeded)
    assert responses.calls == []


def _every_optional_setting_config() -> GenerationConfig:
    """A config with every optional request setting set, seed included."""
    config = _generation_config().model_copy(
        update={
            "max_output_tokens": 999,
            "reasoning_effort": "low",
            "temperature": 0.0,
            "seed": 7,
            "provider_base_url": "http://127.0.0.1:1234/v1",
        }
    )
    unset_optional = [
        name
        for name, field in GenerationConfig.model_fields.items()
        if field.default is None and getattr(config, name) is None
    ]
    # A new optional setting must be added here so its request key is checked.
    assert unset_optional == []
    return config


def test_responses_create_kwargs_exist_in_the_installed_sdk_signature() -> None:
    import inspect

    responses_module = pytest.importorskip("openai.resources.responses")
    parameters = inspect.signature(responses_module.Responses.create).parameters
    accepted = {
        name
        for name, parameter in parameters.items()
        if name != "self" and parameter.kind is not inspect.Parameter.VAR_KEYWORD
    }
    # The premise of refusing a seed: the installed SDK has no such parameter.
    assert "seed" not in accepted

    config = _every_optional_setting_config()
    request = _provider_request()
    kwargs = responses_create_kwargs(request, config)
    assert {"reasoning", "temperature", "max_output_tokens"} <= set(kwargs)
    assert set(kwargs) - accepted == set()

    # ``generate`` sends exactly these arguments (seed unset, as it must be).
    responses = _RecordingResponses()
    provider = OpenAIAnswerProvider(
        client=SimpleNamespace(responses=responses),
        base_url=config.provider_base_url,
    )
    unseeded = config.model_copy(update={"seed": None})
    provider.generate(request, config=unseeded)
    assert responses.calls == [responses_create_kwargs(request, unseeded)]


def test_openai_provider_marks_non_completed_responses_provider_invalid() -> None:
    class Responses:
        @staticmethod
        def create(**_kwargs):
            return SimpleNamespace(
                id="response-1",
                model="resolved-model",
                output_text=None,
                status="incomplete",
                incomplete_details=SimpleNamespace(reason="max_output_tokens"),
                usage=SimpleNamespace(
                    input_tokens=120,
                    output_tokens=256,
                    total_tokens=376,
                    input_tokens_details=SimpleNamespace(cached_tokens=0),
                    output_tokens_details=SimpleNamespace(reasoning_tokens=256),
                ),
            )

    provider = OpenAIAnswerProvider(client=SimpleNamespace(responses=Responses()))

    result = provider.generate(_provider_request(), config=_generation_config())

    assert result.status == "incomplete"
    assert result.incomplete_reason == "max_output_tokens"
    assert result.provider_valid is False
    # A truncated response can carry no text and must still be costed.
    assert result.text == ""
    assert result.output_tokens == 256


class TruncatedJudgeProvider(FixtureProvider):
    """Answers normally but reports every judge response as non-completed.

    The judge text stays parseable and positive, so a run that ignored the
    judge's provider status would publish ``citation_entailment == 1.0`` for a
    verdict no completed judge ever gave.
    """

    def generate(self, request: AnswerRequest, *, config: GenerationConfig):
        answer = super().generate(request, config=config)
        if request.system.endswith(":citation_entailment_judge"):
            return answer.model_copy(
                update={
                    "status": "incomplete",
                    "incomplete_reason": "max_output_tokens",
                }
            )
        return answer


def test_truncated_judge_is_invalid_and_publishes_no_entailment(
    tmp_path: Path,
) -> None:
    """A cut-off judge must not publish a positive entailment score."""
    retrieval = _run(tmp_path, run_id="retrieval-truncated-judge")
    provider = TruncatedJudgeProvider()
    config = _generation_config().model_copy(
        update={
            "systems": (BenchmarkSystem.COMPILER,),
            "citation_entailment_judge": True,
        }
    )

    result = run_generation_benchmark(
        retrieval.path,
        _corpus(tmp_path).questions,
        config=config,
        provider=provider,
        artifacts_root=tmp_path / "artifacts",
        run_id="generation-truncated-judge",
        git_commit="b" * 40,
        git_dirty=False,
        clock=lambda: datetime(2026, 9, 20, tzinfo=UTC),
    )

    record = result.records[0]
    # The answer call itself completed, so only the judge is at fault.
    assert record.response_valid is True
    assert record.citation_entailment_judge_valid is False
    assert record.citation_entailment == 0.0
    assert record.judge_provider_status == "incomplete"
    assert record.judge_provider_incomplete_reason == "max_output_tokens"
    # The judge text was parseable and asserted entailment: only the provider
    # status separates this failure from a genuine positive verdict.
    assert json.loads(record.citation_entailment_judge_raw_response)["entailed"]
    # The truncated judge call is still costed rather than discarded.
    assert record.calls == 2
    assert record.cost_usd == pytest.approx(0.00022)

    row = result.summary.rows[0]
    assert row.citation_entailment_judge_valid_rate == 0.0
    assert row.mean_citation_entailment == 0.0
    written = json.loads(
        (result.path / "generation.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert written["citation_entailment_judge_valid"] is False
    assert written["judge_provider_incomplete_reason"] == "max_output_tokens"
    summary = json.loads((result.path / "summary.json").read_text(encoding="utf-8"))
    assert summary["rows"][0]["citation_entailment_judge_valid_rate"] == 0.0
    assert summary["rows"][0]["mean_citation_entailment"] == 0.0


def test_judge_valid_rate_separates_an_absent_judge_from_a_failed_one() -> None:
    """An arm that never called the judge must not look like one that failed."""
    absent = _summarize(
        "generation-no-judge",
        "retrieval-fixture",
        (_generation_record(question_id="question-1"),),
    )

    assert absent.rows[0].citation_entailment_judge_valid_rate is None

    mixed = _summarize(
        "generation-judge",
        "retrieval-fixture",
        (
            _generation_record(
                question_id="question-1",
                citation_entailment=1.0,
                citation_entailment_judge_valid=True,
            ),
            _generation_record(
                question_id="question-2",
                citation_entailment=0.0,
                citation_entailment_judge_valid=False,
                judge_provider_status="incomplete",
                judge_provider_incomplete_reason="max_output_tokens",
            ),
            # No judge call for this cell: it is neither a pass nor a failure.
            _generation_record(question_id="question-3"),
        ),
    )

    assert mixed.rows[0].citation_entailment_judge_valid_rate == 0.5
    assert mixed.rows[0].question_count == 3
    assert "| n/a |" in _markdown_report(absent)
    assert "| 0.500 |" in _markdown_report(mixed)


def test_openai_provider_records_a_response_that_reports_no_usage() -> None:
    """A response without a usage block must be recorded, not raise."""

    class Responses:
        @staticmethod
        def create(**_kwargs):
            return SimpleNamespace(
                id="response-1",
                model="resolved-model",
                output_text='{"answer":"yes","citations":[]}',
                status="completed",
                usage=None,
            )

    provider = OpenAIAnswerProvider(client=SimpleNamespace(responses=Responses()))

    result = provider.generate(_provider_request(), config=_generation_config())

    assert result.input_tokens == 0
    assert result.output_tokens == 0
    assert result.cached_input_tokens == 0
    assert result.reasoning_tokens == 0
    assert result.provider_usage == {}
    assert result.text == '{"answer":"yes","citations":[]}'
    assert result.provider_valid is True


def test_openai_provider_records_unreadable_response_text() -> None:
    """Unreadable text is a recorded failure, not an aborted run."""

    class _Response:
        id = "response-1"
        model = "resolved-model"
        status = "completed"
        usage = SimpleNamespace(
            input_tokens=120,
            output_tokens=20,
            total_tokens=140,
            input_tokens_details=SimpleNamespace(cached_tokens=0),
            output_tokens_details=SimpleNamespace(reasoning_tokens=0),
        )

        @property
        def output_text(self) -> str:
            raise TypeError("'NoneType' object is not iterable")

    class Responses:
        @staticmethod
        def create(**_kwargs):
            return _Response()

    provider = OpenAIAnswerProvider(client=SimpleNamespace(responses=Responses()))

    result = provider.generate(_provider_request(), config=_generation_config())

    assert result.text == ""
    assert result.text_error is not None
    assert result.text_error.startswith("TypeError:")
    # The provider reported a completed response, so only the unreadable text
    # makes this a failure; it must not be scored as an empty answer.
    assert result.status == "completed"
    assert result.provider_valid is False
    assert result.input_tokens == 120


def _rule_question(
    verification_rule: str,
    *,
    answer_format: str,
    answerable: bool,
) -> BenchmarkQuestion:
    """Build a question carrying one released rule, without reading `data/**`.

    The released unanswerable rows are not null: all 188 carry
    `answer.format == "None"` and `answer.value == "Not answerable"`, so that
    literal string is the runtime gold. See deviation 4 in
    `docs/specs/evaluation.md`.
    """
    return BenchmarkQuestion(
        id=f"question-{verification_rule}",
        question="Which target increased?",
        document_ids=("dataset-doc-1",),
        gold_answer="Not answerable" if answer_format == "None" else "revenue",
        answer_format=answer_format,
        verification_rule=verification_rule,
        gold_evidence=(),
        answerable=answerable,
        task_type="single_doc",
    )


# Every released rule in `xldocbench_strict_1345_v1`, paired with the released
# `answer.format` and answerability that co-occur with it, and the type the
# mapping must produce. Deviations are tabulated in `docs/specs/evaluation.md`.
RELEASED_RULE_MAPPING: tuple[tuple[str, str, bool, str], ...] = (
    ("casefold_exact_match", "Str", True, "entity"),
    ("numeric_tolerance", "Int", True, "numeric"),
    ("numeric_tolerance", "Float", True, "numeric"),
    ("exact_match", "None", False, "unanswerable"),
    ("percentage_exact", "Float", True, "percentage"),
    ("choice_exact_match", "Str", True, "single_choice"),
)


@pytest.mark.parametrize(
    ("verification_rule", "answer_format", "answerable", "expected"),
    RELEASED_RULE_MAPPING,
)
def test_released_verification_rules_map_to_expected_answer_type(
    verification_rule: str,
    answer_format: str,
    answerable: bool,
    expected: str,
) -> None:
    question = _rule_question(
        verification_rule,
        answer_format=answer_format,
        answerable=answerable,
    )
    assert answer_type(question) == expected


def test_released_rule_mapping_covers_every_released_rule() -> None:
    """The table above and the shipped constant must name the same rules.

    This detects an unreviewed edit to either literal. It **cannot** detect a
    rule that first appears in the release data: both sides are literals in this
    repository, `data/raw/**` is git-ignored, and no unit test may read
    `data/**`. Such a rule would leave this suite green and be scored by
    whichever branch its name selects. See the rule inventory in
    `docs/specs/evaluation.md`.
    """
    exercised = {rule for rule, _, _, _ in RELEASED_RULE_MAPPING}
    assert exercised == set(RELEASED_VERIFICATION_RULES)


def test_exact_match_never_reaches_the_relaxed_entity_path() -> None:
    """All 188 released `exact_match` rows are unanswerable rows.

    The unanswerable guard runs before rule dispatch, so `exact_match` is
    scored by abstention detection and not by the relaxed entity predicate.
    """
    question = _rule_question("exact_match", answer_format="None", answerable=False)
    assert answer_type(question) == "unanswerable"
    # No released row pairs `exact_match` with an answerable question. This
    # pins which path such a row would take if a future release added one.
    answerable_variant = _rule_question(
        "exact_match", answer_format="Str", answerable=True
    )
    assert answer_type(answerable_variant) == "entity"


def test_numeric_routing_is_a_substring_test_on_the_rule_name() -> None:
    """Characterization: an unseen rule containing `tolerance` takes numeric.

    This is not desired behavior; it is pinned so that any future change to the
    dispatch is deliberate. See deviation 5 in `docs/specs/evaluation.md`.
    """
    unseen = _rule_question(
        "some_future_tolerance_rule", answer_format="Str", answerable=True
    )
    assert "some_future_tolerance_rule" not in RELEASED_VERIFICATION_RULES
    assert answer_type(unseen) == "numeric"


def test_percentage_shares_the_numeric_relative_tolerance() -> None:
    """Characterization: `percentage_exact` is not scored exactly.

    The percentage path applies the same 5% *relative* tolerance as numeric,
    despite the released rule name. The tolerance value itself has no source in
    the release. See deviations 2 and 3 in `docs/specs/evaluation.md`.
    """
    assert NUMERIC_RELATIVE_TOLERANCE == 0.05
    for kind in ("numeric", "percentage"):
        assert accuracy_score("21", "20", kind) == 1.0  # +5.0%, at the bound
        assert accuracy_score("19", "20", kind) == 1.0  # -5.0%, at the bound
        assert accuracy_score("21.1", "20", kind) == 0.0  # +5.5%, outside
        assert accuracy_score("18.9", "20", kind) == 0.0  # -5.5%, outside
        # Relative, not absolute: the same 1.0 gap passes at 20 and fails at 2.
        assert accuracy_score("3", "2", kind) == 0.0
        # Gold zero is special-cased to a near-exact absolute check, pinned at
        # its boundary so a looser epsilon cannot pass unnoticed.
        assert accuracy_score("0", "0", kind) == 1.0
        assert accuracy_score("0.0000009", "0", kind) == 1.0  # 9e-7, inside
        assert accuracy_score("0.000001", "0", kind) == 0.0  # 1e-6, not < 1e-6
        assert accuracy_score("0.000002", "0", kind) == 0.0  # 2e-6, outside
        assert accuracy_score("0.1", "0", kind) == 0.0
    # The percentage path compares bare numbers, so a value and its percent
    # rendering are treated as equal.
    assert accuracy_score("5%", "5", "percentage") == 1.0


def test_unanswerable_scoring_is_phrase_substring_matching() -> None:
    """Characterization: abstention is detected by phrase, not by structure.

    See deviation 4 in `docs/specs/evaluation.md`.
    """
    for phrase in (
        "Not answerable",
        "unanswerable",
        "This cannot be determined",
        "It cannot be answered",
        "There is not enough information",
        "INSUFFICIENT_EVIDENCE",
    ):
        assert accuracy_score(phrase, "Not answerable", "unanswerable") == 1.0
    # A confident wrong answer scores 1.0 whenever it embeds a listed phrase.
    assert (
        accuracy_score(
            "Revenue rose 12%, though some figures are unanswerable.",
            "Not answerable",
            "unanswerable",
        )
        == 1.0
    )
    # A valid abstention phrased outside the list scores 0.0.
    assert (
        accuracy_score("The document does not say.", "Not answerable", "unanswerable")
        == 0.0
    )
    assert accuracy_score("N/A", "Not answerable", "unanswerable") == 0.0
    # Gold is never read on this path: the released `Not answerable` value and
    # any other gold string score identically.
    assert accuracy_score("N/A", "", "unanswerable") == 0.0
    assert accuracy_score("unanswerable", "", "unanswerable") == 1.0


def test_entity_path_is_laxer_than_casefold_exact_match() -> None:
    """Characterization: the 822 `casefold_exact_match` rows are scored loosely.

    Substring containment or a Levenshtein ratio >= 0.8 both score 1.0. See
    deviation 1 in `docs/specs/evaluation.md`.
    """
    # Substring containment, not equality.
    assert accuracy_score("The answer is revenue increased", "revenue", "entity") == 1.0
    # Near-miss accepted by the 0.8 Levenshtein ratio.
    assert accuracy_score("revenu", "revenue", "entity") == 1.0
    # The threshold is pinned from both sides, so neither raising nor lowering
    # it leaves the suite green. Two edits in ten characters is a ratio of
    # exactly 0.8 and passes; two in nine is 0.778 and fails.
    assert accuracy_score("complionci", "compliance", "entity") == 1.0
    assert accuracy_score("allowinci", "allowance", "entity") == 0.0
    # Far enough away to fail.
    assert accuracy_score("costs", "revenue", "entity") == 0.0


def test_entity_path_scores_an_empty_gold_by_levenshtein_alone() -> None:
    """Characterization: an empty normalized gold skips the substring branch.

    `src/agent_native_content/generation/scoring.py:165` guards the substring test with
    `gold_norm and ...`, so an empty gold does not match every prediction. It
    falls through to Levenshtein, which scores 1.0 only against an equally empty
    prediction. `src/agent_native_content/generation/runner.py:170` maps a missing gold
    to `""`, so this is reachable. See deviation 1 in
    `docs/specs/evaluation.md`.
    """
    # Without the guard, "" is a substring of everything and this would be 1.0.
    assert accuracy_score("revenue", "", "entity") == 0.0
    assert accuracy_score("", "", "entity") == 1.0


def test_single_choice_matches_the_first_option_letter() -> None:
    """Characterization: `choice_exact_match` compares first `A`-`D` tokens.

    The raw prediction and gold are uppercased and searched with
    `\\b([A-D])\\b`; the first standalone letter on each side decides the
    score. This is wrong in both directions on free-text answers and is pinned
    so any change to the predicate is deliberate. See deviation 6 in
    `docs/specs/evaluation.md`.
    """
    # The intended case: a bare or lightly wrapped option letter.
    assert accuracy_score("C", "C", "single_choice") == 1.0
    assert accuracy_score("The answer is A", "A", "single_choice") == 1.0
    # False negative: reasoning that mentions another option first.
    assert (
        accuracy_score(
            "Option A is ruled out, so the answer is C", "C", "single_choice"
        )
        == 0.0
    )
    # False positive: an incidental capital letter precedes the real answer.
    assert (
        accuracy_score("Annex A shows X, so the answer is B", "A", "single_choice")
        == 1.0
    )
    # An option letter beyond `D` never matches and scores 0.0 silently, even
    # against itself. All 16 released golds are bare `A`-`D`.
    assert accuracy_score("E", "E", "single_choice") == 0.0
    # No option letter at all scores 0.0.
    assert accuracy_score("none of these", "A", "single_choice") == 0.0


def test_numeric_extraction_takes_the_first_number_anywhere() -> None:
    """Characterization: `_extract_number` is a first-number-anywhere scan.

    The tolerance in deviation 3 is applied to whatever this extraction returns.
    See deviation 7 in `docs/specs/evaluation.md`.
    """
    # First number anywhere wins, so a leading year defeats the real answer.
    assert accuracy_score("In 2023, revenue was 4.5 billion", "4.5", "numeric") == 0.0
    assert accuracy_score("In 2023, revenue was 4.5 billion", "2023", "numeric") == 1.0
    # Magnitude words are ignored: 4.5 billion and 4.5 are indistinguishable.
    assert accuracy_score("4.5 billion", "4.5", "numeric") == 1.0
    # A `%` is dropped rather than converted, on both sides, so a gold written
    # as a percentage does not match the same quantity written as a fraction.
    assert accuracy_score("42.9", "42.9%", "percentage") == 1.0
    assert accuracy_score("0.429", "42.9%", "percentage") == 0.0
    # A comma before at most two digits is a decimal separator; otherwise it is
    # a thousands separator.
    assert accuracy_score("1,23", "1.23", "numeric") == 1.0
    assert accuracy_score("1,234", "1234", "numeric") == 1.0
    assert accuracy_score("1,234", "1.234", "numeric") == 0.0
    # Powers and fractions are evaluated before the plain-number scan.
    assert accuracy_score("2^3", "8", "numeric") == 1.0
    assert accuracy_score("3/4", "0.75", "numeric") == 1.0
    # Text with no number scores 0.0 rather than raising.
    assert accuracy_score("no digits here", "4.5", "numeric") == 0.0


def _pinned_run(tmp_path: Path, provider, *, expected: str | None, run_id: str):
    retrieval = _run(tmp_path, run_id=f"retrieval-{run_id}")
    artifacts_root = tmp_path / "generation-artifacts"
    result = run_generation_benchmark(
        retrieval.path,
        _corpus(tmp_path).questions,
        config=_generation_config(),
        provider=provider,
        artifacts_root=artifacts_root,
        run_id=run_id,
        git_commit="b" * 40,
        git_dirty=False,
        clock=lambda: datetime(2026, 9, 20, tzinfo=UTC),
        expected_retrieval_artifact_sha256=expected,
    )
    return retrieval, artifacts_root, result


def test_a_mismatched_artifact_hash_is_refused_before_any_provider_call(
    tmp_path: Path,
) -> None:
    """A preregistered run over the wrong contexts must not spend anything.

    The count of provider requests is asserted, not just the exception: a check
    placed after the answer loop would still raise, and would still have paid.
    """
    retrieval = _run(tmp_path, run_id="retrieval-pin-mismatch")
    provider = FixtureProvider()
    artifacts_root = tmp_path / "generation-artifacts"
    wrong = "0" * 64
    actual = _artifact_hash(
        retrieval.path / "manifest.json", retrieval.path / "contexts.jsonl"
    )

    with pytest.raises(GenerationError) as refused:
        run_generation_benchmark(
            retrieval.path,
            _corpus(tmp_path).questions,
            config=_generation_config(),
            provider=provider,
            artifacts_root=artifacts_root,
            run_id="generation-pin-mismatch",
            git_commit="b" * 40,
            git_dirty=False,
            clock=lambda: datetime(2026, 9, 20, tzinfo=UTC),
            expected_retrieval_artifact_sha256=wrong,
        )

    assert provider.requests == []
    # Both hashes are named, so the operator can see which side is wrong.
    assert wrong in str(refused.value)
    assert actual in str(refused.value)
    # And nothing was written: no run directory, not even the parent.
    assert not artifacts_root.exists()


def test_a_matching_artifact_hash_runs_and_is_recorded_as_verified(
    tmp_path: Path,
) -> None:
    retrieval = _run(tmp_path, run_id="retrieval-pin-match")
    expected = _artifact_hash(
        retrieval.path / "manifest.json", retrieval.path / "contexts.jsonl"
    )
    provider = FixtureProvider()

    result = run_generation_benchmark(
        retrieval.path,
        _corpus(tmp_path).questions,
        config=_generation_config(),
        provider=provider,
        artifacts_root=tmp_path / "generation-artifacts",
        run_id="generation-pin-match",
        git_commit="b" * 40,
        git_dirty=False,
        clock=lambda: datetime(2026, 9, 20, tzinfo=UTC),
        expected_retrieval_artifact_sha256=expected,
    )

    assert len(provider.requests) == len(BenchmarkSystem)
    recorded = json.loads((result.path / "manifest.json").read_text())
    assert recorded["retrieval_artifact_sha256"] == expected
    assert recorded["expected_retrieval_artifact_sha256"] == expected
    assert recorded["retrieval_artifact_verified"] is True


def test_an_unchecked_run_is_unchanged_and_says_nothing_about_verification(
    tmp_path: Path,
) -> None:
    """No option, no check, and the manifest keeps its original layout."""
    provider = FixtureProvider()
    retrieval, _root, result = _pinned_run(
        tmp_path, provider, expected=None, run_id="generation-unchecked"
    )

    assert len(provider.requests) == len(BenchmarkSystem)
    recorded = json.loads((result.path / "manifest.json").read_text())
    assert "expected_retrieval_artifact_sha256" not in recorded
    assert "retrieval_artifact_verified" not in recorded
    # The recorded hash is still the published definition of the artifact
    # hash: the single read at the start hashes exactly what the old end-of-run
    # re-read would have.
    assert recorded["retrieval_artifact_sha256"] == _artifact_hash(
        retrieval.path / "manifest.json", retrieval.path / "contexts.jsonl"
    )


def test_eval_generation_passes_the_expected_hash_through(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The CLI option must reach the runner, or the guard is decoration."""
    from typer.testing import CliRunner

    from agent_native_content.cli import app

    captured = {}

    def fake_run_generation_benchmark(*args, **kwargs):
        captured.update(kwargs)
        raise GenerationError("stop after capture")

    monkeypatch.setattr(
        "agent_native_content.generation.run_generation_benchmark",
        fake_run_generation_benchmark,
    )
    monkeypatch.setattr(
        "agent_native_content.generation.OpenAIAnswerProvider",
        lambda **_kwargs: SimpleNamespace(),
    )
    # Keep the test off the local dataset cache: the CLI loads a subset and the
    # dataset only to build the question list, which this test never uses.
    monkeypatch.setattr("agent_native_content.cli.load_subset", lambda _path: None)
    monkeypatch.setattr(
        "agent_native_content.cli.XLDocBenchDataset",
        lambda _path: SimpleNamespace(iter_subset=lambda _subset: iter(())),
    )
    retrieval = _run(tmp_path, run_id="retrieval-cli-pin")

    result = CliRunner().invoke(
        app,
        [
            "eval-generation",
            str(retrieval.path),
            "--model",
            "fixture-model",
            "--input-usd-per-million",
            "0",
            "--cached-input-usd-per-million",
            "0",
            "--output-usd-per-million",
            "0",
            "--max-calls",
            "1000",
            "--expected-retrieval-artifact-sha256",
            "a" * 64,
        ],
    )

    assert captured.get("expected_retrieval_artifact_sha256") == "a" * 64, (
        result.output
    )


def _render_config(version: str):
    config = _config()
    return config.model_copy(
        update={
            "compiler": config.compiler.model_copy(
                update={"evidence_render_version": version}
            )
        }
    )


class CitingProvider(FixtureProvider):
    """Answers correctly and cites whatever labels it is told to."""

    def __init__(self, labels: tuple[str, ...]) -> None:
        super().__init__()
        self.labels = labels

    def generate(self, request: AnswerRequest, *, config: GenerationConfig):
        answer = super().generate(request, config=config)
        if request.system.endswith(":citation_entailment_judge"):
            return answer
        return answer.model_copy(
            update={
                "text": json.dumps(
                    {"answer": "revenue", "citations": list(self.labels)}
                )
            }
        )


def _generate(tmp_path: Path, retrieval, provider, run_id: str):
    return run_generation_benchmark(
        retrieval.path,
        _corpus(tmp_path).questions,
        config=_generation_config().model_copy(
            update={"systems": (BenchmarkSystem.COMPILER,)}
        ),
        provider=provider,
        artifacts_root=tmp_path / "generation-artifacts",
        run_id=run_id,
        git_commit="b" * 40,
        git_dirty=False,
        clock=lambda: datetime(2026, 9, 20, tzinfo=UTC),
    )


def _previous_answer_prompt(question: str, packet) -> str:
    """The v1 answer prompt exactly as it was built before render versions."""
    evidence = "\n\n".join(
        f'<evidence id="{item.evidence_id}">\n{item.content}\n</evidence>'
        for item in packet.items
    )
    return (
        f"{ANSWER_PROMPT_INSTRUCTIONS}\n\n"
        f"Question:\n{question}\n\nEvidence:\n{evidence}"
    )


@pytest.mark.parametrize("manifest_field", ["explicit", "absent"])
def test_v1_generation_prompts_are_byte_identical_to_before(
    tmp_path: Path, manifest_field: str
) -> None:
    """A v1 retrieval run -- or one predating the field -- renders as always.

    ``absent`` is the published Gate 2 case: its retrieval manifest has no
    render version, and its prompts must come out exactly as they did.
    """
    retrieval = _run(
        tmp_path, run_id=f"retrieval-v1-{manifest_field}",
        config=_render_config("evidence-render-v1"),
    )
    if manifest_field == "absent":
        manifest_path = retrieval.path / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        del manifest["config"]["compiler"]["evidence_render_version"]
        manifest_path.write_text(json.dumps(manifest))
    provider = FixtureProvider()

    result = _generate(tmp_path, retrieval, provider, f"v1-{manifest_field}")

    contexts = {
        (row["question_id"], row["system"], row["token_budget"]): row["context"]
        for row in map(
            json.loads, (retrieval.path / "contexts.jsonl").read_text().splitlines()
        )
    }
    question = _corpus(tmp_path).questions[0]
    # Premise: at least one prompt carries evidence, so this is not a
    # comparison of empty blocks.
    assert any(request.evidence_ids for request in provider.requests)
    for request in provider.requests:
        packet = ContextPacket.model_validate(
            contexts[(request.question_id, request.system, request.token_budget)]
        )
        assert request.prompt == _previous_answer_prompt(question.question, packet)
    recorded = json.loads((result.path / "manifest.json").read_text())
    assert recorded["evidence_render_version"] == "evidence-render-v1"
    assert recorded["prompt_sha256"] == hashlib.sha256(
        ANSWER_PROMPT_INSTRUCTIONS.encode("utf-8")
    ).hexdigest()


def test_v2_generation_shows_aliases_and_records_full_ids(tmp_path: Path) -> None:
    retrieval = _run(tmp_path, run_id="retrieval-v2-alias")
    provider = CitingProvider(("E1",))

    result = _generate(tmp_path, retrieval, provider, "v2-alias")

    (record,) = result.records
    (request,) = provider.requests
    assert '<evidence id="E1">' in request.prompt
    assert request.evidence_ids[0] not in request.prompt
    assert ANSWER_PROMPT_INSTRUCTIONS_ALIASED in request.prompt
    # The alias is mapped back: the record holds the full, provenance ID.
    assert record.citations == (request.evidence_ids[0],)
    assert record.citation_validity == 1
    recorded = json.loads((result.path / "manifest.json").read_text())
    retrieval_manifest = json.loads((retrieval.path / "manifest.json").read_text())
    assert recorded["evidence_render_version"] == "evidence-render-v2"
    assert (
        retrieval_manifest["config"]["compiler"]["evidence_render_version"]
        == "evidence-render-v2"
    )
    assert recorded["prompt_sha256"] == hashlib.sha256(
        ANSWER_PROMPT_INSTRUCTIONS_ALIASED.encode("utf-8")
    ).hexdigest()


def test_an_unknown_alias_scores_as_an_invalid_citation(tmp_path: Path) -> None:
    """Exactly as an unknown full ID always has."""
    retrieval = _run(tmp_path, run_id="retrieval-v2-unknown")
    provider = CitingProvider(("E1", "E99"))

    result = _generate(tmp_path, retrieval, provider, "v2-unknown")

    (record,) = result.records
    (request,) = provider.requests
    assert record.citations == (request.evidence_ids[0], "E99")
    assert record.citation_validity == 0.5


def test_citation_entailment_prompt_keeps_packet_aliases_and_v1_bytes() -> None:
    items = tuple(
        ContextItem(
            evidence_id=f"evidence_{index:064x}",
            document_id="doc",
            content=f"passage {index}",
            token_count=2,
            source_node_ids=("node",),
            source_item_ids=("#/texts/0",),
            scores=RetrievalScores(),
        )
        for index in range(3)
    )
    cited = (items[1],)
    previous = (
        f"{CITATION_ENTAILMENT_PROMPT_INSTRUCTIONS}\n\n"
        "Question:\nq\n\nAnswer:\na\n\n"
        f'Cited evidence:\n<evidence id="{items[1].evidence_id}">\n'
        "passage 1\n</evidence>"
    )

    assert render_citation_entailment_prompt("q", "a", cited) == previous
    aliased = render_citation_entailment_prompt(
        "q", "a", cited, labels={item.evidence_id: f"E{i + 1}" for i, item in
                                 enumerate(items)}
    )
    # The cited item keeps the alias the answer prompt showed it under.
    assert '<evidence id="E2">' in aliased
    assert items[1].evidence_id not in aliased
