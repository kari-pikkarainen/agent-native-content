"""Evidence-only A/B/D benchmark orchestration and immutable artifacts."""

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from docling_core.types.doc import DoclingDocument

from contextbench.compiler import (
    CompilerQueryCache,
    DocumentScope,
    compile_context,
    compile_context_with_trace,
)
from contextbench.compiler.candidates import node_chunks
from contextbench.compiler.facets import retrieve_faceted
from contextbench.datasets.base import BenchmarkQuestion
from contextbench.evaluation.evidence import evaluate_context
from contextbench.evaluation.models import (
    BenchmarkSystem,
    CompilerStageAuditRecord,
    RetrievalBenchmarkConfig,
    RetrievalBenchmarkSummary,
    RetrievalEvaluationRecord,
)
from contextbench.evaluation.reports import markdown_report, summarize
from contextbench.evaluation.stages import (
    evaluate_candidate_stage,
    evaluate_compiler_candidates,
    evaluate_packed_stage,
    gold_pages,
)
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
    embedding_model_from_config,
    reranker_from_config,
)
from contextbench.retrieval.embeddings import EmbeddingModel
from contextbench.retrieval.models import ContextPacket
from contextbench.retrieval.rerank import Reranker


class EvaluationError(RuntimeError):
    """Raised when benchmark inputs or immutable outputs are invalid."""


@dataclass(frozen=True)
class EvaluationCorpus:
    """Questions and parsed documents keyed by dataset document ID."""

    questions: tuple[BenchmarkQuestion, ...]
    documents: Mapping[str, IRDocument]
    source_documents: Mapping[str, DoclingDocument]


@dataclass(frozen=True)
class BenchmarkRun:
    """Completed immutable run and its in-memory summaries."""

    path: Path
    manifest: RunManifest
    summary: RetrievalBenchmarkSummary
    records: tuple[RetrievalEvaluationRecord, ...]
    stage_audits: tuple[CompilerStageAuditRecord, ...] = ()


def run_retrieval_benchmark(
    corpus: EvaluationCorpus,
    *,
    config: RetrievalBenchmarkConfig,
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
) -> BenchmarkRun:
    """Run all configured evidence-only cells and publish immutable artifacts."""
    _validate_corpus(corpus)
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
        f"retrieval-{created_at.strftime('%Y%m%dT%H%M%SZ')}-{config_sha256[:12]}"
    )
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", resolved_run_id):
        raise EvaluationError("run_id contains unsafe path characters")
    final_path = artifacts_root / "runs" / resolved_run_id
    if final_path.exists():
        raise EvaluationError(f"completed run already exists: {final_path}")

    ordered_document_ids = sorted(corpus.documents)
    documents = [corpus.documents[document_id] for document_id in ordered_document_ids]
    sources_by_ir_id = {
        corpus.documents[document_id].id: corpus.source_documents[document_id]
        for document_id in ordered_document_ids
    }
    indexes = _build_indexes(
        documents,
        sources_by_ir_id=sources_by_ir_id,
        systems=config.systems,
        config=config,
        artifacts_root=artifacts_root,
        tokenizer=counter,
        embedder=shared_embedder,
        reranker=shared_reranker,
    )
    records, contexts, stage_audits = _evaluate_cells(
        corpus,
        config=config,
        indexes=indexes,
        tokenizer=counter,
        embedder=shared_embedder,
        reranker=shared_reranker,
    )
    summary = summarize(resolved_run_id, records)
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
        systems=tuple(system.value for system in config.systems),
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
    _publish_run(
        final_path,
        manifest=manifest,
        records=records,
        contexts=contexts,
        stage_audits=stage_audits,
        summary=summary,
    )
    return BenchmarkRun(
        path=final_path,
        manifest=manifest,
        summary=summary,
        records=records,
        stage_audits=stage_audits,
    )


def _build_indexes(
    documents: Sequence[IRDocument],
    *,
    sources_by_ir_id: Mapping[str, DoclingDocument],
    systems: Sequence[BenchmarkSystem],
    config: RetrievalBenchmarkConfig,
    artifacts_root: Path,
    tokenizer: TokenCounter,
    embedder: EmbeddingModel,
    reranker: Reranker,
) -> dict[BenchmarkSystem, HybridIndex]:
    indexes: dict[BenchmarkSystem, HybridIndex] = {}
    if BenchmarkSystem.FIXED in systems:
        indexes[BenchmarkSystem.FIXED] = HybridIndex.build(
            documents,
            arm=RetrievalArm.FIXED,
            config=config.retrieval,
            tokenizer=tokenizer,
            embedder=embedder,
            reranker=reranker,
            artifacts_root=artifacts_root,
        )
    if BenchmarkSystem.STRUCTURAL in systems or config.compiler_stage_audit:
        indexes[BenchmarkSystem.STRUCTURAL] = HybridIndex.build(
            documents,
            arm=RetrievalArm.STRUCTURAL,
            config=config.retrieval,
            source_documents=sources_by_ir_id,
            tokenizer=tokenizer,
            embedder=embedder,
            reranker=reranker,
            artifacts_root=artifacts_root,
        )
    if BenchmarkSystem.COMPILER in systems:
        chunks = node_chunks(
            documents,
            tokenizer=tokenizer,
            table_rows=config.compiler.table_row_retrieval_enabled,
            table_row_group_size=config.compiler.table_row_group_size,
            table_empty_cell_marker=config.compiler.table_empty_cell_marker,
        )
        index = HybridIndex(
            chunks,
            config=config.retrieval,
            tokenizer=tokenizer,
            embedder=embedder,
            reranker=reranker,
        )
        index.save(
            artifacts_root,
            documents=documents,
            arm=RetrievalArm.COMPILER,
        )
        indexes[BenchmarkSystem.COMPILER] = index
    return indexes


def _evaluate_cells(
    corpus: EvaluationCorpus,
    *,
    config: RetrievalBenchmarkConfig,
    indexes: Mapping[BenchmarkSystem, HybridIndex],
    tokenizer: TokenCounter,
    embedder: EmbeddingModel,
    reranker: Reranker,
) -> tuple[
    tuple[RetrievalEvaluationRecord, ...],
    tuple[dict[str, object], ...],
    tuple[CompilerStageAuditRecord, ...],
]:
    records: list[RetrievalEvaluationRecord] = []
    contexts: list[dict[str, object]] = []
    stage_audits: list[CompilerStageAuditRecord] = []
    for question in corpus.questions:
        question_documents = {
            document_id: corpus.documents[document_id]
            for document_id in question.document_ids
        }
        ir_document_ids = {document.id for document in question_documents.values()}
        scope = DocumentScope.from_documents(
            question_documents.values(),
            source_documents={
                document.id: corpus.source_documents[document_id]
                for document_id, document in question_documents.items()
            },
        )
        retrieval_systems = list(config.systems)
        if (
            config.compiler_stage_audit
            and BenchmarkSystem.STRUCTURAL not in retrieval_systems
        ):
            retrieval_systems.append(BenchmarkSystem.STRUCTURAL)
        raw_rankings: dict[BenchmarkSystem, tuple[RankedEvidence, ...]] = {}
        rankings: dict[BenchmarkSystem, tuple[RankedEvidence, ...]] = {}
        retrieval_latencies: dict[BenchmarkSystem, float] = {}
        for system in retrieval_systems:
            retrieval_started = time.perf_counter_ns()
            raw_ranked = indexes[system].retrieve(
                question.question,
                token_budget=max(config.budgets),
                document_ids=ir_document_ids,
            )
            ranked = raw_ranked
            if system == BenchmarkSystem.COMPILER:
                ranked = retrieve_faceted(
                    indexes[system],
                    question.question,
                    raw_ranked,
                    token_budget=max(config.budgets),
                    document_ids=ir_document_ids,
                    config=config.compiler,
                )
            raw_rankings[system] = raw_ranked
            rankings[system] = ranked
            retrieval_latencies[system] = (
                time.perf_counter_ns() - retrieval_started
            ) / 1_000_000

        for system in config.systems:
            compiler_cache = (
                CompilerQueryCache() if system == BenchmarkSystem.COMPILER else None
            )
            ranked = rankings[system]
            retrieval_elapsed_ms = retrieval_latencies[system]
            for budget in config.budgets:
                started = time.perf_counter_ns()
                trace = None
                if system == BenchmarkSystem.COMPILER and config.compiler_stage_audit:
                    packet, trace = compile_context_with_trace(
                        question.question,
                        scope,
                        budget,
                        config.compiler,
                        tokenizer=tokenizer,
                        embedder=embedder,
                        reranker=reranker,
                        hybrid_index=indexes[system],
                        ranked_evidence=ranked,
                        query_cache=compiler_cache,
                    )
                else:
                    packet = _context_for_system(
                        question.question,
                        system=system,
                        budget=budget,
                        scope=scope,
                        config=config,
                        index=indexes[system],
                        tokenizer=tokenizer,
                        embedder=embedder,
                        reranker=reranker,
                        ranked_evidence=ranked,
                        compiler_cache=compiler_cache,
                    )
                elapsed_ms = retrieval_elapsed_ms + (
                    time.perf_counter_ns() - started
                ) / 1_000_000
                if (
                    compiler_cache is not None
                    and compiler_cache.page_neighbors_used
                    and compiler_cache.page_neighbor_cache_hit
                ):
                    elapsed_ms += compiler_cache.page_neighbor_prepare_ms
                metrics = evaluate_context(question, packet, corpus.documents)
                records.append(
                    RetrievalEvaluationRecord(
                        question_id=question.id,
                        system=system,
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
                        "system": system.value,
                        "token_budget": budget,
                        "context": packet.model_dump(mode="json"),
                    }
                )
                if trace is not None:
                    raw_chunks = [
                        evidence.chunk
                        for evidence in raw_rankings[BenchmarkSystem.COMPILER]
                    ]
                    faceted_chunks = [evidence.chunk for evidence in ranked]
                    structural_chunks = [
                        evidence.chunk
                        for evidence in rankings[BenchmarkSystem.STRUCTURAL]
                    ]
                    stage_audits.append(
                        CompilerStageAuditRecord(
                            question_id=question.id,
                            token_budget=budget,
                            gold_pages=gold_pages(question),
                            raw_node_retrieval=evaluate_candidate_stage(
                                question, raw_chunks, corpus.documents
                            ),
                            faceted_node_retrieval=evaluate_candidate_stage(
                                question, faceted_chunks, corpus.documents
                            ),
                            structural_retrieval=evaluate_candidate_stage(
                                question, structural_chunks, corpus.documents
                            ),
                            compiler_structural_union=evaluate_candidate_stage(
                                question,
                                [*faceted_chunks, *structural_chunks],
                                corpus.documents,
                            ),
                            structural_expansion=evaluate_compiler_candidates(
                                question,
                                trace.expanded_candidates,
                                corpus.documents,
                            ),
                            deduplication=evaluate_compiler_candidates(
                                question,
                                trace.deduplicated_candidates,
                                corpus.documents,
                            ),
                            packing=evaluate_packed_stage(
                                question, packet, corpus.documents
                            ),
                        )
                    )
    return tuple(records), tuple(contexts), tuple(stage_audits)


def _context_for_system(
    query: str,
    *,
    system: BenchmarkSystem,
    budget: int,
    scope: DocumentScope,
    config: RetrievalBenchmarkConfig,
    index: HybridIndex,
    tokenizer: TokenCounter,
    embedder: EmbeddingModel,
    reranker: Reranker,
    ranked_evidence: Sequence[RankedEvidence],
    compiler_cache: CompilerQueryCache | None,
) -> ContextPacket:
    if system == BenchmarkSystem.COMPILER:
        return compile_context(
            query,
            scope,
            budget,
            config.compiler,
            tokenizer=tokenizer,
            embedder=embedder,
            reranker=reranker,
            hybrid_index=index,
            ranked_evidence=ranked_evidence,
            query_cache=compiler_cache,
        )
    return index.pack_ranked(
        query,
        ranked_evidence,
        token_budget=budget,
    )


def _validate_corpus(corpus: EvaluationCorpus) -> None:
    if not corpus.questions:
        raise EvaluationError("retrieval benchmark requires at least one question")
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
    ir_ids = [corpus.documents[document_id].id for document_id in required]
    if len(ir_ids) != len(set(ir_ids)):
        raise EvaluationError("dataset documents resolve to duplicate IR IDs")


def _publish_run(
    final_path: Path,
    *,
    manifest: RunManifest,
    records: Sequence[RetrievalEvaluationRecord],
    contexts: Sequence[dict[str, object]],
    stage_audits: Sequence[CompilerStageAuditRecord],
    summary: RetrievalBenchmarkSummary,
) -> None:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".retrieval-run-", dir=final_path.parent))
    try:
        _write_json(staging / "manifest.json", manifest.model_dump(mode="json"))
        _write_jsonl(
            staging / "retrieval.jsonl",
            [record.model_dump(mode="json") for record in records],
        )
        _write_jsonl(staging / "contexts.jsonl", contexts)
        if stage_audits:
            _write_jsonl(
                staging / "compiler-stages.jsonl",
                [record.model_dump(mode="json") for record in stage_audits],
            )
        _write_json(staging / "summary.json", summary.model_dump(mode="json"))
        (staging / "report.md").write_text(
            markdown_report(summary),
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
