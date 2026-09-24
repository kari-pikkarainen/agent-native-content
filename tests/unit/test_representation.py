"""Gold-page representation experiment acceptance tests."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_evaluation import _corpus
from test_ir import FixtureTokenCounter

from contextbench.evaluation import EvaluationCorpus
from contextbench.experiments import manifest
from contextbench.generation import AnswerRequest, PricingMetadata, ProviderAnswer
from contextbench.representation import (
    RepresentationCondition,
    RepresentationError,
    RepresentationExperimentConfig,
    run_gold_representation_benchmark,
)


class RepresentationProvider:
    name = "fixture"
    version = "1"

    def __init__(self) -> None:
        self.requests: list[AnswerRequest] = []

    def generate(self, request, *, config):
        self.requests.append(request)
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
            provider_usage={"total_tokens": 110},
        )


class IncompleteRepresentationProvider(RepresentationProvider):
    def generate(self, request, *, config):
        response = super().generate(request, config=config)
        if request.system == RepresentationCondition.IR.value:
            return response.model_copy(
                update={
                    "status": "incomplete",
                    "incomplete_reason": "max_output_tokens",
                }
            )
        return response


def _config() -> RepresentationExperimentConfig:
    return RepresentationExperimentConfig(
        model="fixture-model",
        pricing=PricingMetadata(
            input_usd_per_million=1,
            cached_input_usd_per_million=0.5,
            output_usd_per_million=2,
        ),
        tokenizer_name="fixture-words",
    )


def test_gold_representation_runner_varies_encoding_not_source_nodes(
    tmp_path: Path,
) -> None:
    base = _corpus(tmp_path)
    skipped = base.questions[0].model_copy(
        update={"id": "question-without-gold", "gold_evidence": ()}
    )
    corpus = EvaluationCorpus(
        questions=(*base.questions, skipped),
        documents=base.documents,
        source_documents=base.source_documents,
    )
    provider = RepresentationProvider()

    result = run_gold_representation_benchmark(
        corpus,
        config=_config(),
        provider=provider,
        artifacts_root=tmp_path / "artifacts",
        dataset="fixture",
        dataset_version="v1",
        dataset_revision="revision-1",
        subset_name="fixture-two",
        subset_sha256="1" * 64,
        run_id="representation-fixture",
        tokenizer=FixtureTokenCounter(),
        git_commit="c" * 40,
        git_dirty=False,
        clock=lambda: datetime(2026, 9, 20, tzinfo=UTC),
    )

    assert len(result.records) == len(RepresentationCondition)
    assert len(provider.requests) == len(RepresentationCondition)
    assert result.summary.evaluated_question_ids == ("question-1",)
    assert result.summary.skipped_question_ids == ("question-without-gold",)
    assert result.summary.enrichment_prepare_ms >= 0
    assert result.summary.amortized_enrichment_ms_per_question >= 0
    assert {record.condition for record in result.records} == set(
        RepresentationCondition
    )
    assert len({record.source_node_count for record in result.records}) == 1
    assert all(record.accuracy == 1 for record in result.records)
    assert all(record.citation_support == 1 for record in result.records)
    by_condition = {record.condition: record for record in result.records}
    assert by_condition[RepresentationCondition.RAW].feature_count == 0
    assert by_condition[RepresentationCondition.IR].feature_count == 0
    assert by_condition[RepresentationCondition.ENRICHED].feature_count > 0
    assert by_condition[RepresentationCondition.INDEXED].feature_count > 0
    assert by_condition[RepresentationCondition.RAW].representation_tokens < (
        by_condition[RepresentationCondition.IR].representation_tokens
    )
    assert by_condition[RepresentationCondition.IR].representation_tokens < (
        by_condition[RepresentationCondition.ENRICHED].representation_tokens
    )
    assert by_condition[RepresentationCondition.INDEXED].representation_tokens < (
        by_condition[RepresentationCondition.ENRICHED].representation_tokens
    )

    contexts = [
        json.loads(line)
        for line in (result.path / "contexts.jsonl").read_text().splitlines()
    ]
    assert len({tuple(row["evidence_ids"]) for row in contexts}) == 1
    rendered = {row["condition"]: row["representation"] for row in contexts}
    assert 'kind="paragraph"' not in rendered["raw"]
    assert 'kind="paragraph"' in rendered["ir"]
    assert "<agent_features>" in rendered["enriched"]
    assert "<agent_map" in rendered["indexed"]
    assert "<source_evidence>" in rendered["indexed"]
    assert rendered["enriched"].index('type="table_schema"') < rendered[
        "enriched"
    ].index('type="key_fact"')
    assert {path.name for path in result.path.iterdir()} == {
        "contexts.jsonl",
        "manifest.json",
        "report.md",
        "representation.jsonl",
        "summary.json",
    }
    manifest = json.loads((result.path / "manifest.json").read_text())
    assert manifest["provider"] == "fixture"
    assert manifest["git_commit"] == "c" * 40
    assert manifest["config"]["enrichment"]["summary_sentences"] == 2
    assert manifest["enrichment_prepare_ms"] >= 0


def test_representation_runner_reports_provider_incomplete_responses(
    tmp_path: Path,
) -> None:
    result = run_gold_representation_benchmark(
        _corpus(tmp_path),
        config=_config(),
        provider=IncompleteRepresentationProvider(),
        artifacts_root=tmp_path / "artifacts",
        dataset="fixture",
        dataset_version="v1",
        dataset_revision="revision-1",
        subset_name="fixture-two",
        subset_sha256="1" * 64,
        run_id="representation-incomplete",
        tokenizer=FixtureTokenCounter(),
        git_commit="c" * 40,
        git_dirty=False,
        clock=lambda: datetime(2026, 9, 20, tzinfo=UTC),
    )

    by_condition = {record.condition: record for record in result.records}
    incomplete = by_condition[RepresentationCondition.IR]
    assert incomplete.response_valid is False
    assert incomplete.provider_status == "incomplete"
    assert incomplete.provider_incomplete_reason == "max_output_tokens"
    assert incomplete.provider_text_error is None
    assert incomplete.accuracy == 0
    assert incomplete.token_f1 == 0
    assert incomplete.anls == 0

    summary_by_condition = {
        row.condition: row for row in result.summary.rows
    }
    assert summary_by_condition[RepresentationCondition.IR].response_valid_rate == 0
    assert summary_by_condition[RepresentationCondition.RAW].response_valid_rate == 1

    written = [
        json.loads(line)
        for line in (result.path / "representation.jsonl").read_text().splitlines()
    ]
    ir_row = next(row for row in written if row["condition"] == "ir")
    assert ir_row["response_valid"] is False
    assert ir_row["provider_status"] == "incomplete"
    assert ir_row["provider_incomplete_reason"] == "max_output_tokens"
    assert "Valid responses" in (result.path / "report.md").read_text()


def test_representation_runner_requires_at_least_one_gold_page(
    tmp_path: Path,
) -> None:
    base = _corpus(tmp_path)
    question = base.questions[0].model_copy(update={"gold_evidence": ()})
    corpus = EvaluationCorpus(
        questions=(question,),
        documents=base.documents,
        source_documents=base.source_documents,
    )

    with pytest.raises(RepresentationError, match="requires gold evidence pages"):
        run_gold_representation_benchmark(
            corpus,
            config=_config(),
            provider=RepresentationProvider(),
            artifacts_root=tmp_path / "artifacts",
            dataset="fixture",
            dataset_version="v1",
            dataset_revision="revision-1",
            subset_name="fixture-no-gold",
            subset_sha256="1" * 64,
            run_id="no-gold",
            tokenizer=FixtureTokenCounter(),
        )


def test_representation_dirty_worktree_is_refused_before_any_artifact_is_written(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider = RepresentationProvider()
    artifacts_root = tmp_path / "artifacts"

    monkeypatch.setattr(manifest, "current_git_commit", lambda: "d" * 40)
    monkeypatch.setattr(manifest, "current_git_dirty", lambda: True)

    with pytest.raises(RepresentationError, match="modified worktree"):
        run_gold_representation_benchmark(
            _corpus(tmp_path),
            config=_config(),
            provider=provider,
            artifacts_root=artifacts_root,
            dataset="fixture",
            dataset_version="v1",
            dataset_revision="revision-1",
            subset_name="fixture-two",
            subset_sha256="1" * 64,
            run_id="representation-dirty",
            tokenizer=FixtureTokenCounter(),
            git_commit=None,
            allow_dirty=False,
            clock=lambda: datetime(2026, 9, 20, tzinfo=UTC),
        )

    assert provider.requests == []
    assert not artifacts_root.exists()
