"""End-to-end XL-DocBench retrieval benchmark preparation."""

import hashlib
from collections.abc import Callable
from pathlib import Path

from contextbench.datasets.download import SourceDocumentCache, download_release
from contextbench.datasets.subsets import load_subset
from contextbench.datasets.xl_docbench import (
    DATASET_NAME,
    RELEASE_REVISION,
    RELEASE_VERSION,
    XLDocBenchDataset,
)
from contextbench.evaluation.models import RetrievalBenchmarkConfig
from contextbench.evaluation.runner import (
    BenchmarkRun,
    EvaluationCorpus,
    EvaluationError,
    run_retrieval_benchmark,
)
from contextbench.ingest import DoclingParser, IngestionCache
from contextbench.ir import project_document
from contextbench.ir.tokenizer import TiktokenTokenCounter

ProgressCallback = Callable[[str], None]


def run_xl_retrieval(
    *,
    data_dir: Path,
    subset_file: Path,
    retrieval_corpus_subset_file: Path | None = None,
    source_cache_dir: Path,
    ingest_cache_dir: Path,
    artifacts_root: Path,
    config: RetrievalBenchmarkConfig,
    docling_artifacts_dir: Path | None = None,
    embedding_revision: str | None = None,
    reranker_revision: str | None = None,
    run_id: str | None = None,
    allow_dirty: bool = False,
    progress: ProgressCallback | None = None,
) -> BenchmarkRun:
    """Benchmark an XL question subset against an optional fixed retrieval corpus."""
    report = progress or (lambda _message: None)
    report("verifying pinned XL-DocBench release")
    download_release(data_dir)
    dataset = XLDocBenchDataset(data_dir)
    subset = load_subset(subset_file)
    questions = tuple(dataset.iter_subset(subset))
    retrieval_corpus_file = retrieval_corpus_subset_file or subset_file
    retrieval_corpus_subset = load_subset(retrieval_corpus_file)
    retrieval_corpus_questions = tuple(
        dataset.iter_subset(retrieval_corpus_subset)
    )
    evaluation_ids = {question.id for question in questions}
    retrieval_corpus_ids = {
        question.id for question in retrieval_corpus_questions
    }
    if not evaluation_ids.issubset(retrieval_corpus_ids):
        missing = sorted(evaluation_ids.difference(retrieval_corpus_ids))
        raise EvaluationError(
            "evaluation subset is not contained in retrieval corpus subset: "
            f"{missing}"
        )

    document_ids = tuple(
        sorted(
            {
                document_id
                for question in retrieval_corpus_questions
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

    system_names = ", ".join(system.value for system in config.systems)
    report(f"running {system_names} evidence retrieval")
    return run_retrieval_benchmark(
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
        retrieval_corpus_name=retrieval_corpus_subset.name,
        retrieval_corpus_sha256=_sha256(retrieval_corpus_file),
        retrieval_corpus_question_ids=tuple(
            question.id for question in retrieval_corpus_questions
        ),
        run_id=run_id,
        tokenizer=tokenizer,
        embedding_revision=embedding_revision,
        reranker_revision=reranker_revision,
        allow_dirty=allow_dirty,
    )


# Backward-compatible name retained for callers from the XL100 milestone.
run_xl100_retrieval = run_xl_retrieval


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
