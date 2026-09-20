"""XL-DocBench preparation for the gold-evidence representation experiment."""

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
from contextbench.evaluation.runner import EvaluationCorpus
from contextbench.generation import AnswerProvider
from contextbench.ingest import DoclingParser, IngestionCache
from contextbench.ir import project_document
from contextbench.ir.tokenizer import TiktokenTokenCounter
from contextbench.representation.models import RepresentationExperimentConfig
from contextbench.representation.runner import (
    RepresentationRun,
    run_gold_representation_benchmark,
)

ProgressCallback = Callable[[str], None]


def run_xl_gold_representation(
    *,
    data_dir: Path,
    subset_file: Path,
    source_cache_dir: Path,
    ingest_cache_dir: Path,
    artifacts_root: Path,
    config: RepresentationExperimentConfig,
    provider: AnswerProvider,
    docling_artifacts_dir: Path | None = None,
    run_id: str | None = None,
    progress: ProgressCallback | None = None,
) -> RepresentationRun:
    """Prepare selected XL documents and compare gold-page representations."""
    report = progress or (lambda _message: None)
    report("verifying pinned XL-DocBench release")
    download_release(data_dir)
    dataset = XLDocBenchDataset(data_dir)
    subset = load_subset(subset_file)
    questions = tuple(dataset.iter_subset(subset))
    document_ids = tuple(
        sorted(
            {
                document_id
                for question in questions
                if any(question.gold_evidence_pages.values())
                for document_id in question.gold_evidence_pages
            }
        )
    )
    report(
        f"preparing {len(document_ids)} gold-evidence source documents "
        f"for {len(questions)} questions"
    )
    source_cache = SourceDocumentCache(source_cache_dir)
    ingestion_cache = IngestionCache(
        ingest_cache_dir,
        DoclingParser(artifacts_path=docling_artifacts_dir),
    )
    tokenizer = TiktokenTokenCounter(config.tokenizer_name)
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

    report(
        "running "
        + ", ".join(condition.value for condition in config.conditions)
        + " gold-evidence representations"
    )
    return run_gold_representation_benchmark(
        EvaluationCorpus(
            questions=questions,
            documents=documents,
            source_documents=source_documents,
        ),
        config=config,
        provider=provider,
        artifacts_root=artifacts_root,
        dataset=DATASET_NAME,
        dataset_version=RELEASE_VERSION,
        dataset_revision=RELEASE_REVISION,
        subset_name=subset.name,
        subset_sha256=hashlib.sha256(subset_file.read_bytes()).hexdigest(),
        run_id=run_id,
        tokenizer=tokenizer,
    )
