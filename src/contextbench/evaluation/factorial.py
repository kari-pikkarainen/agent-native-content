"""Controlled content-unit × selection-policy retrieval experiment."""

import hashlib
import json
import os
import re
import shutil
import statistics
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from docling_core.types.doc import DoclingDocument

from contextbench.compiler.candidates import node_chunks
from contextbench.compiler.facets import retrieve_faceted
from contextbench.compiler.models import CompilerCandidate
from contextbench.compiler.pack import pack_candidates
from contextbench.evaluation.evidence import evaluate_context
from contextbench.evaluation.factorial_models import (
    ContentUnit,
    FactorialConfig,
    FactorialEvaluationRecord,
    FactorialSummary,
    FactorialSummaryRow,
    SelectionPolicy,
)
from contextbench.evaluation.runner import EvaluationCorpus, EvaluationError
from contextbench.experiments import (
    DocumentProvenance,
    RunManifest,
    current_git_commit,
    environment_info,
    utc_now,
)
from contextbench.ir.models import IRDocument
from contextbench.ir.tokenizer import TiktokenTokenCounter, TokenCounter
from contextbench.retrieval import (
    HybridIndex,
    RankedEvidence,
    RetrievalArm,
    RetrievalChunk,
    embedding_model_from_config,
    fixed_chunks,
    reranker_from_config,
    structural_chunks,
)
from contextbench.retrieval.embeddings import EmbeddingModel
from contextbench.retrieval.models import ContextPacket
from contextbench.retrieval.rerank import Reranker


@dataclass(frozen=True)
class FactorialRun:
    """Completed immutable factorial run."""

    path: Path
    manifest: RunManifest
    summary: FactorialSummary
    records: tuple[FactorialEvaluationRecord, ...]


def run_factorial_benchmark(
    corpus: EvaluationCorpus,
    *,
    config: FactorialConfig,
    artifacts_root: Path,
    dataset: str,
    dataset_version: str,
    dataset_revision: str,
    subset_name: str,
    subset_sha256: str,
    retrieval_corpus_name: str | None = None,
    retrieval_corpus_sha256: str | None = None,
    retrieval_corpus_question_ids: Sequence[str] | None = None,
    run_id: str | None = None,
    tokenizer: TokenCounter | None = None,
    embedder: EmbeddingModel | None = None,
    reranker: Reranker | None = None,
    git_commit: str | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> FactorialRun:
    """Run every configured content unit under every selection policy."""
    _validate_factorial_corpus(corpus)
    evaluated_question_ids = tuple(question.id for question in corpus.questions)
    corpus_question_ids = (
        tuple(retrieval_corpus_question_ids)
        if retrieval_corpus_question_ids is not None
        else evaluated_question_ids
    )
    if not set(evaluated_question_ids).issubset(corpus_question_ids):
        raise EvaluationError(
            "evaluated questions must be included in the retrieval corpus"
        )

    counter = tokenizer or TiktokenTokenCounter(config.retrieval.tokenizer_name)
    shared_embedder = embedder or embedding_model_from_config(config.retrieval)
    shared_reranker = reranker or reranker_from_config(config.retrieval)
    created_at = clock()
    config_value = config.model_dump(mode="json")
    config_sha256 = _json_hash(config_value)
    resolved_run_id = run_id or (
        f"factorial-{created_at.strftime('%Y%m%dT%H%M%SZ')}-"
        f"{config_sha256[:12]}"
    )
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", resolved_run_id):
        raise EvaluationError("run_id contains unsafe path characters")
    final_path = artifacts_root / "factorial-runs" / resolved_run_id
    if final_path.exists():
        raise EvaluationError(f"completed run already exists: {final_path}")

    ordered_document_ids = sorted(corpus.documents)
    documents = tuple(
        corpus.documents[document_id] for document_id in ordered_document_ids
    )
    sources_by_ir_id = {
        corpus.documents[document_id].id: corpus.source_documents[document_id]
        for document_id in ordered_document_ids
    }
    indexes = _build_factorial_indexes(
        documents,
        sources_by_ir_id=sources_by_ir_id,
        config=config,
        artifacts_root=artifacts_root,
        tokenizer=counter,
        embedder=shared_embedder,
        reranker=shared_reranker,
    )
    records, contexts = _evaluate_factorial_cells(
        corpus,
        config=config,
        indexes=indexes,
        tokenizer=counter,
    )
    summary = summarize_factorial(resolved_run_id, records)
    python_version, platform_name = environment_info()
    manifest = RunManifest(
        run_id=resolved_run_id,
        created_at=created_at.isoformat(),
        git_commit=git_commit or current_git_commit(),
        dataset=dataset,
        dataset_version=dataset_version,
        dataset_revision=dataset_revision,
        subset_name=subset_name,
        subset_sha256=subset_sha256,
        question_ids=evaluated_question_ids,
        retrieval_corpus_name=retrieval_corpus_name or subset_name,
        retrieval_corpus_sha256=retrieval_corpus_sha256 or subset_sha256,
        retrieval_corpus_question_ids=corpus_question_ids,
        documents={
            document_id: DocumentProvenance(
                ir_document_id=document.id,
                source_sha256=document.source_sha256,
                parser_name=document.parser_name,
                parser_version=document.parser_version,
                parser_core_version=document.parser_core_version,
            )
            for document_id, document in sorted(corpus.documents.items())
        },
        systems=tuple(
            _system_name(unit, policy)
            for unit in config.content_units
            for policy in config.selection_policies
        ),
        token_budgets=config.budgets,
        seed=config.seed,
        config=config_value,
        config_sha256=config_sha256,
        embedding_model=shared_embedder.name,
        embedding_version=shared_embedder.version,
        reranker_model=shared_reranker.name,
        reranker_version=shared_reranker.version,
        tokenizer=counter.name,
        tokenizer_version=counter.version,
        python_version=python_version,
        platform=platform_name,
    )
    _publish_factorial_run(
        final_path,
        manifest=manifest,
        records=records,
        contexts=contexts,
        summary=summary,
    )
    return FactorialRun(
        path=final_path,
        manifest=manifest,
        summary=summary,
        records=records,
    )


def _build_factorial_indexes(
    documents: Sequence[IRDocument],
    *,
    sources_by_ir_id: Mapping[str, DoclingDocument],
    config: FactorialConfig,
    artifacts_root: Path,
    tokenizer: TokenCounter,
    embedder: EmbeddingModel,
    reranker: Reranker,
) -> dict[tuple[ContentUnit, SelectionPolicy], HybridIndex]:
    chunks_by_unit: dict[ContentUnit, tuple[RetrievalChunk, ...]] = {}
    if ContentUnit.FIXED in config.content_units:
        chunks_by_unit[ContentUnit.FIXED] = tuple(
            chunk
            for document in documents
            for chunk in fixed_chunks(
                document,
                config=config.retrieval,
                tokenizer=tokenizer,
            )
        )
    if ContentUnit.STRUCTURAL in config.content_units:
        chunks_by_unit[ContentUnit.STRUCTURAL] = tuple(
            chunk
            for document in documents
            for chunk in structural_chunks(
                document,
                sources_by_ir_id[document.id],
                config=config.retrieval,
                tokenizer=tokenizer,
            )
        )
    if ContentUnit.IR in config.content_units:
        chunks_by_unit[ContentUnit.IR] = node_chunks(
            documents,
            tokenizer=tokenizer,
        )

    arm_by_unit = {
        ContentUnit.FIXED: RetrievalArm.FIXED,
        ContentUnit.STRUCTURAL: RetrievalArm.STRUCTURAL,
        ContentUnit.IR: RetrievalArm.COMPILER,
    }
    return {
        (unit, policy): HybridIndex.from_chunks(
            chunks_by_unit[unit],
            config=config.retrieval,
            documents=documents,
            arm=arm_by_unit[unit],
            artifacts_root=artifacts_root,
            embedder=embedder,
            reranker=reranker,
            tokenizer=tokenizer,
        )
        for unit in config.content_units
        for policy in config.selection_policies
    }


def _evaluate_factorial_cells(
    corpus: EvaluationCorpus,
    *,
    config: FactorialConfig,
    indexes: Mapping[tuple[ContentUnit, SelectionPolicy], HybridIndex],
    tokenizer: TokenCounter,
) -> tuple[tuple[FactorialEvaluationRecord, ...], tuple[dict[str, object], ...]]:
    records: list[FactorialEvaluationRecord] = []
    contexts: list[dict[str, object]] = []
    for question in corpus.questions:
        ir_document_ids = {
            corpus.documents[document_id].id for document_id in question.document_ids
        }
        for unit in config.content_units:
            for policy in config.selection_policies:
                index = indexes[(unit, policy)]
                retrieval_started = time.perf_counter_ns()
                candidates = index.retrieve_candidates(
                    question.question,
                    token_budget=max(config.budgets),
                    document_ids=ir_document_ids,
                    maximum_rerank_limit=(
                        config.faceting.query_facet_rerank_candidate_limit
                    ),
                )
                if policy == SelectionPolicy.RANKED:
                    ranked = index.rerank(question.question, candidates)
                else:
                    ranked = retrieve_faceted(
                        index,
                        question.question,
                        candidates,
                        token_budget=max(config.budgets),
                        document_ids=ir_document_ids,
                        config=config.faceting,
                    )
                retrieval_elapsed_ms = (
                    time.perf_counter_ns() - retrieval_started
                ) / 1_000_000
                for budget in config.budgets:
                    packing_started = time.perf_counter_ns()
                    packet = _pack_factorial_context(
                        question.question,
                        ranked,
                        unit=unit,
                        policy=policy,
                        token_budget=budget,
                        tokenizer=tokenizer,
                    )
                    elapsed_ms = retrieval_elapsed_ms + (
                        time.perf_counter_ns() - packing_started
                    ) / 1_000_000
                    metrics = evaluate_context(question, packet, corpus.documents)
                    records.append(
                        FactorialEvaluationRecord(
                            question_id=question.id,
                            content_unit=unit,
                            selection_policy=policy,
                            token_budget=budget,
                            token_count=packet.token_count,
                            selected_evidence_ids=tuple(
                                item.evidence_id for item in packet.items
                            ),
                            retrieval_latency_ms=elapsed_ms,
                            **metrics,
                        )
                    )
                    contexts.append(
                        {
                            "question_id": question.id,
                            "content_unit": unit.value,
                            "selection_policy": policy.value,
                            "token_budget": budget,
                            "context": packet.model_dump(mode="json"),
                        }
                    )
    return tuple(records), tuple(contexts)


def _pack_factorial_context(
    query: str,
    ranked: Sequence[RankedEvidence],
    *,
    unit: ContentUnit,
    policy: SelectionPolicy,
    token_budget: int,
    tokenizer: TokenCounter,
) -> ContextPacket:
    """Apply identical provenance deduplication before either packing policy."""
    candidates: list[CompilerCandidate] = []
    used_sources: set[tuple[str, ...]] = set()
    for evidence in ranked:
        source_key = (evidence.chunk.document_id, *evidence.chunk.source_item_ids)
        if source_key in used_sources:
            continue
        used_sources.add(source_key)
        candidates.append(
            CompilerCandidate(
                chunk=evidence.chunk,
                scores=evidence.scores,
                origin_rank=evidence.rank,
                expansion_order=0,
            )
        )
    return pack_candidates(
        query,
        candidates,
        token_budget=token_budget,
        tokenizer=tokenizer,
        strategy=(
            "ranked" if policy == SelectionPolicy.RANKED else "coverage"
        ),
        metadata={
            "experiment": "content-unit-selection-policy-factorial-v1",
            "content_unit": unit.value,
            "selection_policy": policy.value,
        },
    )


def summarize_factorial(
    run_id: str,
    records: Sequence[FactorialEvaluationRecord],
) -> FactorialSummary:
    """Aggregate every unit × policy × budget cell."""
    rows: list[FactorialSummaryRow] = []
    cells = sorted(
        {
            (record.content_unit, record.selection_policy, record.token_budget)
            for record in records
        },
        key=lambda value: (value[0].value, value[1].value, value[2]),
    )
    for unit, policy, budget in cells:
        selected = [
            record
            for record in records
            if record.content_unit == unit
            and record.selection_policy == policy
            and record.token_budget == budget
        ]
        tokens_to_full = [
            record.tokens_to_full_evidence
            for record in selected
            if record.tokens_to_full_evidence is not None
        ]
        rows.append(
            FactorialSummaryRow(
                content_unit=unit,
                selection_policy=policy,
                token_budget=budget,
                question_count=len(selected),
                mean_evidence_page_recall=statistics.fmean(
                    record.evidence_page_recall for record in selected
                ),
                full_evidence_coverage_rate=statistics.fmean(
                    float(record.full_evidence_coverage) for record in selected
                ),
                mean_evidence_quote_recall=statistics.fmean(
                    record.evidence_quote_recall for record in selected
                ),
                full_quote_coverage_rate=statistics.fmean(
                    float(record.full_quote_coverage) for record in selected
                ),
                mean_context_tokens=statistics.fmean(
                    record.token_count for record in selected
                ),
                median_context_tokens=statistics.median(
                    record.token_count for record in selected
                ),
                median_tokens_to_full_evidence=(
                    statistics.median(tokens_to_full) if tokens_to_full else None
                ),
                mean_redundancy=statistics.fmean(
                    record.redundancy for record in selected
                ),
                mean_retrieval_latency_ms=statistics.fmean(
                    record.retrieval_latency_ms for record in selected
                ),
            )
        )
    return FactorialSummary(run_id=run_id, rows=tuple(rows))


def factorial_markdown_report(summary: FactorialSummary) -> str:
    """Render cell metrics plus the two causal contrasts."""
    lines = [
        f"# Content-unit × selection-policy report: {summary.run_id}",
        "",
        "No structural expansion, table joins, page-neighbor backfill, or answer "
        "model participates in this controlled experiment.",
        "",
        "| Unit | Policy | Budget | Page recall | Full pages | Quote recall | "
        "Full quotes | Mean tokens | Redundancy | Latency (ms) |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary.rows:
        lines.append(
            f"| {row.content_unit.value} | {row.selection_policy.value} | "
            f"{row.token_budget} | {row.mean_evidence_page_recall:.3f} | "
            f"{row.full_evidence_coverage_rate:.3f} | "
            f"{row.mean_evidence_quote_recall:.3f} | "
            f"{row.full_quote_coverage_rate:.3f} | "
            f"{row.mean_context_tokens:.1f} | {row.mean_redundancy:.3f} | "
            f"{row.mean_retrieval_latency_ms:.2f} |"
        )

    by_cell = {
        (row.content_unit, row.selection_policy, row.token_budget): row
        for row in summary.rows
    }
    lines.extend(["", "## Policy effect within each content unit", ""])
    for unit in ContentUnit:
        for budget in sorted({row.token_budget for row in summary.rows}):
            control = by_cell.get((unit, SelectionPolicy.RANKED, budget))
            enhanced = by_cell.get(
                (unit, SelectionPolicy.FACETED_COVERAGE, budget)
            )
            if control is None or enhanced is None:
                continue
            page_delta = (
                enhanced.mean_evidence_page_recall
                - control.mean_evidence_page_recall
            )
            quote_delta = (
                enhanced.mean_evidence_quote_recall
                - control.mean_evidence_quote_recall
            )
            lines.append(
                f"- {unit.value} at {budget}: "
                f"{page_delta:+.3f} page recall, "
                f"{quote_delta:+.3f} quote recall."
            )

    lines.extend(["", "## IR effect under each selection policy", ""])
    for policy in SelectionPolicy:
        for budget in sorted({row.token_budget for row in summary.rows}):
            ir = by_cell.get((ContentUnit.IR, policy, budget))
            chunk_rows = [
                by_cell.get((unit, policy, budget))
                for unit in (ContentUnit.FIXED, ContentUnit.STRUCTURAL)
            ]
            available = [row for row in chunk_rows if row is not None]
            if ir is None or not available:
                continue
            best_chunk = max(
                available,
                key=lambda row: row.mean_evidence_page_recall,
            )
            page_delta = (
                ir.mean_evidence_page_recall
                - best_chunk.mean_evidence_page_recall
            )
            quote_delta = (
                ir.mean_evidence_quote_recall
                - best_chunk.mean_evidence_quote_recall
            )
            lines.append(
                f"- {policy.value} at {budget}: IR vs best chunk unit "
                f"({best_chunk.content_unit.value}) is "
                f"{page_delta:+.3f} page recall and "
                f"{quote_delta:+.3f} quote recall."
            )
    lines.extend(
        [
            "",
            "This experiment isolates content units from retrieval and packing "
            "policy. It does not test structural compiler operators or answer "
            "quality.",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_factorial_corpus(corpus: EvaluationCorpus) -> None:
    if not corpus.questions:
        raise EvaluationError("factorial benchmark requires at least one question")
    required = {
        document_id
        for question in corpus.questions
        for document_id in question.document_ids
    }
    missing_ir = required.difference(corpus.documents)
    missing_sources = required.difference(corpus.source_documents)
    if missing_ir or missing_sources:
        raise EvaluationError(
            "corpus is missing documents: "
            f"IR={sorted(missing_ir)}, source={sorted(missing_sources)}"
        )


def _publish_factorial_run(
    final_path: Path,
    *,
    manifest: RunManifest,
    records: Sequence[FactorialEvaluationRecord],
    contexts: Sequence[dict[str, object]],
    summary: FactorialSummary,
) -> None:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".factorial-run-", dir=final_path.parent))
    try:
        _write_json(staging / "manifest.json", manifest.model_dump(mode="json"))
        _write_jsonl(
            staging / "retrieval.jsonl",
            [record.model_dump(mode="json") for record in records],
        )
        _write_jsonl(staging / "contexts.jsonl", contexts)
        _write_json(staging / "summary.json", summary.model_dump(mode="json"))
        (staging / "report.md").write_text(
            factorial_markdown_report(summary),
            encoding="utf-8",
        )
        os.replace(staging, final_path)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, values: Sequence[object]) -> None:
    path.write_text(
        "".join(
            json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
            for value in values
        ),
        encoding="utf-8",
    )


def _json_hash(value: object) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


def _system_name(unit: ContentUnit, policy: SelectionPolicy) -> str:
    return f"{unit.value}:{policy.value}"
