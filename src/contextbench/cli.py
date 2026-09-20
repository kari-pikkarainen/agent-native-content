"""Command-line interface for the Context IR benchmark."""

import json
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from contextbench import __version__
from contextbench.datasets.base import BenchmarkQuestion, DatasetError
from contextbench.datasets.download import SourceDocumentCache, download_release
from contextbench.datasets.subsets import load_subset
from contextbench.datasets.xl_docbench import DATASET_NAME, XLDocBenchDataset

app = typer.Typer(
    name="contextbench",
    help="Run reproducible context-compilation benchmark experiments.",
    no_args_is_help=True,
)
dataset_app = typer.Typer(help="Download and inspect benchmark datasets.")
app.add_typer(dataset_app, name="dataset")

DEFAULT_DATASET_DIR = Path("data/raw/xl-docbench")
DEFAULT_DOCUMENT_CACHE = Path("data/cache/xl-docbench")
DEFAULT_INGEST_CACHE = Path("data/cache/ingest")
DEFAULT_XL100 = Path("configs/subsets/xl100.json")
DEFAULT_ARTIFACTS_ROOT = Path("artifacts")
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def version_callback(value: bool) -> None:
    """Print the package version and exit."""
    if value:
        typer.echo(__version__)
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            callback=version_callback,
            is_eager=True,
            help="Show the package version and exit.",
        ),
    ] = None,
) -> None:
    """Run reproducible context-compilation benchmark experiments."""


@app.command("ingest")
def ingest_document(
    document: Annotated[Path, typer.Argument(help="Local PDF to ingest.")],
    cache_dir: Annotated[
        Path,
        typer.Option(help="Content-addressed ingestion cache directory."),
    ] = DEFAULT_INGEST_CACHE,
    artifacts_dir: Annotated[
        Path | None,
        typer.Option(help="Optional directory of pre-downloaded Docling models."),
    ] = None,
) -> None:
    """Convert a local PDF into a cached authoritative DoclingDocument."""
    # Keep Docling's expensive conversion imports off help and dataset paths.
    from contextbench.ingest import DoclingParser, IngestionCache, IngestionError

    try:
        result = IngestionCache(
            cache_dir,
            DoclingParser(artifacts_path=artifacts_dir),
        ).ingest(document)
    except IngestionError as exc:
        _abort(str(exc))
    value = {
        "artifact_dir": str(result.artifact_dir),
        "document_path": str(result.document_path),
        "heading_count": result.metadata.heading_count,
        "page_count": result.metadata.page_count,
        "parser_name": result.metadata.parser_name,
        "parser_version": result.metadata.parser_version,
        "reused": result.reused,
        "source_sha256": result.metadata.source_sha256,
        "table_count": result.metadata.table_count,
        "text_count": result.metadata.text_count,
    }
    typer.echo(json.dumps(value, ensure_ascii=False, sort_keys=True))


@app.command("eval-retrieval")
def evaluate_retrieval(
    data_dir: Annotated[
        Path,
        typer.Option(help="Directory for pinned XL-DocBench release metadata."),
    ] = DEFAULT_DATASET_DIR,
    subset_file: Annotated[
        Path,
        typer.Option(help="Committed benchmark subset manifest."),
    ] = DEFAULT_XL100,
    retrieval_corpus_subset_file: Annotated[
        Path | None,
        typer.Option(
            help=(
                "Optional parent subset whose documents define retrieval index "
                "statistics while only --subset-file questions are evaluated."
            )
        ),
    ] = None,
    source_cache_dir: Annotated[
        Path,
        typer.Option(help="Content-addressed source PDF cache."),
    ] = DEFAULT_DOCUMENT_CACHE,
    ingest_cache_dir: Annotated[
        Path,
        typer.Option(help="Content-addressed Docling ingestion cache."),
    ] = DEFAULT_INGEST_CACHE,
    artifacts_root: Annotated[
        Path,
        typer.Option(help="Root for derived indexes and immutable runs."),
    ] = DEFAULT_ARTIFACTS_ROOT,
    docling_artifacts_dir: Annotated[
        Path | None,
        typer.Option(help="Optional directory of pre-downloaded Docling models."),
    ] = None,
    embedding_model: Annotated[
        str,
        typer.Option(help="SentenceTransformers embedding model ID."),
    ] = DEFAULT_EMBEDDING_MODEL,
    reranker_model: Annotated[
        str,
        typer.Option(help="SentenceTransformers cross-encoder model ID."),
    ] = DEFAULT_RERANKER_MODEL,
    seed: Annotated[
        int,
        typer.Option(help="Recorded benchmark seed."),
    ] = 20260919,
    compiler_stage_audit: Annotated[
        bool,
        typer.Option(
            "--compiler-stage-audit",
            help=(
                "Write candidate recall at retrieval, expansion, deduplication, "
                "and packing boundaries."
            ),
        ),
    ] = False,
    compiler_keyed_table_joins: Annotated[
        bool,
        typer.Option(
            "--compiler-keyed-table-joins/--no-compiler-keyed-table-joins",
            help=(
                "Join rows deterministically across explicitly referenced "
                "tables."
            ),
        ),
    ] = True,
    compiler_node_rerank_candidate_limit: Annotated[
        int,
        typer.Option(
            min=1,
            help="Maximum compiler node candidates reranked per query or facet.",
        ),
    ] = 250,
    compiler_query_facet_rerank_candidate_limit: Annotated[
        int,
        typer.Option(
            min=1,
            help="Maximum candidates reranked for each supplemental query facet.",
        ),
    ] = 250,
    run_id: Annotated[
        str | None,
        typer.Option(help="Optional immutable run identifier."),
    ] = None,
) -> None:
    """Run the evidence-only A/B/D benchmark on a committed XL subset."""
    # Keep evaluation and model imports off lightweight CLI paths.
    from contextbench.compiler import CompilerConfig
    from contextbench.evaluation import RetrievalBenchmarkConfig
    from contextbench.evaluation.xl_docbench import run_xl_retrieval
    from contextbench.ingest import IngestionError
    from contextbench.ir.project import IRProjectionError
    from contextbench.retrieval import RetrievalConfig

    retrieval = RetrievalConfig(
        embedding_model=embedding_model,
        reranker_model=reranker_model,
    )
    config = RetrievalBenchmarkConfig(
        seed=seed,
        compiler_stage_audit=compiler_stage_audit,
        retrieval=retrieval,
        compiler=CompilerConfig(
            retrieval=retrieval,
            keyed_table_join_enabled=compiler_keyed_table_joins,
            node_rerank_candidate_limit=compiler_node_rerank_candidate_limit,
            query_facet_rerank_candidate_limit=(
                compiler_query_facet_rerank_candidate_limit
            ),
        ),
    )
    try:
        result = run_xl_retrieval(
            data_dir=data_dir,
            subset_file=subset_file,
            retrieval_corpus_subset_file=retrieval_corpus_subset_file,
            source_cache_dir=source_cache_dir,
            ingest_cache_dir=ingest_cache_dir,
            artifacts_root=artifacts_root,
            docling_artifacts_dir=docling_artifacts_dir,
            config=config,
            run_id=run_id,
            progress=lambda message: typer.echo(message, err=True),
        )
    except (DatasetError, IngestionError, IRProjectionError, RuntimeError) as exc:
        _abort(str(exc))
    typer.echo(
        json.dumps(
            {
                "report": str(result.path / "report.md"),
                "run_dir": str(result.path),
                "run_id": result.manifest.run_id,
                "stage_audit": (
                    str(result.path / "compiler-stages.jsonl")
                    if compiler_stage_audit
                    else None
                ),
                "summary": str(result.path / "summary.json"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


@dataset_app.command("download")
def download_dataset(
    dataset_name: Annotated[str, typer.Argument(help="Dataset name.")],
    data_dir: Annotated[
        Path,
        typer.Option(help="Directory for pinned release metadata."),
    ] = DEFAULT_DATASET_DIR,
    sources: Annotated[
        bool,
        typer.Option(help="Also download and cache source PDFs."),
    ] = False,
    document_id: Annotated[
        list[str] | None,
        typer.Option(help="Limit source downloads to repeatable document IDs."),
    ] = None,
    cache_dir: Annotated[
        Path,
        typer.Option(help="Permanent source-document cache directory."),
    ] = DEFAULT_DOCUMENT_CACHE,
) -> None:
    """Download the pinned XL-DocBench release and optionally its source PDFs."""
    _require_xl_docbench(dataset_name)
    try:
        download_release(data_dir)
        typer.echo(f"release: {data_dir}")
        if not sources:
            return

        dataset = XLDocBenchDataset(data_dir)
        cache = SourceDocumentCache(cache_dir)
        requested = set(document_id or ())
        if requested:
            available = {source.id for source in dataset.iter_documents()}
            unknown = requested.difference(available)
            if unknown:
                names = ", ".join(sorted(unknown))
                raise typer.BadParameter(f"unknown document IDs: {names}")

        failures = 0
        for source in dataset.iter_documents():
            if requested and source.id not in requested:
                continue
            try:
                result = cache.fetch(source)
                status = "cached" if result.reused else "downloaded"
                typer.echo(f"{source.id}: {status} {result.sha256}")
            except DatasetError as exc:
                failures += 1
                typer.echo(f"{source.id}: ERROR {exc}", err=True)
        if failures:
            failure_log = cache_dir / "failures.jsonl"
            _abort(f"{failures} source download(s) failed; see {failure_log}")
    except DatasetError as exc:
        _abort(str(exc))


@dataset_app.command("inspect")
def inspect_question(
    dataset_name: Annotated[str, typer.Argument(help="Dataset name.")],
    question_id: Annotated[str, typer.Argument(help="Question ID to inspect.")],
    data_dir: Annotated[
        Path,
        typer.Option(help="Directory containing release metadata."),
    ] = DEFAULT_DATASET_DIR,
    verify_release: Annotated[
        bool,
        typer.Option(
            "--verify-release/--no-verify-release",
            help="Verify official release file hashes.",
        ),
    ] = True,
) -> None:
    """Print one normalized benchmark question as JSON."""
    _require_xl_docbench(dataset_name)
    try:
        dataset = XLDocBenchDataset(data_dir, verify_release=verify_release)
        question = dataset.get_question(question_id)
    except (DatasetError, KeyError) as exc:
        _abort(str(exc))
    typer.echo(_question_json(question))


@dataset_app.command("list")
def list_questions(
    dataset_name: Annotated[str, typer.Argument(help="Dataset name.")],
    subset_file: Annotated[
        Path,
        typer.Option(help="Committed subset manifest to list."),
    ] = DEFAULT_XL100,
    data_dir: Annotated[
        Path,
        typer.Option(help="Directory containing release metadata."),
    ] = DEFAULT_DATASET_DIR,
    verify_release: Annotated[
        bool,
        typer.Option(
            "--verify-release/--no-verify-release",
            help="Verify official release file hashes.",
        ),
    ] = True,
) -> None:
    """Print normalized subset questions as deterministic JSON Lines."""
    _require_xl_docbench(dataset_name)
    try:
        dataset = XLDocBenchDataset(data_dir, verify_release=verify_release)
        subset = load_subset(subset_file)
        for question in dataset.iter_subset(subset):
            typer.echo(_question_json(question))
    except DatasetError as exc:
        _abort(str(exc))


def _require_xl_docbench(dataset_name: str) -> None:
    if dataset_name not in {"xl-docbench", DATASET_NAME}:
        raise typer.BadParameter(
            f"unsupported dataset {dataset_name!r}; expected 'xl-docbench'"
        )


def _abort(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=1)


def _question_json(question: BenchmarkQuestion) -> str:
    value = {
        "answerable": question.answerable,
        "gold_answer": question.gold_answer,
        "gold_evidence_pages": {
            document_id: list(pages)
            for document_id, pages in question.gold_evidence_pages.items()
        },
        "question": question.question,
        "question_id": question.id,
        "source_document_ids": list(question.document_ids),
    }
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
