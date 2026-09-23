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
# Hugging Face commits the model IDs above resolved to when these defaults were
# pinned. A model ID alone names a moving branch, so a run configured with only
# the ID is not reproducible: the pin lives here, in configuration, rather than
# in the retrieval library.
DEFAULT_EMBEDDING_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
DEFAULT_RERANKER_REVISION = "233902d25c440f23af6f7d6e94d2946bac0bee0a"
# The offline deterministic models have no hub identity, so no commit can pin
# them: ``embedding_model_from_config`` and ``reranker_from_config`` build them
# locally and ignore the revision argument. Selecting one is therefore not a
# model/revision mismatch. These two names mirror the dispatch in
# ``contextbench.retrieval.index``; keep them in step with it.
OFFLINE_EMBEDDING_PREFIX = "hash-"
OFFLINE_RERANKER_MODEL = "lexical-overlap-v1"
# Command-line spelling of the two heading-context positions, matching the
# ``heading-on`` / ``heading-off`` labels the factorial report and manifest use.
HEADING_CONTEXT_POSITIONS = {"on": True, "off": False}


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
        typer.Option(
            help=(
                "SentenceTransformers embedding model ID. A non-default hub "
                "ID requires an explicit --embedding-revision; the offline "
                "hash-* models take none."
            )
        ),
    ] = DEFAULT_EMBEDDING_MODEL,
    embedding_revision: Annotated[
        str,
        typer.Option(help="Pinned Hugging Face commit for the embedding model."),
    ] = DEFAULT_EMBEDDING_REVISION,
    reranker_model: Annotated[
        str,
        typer.Option(
            help=(
                "SentenceTransformers cross-encoder model ID. A non-default "
                "hub ID requires an explicit --reranker-revision; the offline "
                "lexical-overlap-v1 reranker takes none."
            )
        ),
    ] = DEFAULT_RERANKER_MODEL,
    reranker_revision: Annotated[
        str,
        typer.Option(help="Pinned Hugging Face commit for the cross-encoder."),
    ] = DEFAULT_RERANKER_REVISION,
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
        typer.Option(
            help=(
                "Compiler packing strategy: ranked, coverage, or adaptive "
                "(coverage-pack until breadth is exhausted, then backfill in "
                "reranked order)."
            )
        ),
    ] = "coverage",
    compiler_node_heading_search_context: Annotated[
        bool,
        typer.Option(
            "--compiler-node-heading-search-context"
            "/--no-compiler-node-heading-search-context",
            help=(
                "Index the heading trail with each compiler IR-node candidate. "
                "Off leaves the structural arm's heading context untouched."
            ),
        ),
    ] = True,
    # The six expansion switches the D1-D4 ablations in
    # ``docs/specs/benchmark.md`` section 25 turn on and off. Every default
    # below is the shipped ``CompilerConfig`` default, so an invocation that
    # names none of them is unchanged. See
    # ``contextbench.evaluation.ablations`` for the configurations themselves.
    compiler_heading_context: Annotated[
        bool,
        typer.Option(
            "--compiler-heading-context/--no-compiler-heading-context",
            help="Render the heading trail above each piece of evidence.",
        ),
    ] = True,
    compiler_previous_sibling: Annotated[
        bool,
        typer.Option(
            "--compiler-previous-sibling/--no-compiler-previous-sibling",
            help=(
                "Expand a paragraph hit to the paragraph before it. On by "
                "default since the Phase 1 freeze."
            ),
        ),
    ] = True,
    compiler_next_sibling: Annotated[
        bool,
        typer.Option(
            "--compiler-next-sibling/--no-compiler-next-sibling",
            help=(
                "Expand a paragraph hit to the paragraph after it. On by "
                "default since the Phase 1 freeze."
            ),
        ),
    ] = True,
    compiler_group_adjacent_list_items: Annotated[
        bool,
        typer.Option(
            "--compiler-group-adjacent-list-items"
            "/--no-compiler-group-adjacent-list-items",
            help="Expand a list-item hit to its adjacent list items.",
        ),
    ] = True,
    compiler_preserve_tables: Annotated[
        bool,
        typer.Option(
            "--compiler-preserve-tables/--no-compiler-preserve-tables",
            help=(
                "Emit header-bearing fragments for a table too large for the "
                "budget instead of dropping it."
            ),
        ),
    ] = True,
    compiler_page_neighbor_radius: Annotated[
        int,
        typer.Option(
            min=0,
            help=(
                "Pages either side of a hit eligible as fixed-window "
                "neighbour evidence. 0 disables page neighbours."
            ),
        ),
    ] = 3,
    budget_accounting: Annotated[
        str,
        typer.Option(
            help=(
                "What the token budget counts, for every arm: "
                "rendered_evidence (tags, evidence IDs, joiners and content, "
                "as the answer prompt carries them) or content (the earlier "
                "accounting, kept so a re-baseline can measure the change)."
            ),
        ),
    ] = "rendered_evidence",
    evidence_render_version: Annotated[
        str,
        typer.Option(
            help=(
                "How evidence is rendered and priced: evidence-render-v2 "
                "(positional aliases E1, E2, ...; the default) or "
                "evidence-render-v1 (full evidence IDs, as earlier runs used)."
            ),
        ),
    ] = "evidence-render-v2",
    run_id: Annotated[
        str | None,
        typer.Option(help="Optional immutable run identifier."),
    ] = None,
    allow_dirty: Annotated[
        bool,
        typer.Option(
            "--allow-dirty",
            help=(
                "Record a run from a modified worktree, stamping "
                "git_dirty: true in the manifest."
            ),
        ),
    ] = False,
) -> None:
    """Run the evidence-only A/B/C/D benchmark on a committed XL subset."""
    # Keep evaluation and model imports off lightweight CLI paths.
    from contextbench.compiler import CompilerConfig
    from contextbench.evaluation import RetrievalBenchmarkConfig
    from contextbench.evaluation.xl_docbench import run_xl_retrieval
    from contextbench.ingest import IngestionError
    from contextbench.ir.project import IRProjectionError
    from contextbench.retrieval import RetrievalConfig

    _require_matching_revisions(
        embedding_model=embedding_model,
        embedding_revision=embedding_revision,
        reranker_model=reranker_model,
        reranker_revision=reranker_revision,
    )
    # One ``RetrievalConfig`` is shared by every arm and by the compiler, so the
    # asymmetric configuration the development factorial pointed at -- heading
    # context for the structural baseline, none for the compiler's node
    # candidates -- is reachable only because those are two fields. The
    # structural field has no flag: this phase makes the asymmetry reachable
    # without moving any default.
    retrieval = RetrievalConfig(
        embedding_model=embedding_model,
        reranker_model=reranker_model,
        compiler_node_heading_search_context=compiler_node_heading_search_context,
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
            include_heading_context=compiler_heading_context,
            include_previous_sibling=compiler_previous_sibling,
            include_next_sibling=compiler_next_sibling,
            group_adjacent_list_items=compiler_group_adjacent_list_items,
            preserve_tables=compiler_preserve_tables,
            page_neighbor_radius=compiler_page_neighbor_radius,
            budget_accounting=budget_accounting,
            evidence_render_version=evidence_render_version,
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
            embedding_revision=embedding_revision,
            reranker_revision=reranker_revision,
            run_id=run_id,
            allow_dirty=allow_dirty,
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
        typer.Option(
            help=(
                "SentenceTransformers embedding model ID. A non-default hub "
                "ID requires an explicit --embedding-revision; the offline "
                "hash-* models take none."
            )
        ),
    ] = DEFAULT_EMBEDDING_MODEL,
    embedding_revision: Annotated[
        str,
        typer.Option(help="Pinned Hugging Face commit for the embedding model."),
    ] = DEFAULT_EMBEDDING_REVISION,
    reranker_model: Annotated[
        str,
        typer.Option(
            help=(
                "SentenceTransformers cross-encoder model ID. A non-default "
                "hub ID requires an explicit --reranker-revision; the offline "
                "lexical-overlap-v1 reranker takes none."
            )
        ),
    ] = DEFAULT_RERANKER_MODEL,
    reranker_revision: Annotated[
        str,
        typer.Option(help="Pinned Hugging Face commit for the cross-encoder."),
    ] = DEFAULT_RERANKER_REVISION,
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
    heading_context: Annotated[
        list[str] | None,
        typer.Option(
            "--heading-context",
            help=(
                "Repeatable heading-context position, on or off; defaults to "
                "on alone. Passing both crosses the heading-context ablation "
                "with every unit and policy and doubles the cell count."
            ),
        ),
    ] = None,
    budget_accounting: Annotated[
        str,
        typer.Option(
            help=(
                "What the token budget counts in every cell: "
                "rendered_evidence or content. See eval-retrieval."
            ),
        ),
    ] = "rendered_evidence",
    evidence_render_version: Annotated[
        str,
        typer.Option(
            help=(
                "How evidence is rendered and priced in every cell: "
                "evidence-render-v2 or evidence-render-v1. See eval-retrieval."
            ),
        ),
    ] = "evidence-render-v2",
    run_id: Annotated[
        str | None,
        typer.Option(help="Optional immutable factorial run identifier."),
    ] = None,
    allow_dirty: Annotated[
        bool,
        typer.Option(
            "--allow-dirty",
            help=(
                "Record a run from a modified worktree, stamping "
                "git_dirty: true in the manifest."
            ),
        ),
    ] = False,
) -> None:
    """Cross content units with ranked and faceted-coverage policies."""
    from pydantic import ValidationError

    from contextbench.evaluation import FactorialConfig, FactorialFacetConfig
    from contextbench.evaluation.factorial_xl import run_xl_factorial
    from contextbench.ingest import IngestionError
    from contextbench.ir.project import IRProjectionError
    from contextbench.retrieval import RetrievalConfig

    _require_matching_revisions(
        embedding_model=embedding_model,
        embedding_revision=embedding_revision,
        reranker_model=reranker_model,
        reranker_revision=reranker_revision,
    )
    retrieval = RetrievalConfig(
        embedding_model=embedding_model,
        reranker_model=reranker_model,
    )
    # An omitted flag passes no factor at all, so the single-valued default on
    # ``FactorialConfig.heading_contexts`` stays the only definition of it and
    # a run without the flag is identical to one made before the flag existed.
    factors: dict[str, tuple[bool, ...]] = {}
    if heading_context is not None:
        factors["heading_contexts"] = _heading_contexts(heading_context)
    try:
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
            budget_accounting=budget_accounting,
            evidence_render_version=evidence_render_version,
            **factors,
        )
    except ValidationError as exc:
        # The config owns the factor rules -- non-empty and unique -- so the
        # CLI surfaces its message rather than carrying a second copy of them.
        _abort(
            "; ".join(
                str(error["msg"]).removeprefix("Value error, ")
                for error in exc.errors()
            )
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
            embedding_revision=embedding_revision,
            reranker_revision=reranker_revision,
            run_id=run_id,
            allow_dirty=allow_dirty,
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
    temperature: Annotated[
        float | None,
        typer.Option(
            min=0,
            help="Optional sampling temperature; unset sends no temperature.",
        ),
    ] = None,
    seed: Annotated[
        int | None,
        typer.Option(help="Optional provider sampling seed; unset sends no seed."),
    ] = None,
    citation_entailment_judge: Annotated[
        bool,
        typer.Option(
            help=(
                "Use the same model for a second call judging whether cited "
                "evidence semantically supports each answer."
            )
        ),
    ] = False,
    run_id: Annotated[
        str | None,
        typer.Option(help="Optional immutable generation run identifier."),
    ] = None,
    allow_dirty: Annotated[
        bool,
        typer.Option(
            "--allow-dirty",
            help=(
                "Record a run from a modified worktree, stamping "
                "git_dirty: true in the manifest."
            ),
        ),
    ] = False,
    expected_retrieval_artifact_sha256: Annotated[
        str | None,
        typer.Option(
            help=(
                "Refuse to run, before any provider call, unless the retrieval "
                "run's manifest.json and contexts.jsonl hash to this value. "
                "Use the value a preregistration pins."
            ),
        ),
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
        answer_calls = (
            len(retrieval_manifest["question_ids"])
            * len(selected_systems)
            * len(selected_budgets)
        )
        expected_calls = answer_calls * (2 if citation_entailment_judge else 1)
        if expected_calls > max_calls:
            raise GenerationError(
                f"run requires {expected_calls} calls, above --max-calls {max_calls}"
            )
        config = GenerationConfig(
            model=model,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
            temperature=temperature,
            seed=seed,
            systems=selected_systems,
            budgets=selected_budgets,
            citation_entailment_judge=citation_entailment_judge,
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
            allow_dirty=allow_dirty,
            expected_retrieval_artifact_sha256=expected_retrieval_artifact_sha256,
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
    allow_dirty: Annotated[
        bool,
        typer.Option(
            "--allow-dirty",
            help=(
                "Record a run from a modified worktree, stamping "
                "git_dirty: true in the manifest."
            ),
        ),
    ] = False,
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
            allow_dirty=allow_dirty,
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


def _require_matching_revisions(
    *,
    embedding_model: str,
    embedding_revision: str,
    reranker_model: str,
    reranker_revision: str,
) -> None:
    """Refuse a non-default hub model ID still carrying the default revision.

    Each default revision is the commit its own default model ID resolved to.
    Pairing it with a different hub model ID would stamp a manifest with a hash
    that never belonged to those weights, so fail before the run starts rather
    than leave the hub to reject the pair mid-download.

    An offline model name is exempt. It resolves to no hub repository, so there
    is no commit to name and the revision is never used; demanding one would be
    asking for something that cannot exist.
    """
    pairs = (
        (
            "--embedding-model",
            embedding_model,
            DEFAULT_EMBEDDING_MODEL,
            "--embedding-revision",
            embedding_revision,
            DEFAULT_EMBEDDING_REVISION,
            embedding_model.startswith(OFFLINE_EMBEDDING_PREFIX),
        ),
        (
            "--reranker-model",
            reranker_model,
            DEFAULT_RERANKER_MODEL,
            "--reranker-revision",
            reranker_revision,
            DEFAULT_RERANKER_REVISION,
            reranker_model == OFFLINE_RERANKER_MODEL,
        ),
    )
    for (
        model_flag,
        model,
        default_model,
        revision_flag,
        revision,
        default_revision,
        is_offline,
    ) in pairs:
        if is_offline:
            continue
        if model != default_model and revision == default_revision:
            _abort(
                f"{model_flag} {model} is not the default model, and "
                f"{revision_flag} is still the default revision "
                f"{default_revision}, which pins {default_model}. Pass "
                f"{revision_flag} <commit> naming the commit of {model}."
            )


def _heading_contexts(values: list[str]) -> tuple[bool, ...]:
    """Map repeated ``--heading-context`` tokens onto the factorial booleans.

    The tokens are spelled as the generated report and the manifest system
    names spell the positions, ``on`` and ``off``. Only the vocabulary is
    checked here; whether the resulting tuple is non-empty and unique is
    ``FactorialConfig``'s rule and is left to its validator.
    """
    positions: list[bool] = []
    for value in values:
        if value not in HEADING_CONTEXT_POSITIONS:
            _abort(f"--heading-context takes 'on' or 'off', not {value!r}")
        positions.append(HEADING_CONTEXT_POSITIONS[value])
    return tuple(positions)


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
