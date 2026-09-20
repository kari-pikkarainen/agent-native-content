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

from contextbench.compiler import DocumentScope, compile_context
from contextbench.compiler.candidates import node_chunks
from contextbench.datasets.base import BenchmarkQuestion
from contextbench.evaluation.evidence import evaluate_context
from contextbench.evaluation.models import (
    BenchmarkSystem,
    RetrievalBenchmarkConfig,
    RetrievalBenchmarkSummary,
    RetrievalEvaluationRecord,
)
from contextbench.evaluation.reports import markdown_report, summarize
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
    run_id: str | None = None,
    tokenizer: TokenCounter | None = None,
    embedder: EmbeddingModel | None = None,
    reranker: Reranker | None = None,
    git_commit: str | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> BenchmarkRun:
    """Run all configured evidence-only cells and publish immutable artifacts."""
    _validate_corpus(corpus)
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
    records, contexts = _evaluate_cells(
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
        question_ids=tuple(question.id for question in corpus.questions),
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
        summary=summary,
    )
    return BenchmarkRun(
        path=final_path,
        manifest=manifest,
        summary=summary,
        records=records,
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
    if BenchmarkSystem.STRUCTURAL in systems:
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
        chunks = node_chunks(documents, tokenizer=tokenizer)
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
) -> tuple[tuple[RetrievalEvaluationRecord, ...], tuple[dict[str, object], ...]]:
    records: list[RetrievalEvaluationRecord] = []
    contexts: list[dict[str, object]] = []
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
        for system in config.systems:
            retrieval_started = time.perf_counter_ns()
            ranked = indexes[system].retrieve(
                question.question,
                token_budget=max(config.budgets),
                document_ids=ir_document_ids,
            )
            retrieval_elapsed_ms = (
                time.perf_counter_ns() - retrieval_started
            ) / 1_000_000
            for budget in config.budgets:
                started = time.perf_counter_ns()
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
                )
                elapsed_ms = retrieval_elapsed_ms + (
                    time.perf_counter_ns() - started
                ) / 1_000_000
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
    return tuple(records), tuple(contexts)


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
