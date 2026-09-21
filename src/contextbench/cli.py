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
DEFAULT_XL100 = Path("benchmarks/xl-docbench/subsets/xl100.json")
DEFAULT_XLDEV2 = Path("benchmarks/xl-docbench/subsets/xldev2-tables.json")
DEFAULT_XLDEV24 = Path("benchmarks/xl-docbench/subsets/xldev24.json")
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


@app.command("agentize")
def agentize_document(
    document: Annotated[Path, typer.Argument(help="Local PDF to encode.")],
    output_dir: Annotated[
        Path,
        typer.Argument(help="New directory for the immutable agent-document bundle."),
    ],
    cache_dir: Annotated[
        Path,
        typer.Option(help="Content-addressed ingestion cache directory."),
    ] = DEFAULT_INGEST_CACHE,
    artifacts_dir: Annotated[
        Path | None,
        typer.Option(help="Optional directory of pre-downloaded Docling models."),
    ] = None,
    include_source: Annotated[
        bool,
        typer.Option(
            "--include-source/--no-include-source",
            help="Copy the hash-verified source PDF into the portable bundle.",
        ),
    ] = True,
) -> None:
    """Decode a PDF and create semantic HTML plus source-grounded JSON-LD."""
    from contextbench.agentdoc import AgentBundleError, create_agent_bundle
    from contextbench.ingest import DoclingParser, IngestionCache, IngestionError
    from contextbench.ir import IRProjectionError, project_document

    try:
        ingested = IngestionCache(
            cache_dir,
            DoclingParser(artifacts_path=artifacts_dir),
        ).ingest(document)
        projected = project_document(ingested.document, ingested.metadata)
        manifest = create_agent_bundle(
            projected,
            output_dir,
            source_path=document,
            include_source=include_source,
        )
    except (AgentBundleError, IngestionError, IRProjectionError, OSError) as exc:
        _abort(str(exc))
    typer.echo(
        json.dumps(
            {
                "bundle_dir": str(output_dir),
                "document_id": manifest.document_id,
                "html": str(output_dir / "agent.html"),
                "jsonld": str(output_dir / "enrichments.jsonld"),
                "manifest": str(output_dir / "manifest.json"),
                "source_included": manifest.source_file is not None,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


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
    compiler_heading_context_depth: Annotated[
        int | None,
        typer.Option(
            min=1,
            help="Optional number of trailing headings rendered with evidence.",
        ),
    ] = None,
    compiler_query_facet_rerank_candidate_limit: Annotated[
        int,
        typer.Option(
            min=1,
            help="Maximum candidates reranked for each supplemental query facet.",
        ),
    ] = 250,
    compiler_packing_strategy: Annotated[
        str,
        typer.Option(help="Compiler packing strategy: ranked or coverage."),
    ] = "coverage",
    run_id: Annotated[
        str | None,
        typer.Option(help="Optional immutable run identifier."),
    ] = None,
) -> None:
    """Run the evidence-only A/B/C/D benchmark on a committed XL subset."""
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
            heading_context_depth=compiler_heading_context_depth,
            query_facet_rerank_candidate_limit=(
                compiler_query_facet_rerank_candidate_limit
            ),
            packing_strategy=compiler_packing_strategy,
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


@app.command("eval-factorial")
def evaluate_factorial(
    data_dir: Annotated[
        Path,
        typer.Option(help="Directory for pinned XL-DocBench release metadata."),
    ] = DEFAULT_DATASET_DIR,
    subset_file: Annotated[
        Path,
        typer.Option(help="Small committed evaluation subset manifest."),
    ] = DEFAULT_XLDEV2,
    retrieval_corpus_subset_file: Annotated[
        Path,
        typer.Option(help="Fixed parent corpus defining all retrieval indexes."),
    ] = DEFAULT_XLDEV24,
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
        typer.Option(help="Recorded experiment seed."),
    ] = 20260919,
    query_facet_limit: Annotated[
        int,
        typer.Option(min=1, help="Maximum deterministic lexical query facets."),
    ] = 3,
    query_facet_min_terms: Annotated[
        int,
        typer.Option(min=1, help="Minimum terms required in a query facet."),
    ] = 3,
    query_facet_rerank_candidate_limit: Annotated[
        int,
        typer.Option(min=1, help="Maximum candidates reranked for each facet."),
    ] = 250,
    run_id: Annotated[
        str | None,
        typer.Option(help="Optional immutable factorial run identifier."),
    ] = None,
) -> None:
    """Cross content units with ranked and faceted-coverage policies."""
    from contextbench.evaluation import FactorialConfig, FactorialFacetConfig
    from contextbench.evaluation.factorial_xl import run_xl_factorial
    from contextbench.ingest import IngestionError
    from contextbench.ir.project import IRProjectionError
    from contextbench.retrieval import RetrievalConfig

    retrieval = RetrievalConfig(
        embedding_model=embedding_model,
        reranker_model=reranker_model,
    )
    config = FactorialConfig(
        seed=seed,
        retrieval=retrieval,
        faceting=FactorialFacetConfig(
            retrieval=retrieval,
            query_facet_limit=query_facet_limit,
            query_facet_min_terms=query_facet_min_terms,
            query_facet_rerank_candidate_limit=(
                query_facet_rerank_candidate_limit
            ),
        ),
    )
    try:
        result = run_xl_factorial(
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
                "summary": str(result.path / "summary.json"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


@app.command("eval-generation")
def evaluate_generation(
    retrieval_run: Annotated[
        Path,
        typer.Argument(help="Completed retrieval run containing contexts.jsonl."),
    ],
    model: Annotated[
        str,
        typer.Option(help="Explicit answer model ID."),
    ],
    input_usd_per_million: Annotated[
        float,
        typer.Option(min=0, help="Configured uncached input-token price."),
    ],
    cached_input_usd_per_million: Annotated[
        float,
        typer.Option(min=0, help="Configured cached input-token price."),
    ],
    output_usd_per_million: Annotated[
        float,
        typer.Option(min=0, help="Configured output-token price."),
    ],
    max_calls: Annotated[
        int,
        typer.Option(min=1, help="Hard authorization ceiling for provider calls."),
    ],
    data_dir: Annotated[
        Path,
        typer.Option(help="Directory for pinned XL-DocBench release metadata."),
    ] = DEFAULT_DATASET_DIR,
    subset_file: Annotated[
        Path,
        typer.Option(help="Committed subset containing the retrieval questions."),
    ] = DEFAULT_XL100,
    artifacts_root: Annotated[
        Path,
        typer.Option(help="Root for immutable generation runs."),
    ] = DEFAULT_ARTIFACTS_ROOT,
    system: Annotated[
        list[str] | None,
        typer.Option("--system", help="Repeatable system; defaults to retrieval run."),
    ] = None,
    budget: Annotated[
        list[int] | None,
        typer.Option("--budget", min=1, help="Repeatable budget; defaults to run."),
    ] = None,
    max_output_tokens: Annotated[
        int,
        typer.Option(min=1, help="Maximum answer tokens per provider call."),
    ] = 256,
    reasoning_effort: Annotated[
        str | None,
        typer.Option(help="Optional provider reasoning-effort setting."),
    ] = None,
    run_id: Annotated[
        str | None,
        typer.Option(help="Optional immutable generation run identifier."),
    ] = None,
) -> None:
    """Generate and score answers from immutable retrieval contexts."""
    from contextbench.evaluation import BenchmarkSystem
    from contextbench.generation import (
        GenerationConfig,
        GenerationError,
        OpenAIAnswerProvider,
        PricingMetadata,
        run_generation_benchmark,
    )

    try:
        retrieval_manifest = json.loads(
            (retrieval_run / "manifest.json").read_text(encoding="utf-8")
        )
        selected_systems = tuple(
            BenchmarkSystem(value)
            for value in (system or retrieval_manifest["systems"])
        )
        selected_budgets = tuple(
            sorted(set(budget or retrieval_manifest["token_budgets"]))
        )
        subset = load_subset(subset_file)
        dataset = XLDocBenchDataset(data_dir)
        questions = tuple(dataset.iter_subset(subset))
        expected_calls = (
            len(retrieval_manifest["question_ids"])
            * len(selected_systems)
            * len(selected_budgets)
        )
        if expected_calls > max_calls:
            raise GenerationError(
                f"run requires {expected_calls} calls, above --max-calls {max_calls}"
            )
        config = GenerationConfig(
            model=model,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
            systems=selected_systems,
            budgets=selected_budgets,
            pricing=PricingMetadata(
                input_usd_per_million=input_usd_per_million,
                cached_input_usd_per_million=cached_input_usd_per_million,
                output_usd_per_million=output_usd_per_million,
            ),
        )
        result = run_generation_benchmark(
            retrieval_run,
            questions,
            config=config,
            provider=OpenAIAnswerProvider(),
            artifacts_root=artifacts_root,
            run_id=run_id,
        )
    except (DatasetError, GenerationError, OSError, RuntimeError, ValueError) as exc:
        _abort(str(exc))
    typer.echo(
        json.dumps(
            {
                "report": str(result.path / "report.md"),
                "run_dir": str(result.path),
                "run_id": result.summary.run_id,
                "summary": str(result.path / "summary.json"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


@app.command("eval-representation")
def evaluate_representation(
    model: Annotated[
        str,
        typer.Option(help="Explicit answer model ID."),
    ],
    input_usd_per_million: Annotated[
        float,
        typer.Option(min=0, help="Configured uncached input-token price."),
    ],
    cached_input_usd_per_million: Annotated[
        float,
        typer.Option(min=0, help="Configured cached input-token price."),
    ],
    output_usd_per_million: Annotated[
        float,
        typer.Option(min=0, help="Configured output-token price."),
    ],
    max_calls: Annotated[
        int,
        typer.Option(min=1, help="Hard authorization ceiling for provider calls."),
    ],
    data_dir: Annotated[
        Path,
        typer.Option(help="Directory for pinned XL-DocBench release metadata."),
    ] = DEFAULT_DATASET_DIR,
    subset_file: Annotated[
        Path,
        typer.Option(help="Committed subset manifest."),
    ] = DEFAULT_XL100,
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
        typer.Option(help="Root for immutable representation runs."),
    ] = DEFAULT_ARTIFACTS_ROOT,
    docling_artifacts_dir: Annotated[
        Path | None,
        typer.Option(help="Optional directory of pre-downloaded Docling models."),
    ] = None,
    condition: Annotated[
        list[str] | None,
        typer.Option(
            "--condition",
            help="Repeatable raw, ir, or enriched condition; defaults to all.",
        ),
    ] = None,
    max_output_tokens: Annotated[
        int,
        typer.Option(min=1, help="Maximum answer tokens per provider call."),
    ] = 256,
    reasoning_effort: Annotated[
        str | None,
        typer.Option(help="Optional provider reasoning-effort setting."),
    ] = None,
    run_id: Annotated[
        str | None,
        typer.Option(help="Optional immutable representation run identifier."),
    ] = None,
) -> None:
    """Compare RAW, IR, and enriched encodings of identical gold pages."""
    from contextbench.generation import OpenAIAnswerProvider, PricingMetadata
    from contextbench.representation import (
        RepresentationCondition,
        RepresentationError,
        RepresentationExperimentConfig,
        run_xl_gold_representation,
    )

    try:
        download_release(data_dir)
        dataset = XLDocBenchDataset(data_dir)
        subset = load_subset(subset_file)
        questions = tuple(dataset.iter_subset(subset))
        conditions = tuple(
            RepresentationCondition(value)
            for value in (condition or tuple(RepresentationCondition))
        )
        eligible_count = sum(
            any(evidence.pages for evidence in question.gold_evidence)
            for question in questions
        )
        expected_calls = eligible_count * len(conditions)
        if expected_calls > max_calls:
            raise RepresentationError(
                f"run requires {expected_calls} calls, above --max-calls {max_calls}"
            )
        config = RepresentationExperimentConfig(
            model=model,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
            conditions=conditions,
            pricing=PricingMetadata(
                input_usd_per_million=input_usd_per_million,
                cached_input_usd_per_million=cached_input_usd_per_million,
                output_usd_per_million=output_usd_per_million,
            ),
        )
        result = run_xl_gold_representation(
            data_dir=data_dir,
            subset_file=subset_file,
            source_cache_dir=source_cache_dir,
            ingest_cache_dir=ingest_cache_dir,
            artifacts_root=artifacts_root,
            config=config,
            provider=OpenAIAnswerProvider(),
            docling_artifacts_dir=docling_artifacts_dir,
            run_id=run_id,
            progress=lambda message: typer.echo(message, err=True),
        )
    except (
        DatasetError,
        RepresentationError,
        OSError,
        RuntimeError,
        ValueError,
    ) as exc:
        _abort(str(exc))
    typer.echo(
        json.dumps(
            {
                "report": str(result.path / "report.md"),
                "run_dir": str(result.path),
                "run_id": result.summary.run_id,
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
