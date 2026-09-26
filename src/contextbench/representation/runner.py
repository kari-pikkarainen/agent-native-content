"""Gold-page representation experiment orchestration."""

import hashlib
import html
import json
import re
import shutil
import tempfile
import time
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean

from contextbench.agentdoc import (
    AgentDocument,
    AgentFeatureKind,
    enrich_document,
    feature_type_counts,
    features_for_nodes,
    select_agent_features,
)
from contextbench.datasets.base import BenchmarkQuestion
from contextbench.evaluation.runner import EvaluationCorpus
from contextbench.experiments import resolve_git_state, utc_now
from contextbench.generation import (
    ANSWER_EQUIVALENCE_PROMPT_INSTRUCTIONS,
    AnswerProvider,
    AnswerRequest,
    ProviderAnswer,
    is_abstention,
    parse_answer_equivalence_response,
    parse_answer_response,
    parse_citation_entailment_response,
    render_answer_equivalence_prompt,
    render_citation_entailment_prompt_from_blocks,
    render_grounded_prompt,
    response_cost,
)
from contextbench.generation.runner import (
    ANSWER_PROMPT_INSTRUCTIONS,
    CITATION_ENTAILMENT_PROMPT_INSTRUCTIONS,
)
from contextbench.generation.scoring import (
    accuracy_score,
    anls_score,
    answer_type,
    token_f1_score,
)
from contextbench.ir.models import IRNode, IRNodeKind
from contextbench.ir.tokenizer import TiktokenTokenCounter, TokenCounter
from contextbench.representation.models import (
    RepresentationBenchmarkSummary,
    RepresentationCondition,
    RepresentationEvaluationRecord,
    RepresentationExperimentConfig,
    RepresentationSummaryRow,
)


class RepresentationError(RuntimeError):
    """Raised when a representation experiment cannot run reproducibly."""


@dataclass(frozen=True)
class RepresentationRun:
    """Completed immutable representation experiment."""

    path: Path
    summary: RepresentationBenchmarkSummary
    records: tuple[RepresentationEvaluationRecord, ...]


@dataclass(frozen=True)
class _EvidenceNode:
    dataset_document_id: str
    evidence_id: str
    node: IRNode


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def representation_prompt_hashes(
    config: RepresentationExperimentConfig,
) -> dict[str, str]:
    """Hash every fixed prompt template a run can send to the provider.

    ``prompt_sha256`` keeps its historical meaning (the answer instructions)
    so earlier manifests stay comparable. A judge's hash is present only when
    that judge is enabled, so a run's config plus Git SHA identifies exactly
    which prompt templates could have been used.
    """
    hashes = {"prompt_sha256": _sha256_text(ANSWER_PROMPT_INSTRUCTIONS)}
    if config.answer_equivalence_judge:
        hashes["answer_equivalence_prompt_sha256"] = _sha256_text(
            ANSWER_EQUIVALENCE_PROMPT_INSTRUCTIONS
        )
    if config.citation_entailment_judge:
        hashes["citation_entailment_prompt_sha256"] = _sha256_text(
            CITATION_ENTAILMENT_PROMPT_INSTRUCTIONS
        )
    return hashes


def representation_call_ceiling(
    eligible_questions: int,
    config: RepresentationExperimentConfig,
) -> int:
    """Return the most provider calls a run can make.

    Every enabled judge is counted for every cell even though abstentions,
    invalid answers and uncited answers skip it, so authorization is
    conservative: actual calls can be fewer, never more.
    """
    if eligible_questions < 0:
        raise ValueError("eligible_questions cannot be negative")
    calls_per_cell = (
        1
        + int(config.answer_equivalence_judge)
        + int(config.citation_entailment_judge)
    )
    return eligible_questions * len(config.conditions) * calls_per_cell


def _generate(
    provider: AnswerProvider,
    request: AnswerRequest,
    *,
    config: RepresentationExperimentConfig,
    cell: str,
) -> tuple[ProviderAnswer, float]:
    """Make one measured provider call with a cell-specific failure message."""
    started = time.perf_counter_ns()
    try:
        response = provider.generate(request, config=config)
    except Exception as exc:
        # A provider exception still aborts the all-or-nothing run. Durable
        # partial paid artifacts are a separate design change; the call limit
        # keeps this experiment deliberately small until that exists.
        raise RepresentationError(f"provider failed for {cell}: {exc}") from exc
    return response, (time.perf_counter_ns() - started) / 1_000_000


def run_gold_representation_benchmark(
    corpus: EvaluationCorpus,
    *,
    config: RepresentationExperimentConfig,
    provider: AnswerProvider,
    artifacts_root: Path,
    dataset: str,
    dataset_version: str,
    dataset_revision: str,
    subset_name: str,
    subset_sha256: str,
    run_id: str | None = None,
    tokenizer: TokenCounter | None = None,
    git_commit: str | None = None,
    git_dirty: bool | None = None,
    allow_dirty: bool = False,
    clock: Callable[[], datetime] = utc_now,
) -> RepresentationRun:
    """Compare encodings of identical gold evidence without retrieval.

    Every evidence-bearing condition renders the same gold-page source nodes;
    ``question_only`` renders none and measures what the model answers from
    the question alone.

    Supplying ``git_commit`` means the caller owns the recorded provenance: the
    worktree is not inspected, so ``git_dirty`` must be supplied too.
    """
    counter = tokenizer or TiktokenTokenCounter(config.tokenizer_name)
    eligible = tuple(
        question for question in corpus.questions if _has_gold_pages(question)
    )
    skipped = tuple(
        question for question in corpus.questions if not _has_gold_pages(question)
    )
    if not eligible:
        raise RepresentationError(
            "representation benchmark requires gold evidence pages"
        )
    required_documents = {
        document_id
        for question in eligible
        for document_id in question.gold_evidence_pages
    }
    missing_documents = required_documents.difference(corpus.documents)
    if missing_documents:
        raise RepresentationError(
            f"corpus is missing gold documents: {sorted(missing_documents)}"
        )

    created_at = clock()
    config_value = config.model_dump(mode="json")
    config_sha256 = _json_hash(config_value)
    resolved_run_id = run_id or (
        f"representation-{created_at.strftime('%Y%m%dT%H%M%SZ')}-"
        f"{config_sha256[:12]}"
    )
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", resolved_run_id):
        raise RepresentationError("run_id contains unsafe path characters")
    final_path = artifacts_root / "representation-runs" / resolved_run_id
    if final_path.exists():
        raise RepresentationError(f"completed run already exists: {final_path}")
    resolved_commit, resolved_dirty = resolve_git_state(
        git_commit=git_commit,
        git_dirty=git_dirty,
        allow_dirty=allow_dirty,
        error=RepresentationError,
    )

    enrichment_started = time.perf_counter_ns()
    enrichments: dict[str, AgentDocument] = {}
    enrichment_document_ms: dict[str, float] = {}
    for dataset_document_id in sorted(required_documents):
        document = corpus.documents[dataset_document_id]
        document_started = time.perf_counter_ns()
        enrichments[document.id] = enrich_document(
            document, config=config.enrichment
        )
        enrichment_document_ms[dataset_document_id] = (
            time.perf_counter_ns() - document_started
        ) / 1_000_000
    enrichment_prepare_ms = (
        time.perf_counter_ns() - enrichment_started
    ) / 1_000_000
    records: list[RepresentationEvaluationRecord] = []
    contexts: list[dict[str, object]] = []
    for question in eligible:
        evidence_nodes = _gold_evidence_nodes(question, corpus)
        if not evidence_nodes:
            raise RepresentationError(
                f"question {question.id} has gold pages but no projected nodes"
            )
        for condition in config.conditions:
            condition_nodes = (
                ()
                if condition == RepresentationCondition.QUESTION_ONLY
                else evidence_nodes
            )
            representation, feature_count = render_representation(
                condition,
                condition_nodes,
                query=question.question,
                enrichments=enrichments,
                inline_feature_kinds=set(config.inline_feature_kinds),
                max_inline_features=config.max_inline_features,
                indexed_max_features=config.indexed_max_features,
                indexed_feature_token_budget=config.indexed_feature_token_budget,
                tokenizer=counter,
            )
            prompt = render_grounded_prompt(question.question, representation)
            evidence_ids = tuple(item.evidence_id for item in condition_nodes)
            request = AnswerRequest(
                question_id=question.id,
                system=condition.value,
                prompt=prompt,
                evidence_ids=evidence_ids,
            )
            response, answer_latency_ms = _generate(
                provider,
                request,
                config=config,
                cell=f"{question.id}/{condition.value}",
            )
            parsed_answer, citations, parsed_valid = parse_answer_response(
                response.text
            )
            # A response the provider did not complete is a failed call, not a
            # wrong answer. Keep the paid cell, its usage and diagnostics, but
            # score it zero and expose the failure in the condition summary.
            response_valid = parsed_valid and response.provider_valid
            abstained = response_valid and is_abstention(parsed_answer)
            gold = "" if question.gold_answer is None else str(question.gold_answer)
            kind = answer_type(question)
            accuracy = (
                accuracy_score(parsed_answer, gold, kind) if response_valid else 0.0
            )
            token_f1 = (
                token_f1_score(parsed_answer, gold) if response_valid else 0.0
            )
            anls = anls_score(parsed_answer, gold) if response_valid else 0.0
            valid_ids = set(evidence_ids)
            valid_citations = sum(citation in valid_ids for citation in citations)
            citation_score = valid_citations / len(citations) if citations else 0.0

            answer_judge_response: ProviderAnswer | None = None
            answer_judge_valid: bool | None = None
            answer_judge_reason: str | None = None
            answer_judge_raw: str | None = None
            semantic_accuracy: float | None = None
            answer_judge_latency_ms = 0.0
            if config.answer_equivalence_judge:
                semantic_accuracy = 0.0
                if abstained:
                    # The exact abstention marker has no content to compare:
                    # it is correct exactly when the question is unanswerable.
                    # Deciding that deterministically avoids a paid call and
                    # keeps the judge from ever grading an abstention.
                    semantic_accuracy = float(not question.answerable)
                elif response_valid:
                    answer_judge_request = AnswerRequest(
                        question_id=question.id,
                        system=f"{condition.value}:answer_equivalence_judge",
                        prompt=render_answer_equivalence_prompt(
                            question.question,
                            gold,
                            parsed_answer,
                        ),
                        evidence_ids=(),
                    )
                    answer_judge_response, answer_judge_latency_ms = _generate(
                        provider,
                        answer_judge_request,
                        config=config,
                        cell=(
                            f"{question.id}/{condition.value}/"
                            "answer_equivalence_judge"
                        ),
                    )
                    answer_judge_raw = answer_judge_response.text
                    equivalent, answer_judge_reason, judge_parsed = (
                        parse_answer_equivalence_response(answer_judge_raw)
                    )
                    answer_judge_valid = (
                        judge_parsed and answer_judge_response.provider_valid
                    )
                    semantic_accuracy = float(equivalent) if answer_judge_valid else 0.0

            citation_judge_response: ProviderAnswer | None = None
            citation_judge_valid: bool | None = None
            citation_judge_reason: str | None = None
            citation_judge_raw: str | None = None
            citation_entailment: float | None = None
            citation_judge_latency_ms = 0.0
            if config.citation_entailment_judge and not abstained:
                citation_entailment = 0.0
                node_by_evidence_id = {
                    item.evidence_id: item for item in condition_nodes
                }
                cited_nodes = tuple(
                    node_by_evidence_id[citation]
                    for citation in citations
                    if citation in node_by_evidence_id
                )
                if response_valid and citations and cited_nodes:
                    citation_judge_request = AnswerRequest(
                        question_id=question.id,
                        system=f"{condition.value}:citation_entailment_judge",
                        prompt=render_citation_entailment_prompt_from_blocks(
                            question.question,
                            parsed_answer,
                            (
                                (item.evidence_id, item.node.text)
                                for item in cited_nodes
                            ),
                        ),
                        evidence_ids=tuple(
                            item.evidence_id for item in cited_nodes
                        ),
                    )
                    citation_judge_response, citation_judge_latency_ms = _generate(
                        provider,
                        citation_judge_request,
                        config=config,
                        cell=(
                            f"{question.id}/{condition.value}/"
                            "citation_entailment_judge"
                        ),
                    )
                    citation_judge_raw = citation_judge_response.text
                    entailed, citation_judge_reason, judge_parsed = (
                        parse_citation_entailment_response(citation_judge_raw)
                    )
                    citation_judge_valid = (
                        judge_parsed and citation_judge_response.provider_valid
                    )
                    citation_entailment = (
                        float(entailed) if citation_judge_valid else 0.0
                    )

            responses = tuple(
                value
                for value in (
                    response,
                    answer_judge_response,
                    citation_judge_response,
                )
                if value is not None
            )
            judge_responses = responses[1:]
            answer_cost = response_cost(response, config)
            judge_cost = sum(response_cost(value, config) for value in judge_responses)
            total_cost = answer_cost + judge_cost
            judge_latency_ms = answer_judge_latency_ms + citation_judge_latency_ms
            usage = (
                response.provider_usage
                if len(responses) == 1
                else {
                    "answer": response.provider_usage,
                    "answer_equivalence_judge": (
                        answer_judge_response.provider_usage
                        if answer_judge_response is not None
                        else None
                    ),
                    "citation_entailment_judge": (
                        citation_judge_response.provider_usage
                        if citation_judge_response is not None
                        else None
                    ),
                }
            )
            records.append(
                RepresentationEvaluationRecord(
                    question_id=question.id,
                    condition=condition,
                    answerable=question.answerable,
                    gold_answer=gold,
                    gold_pages=question.gold_evidence_pages,
                    source_node_count=len(condition_nodes),
                    feature_count=feature_count,
                    representation_tokens=counter.count(representation),
                    raw_response=response.text,
                    parsed_answer=parsed_answer,
                    citations=citations,
                    response_valid=response_valid,
                    provider_status=response.status,
                    provider_incomplete_reason=response.incomplete_reason,
                    provider_text_error=response.text_error,
                    abstained=abstained,
                    accuracy=accuracy,
                    semantic_accuracy=semantic_accuracy,
                    answer_equivalence_judge_valid=answer_judge_valid,
                    answer_equivalence_judge_reason=answer_judge_reason,
                    answer_equivalence_judge_raw_response=answer_judge_raw,
                    answer_judge_provider_status=(
                        answer_judge_response.status
                        if answer_judge_response is not None
                        else None
                    ),
                    answer_judge_provider_incomplete_reason=(
                        answer_judge_response.incomplete_reason
                        if answer_judge_response is not None
                        else None
                    ),
                    answer_judge_provider_text_error=(
                        answer_judge_response.text_error
                        if answer_judge_response is not None
                        else None
                    ),
                    token_f1=token_f1,
                    anls=anls,
                    citation_validity=citation_score,
                    citation_support=citation_score,
                    citation_entailment=citation_entailment,
                    citation_entailment_judge_valid=citation_judge_valid,
                    citation_entailment_judge_reason=citation_judge_reason,
                    citation_entailment_judge_raw_response=citation_judge_raw,
                    citation_judge_provider_status=(
                        citation_judge_response.status
                        if citation_judge_response is not None
                        else None
                    ),
                    citation_judge_provider_incomplete_reason=(
                        citation_judge_response.incomplete_reason
                        if citation_judge_response is not None
                        else None
                    ),
                    citation_judge_provider_text_error=(
                        citation_judge_response.text_error
                        if citation_judge_response is not None
                        else None
                    ),
                    citation_present=bool(citations),
                    input_tokens=sum(value.input_tokens for value in responses),
                    cached_input_tokens=sum(
                        value.cached_input_tokens for value in responses
                    ),
                    output_tokens=sum(value.output_tokens for value in responses),
                    reasoning_tokens=sum(
                        value.reasoning_tokens for value in responses
                    ),
                    calls=len(responses),
                    latency_ms=answer_latency_ms + judge_latency_ms,
                    model_id=response.model_id,
                    response_id=response.response_id,
                    provider_usage=usage,
                    cost_usd=total_cost,
                    answer_input_tokens=response.input_tokens,
                    answer_cached_input_tokens=response.cached_input_tokens,
                    answer_output_tokens=response.output_tokens,
                    answer_reasoning_tokens=response.reasoning_tokens,
                    answer_latency_ms=answer_latency_ms,
                    answer_cost_usd=answer_cost,
                    judge_calls=len(judge_responses),
                    judge_input_tokens=sum(
                        value.input_tokens for value in judge_responses
                    ),
                    judge_output_tokens=sum(
                        value.output_tokens for value in judge_responses
                    ),
                    judge_latency_ms=judge_latency_ms,
                    judge_cost_usd=judge_cost,
                )
            )
            contexts.append(
                {
                    "question_id": question.id,
                    "condition": condition.value,
                    "evidence_ids": evidence_ids,
                    "representation": representation,
                    "prompt_sha256": hashlib.sha256(
                        prompt.encode("utf-8")
                    ).hexdigest(),
                }
            )

    summary = _summarize(
        resolved_run_id,
        records,
        eligible_ids=tuple(question.id for question in eligible),
        skipped_ids=tuple(question.id for question in skipped),
        enrichment_prepare_ms=enrichment_prepare_ms,
    )
    manifest = {
        "run_id": resolved_run_id,
        "created_at": created_at.isoformat(),
        "git_commit": resolved_commit,
        "git_dirty": resolved_dirty,
        "dataset": dataset,
        "dataset_version": dataset_version,
        "dataset_revision": dataset_revision,
        "subset_name": subset_name,
        "subset_sha256": subset_sha256,
        "question_ids": [question.id for question in corpus.questions],
        "evaluated_question_ids": list(summary.evaluated_question_ids),
        "skipped_question_ids": list(summary.skipped_question_ids),
        "documents": {
            dataset_id: {
                "ir_document_id": document.id,
                "source_sha256": document.source_sha256,
                "parser_name": document.parser_name,
                "parser_version": document.parser_version,
                "parser_core_version": document.parser_core_version,
            }
            for dataset_id, document in sorted(corpus.documents.items())
        },
        "provider": provider.name,
        "provider_version": provider.version,
        # The endpoint and retry count the client was built with; null base
        # URL means the SDK default (the OpenAI API). No key is ever recorded.
        "provider_base_url": config.provider_base_url,
        "provider_max_retries": config.provider_max_retries,
        **representation_prompt_hashes(config),
        "tokenizer": counter.name,
        "tokenizer_version": counter.version,
        "enrichment_prepare_ms": enrichment_prepare_ms,
        "enrichment_document_ms": enrichment_document_ms,
        "config": config_value,
        "config_sha256": config_sha256,
    }
    _publish_run(final_path, manifest, contexts, records, summary)
    return RepresentationRun(
        path=final_path,
        summary=summary,
        records=tuple(records),
    )


def render_representation(
    condition: RepresentationCondition,
    evidence_nodes: Sequence[_EvidenceNode],
    *,
    query: str,
    enrichments: Mapping[str, AgentDocument],
    inline_feature_kinds: set[AgentFeatureKind],
    max_inline_features: int,
    indexed_max_features: int,
    indexed_feature_token_budget: int,
    tokenizer: TokenCounter,
) -> tuple[str, int]:
    """Render one condition while keeping the underlying source nodes fixed."""
    if condition == RepresentationCondition.QUESTION_ONLY:
        if evidence_nodes:
            raise RepresentationError("question-only condition received evidence")
        return "", 0
    if condition == RepresentationCondition.RAW:
        return "\n\n".join(_raw_block(item) for item in evidence_nodes), 0
    source = "\n\n".join(_ir_block(item) for item in evidence_nodes)
    if condition == RepresentationCondition.IR:
        return source, 0
    if condition not in {
        RepresentationCondition.ENRICHED,
        RepresentationCondition.INDEXED,
    }:
        raise RepresentationError(f"unsupported condition: {condition}")

    ids_by_node = {item.node.id: item.evidence_id for item in evidence_nodes}
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


def _gold_evidence_nodes(
    question: BenchmarkQuestion,
    corpus: EvaluationCorpus,
) -> tuple[_EvidenceNode, ...]:
    selected: list[_EvidenceNode] = []
    for dataset_document_id in question.document_ids:
        pages = set(question.gold_evidence_pages.get(dataset_document_id, ()))
        if not pages:
            continue
        document = corpus.documents[dataset_document_id]
        for node in sorted(document.nodes, key=lambda value: value.ordinal):
            if (
                node.content_layer != "body"
                or not node.text.strip()
                or node.kind == IRNodeKind.LIST
                or node.page_start is None
                or node.page_end is None
            ):
                continue
            if not any(node.page_start <= page <= node.page_end for page in pages):
                continue
            selected.append(
                _EvidenceNode(
                    dataset_document_id=dataset_document_id,
                    evidence_id=_evidence_id(node),
                    node=node,
                )
            )
    return tuple(selected)


def _raw_block(item: _EvidenceNode) -> str:
    return (
        f'<evidence id="{item.evidence_id}">\n'
        f"{html.escape(item.node.text)}\n</evidence>"
    )


def _ir_block(item: _EvidenceNode) -> str:
    node = item.node
    heading = " > ".join(node.heading_path)
    return (
        f'<evidence id="{item.evidence_id}" '
        f'document="{html.escape(item.dataset_document_id)}" '
        f'kind="{node.kind.value}" pages="{node.page_start}-{node.page_end}" '
        f'source_node="{node.id}">\n'
        f"Heading: {html.escape(heading or '[root]')}\n"
        f"{html.escape(node.text)}\n</evidence>"
    )


def _evidence_id(node: IRNode) -> str:
    payload = f"gold-evidence-v1\0{node.document_id}\0{node.id}".encode()
    return f"evidence_{hashlib.sha256(payload).hexdigest()}"


def _has_gold_pages(question: BenchmarkQuestion) -> bool:
    return any(evidence.pages for evidence in question.gold_evidence)


def _summarize(
    run_id: str,
    records: Sequence[RepresentationEvaluationRecord],
    *,
    eligible_ids: tuple[str, ...],
    skipped_ids: tuple[str, ...],
    enrichment_prepare_ms: float,
) -> RepresentationBenchmarkSummary:
    groups: dict[RepresentationCondition, list[RepresentationEvaluationRecord]] = (
        defaultdict(list)
    )
    for record in records:
        groups[record.condition].append(record)
    question_only_correct: list[str] = []
    question_only_incorrect: list[str] = []
    question_only_invalid: list[str] = []
    question_only_abstained: list[str] = []
    for cell in groups.get(RepresentationCondition.QUESTION_ONLY, ()):
        if not cell.response_valid or cell.answer_equivalence_judge_valid is False:
            question_only_invalid.append(cell.question_id)
        elif cell.abstained:
            # The prompt demands INSUFFICIENT_EVIDENCE for an empty evidence
            # section, so this is compliance, not a wrong answer.
            question_only_abstained.append(cell.question_id)
        elif cell.semantic_accuracy is not None:
            target = (
                question_only_correct
                if cell.semantic_accuracy == 1.0
                else question_only_incorrect
            )
            target.append(cell.question_id)
        else:
            target = (
                question_only_correct
                if cell.accuracy == 1.0
                else question_only_incorrect
            )
            target.append(cell.question_id)
    rows = []
    for condition in RepresentationCondition:
        cells = groups.get(condition)
        if not cells:
            continue
        correct = sum(cell.accuracy for cell in cells)
        semantic = [
            cell.semantic_accuracy
            for cell in cells
            if cell.semantic_accuracy is not None
        ]
        semantic_correct = sum(semantic)
        answer_judged = [
            cell.answer_equivalence_judge_valid
            for cell in cells
            if cell.answer_equivalence_judge_valid is not None
        ]
        citation_judged = [
            cell.citation_entailment_judge_valid
            for cell in cells
            if cell.citation_entailment_judge_valid is not None
        ]
        citation_entailed = [
            cell.citation_entailment
            for cell in cells
            if cell.citation_entailment is not None
        ]
        total_cost = sum(cell.cost_usd for cell in cells)
        answer_cost = sum(cell.answer_cost_usd for cell in cells)
        rows.append(
            RepresentationSummaryRow(
                condition=condition,
                question_count=len(cells),
                response_valid_rate=mean(cell.response_valid for cell in cells),
                answer_rate=mean(not cell.abstained for cell in cells),
                answer_equivalence_judge_valid_rate=(
                    mean(answer_judged) if answer_judged else None
                ),
                citation_entailment_judge_valid_rate=(
                    mean(citation_judged) if citation_judged else None
                ),
                mean_accuracy=mean(cell.accuracy for cell in cells),
                mean_semantic_accuracy=mean(semantic) if semantic else None,
                mean_token_f1=mean(cell.token_f1 for cell in cells),
                mean_anls=mean(cell.anls for cell in cells),
                mean_citation_validity=mean(cell.citation_validity for cell in cells),
                mean_citation_support=mean(cell.citation_support for cell in cells),
                mean_citation_entailment=(
                    mean(citation_entailed) if citation_entailed else None
                ),
                citation_present_rate=mean(cell.citation_present for cell in cells),
                mean_representation_tokens=mean(
                    cell.representation_tokens for cell in cells
                ),
                mean_answer_input_tokens=mean(
                    cell.answer_input_tokens for cell in cells
                ),
                mean_answer_output_tokens=mean(
                    cell.answer_output_tokens for cell in cells
                ),
                mean_answer_latency_ms=mean(cell.answer_latency_ms for cell in cells),
                answer_dollars_per_query=answer_cost / len(cells),
                answer_dollars_per_correct=answer_cost / correct if correct else None,
                answer_dollars_per_semantic_correct=(
                    answer_cost / semantic_correct if semantic_correct else None
                ),
                mean_input_tokens=mean(cell.input_tokens for cell in cells),
                mean_output_tokens=mean(cell.output_tokens for cell in cells),
                mean_calls=mean(cell.calls for cell in cells),
                mean_latency_ms=mean(cell.latency_ms for cell in cells),
                dollars_per_query=total_cost / len(cells),
                dollars_per_correct=total_cost / correct if correct else None,
                dollars_per_semantic_correct=(
                    total_cost / semantic_correct if semantic_correct else None
                ),
                mean_judge_calls=mean(cell.judge_calls for cell in cells),
                mean_judge_input_tokens=mean(
                    cell.judge_input_tokens for cell in cells
                ),
                mean_judge_output_tokens=mean(
                    cell.judge_output_tokens for cell in cells
                ),
                mean_judge_latency_ms=mean(cell.judge_latency_ms for cell in cells),
                judge_dollars_per_query=(
                    sum(cell.judge_cost_usd for cell in cells) / len(cells)
                ),
            )
        )
    return RepresentationBenchmarkSummary(
        run_id=run_id,
        evaluated_question_ids=eligible_ids,
        skipped_question_ids=skipped_ids,
        question_only_correct_ids=tuple(question_only_correct),
        question_only_incorrect_ids=tuple(question_only_incorrect),
        question_only_invalid_ids=tuple(question_only_invalid),
        question_only_abstained_ids=tuple(question_only_abstained),
        enrichment_prepare_ms=enrichment_prepare_ms,
        amortized_enrichment_ms_per_question=(
            enrichment_prepare_ms / len(eligible_ids)
        ),
        rows=tuple(rows),
    )


def _publish_run(
    final_path: Path,
    manifest: Mapping[str, object],
    contexts: Sequence[Mapping[str, object]],
    records: Sequence[RepresentationEvaluationRecord],
    summary: RepresentationBenchmarkSummary,
) -> None:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=".representation-run-", dir=final_path.parent)
    )
    try:
        _write_json(staging / "manifest.json", manifest)
        _write_jsonl(staging / "contexts.jsonl", contexts)
        _write_jsonl(
            staging / "representation.jsonl",
            [record.model_dump(mode="json") for record in records],
        )
        _write_json(staging / "summary.json", summary.model_dump(mode="json"))
        (staging / "report.md").write_text(
            _markdown_report(summary), encoding="utf-8"
        )
        staging.replace(final_path)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _optional(value: float | None, digits: int) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _markdown_report(summary: RepresentationBenchmarkSummary) -> str:
    lines = [
        f"# Gold-Evidence Representation Report: {summary.run_id}",
        "",
        "No retrieval was used. Every evidence-bearing condition received the "
        "same annotated pages; question_only received none.",
        f"One-time enrichment: {summary.enrichment_prepare_ms:.2f} ms "
        f"({summary.amortized_enrichment_ms_per_question:.2f} ms/question).",
        f"Question-only correct: {len(summary.question_only_correct_ids)}; "
        f"incorrect: {len(summary.question_only_incorrect_ids)}; "
        f"abstained: {len(summary.question_only_abstained_ids)}; "
        f"invalid: {len(summary.question_only_invalid_ids)}.",
        "",
        "## Quality",
        "",
        "| Condition | Questions | Valid responses | Answer rate | Accuracy | "
        "Token F1 | ANLS | Citation support | Semantic accuracy | "
        "Valid answer judges | Citation entailment | Valid citation judges |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
        "---: | ---: | ---: |",
    ]
    for row in summary.rows:
        lines.append(
            f"| {row.condition.value} | {row.question_count} "
            f"| {row.response_valid_rate:.3f} | {row.answer_rate:.3f} "
            f"| {row.mean_accuracy:.3f} | {row.mean_token_f1:.3f} "
            f"| {row.mean_anls:.3f} | {row.mean_citation_support:.3f} "
            f"| {_optional(row.mean_semantic_accuracy, 3)} "
            f"| {_optional(row.answer_equivalence_judge_valid_rate, 3)} "
            f"| {_optional(row.mean_citation_entailment, 3)} "
            f"| {_optional(row.citation_entailment_judge_valid_rate, 3)} |"
        )
    lines.extend(
        [
            "",
            "## Answer-call efficiency (representation comparison)",
            "",
            "| Condition | Rep. tokens | Input tokens | Output tokens | "
            "Latency (ms) | $/query | $/correct | $/semantic correct |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in summary.rows:
        lines.append(
            f"| {row.condition.value} | {row.mean_representation_tokens:.1f} "
            f"| {row.mean_answer_input_tokens:.1f} "
            f"| {row.mean_answer_output_tokens:.1f} "
            f"| {row.mean_answer_latency_ms:.2f} "
            f"| {row.answer_dollars_per_query:.6f} "
            f"| {_optional(row.answer_dollars_per_correct, 6)} "
            f"| {_optional(row.answer_dollars_per_semantic_correct, 6)} |"
        )
    lines.extend(
        [
            "",
            "## All calls (answer plus judges)",
            "",
            "| Condition | Calls | Judge calls | Input tokens | Output tokens | "
            "Latency (ms) | $/query | Judge $/query | $/correct | "
            "$/semantic correct |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in summary.rows:
        lines.append(
            f"| {row.condition.value} | {row.mean_calls:.2f} "
            f"| {row.mean_judge_calls:.2f} "
            f"| {row.mean_input_tokens:.1f} | {row.mean_output_tokens:.1f} "
            f"| {row.mean_latency_ms:.2f} | {row.dollars_per_query:.6f} "
            f"| {row.judge_dollars_per_query:.6f} "
            f"| {_optional(row.dollars_per_correct, 6)} "
            f"| {_optional(row.dollars_per_semantic_correct, 6)} |"
        )
    lines.extend(
        [
            "",
            f"Skipped without gold pages: {len(summary.skipped_question_ids)}.",
            "Costs use the pricing metadata frozen in the manifest.",
            "Compare representations on answer-call efficiency. The all-calls "
            "table adds judge calls, whose number and prompt size depend on "
            "the answer (none for abstentions or question_only citations), so "
            "it measures evaluation cost, not representation cost.",
            "Valid responses is the share of answer calls the provider "
            "completed and that parsed against the answer contract.",
            "Answer rate is the share of cells that did not return the exact "
            "INSUFFICIENT_EVIDENCE marker. Citation entailment is over "
            "non-abstaining cells only, so it must be read with answer rate.",
            "Valid judges is the share of judge calls that completed and "
            "parsed, over the cells that called that judge; n/a means no cell "
            "called it. An invalid judge scores zero.",
            "Citation support is the historical citation-ID validity field; "
            "it is not semantic entailment. Accuracy, token F1 and ANLS are "
            "the deterministic relaxed metrics; semantic accuracy is the "
            "separate same-model equivalence judge.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, values: Sequence[Mapping[str, object]]) -> None:
    path.write_text(
        "".join(
            json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
            for value in values
        ),
        encoding="utf-8",
    )


def _json_hash(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
