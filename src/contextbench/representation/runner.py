"""Gold-page RAW/IR/ENRICHED representation experiment orchestration."""

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
    AnswerProvider,
    AnswerRequest,
    parse_answer_response,
    render_grounded_prompt,
    response_cost,
)
from contextbench.generation.runner import ANSWER_PROMPT_INSTRUCTIONS
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
    """Compare three encodings of identical gold evidence without retrieval.

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
            representation, feature_count = render_representation(
                condition,
                evidence_nodes,
                query=question.question,
                enrichments=enrichments,
                inline_feature_kinds=set(config.inline_feature_kinds),
                max_inline_features=config.max_inline_features,
                indexed_max_features=config.indexed_max_features,
                indexed_feature_token_budget=config.indexed_feature_token_budget,
                tokenizer=counter,
            )
            prompt = render_grounded_prompt(question.question, representation)
            evidence_ids = tuple(item.evidence_id for item in evidence_nodes)
            request = AnswerRequest(
                question_id=question.id,
                system=condition.value,
                prompt=prompt,
                evidence_ids=evidence_ids,
            )
            started = time.perf_counter_ns()
            try:
                response = provider.generate(request, config=config)
            except Exception as exc:
                # Recorded, not fixed: this re-raise aborts the whole run, and
                # ``_publish_run`` runs only after the loop completes, so a
                # rate-limit or timeout on the last call discards every
                # response already paid for in this run. Nothing is written.
                # Only a *non-completed* response is survivable, and only in
                # the generation runner; an exception is not. Writing a
                # durable partial artifact is a design change, not a fix to
                # make here.
                raise RepresentationError(
                    f"provider failed for {question.id}/{condition.value}: {exc}"
                ) from exc
            latency_ms = (time.perf_counter_ns() - started) / 1_000_000
            parsed_answer, citations, parsed_valid = parse_answer_response(
                response.text
            )
            # A response the provider did not complete is a failed call, not a
            # wrong answer. Keep the paid cell, its usage and diagnostics, but
            # score it zero and expose the failure in the condition summary.
            response_valid = parsed_valid and response.provider_valid
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
            records.append(
                RepresentationEvaluationRecord(
                    question_id=question.id,
                    condition=condition,
                    answerable=question.answerable,
                    gold_answer=gold,
                    gold_pages=question.gold_evidence_pages,
                    source_node_count=len(evidence_nodes),
                    feature_count=feature_count,
                    representation_tokens=counter.count(representation),
                    raw_response=response.text,
                    parsed_answer=parsed_answer,
                    citations=citations,
                    response_valid=response_valid,
                    provider_status=response.status,
                    provider_incomplete_reason=response.incomplete_reason,
                    provider_text_error=response.text_error,
                    accuracy=accuracy,
                    token_f1=token_f1,
                    anls=anls,
                    citation_validity=citation_score,
                    citation_support=citation_score,
                    citation_present=bool(citations),
                    input_tokens=response.input_tokens,
                    cached_input_tokens=response.cached_input_tokens,
                    output_tokens=response.output_tokens,
                    reasoning_tokens=response.reasoning_tokens,
                    latency_ms=latency_ms,
                    model_id=response.model_id,
                    response_id=response.response_id,
                    provider_usage=response.provider_usage,
                    cost_usd=response_cost(response, config),
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
        "prompt_sha256": hashlib.sha256(
            ANSWER_PROMPT_INSTRUCTIONS.encode("utf-8")
        ).hexdigest(),
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
    rows = []
    for condition in RepresentationCondition:
        cells = groups.get(condition)
        if not cells:
            continue
        correct = sum(cell.accuracy for cell in cells)
        total_cost = sum(cell.cost_usd for cell in cells)
        rows.append(
            RepresentationSummaryRow(
                condition=condition,
                question_count=len(cells),
                response_valid_rate=mean(cell.response_valid for cell in cells),
                mean_accuracy=mean(cell.accuracy for cell in cells),
                mean_token_f1=mean(cell.token_f1 for cell in cells),
                mean_anls=mean(cell.anls for cell in cells),
                mean_citation_validity=mean(cell.citation_validity for cell in cells),
                mean_citation_support=mean(cell.citation_support for cell in cells),
                citation_present_rate=mean(cell.citation_present for cell in cells),
                mean_representation_tokens=mean(
                    cell.representation_tokens for cell in cells
                ),
                mean_input_tokens=mean(cell.input_tokens for cell in cells),
                mean_output_tokens=mean(cell.output_tokens for cell in cells),
                mean_latency_ms=mean(cell.latency_ms for cell in cells),
                dollars_per_query=total_cost / len(cells),
                dollars_per_correct=total_cost / correct if correct else None,
            )
        )
    return RepresentationBenchmarkSummary(
        run_id=run_id,
        evaluated_question_ids=eligible_ids,
        skipped_question_ids=skipped_ids,
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


def _markdown_report(summary: RepresentationBenchmarkSummary) -> str:
    lines = [
        f"# Gold-Evidence Representation Report: {summary.run_id}",
        "",
        "No retrieval was used. Every condition received the same annotated pages.",
        f"One-time enrichment: {summary.enrichment_prepare_ms:.2f} ms "
        f"({summary.amortized_enrichment_ms_per_question:.2f} ms/question).",
        "",
        "| Condition | Questions | Valid responses | Accuracy | Token F1 | "
        "ANLS | Rep. tokens | Citation support | Input tokens | Latency (ms) "
        "| $/query | $/correct |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
        "---: | ---: | ---: |",
    ]
    for row in summary.rows:
        cost_correct = (
            f"{row.dollars_per_correct:.6f}"
            if row.dollars_per_correct is not None
            else "n/a"
        )
        lines.append(
            f"| {row.condition.value} | {row.question_count} "
            f"| {row.response_valid_rate:.3f} | {row.mean_accuracy:.3f} "
            f"| {row.mean_token_f1:.3f} "
            f"| {row.mean_anls:.3f} | {row.mean_representation_tokens:.1f} "
            f"| {row.mean_citation_support:.3f} | {row.mean_input_tokens:.1f} "
            f"| {row.mean_latency_ms:.2f} | {row.dollars_per_query:.6f} "
            f"| {cost_correct} |"
        )
    lines.extend(
        [
            "",
            f"Skipped without gold pages: {len(summary.skipped_question_ids)}.",
            "Costs use the pricing metadata frozen in the manifest.",
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
