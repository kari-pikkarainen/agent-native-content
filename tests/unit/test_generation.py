"""Generation prompt, provider, scoring, and artifact acceptance tests."""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_evaluation import _corpus, _run

from contextbench.evaluation import BenchmarkSystem
from contextbench.experiments import manifest
from contextbench.generation import (
    GenerationConfig,
    GenerationError,
    OpenAIAnswerProvider,
    PricingMetadata,
    ProviderAnswer,
    parse_answer_response,
    parse_citation_entailment_response,
    run_generation_benchmark,
)
from contextbench.generation.models import AnswerRequest
from contextbench.generation.scoring import accuracy_score, anls_score, token_f1_score


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
            text=json.dumps(
                {
                    "answer": "revenue",
                    "citations": [request.evidence_ids[0]],
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


def test_generation_runner_reuses_immutable_contexts_and_writes_costs(
    tmp_path: Path,
) -> None:
    retrieval = _run(tmp_path, run_id="retrieval-fixture")
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
    assert all(record.citation_validity == 1 for record in result.records)
    assert all(record.citation_support == 1 for record in result.records)
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
