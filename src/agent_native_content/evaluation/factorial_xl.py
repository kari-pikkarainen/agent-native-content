"""XL-DocBench preparation for the controlled factorial experiment."""

import hashlib
from collections.abc import Callable
from pathlib import Path

from agent_native_content.datasets.download import SourceDocumentCache, download_release
from agent_native_content.datasets.subsets import load_subset
from agent_native_content.datasets.xl_docbench import (
    DATASET_NAME,
    RELEASE_REVISION,
    RELEASE_VERSION,
    XLDocBenchDataset,
)
from agent_native_content.evaluation.factorial import (
    FactorialRun,
    run_factorial_benchmark,
)
from agent_native_content.evaluation.factorial_models import FactorialConfig
from agent_native_content.evaluation.runner import EvaluationCorpus, EvaluationError
from agent_native_content.ingest import DoclingParser, IngestionCache
from agent_native_content.ingest.parallel import warm_ingestion_cache
from agent_native_content.ir import project_document
from agent_native_content.ir.tokenizer import TiktokenTokenCounter

ProgressCallback = Callable[[str], None]


def run_xl_factorial(
    *,
    data_dir: Path,
    subset_file: Path,
    retrieval_corpus_subset_file: Path,
    source_cache_dir: Path,
    ingest_cache_dir: Path,
    artifacts_root: Path,
    config: FactorialConfig,
    docling_artifacts_dir: Path | None = None,
    embedding_revision: str | None = None,
    reranker_revision: str | None = None,
    run_id: str | None = None,
    allow_dirty: bool = False,
    progress: ProgressCallback | None = None,
    parse_workers: int = 1,
) -> FactorialRun:
    """Run the controlled factorial on an XL subset and fixed parent corpus."""
    if parse_workers < 1:
        # Checked first, before any download, ingestion or run directory:
        # below, anything but > 1 would silently mean "sequential".
        raise ValueError(f"parse_workers must be at least 1, got {parse_workers}")
    report = progress or (lambda _message: None)
    report("verifying pinned XL-DocBench release")
    download_release(data_dir)
    dataset = XLDocBenchDataset(data_dir)
    subset = load_subset(subset_file)
    questions = tuple(dataset.iter_subset(subset))
    retrieval_subset = load_subset(retrieval_corpus_subset_file)
    retrieval_questions = tuple(dataset.iter_subset(retrieval_subset))
    evaluation_ids = {question.id for question in questions}
    retrieval_ids = {question.id for question in retrieval_questions}
    if not evaluation_ids.issubset(retrieval_ids):
        missing = sorted(evaluation_ids.difference(retrieval_ids))
        raise EvaluationError(
            "evaluation subset is not contained in retrieval corpus subset: "
            f"{missing}"
        )

    document_ids = tuple(
        sorted(
            {
                document_id
                for question in retrieval_questions
                for document_id in question.document_ids
            }
        )
    )
    report(
        f"preparing {len(document_ids)} retrieval-corpus source documents "
        f"for {len(questions)} evaluated questions"
    )
    source_cache = SourceDocumentCache(source_cache_dir)
    ingestion_cache = IngestionCache(
        ingest_cache_dir,
        DoclingParser(artifacts_path=docling_artifacts_dir),
    )
    if parse_workers > 1:
        # Parse uncached documents in parallel first; the loop below then runs
        # unchanged against a warm cache. At 1 this is skipped entirely.
        warm_ingestion_cache(
            [dataset.get_document(document_id) for document_id in document_ids],
            source_cache=source_cache,
            ingestion_cache=ingestion_cache,
            workers=parse_workers,
            progress=report,
        )
    tokenizer = TiktokenTokenCounter(config.retrieval.tokenizer_name)
    documents = {}
    source_documents = {}
    for position, document_id in enumerate(document_ids, 1):
        source = dataset.get_document(document_id)
        report(f"[{position}/{len(document_ids)}] {document_id}: source")
        cached = source_cache.fetch(source)
        report(f"[{position}/{len(document_ids)}] {document_id}: ingest")
        ingested = ingestion_cache.ingest(cached.path)
        documents[document_id] = project_document(
            ingested.document,
            ingested.metadata,
            source_uri=source.url,
            tokenizer=tokenizer,
        )
        source_documents[document_id] = ingested.document

    report("running controlled content-unit × selection-policy retrieval")
    return run_factorial_benchmark(
        EvaluationCorpus(
            questions=questions,
            documents=documents,
            source_documents=source_documents,
        ),
        config=config,
        artifacts_root=artifacts_root,
        dataset=DATASET_NAME,
        dataset_version=RELEASE_VERSION,
        dataset_revision=RELEASE_REVISION,
        subset_name=subset.name,
        subset_sha256=_sha256(subset_file),
        retrieval_corpus_name=retrieval_subset.name,
        retrieval_corpus_sha256=_sha256(retrieval_corpus_subset_file),
        retrieval_corpus_question_ids=tuple(
            question.id for question in retrieval_questions
        ),
        run_id=run_id,
        tokenizer=tokenizer,
        embedding_revision=embedding_revision,
        reranker_revision=reranker_revision,
        allow_dirty=allow_dirty,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
