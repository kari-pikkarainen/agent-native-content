"""Gold-page representation experiment acceptance tests."""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_evaluation import _corpus
from test_ir import FixtureTokenCounter

from contextbench.evaluation import EvaluationCorpus
from contextbench.experiments import manifest
from contextbench.generation import AnswerRequest, PricingMetadata, ProviderAnswer
from contextbench.generation.runner import (
    ANSWER_EQUIVALENCE_PROMPT_INSTRUCTIONS,
    ANSWER_PROMPT_INSTRUCTIONS_ALIASED,
    CITATION_ENTAILMENT_PROMPT_INSTRUCTIONS,
)
from contextbench.representation import (
    DEFAULT_REPRESENTATION_CONDITIONS,
    RepresentationCondition,
    RepresentationError,
    RepresentationExperimentConfig,
    representation_call_ceiling,
    representation_prompt_hashes,
    run_gold_representation_benchmark,
)
from contextbench.retrieval.rendering import evidence_label


class RepresentationProvider:
    """Cites the first evidence item under the label the prompt showed it.

    Under v2 and v3 that is ``E1``; under v1 the full ID. The
    label is read from the rendering module, as a model would read it from the
    prompt, and the fixture checks the prompt really shows it.
    """

    name = "fixture"
    version = "1"

    def __init__(self) -> None:
        self.requests: list[AnswerRequest] = []
        # Full evidence ID -> label, from every answer prompt seen.
        self.labels: dict[str, str] = {}

    def _first_citation(self, request, config) -> list[str]:
        # question_only carries no evidence, so there is nothing to cite.
        if ":" in request.system or not request.evidence_ids:
            return []
        for index, evidence_id in enumerate(request.evidence_ids):
            self.labels[evidence_id] = evidence_label(
                evidence_id, index, config.evidence_render_version
            )
        label = self.labels[request.evidence_ids[0]]
        assert f'<evidence id="{label}"' in request.prompt
        return [label]

    def generate(self, request, *, config):
        self.requests.append(request)
        return ProviderAnswer(
            text=json.dumps(
                {
                    "answer": "revenue",
                    "citations": self._first_citation(request, config),
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


def _config(**overrides) -> RepresentationExperimentConfig:
    return RepresentationExperimentConfig(
        model="fixture-model",
        pricing=PricingMetadata(
            input_usd_per_million=1,
            cached_input_usd_per_million=0.5,
            output_usd_per_million=2,
        ),
        tokenizer_name="fixture-words",
        **overrides,
    )


EVIDENCE_CONDITIONS = (
    RepresentationCondition.RAW,
    RepresentationCondition.IR,
    RepresentationCondition.ENRICHED,
    RepresentationCondition.INDEXED,
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
        config=_config(conditions=tuple(RepresentationCondition)),
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
    by_condition = {record.condition: record for record in result.records}
    question_only = by_condition[RepresentationCondition.QUESTION_ONLY]
    assert question_only.source_node_count == 0
    assert question_only.feature_count == 0
    assert question_only.representation_tokens == 0
    assert question_only.citations == ()
    assert question_only.citation_present is False
    assert question_only.citation_support == 0
    evidence_records = [by_condition[condition] for condition in EVIDENCE_CONDITIONS]
    assert len({record.source_node_count for record in evidence_records}) == 1
    assert evidence_records[0].source_node_count > 0
    assert all(record.accuracy == 1 for record in result.records)
    assert all(record.citation_support == 1 for record in evidence_records)
    requests = {request.system: request for request in provider.requests}
    assert requests["question_only"].evidence_ids == ()
    assert "Evidence:\n" in requests["question_only"].prompt
    assert requests["question_only"].prompt.endswith("Evidence:\n")
    assert len({requests[c.value].evidence_ids for c in EVIDENCE_CONDITIONS}) == 1
    assert requests["raw"].evidence_ids
    # Without the equivalence judge a deterministic exact match classifies it.
    assert result.summary.question_only_correct_ids == ("question-1",)
    assert result.summary.question_only_incorrect_ids == ()
    assert result.summary.question_only_invalid_ids == ()
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
    evidence_rows = [row for row in contexts if row["condition"] != "question_only"]
    assert len({tuple(row["evidence_ids"]) for row in evidence_rows}) == 1
    rendered = {row["condition"]: row["representation"] for row in contexts}
    assert rendered["question_only"] == ""
    assert next(
        row["evidence_ids"] for row in contexts if row["condition"] == "question_only"
    ) == []
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
    # New runs label evidence with aliases, so the hash is of the aliased
    # answer instructions actually sent; disabled judges add no prompt hashes.
    assert manifest["evidence_render_version"] == "evidence-render-v3"
    assert manifest["config"]["evidence_render_version"] == "evidence-render-v3"
    assert manifest["prompt_sha256"] == hashlib.sha256(
        ANSWER_PROMPT_INSTRUCTIONS_ALIASED.encode("utf-8")
    ).hexdigest()
    assert requests["raw"].prompt.startswith(ANSWER_PROMPT_INSTRUCTIONS_ALIASED)
    assert "answer_equivalence_prompt_sha256" not in manifest
    assert "citation_entailment_prompt_sha256" not in manifest
    assert manifest["config"]["answer_equivalence_judge"] is False
    assert manifest["config"]["citation_entailment_judge"] is False


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


ANSWER_JUDGE = ":answer_equivalence_judge"
CITATION_JUDGE = ":citation_entailment_judge"
# One fixture call: (100 - 20) uncached, 20 cached and 10 output tokens.
CALL_COST = (80 * 1 + 20 * 0.5 + 10 * 2) / 1_000_000


class JudgedRepresentationProvider(RepresentationProvider):
    """Deterministic answerer plus both judges; never touches the network.

    Evidence-bearing conditions answer with a paraphrase that deterministic
    exact scoring rejects; question_only answers something wrong. The
    equivalence judge sees only the question and the two answers, so it
    decides from the candidate text, never from the condition.
    """

    def __init__(
        self,
        *,
        evidence_answer: str = "turnover",
        question_only_answer: str = "profit",
        answer_judge: dict[str, object] | None = None,
        citation_judge: dict[str, object] | None = None,
    ) -> None:
        super().__init__()
        self.evidence_answer = evidence_answer
        self.question_only_answer = question_only_answer
        self.answer_judge = answer_judge or {}
        self.citation_judge = citation_judge or {}

    def generate(self, request, *, config):
        response = super().generate(request, config=config)
        if request.system.endswith(ANSWER_JUDGE):
            payload = json.loads(request.prompt.split("Inputs:\n", 1)[1])
            text = json.dumps(
                {
                    "equivalent": payload["candidate_answer"] == "turnover",
                    "reason": "fixture",
                }
            )
            return response.model_copy(update={"text": text, **self.answer_judge})
        if request.system.endswith(CITATION_JUDGE):
            text = json.dumps(
                {
                    "entailed": all(
                        f'<evidence id="{self.labels[evidence_id]}">'
                        in request.prompt
                        for evidence_id in request.evidence_ids
                    ),
                    "reason": "fixture",
                }
            )
            return response.model_copy(
                update={"text": text, **self.citation_judge}
            )
        answer = (
            self.question_only_answer
            if request.system == RepresentationCondition.QUESTION_ONLY.value
            else self.evidence_answer
        )
        return response.model_copy(
            update={
                "text": json.dumps(
                    {
                        "answer": answer,
                        "citations": self._first_citation(request, config),
                    }
                )
            }
        )


def _run_judged(tmp_path: Path, provider, run_id: str, **overrides):
    return run_gold_representation_benchmark(
        _corpus(tmp_path),
        config=_config(
            **{
                "conditions": tuple(RepresentationCondition),
                "answer_equivalence_judge": True,
                "citation_entailment_judge": True,
                **overrides,
            }
        ),
        provider=provider,
        artifacts_root=tmp_path / "artifacts",
        dataset="fixture",
        dataset_version="v1",
        dataset_revision="revision-1",
        subset_name="fixture-two",
        subset_sha256="1" * 64,
        run_id=run_id,
        tokenizer=FixtureTokenCounter(),
        git_commit="c" * 40,
        git_dirty=False,
        clock=lambda: datetime(2026, 9, 20, tzinfo=UTC),
    )


def _systems(provider) -> list[str]:
    return [request.system for request in provider.requests]


def test_judges_score_a_paraphrase_that_exact_scoring_rejects(
    tmp_path: Path,
) -> None:
    provider = JudgedRepresentationProvider()

    result = _run_judged(tmp_path, provider, "representation-judged")

    systems = _systems(provider)
    for condition in EVIDENCE_CONDITIONS:
        assert systems.count(condition.value) == 1
        assert systems.count(condition.value + ANSWER_JUDGE) == 1
        assert systems.count(condition.value + CITATION_JUDGE) == 1
    assert systems.count("question_only") == 1
    assert systems.count("question_only" + ANSWER_JUDGE) == 1
    # No evidence, no citation, no citation judge call.
    assert "question_only" + CITATION_JUDGE not in systems
    assert len(provider.requests) == 14
    assert len(provider.requests) <= representation_call_ceiling(
        1, _config(
            conditions=tuple(RepresentationCondition),
            answer_equivalence_judge=True,
            citation_entailment_judge=True,
        )
    )

    # The equivalence judge is blind to the representation and the evidence.
    for request in provider.requests:
        if request.system.endswith(ANSWER_JUDGE):
            assert request.evidence_ids == ()
            assert "<evidence" not in request.prompt
            for condition in RepresentationCondition:
                assert not re.search(rf"\b{condition.value}\b", request.prompt)
    cited = {
        request.system: request
        for request in provider.requests
        if request.system.endswith(CITATION_JUDGE)
    }
    raw_answer_request = next(r for r in provider.requests if r.system == "raw")
    assert cited["raw" + CITATION_JUDGE].evidence_ids == (
        raw_answer_request.evidence_ids[0],
    )

    by_condition = {record.condition: record for record in result.records}
    for condition in EVIDENCE_CONDITIONS:
        record = by_condition[condition]
        assert record.parsed_answer == "turnover"
        assert record.accuracy == 0  # historical deterministic metric kept
        assert record.semantic_accuracy == 1
        assert record.answer_equivalence_judge_valid is True
        assert record.citation_entailment == 1
        assert record.citation_entailment_judge_valid is True
        assert record.citation_support == 1
        assert record.calls == 3
        assert record.input_tokens == 300
        assert record.cached_input_tokens == 60
        assert record.output_tokens == 30
        assert record.cost_usd == pytest.approx(3 * CALL_COST)
        assert set(record.provider_usage) == {
            "answer",
            "answer_equivalence_judge",
            "citation_entailment_judge",
        }
    question_only = by_condition[RepresentationCondition.QUESTION_ONLY]
    assert question_only.parsed_answer == "profit"
    assert question_only.accuracy == 0
    assert question_only.semantic_accuracy == 0
    assert question_only.answer_equivalence_judge_valid is True
    assert question_only.citation_entailment == 0
    assert question_only.citation_entailment_judge_valid is None
    assert question_only.calls == 2
    assert question_only.input_tokens == 200
    assert question_only.cost_usd == pytest.approx(2 * CALL_COST)
    assert question_only.provider_usage["citation_entailment_judge"] is None

    rows = {row.condition: row for row in result.summary.rows}
    for condition in EVIDENCE_CONDITIONS:
        row = rows[condition]
        assert row.mean_accuracy == 0
        assert row.mean_semantic_accuracy == 1
        assert row.answer_equivalence_judge_valid_rate == 1
        assert row.citation_entailment_judge_valid_rate == 1
        assert row.mean_citation_entailment == 1
        assert row.mean_calls == 3
        assert row.mean_input_tokens == 300
        assert row.mean_output_tokens == 30
        assert row.dollars_per_query == pytest.approx(3 * CALL_COST)
        assert row.dollars_per_correct is None
        assert row.dollars_per_semantic_correct == pytest.approx(3 * CALL_COST)
    question_only_row = rows[RepresentationCondition.QUESTION_ONLY]
    assert question_only_row.mean_semantic_accuracy == 0
    assert question_only_row.answer_equivalence_judge_valid_rate == 1
    assert question_only_row.citation_entailment_judge_valid_rate is None
    assert question_only_row.mean_calls == 2
    assert question_only_row.dollars_per_semantic_correct is None
    assert result.summary.question_only_correct_ids == ()
    assert result.summary.question_only_incorrect_ids == ("question-1",)
    assert result.summary.question_only_invalid_ids == ()

    manifest = json.loads((result.path / "manifest.json").read_text())
    assert manifest["prompt_sha256"] == hashlib.sha256(
        ANSWER_PROMPT_INSTRUCTIONS_ALIASED.encode("utf-8")
    ).hexdigest()
    assert manifest["answer_equivalence_prompt_sha256"] == hashlib.sha256(
        ANSWER_EQUIVALENCE_PROMPT_INSTRUCTIONS.encode("utf-8")
    ).hexdigest()
    assert manifest["citation_entailment_prompt_sha256"] == hashlib.sha256(
        CITATION_ENTAILMENT_PROMPT_INSTRUCTIONS.encode("utf-8")
    ).hexdigest()
    assert manifest["config"]["answer_equivalence_judge"] is True
    assert manifest["config"]["citation_entailment_judge"] is True
    report = (result.path / "report.md").read_text()
    assert (
        "Question-only correct: 0; incorrect: 1; abstained: 0; invalid: 0."
        in report
    )
    for heading in (
        "Semantic accuracy",
        "Token F1",
        "ANLS",
        "Citation support",
        "## Answer-call efficiency (representation comparison)",
        "## All calls (answer plus judges)",
        "Citation entailment is over non-abstaining cells only",
    ):
        assert heading in report
    # Answer-only efficiency excludes judge overhead; totals include it.
    for condition in EVIDENCE_CONDITIONS:
        record = by_condition[condition]
        assert record.answer_cost_usd == pytest.approx(CALL_COST)
        assert record.judge_cost_usd == pytest.approx(2 * CALL_COST)
        assert record.answer_input_tokens == 100
        assert record.judge_calls == 2
        assert record.judge_input_tokens == 200
        row = rows[condition]
        assert row.answer_dollars_per_query == pytest.approx(CALL_COST)
        assert row.answer_dollars_per_semantic_correct == pytest.approx(CALL_COST)
        assert row.answer_dollars_per_correct is None
        assert row.mean_answer_input_tokens == 100
        assert row.mean_judge_calls == 2
        assert row.judge_dollars_per_query == pytest.approx(2 * CALL_COST)


def test_truncated_and_malformed_judges_never_count_as_correct_or_entailed(
    tmp_path: Path,
) -> None:
    provider = JudgedRepresentationProvider(
        # Valid JSON saying "equivalent", but the provider cut it off.
        answer_judge={"status": "incomplete", "incomplete_reason": "max_tokens"},
        citation_judge={"text": "yes, it is supported"},
    )

    result = _run_judged(tmp_path, provider, "representation-invalid-judges")

    by_condition = {record.condition: record for record in result.records}
    for condition in EVIDENCE_CONDITIONS:
        record = by_condition[condition]
        assert record.response_valid is True
        assert record.answer_equivalence_judge_valid is False
        assert record.semantic_accuracy == 0
        assert record.answer_judge_provider_status == "incomplete"
        assert record.answer_judge_provider_incomplete_reason == "max_tokens"
        assert '"equivalent": true' in record.answer_equivalence_judge_raw_response
        assert record.citation_entailment_judge_valid is False
        assert record.citation_entailment == 0
        assert record.citation_entailment_judge_raw_response == (
            "yes, it is supported"
        )
        # Invalid judge calls are still paid and counted.
        assert record.calls == 3
        assert record.cost_usd == pytest.approx(3 * CALL_COST)
    rows = {row.condition: row for row in result.summary.rows}
    for condition in EVIDENCE_CONDITIONS:
        assert rows[condition].answer_equivalence_judge_valid_rate == 0
        assert rows[condition].citation_entailment_judge_valid_rate == 0
        assert rows[condition].mean_semantic_accuracy == 0
        assert rows[condition].mean_citation_entailment == 0
        assert rows[condition].dollars_per_semantic_correct is None
    # An unjudgeable question-only answer is invalid, not incorrect.
    assert result.summary.question_only_invalid_ids == ("question-1",)
    assert result.summary.question_only_correct_ids == ()
    assert result.summary.question_only_incorrect_ids == ()


def test_abstentions_are_never_sent_to_either_judge(tmp_path: Path) -> None:
    class AbstainingProvider(JudgedRepresentationProvider):
        def generate(self, request, *, config):
            response = super().generate(request, config=config)
            if ":" in request.system:
                return response
            # Cite evidence anyway: an abstention must not reach the
            # entailment judge even when it carries citations.
            return response.model_copy(
                update={
                    "text": json.dumps(
                        {
                            "answer": "INSUFFICIENT_EVIDENCE",
                            "citations": list(request.evidence_ids[:1]),
                        }
                    )
                }
            )

    provider = AbstainingProvider()

    result = _run_judged(tmp_path, provider, "representation-abstain")

    assert all(":" not in system for system in _systems(provider))
    assert len(provider.requests) == len(RepresentationCondition)
    for record in result.records:
        assert record.abstained is True
        assert record.calls == 1
        # The fixture question is answerable, so abstaining is incorrect.
        assert record.semantic_accuracy == 0
        assert record.answer_equivalence_judge_valid is None
        assert record.citation_entailment is None
        assert record.citation_entailment_judge_valid is None
    rows = {row.condition: row for row in result.summary.rows}
    assert all(row.answer_rate == 0 for row in rows.values())
    assert all(row.answer_equivalence_judge_valid_rate is None for row in rows.values())
    assert all(row.mean_citation_entailment is None for row in rows.values())
    # A compliant abstention on an empty evidence section is its own bucket.
    assert result.summary.question_only_abstained_ids == ("question-1",)
    assert result.summary.question_only_incorrect_ids == ()
    assert result.summary.question_only_correct_ids == ()
    assert result.summary.question_only_invalid_ids == ()
    assert "abstained: 1" in (result.path / "report.md").read_text()


def test_bare_marker_without_json_is_an_abstention(tmp_path: Path) -> None:
    class BareMarkerProvider(JudgedRepresentationProvider):
        def generate(self, request, *, config):
            response = super().generate(request, config=config)
            if ":" in request.system:
                return response
            # A local model answering with the marker alone, no JSON.
            return response.model_copy(update={"text": "\nINSUFFICIENT_EVIDENCE\n"})

    provider = BareMarkerProvider()

    result = _run_judged(tmp_path, provider, "representation-bare-abstain")

    assert all(":" not in system for system in _systems(provider))
    assert len(provider.requests) == len(RepresentationCondition)
    for record in result.records:
        assert record.response_valid is True
        assert record.abstained is True
        assert record.calls == 1
        assert record.answer_equivalence_judge_valid is None
        assert record.citation_entailment is None
        assert record.citation_entailment_judge_valid is None
    assert result.summary.question_only_abstained_ids == ("question-1",)
    assert result.summary.question_only_invalid_ids == ()


def test_only_the_exact_marker_is_an_abstention(tmp_path: Path) -> None:
    provider = JudgedRepresentationProvider(
        evidence_answer="insufficient evidence to say, but probably revenue"
    )

    result = _run_judged(tmp_path, provider, "representation-near-abstain")

    raw = next(r for r in result.records if r.condition == RepresentationCondition.RAW)
    assert raw.abstained is False
    assert "raw" + ANSWER_JUDGE in _systems(provider)
    assert "raw" + CITATION_JUDGE in _systems(provider)


@pytest.mark.parametrize(
    ("answer_judge", "citation_judge", "expected"),
    ((False, False, 10), (True, False, 20), (False, True, 20), (True, True, 30)),
)
def test_call_ceiling_counts_every_enabled_judge_for_every_cell(
    answer_judge: bool,
    citation_judge: bool,
    expected: int,
) -> None:
    config = _config(
        conditions=tuple(RepresentationCondition),
        answer_equivalence_judge=answer_judge,
        citation_entailment_judge=citation_judge,
    )

    assert representation_call_ceiling(2, config) == expected
    hashes = representation_prompt_hashes(config)
    assert ("answer_equivalence_prompt_sha256" in hashes) is answer_judge
    assert ("citation_entailment_prompt_sha256" in hashes) is citation_judge


def test_default_conditions_keep_question_only_opt_in() -> None:
    assert _config().conditions == DEFAULT_REPRESENTATION_CONDITIONS
    assert RepresentationCondition.QUESTION_ONLY not in _config().conditions


def _gold_question():
    from contextbench.datasets.base import BenchmarkQuestion, GoldEvidence

    return BenchmarkQuestion(
        id="question-1",
        question="Which target increased?",
        document_ids=("dataset-doc-1",),
        gold_answer="revenue",
        answer_format="short_text",
        verification_rule="exact",
        gold_evidence=(
            GoldEvidence(
                document_id="dataset-doc-1",
                pages=(1,),
                page_numbering="pdf_index",
            ),
        ),
        answerable=True,
        task_type="single_doc",
    )


def _invoke_eval_representation(monkeypatch, *args: str):
    from types import SimpleNamespace

    from typer.testing import CliRunner

    from contextbench.cli import app

    captured: dict[str, object] = {}
    provider_constructions: list[object] = []

    def fake_run(**kwargs):
        captured.update(kwargs)
        raise RepresentationError("stop after capture")

    def forbidden_provider(**_kwargs):
        provider_constructions.append(object())
        return SimpleNamespace()

    monkeypatch.setattr("contextbench.cli.download_release", lambda _path: None)
    monkeypatch.setattr("contextbench.cli.load_subset", lambda _path: None)
    monkeypatch.setattr(
        "contextbench.cli.XLDocBenchDataset",
        lambda _path: SimpleNamespace(
            iter_subset=lambda _subset: iter((_gold_question(), _gold_question()))
        ),
    )
    monkeypatch.setattr(
        "contextbench.representation.run_xl_gold_representation", fake_run
    )
    monkeypatch.setattr(
        "contextbench.generation.OpenAIAnswerProvider", forbidden_provider
    )
    result = CliRunner().invoke(
        app,
        [
            "eval-representation",
            "--model",
            "fixture-model",
            "--input-usd-per-million",
            "0",
            "--cached-input-usd-per-million",
            "0",
            "--output-usd-per-million",
            "0",
            *args,
        ],
    )
    return result, captured, provider_constructions


ALL_CONDITION_ARGS = tuple(
    arg
    for condition in RepresentationCondition
    for arg in ("--condition", condition.value)
)


def test_eval_representation_refuses_when_judges_exceed_the_ceiling(
    monkeypatch,
) -> None:
    # 2 questions x 5 conditions x (1 answer + 2 judges) = 30 calls.
    result, captured, constructions = _invoke_eval_representation(
        monkeypatch,
        *ALL_CONDITION_ARGS,
        "--answer-equivalence-judge",
        "--citation-entailment-judge",
        "--max-calls",
        "29",
    )

    assert result.exit_code != 0
    assert "run requires 30 calls, above --max-calls 29" in result.output
    assert captured == {}
    assert constructions == []


def test_eval_representation_passes_judges_within_the_ceiling(monkeypatch) -> None:
    result, captured, _ = _invoke_eval_representation(
        monkeypatch,
        *ALL_CONDITION_ARGS,
        "--answer-equivalence-judge",
        "--citation-entailment-judge",
        "--max-calls",
        "30",
    )

    config = captured.get("config")
    assert config is not None, result.output
    assert config.conditions == tuple(RepresentationCondition)
    assert config.answer_equivalence_judge is True
    assert config.citation_entailment_judge is True


def test_eval_representation_defaults_are_unchanged(monkeypatch) -> None:
    # 2 questions x 4 default conditions x 1 call: judges off by default.
    refused, _, _ = _invoke_eval_representation(monkeypatch, "--max-calls", "7")
    assert "run requires 8 calls, above --max-calls 7" in refused.output

    result, captured, _ = _invoke_eval_representation(monkeypatch, "--max-calls", "8")
    config = captured.get("config")
    assert config is not None, result.output
    assert config.conditions == DEFAULT_REPRESENTATION_CONDITIONS
    assert config.answer_equivalence_judge is False
    assert config.citation_entailment_judge is False


def test_answer_only_efficiency_excludes_judge_calls(tmp_path: Path) -> None:
    """Two conditions differing only in judge calls cost the same to answer."""

    class UncitedIRProvider(JudgedRepresentationProvider):
        def generate(self, request, *, config):
            response = super().generate(request, config=config)
            if request.system != RepresentationCondition.IR.value:
                return response
            # Same answer, no citation: IR gets no citation-judge call.
            return response.model_copy(
                update={"text": json.dumps({"answer": "turnover", "citations": []})}
            )

    provider = UncitedIRProvider()

    result = _run_judged(
        tmp_path,
        provider,
        "representation-judge-overhead",
        conditions=(RepresentationCondition.RAW, RepresentationCondition.IR),
    )

    by_condition = {record.condition: record for record in result.records}
    raw = by_condition[RepresentationCondition.RAW]
    ir = by_condition[RepresentationCondition.IR]
    assert (raw.judge_calls, ir.judge_calls) == (2, 1)
    assert raw.answer_cost_usd == ir.answer_cost_usd == pytest.approx(CALL_COST)
    assert raw.answer_input_tokens == ir.answer_input_tokens == 100
    assert raw.answer_output_tokens == ir.answer_output_tokens == 10
    assert raw.cost_usd == pytest.approx(3 * CALL_COST)
    assert ir.cost_usd == pytest.approx(2 * CALL_COST)
    for record in (raw, ir):
        assert record.cost_usd == pytest.approx(
            record.answer_cost_usd + record.judge_cost_usd
        )
        assert record.latency_ms == pytest.approx(
            record.answer_latency_ms + record.judge_latency_ms
        )
        assert record.input_tokens == (
            record.answer_input_tokens + record.judge_input_tokens
        )

    rows = {row.condition: row for row in result.summary.rows}
    raw_row = rows[RepresentationCondition.RAW]
    ir_row = rows[RepresentationCondition.IR]
    assert raw_row.answer_dollars_per_query == ir_row.answer_dollars_per_query
    assert raw_row.mean_answer_input_tokens == ir_row.mean_answer_input_tokens
    assert raw_row.mean_answer_output_tokens == ir_row.mean_answer_output_tokens
    assert (
        raw_row.answer_dollars_per_semantic_correct
        == ir_row.answer_dollars_per_semantic_correct
    )
    assert raw_row.dollars_per_query > ir_row.dollars_per_query
    assert raw_row.mean_input_tokens > ir_row.mean_input_tokens
    assert raw_row.mean_judge_calls == 2
    assert ir_row.mean_judge_calls == 1


def test_citation_judge_sees_canonical_node_text_in_every_condition(
    tmp_path: Path,
) -> None:
    provider = JudgedRepresentationProvider()

    _run_judged(tmp_path, provider, "representation-canonical-citation")

    prompts = {
        request.system.removesuffix(CITATION_JUDGE): request.prompt
        for request in provider.requests
        if request.system.endswith(CITATION_JUDGE)
    }
    assert set(prompts) == {condition.value for condition in EVIDENCE_CONDITIONS}
    # Same cited node, same prompt: the rendering never reaches the judge.
    assert len(set(prompts.values())) == 1
    prompt = prompts["raw"]
    assert "<agent_features>" not in prompt
    assert "<agent_map" not in prompt
    assert 'kind="paragraph"' not in prompt
