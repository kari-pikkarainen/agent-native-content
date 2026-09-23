"""Tests for the command-line entry point."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from contextbench import __version__
from contextbench.cli import app
from contextbench.compiler import CompilerConfig
from contextbench.evaluation import BenchmarkSystem, RetrievalBenchmarkConfig
from contextbench.evaluation.ablations import (
    COMPILER_ABLATIONS,
    ablation_command_line,
)

runner = CliRunner()
FIXTURES = Path(__file__).parents[1] / "fixtures"


def test_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "context-compilation benchmark" in result.stdout


def test_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_dataset_inspect_prints_normalized_question() -> None:
    result = runner.invoke(
        app,
        [
            "dataset",
            "inspect",
            "xl-docbench",
            "adubench_single_fixture_002",
            "--data-dir",
            str(FIXTURES / "xl_docbench"),
            "--no-verify-release",
        ],
    )

    assert result.exit_code == 0
    value = json.loads(result.stdout)
    assert value == {
        "answerable": True,
        "gold_answer": "alpha",
        "gold_evidence_pages": {"doc_fixture_001": [3]},
        "question": "What is alpha?",
        "question_id": "adubench_single_fixture_002",
        "source_document_ids": ["doc_fixture_001"],
    }


def test_dataset_list_preserves_subset_order() -> None:
    result = runner.invoke(
        app,
        [
            "dataset",
            "list",
            "xl-docbench",
            "--data-dir",
            str(FIXTURES / "xl_docbench"),
            "--subset-file",
            str(FIXTURES / "xl_fixture_subset.json"),
            "--no-verify-release",
        ],
    )

    assert result.exit_code == 0
    question_ids = [
        json.loads(line)["question_id"] for line in result.stdout.splitlines()
    ]
    assert question_ids == [
        "adubench_single_fixture_002",
        "adubench_cross_fixture_001",
    ]


def test_dataset_error_is_reported_without_traceback(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "dataset",
            "inspect",
            "xl-docbench",
            "missing",
            "--data-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 1
    assert "release file not found" in result.output
    assert "Traceback" not in result.output


def test_eval_retrieval_runs_all_default_budgets_and_prints_artifacts(
    tmp_path: Path, monkeypatch
) -> None:
    captured = {}

    def fake_run_xl_retrieval(**kwargs):
        captured.update(kwargs)
        path = tmp_path / "artifacts" / "runs" / "run-1"
        return SimpleNamespace(
            path=path,
            manifest=SimpleNamespace(run_id="run-1"),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.xl_docbench.run_xl_retrieval",
        fake_run_xl_retrieval,
    )

    result = runner.invoke(
        app,
        [
            "eval-retrieval",
            "--artifacts-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "run-1",
        ],
    )

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output["run_id"] == "run-1"
    assert output["report"].endswith("run-1/report.md")
    config = captured["config"]
    assert config.budgets == (2048, 4096, 8192, 16384)
    assert set(config.systems) == set(BenchmarkSystem)
    assert config.retrieval.embedding_model == "BAAI/bge-small-en-v1.5"
    assert config.retrieval.reranker_model == ("cross-encoder/ms-marco-MiniLM-L-6-v2")
    assert config.compiler.keyed_table_join_enabled
    assert captured["retrieval_corpus_subset_file"] is None


def test_eval_retrieval_accepts_fixed_retrieval_corpus(
    tmp_path: Path, monkeypatch
) -> None:
    captured = {}

    def fake_run_xl_retrieval(**kwargs):
        captured.update(kwargs)
        path = tmp_path / "artifacts" / "runs" / "run-fixed-corpus"
        return SimpleNamespace(
            path=path,
            manifest=SimpleNamespace(run_id="run-fixed-corpus"),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.xl_docbench.run_xl_retrieval",
        fake_run_xl_retrieval,
    )
    corpus = tmp_path / "parent.json"

    result = runner.invoke(
        app,
        [
            "eval-retrieval",
            "--retrieval-corpus-subset-file",
            str(corpus),
            "--run-id",
            "run-fixed-corpus",
        ],
    )

    assert result.exit_code == 0
    assert captured["retrieval_corpus_subset_file"] == corpus


def test_eval_retrieval_disables_keyed_table_joins(
    tmp_path: Path, monkeypatch
) -> None:
    captured = {}

    def fake_run_xl_retrieval(**kwargs):
        captured.update(kwargs)
        path = tmp_path / "artifacts" / "runs" / "run-joins"
        return SimpleNamespace(
            path=path,
            manifest=SimpleNamespace(run_id="run-joins"),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.xl_docbench.run_xl_retrieval",
        fake_run_xl_retrieval,
    )

    result = runner.invoke(
        app,
        [
            "eval-retrieval",
            "--no-compiler-keyed-table-joins",
            "--run-id",
            "run-joins",
        ],
    )

    assert result.exit_code == 0
    assert not captured["config"].compiler.keyed_table_join_enabled


def test_eval_retrieval_exposes_the_compiler_node_heading_search_context(
    tmp_path: Path, monkeypatch
) -> None:
    """The asymmetric configuration has to be reachable from the command.

    The factorial measured heading search context to cost the compiler's
    IR-node unit page recall at every budget while helping structural chunks at
    the smaller budgets, so the configuration worth measuring is structural on
    and compiler nodes off. One ``RetrievalConfig`` is shared by every arm and
    by the compiler, so the flag has to land on the compiler field *only* --
    checked on both ``config.retrieval`` and ``config.compiler.retrieval``,
    since the benchmark reads heading context through both.

    Omitting the flag must reproduce the all-on default exactly: this phase
    makes the configuration reachable and does not choose it.
    """
    captured: dict[str, dict] = {}

    def fake_run_xl_retrieval(**kwargs):
        captured[kwargs["run_id"]] = kwargs
        return SimpleNamespace(
            path=tmp_path / "artifacts" / "runs" / kwargs["run_id"],
            manifest=SimpleNamespace(run_id=kwargs["run_id"]),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.xl_docbench.run_xl_retrieval",
        fake_run_xl_retrieval,
    )

    asymmetric = runner.invoke(
        app,
        [
            "eval-retrieval",
            "--no-compiler-node-heading-search-context",
            "--run-id",
            "asymmetric",
        ],
    )
    default = runner.invoke(app, ["eval-retrieval", "--run-id", "default"])

    assert asymmetric.exit_code == 0, asymmetric.output
    assert default.exit_code == 0, default.output

    config = captured["asymmetric"]["config"]
    for retrieval in (config.retrieval, config.compiler.retrieval):
        assert retrieval.compiler_node_heading_search_context is False
        # The structural baseline keeps heading access, which it needs to stay
        # a fair baseline. The flag must not touch it.
        assert retrieval.structural_heading_search_context is True

    default_config = captured["default"]["config"]
    for retrieval in (default_config.retrieval, default_config.compiler.retrieval):
        assert retrieval.compiler_node_heading_search_context is True
        assert retrieval.structural_heading_search_context is True


def test_eval_factorial_defaults_to_small_fixed_corpus(
    tmp_path: Path, monkeypatch
) -> None:
    captured = {}

    def fake_run_xl_factorial(**kwargs):
        captured.update(kwargs)
        path = tmp_path / "artifacts" / "factorial-runs" / "factorial-1"
        return SimpleNamespace(
            path=path,
            manifest=SimpleNamespace(run_id="factorial-1"),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.factorial_xl.run_xl_factorial",
        fake_run_xl_factorial,
    )

    result = runner.invoke(
        app,
        [
            "eval-factorial",
            "--artifacts-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "factorial-1",
        ],
    )

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output["run_id"] == "factorial-1"
    assert captured["subset_file"].name == "xldev2-tables.json"
    assert captured["retrieval_corpus_subset_file"].name == "xldev24.json"
    config = captured["config"]
    assert config.budgets == (2048, 4096, 8192, 16384)
    assert set(config.content_units) == {"fixed", "structural", "ir"}
    assert set(config.selection_policies) == {"ranked", "faceted_coverage"}


def test_eval_factorial_crosses_both_heading_context_positions(
    tmp_path: Path, monkeypatch
) -> None:
    """The ablation the factor exists for has to be reachable from the command.

    ``FactorialConfig.heading_contexts`` is crossed with the content units and
    the selection policies, but the command built the config without it, so a
    two-position run could be made only from Python. Omitting the flag must
    still produce exactly the single-valued default, because that is what keeps
    an unasked-for run identical to the runs made before the flag existed.
    """
    captured: dict[str, dict] = {}

    def fake_run_xl_factorial(**kwargs):
        captured[kwargs["run_id"]] = kwargs
        return SimpleNamespace(
            path=tmp_path / "artifacts" / "factorial-runs" / kwargs["run_id"],
            manifest=SimpleNamespace(run_id=kwargs["run_id"]),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.factorial_xl.run_xl_factorial",
        fake_run_xl_factorial,
    )

    crossed = runner.invoke(
        app,
        [
            "eval-factorial",
            "--artifacts-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "crossed",
            "--heading-context",
            "on",
            "--heading-context",
            "off",
        ],
    )
    default = runner.invoke(
        app,
        [
            "eval-factorial",
            "--artifacts-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "default",
        ],
    )

    assert crossed.exit_code == 0, crossed.output
    assert default.exit_code == 0, default.output
    assert captured["crossed"]["config"].heading_contexts == (True, False)
    assert captured["default"]["config"].heading_contexts == (True,)


def test_eval_factorial_refuses_an_unusable_heading_context(
    tmp_path: Path, monkeypatch
) -> None:
    """A rejected factor must say what is wrong before any index is built.

    Non-empty and unique are ``FactorialConfig``'s own rules, so a repeated
    position has to surface that validator's message rather than a traceback or
    a silently deduplicated run; an unspellable position is caught by the CLI,
    which owns the on/off vocabulary.
    """
    calls: list[str] = []

    def fake_run_xl_factorial(**kwargs):
        calls.append("factorial")
        return SimpleNamespace(
            path=tmp_path / "artifacts" / "factorial-runs" / "run-1",
            manifest=SimpleNamespace(run_id="run-1"),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.factorial_xl.run_xl_factorial",
        fake_run_xl_factorial,
    )

    repeated = runner.invoke(
        app,
        ["eval-factorial", "--heading-context", "on", "--heading-context", "on"],
    )
    empty = runner.invoke(app, ["eval-factorial", "--heading-context", ""])

    assert repeated.exit_code == 1
    assert "heading_contexts must be non-empty and unique" in repeated.output
    assert empty.exit_code == 1
    assert "--heading-context takes 'on' or 'off'" in empty.output
    assert calls == []


def test_eval_commands_forward_pinned_model_revisions(
    tmp_path: Path, monkeypatch
) -> None:
    """The pin lives in CLI configuration, so it has to reach the runner.

    Both model defaults name a moving Hugging Face branch. If the revision
    stopped being forwarded, a run would resolve whatever the branch points at
    while the recorded configuration still looked pinned.
    """
    captured: dict[str, dict] = {}

    def fake_run_xl_retrieval(**kwargs):
        captured["retrieval"] = kwargs
        return SimpleNamespace(
            path=tmp_path / "artifacts" / "runs" / "run-1",
            manifest=SimpleNamespace(run_id="run-1"),
        )

    def fake_run_xl_factorial(**kwargs):
        captured["factorial"] = kwargs
        return SimpleNamespace(
            path=tmp_path / "artifacts" / "factorial-runs" / "run-2",
            manifest=SimpleNamespace(run_id="run-2"),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.xl_docbench.run_xl_retrieval",
        fake_run_xl_retrieval,
    )
    monkeypatch.setattr(
        "contextbench.evaluation.factorial_xl.run_xl_factorial",
        fake_run_xl_factorial,
    )

    retrieval_result = runner.invoke(
        app,
        [
            "eval-retrieval",
            "--artifacts-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "run-1",
        ],
    )
    factorial_result = runner.invoke(
        app,
        [
            "eval-factorial",
            "--artifacts-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "run-2",
            "--embedding-revision",
            "a" * 40,
        ],
    )

    assert retrieval_result.exit_code == 0, retrieval_result.output
    assert factorial_result.exit_code == 0, factorial_result.output
    assert captured["retrieval"]["embedding_revision"] == (
        "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
    )
    assert captured["retrieval"]["reranker_revision"] == (
        "233902d25c440f23af6f7d6e94d2946bac0bee0a"
    )
    assert captured["factorial"]["embedding_revision"] == "a" * 40
    assert captured["factorial"]["reranker_revision"] == (
        "233902d25c440f23af6f7d6e94d2946bac0bee0a"
    )


def test_eval_commands_refuse_a_new_model_id_on_the_default_revision(
    tmp_path: Path, monkeypatch
) -> None:
    """A default revision pins the default weights and nothing else.

    Each default revision is the commit its own default model ID resolved to.
    Left in place beside a different model ID it would record a hash that never
    belonged to those weights, so the CLI must refuse before the run rather
    than leave the mismatch for the hub to notice.
    """
    calls: list[str] = []

    def fake_run_xl_retrieval(**kwargs):
        calls.append("retrieval")
        return SimpleNamespace(
            path=tmp_path / "artifacts" / "runs" / "run-1",
            manifest=SimpleNamespace(run_id="run-1"),
        )

    def fake_run_xl_factorial(**kwargs):
        calls.append("factorial")
        return SimpleNamespace(
            path=tmp_path / "artifacts" / "factorial-runs" / "run-2",
            manifest=SimpleNamespace(run_id="run-2"),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.xl_docbench.run_xl_retrieval",
        fake_run_xl_retrieval,
    )
    monkeypatch.setattr(
        "contextbench.evaluation.factorial_xl.run_xl_factorial",
        fake_run_xl_factorial,
    )

    embedding = runner.invoke(
        app,
        ["eval-retrieval", "--embedding-model", "other/embedding-v2"],
    )
    reranker = runner.invoke(
        app,
        ["eval-factorial", "--reranker-model", "other/reranker-v2"],
    )

    assert embedding.exit_code == 1
    assert "--embedding-revision" in embedding.output
    assert "other/embedding-v2" in embedding.output
    assert reranker.exit_code == 1
    assert "--reranker-revision" in reranker.output
    assert "other/reranker-v2" in reranker.output
    assert calls == []

    paired = runner.invoke(
        app,
        [
            "eval-retrieval",
            "--artifacts-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "run-1",
            "--embedding-model",
            "other/embedding-v2",
            "--embedding-revision",
            "c" * 40,
        ],
    )

    assert paired.exit_code == 0, paired.output
    assert calls == ["retrieval"]


def test_eval_commands_accept_offline_models_without_a_revision(
    tmp_path: Path, monkeypatch
) -> None:
    """The offline models have no commit to name, so none may be demanded.

    ``hash-256-v1`` and ``lexical-overlap-v1`` are computed locally and have no
    Hugging Face repository, so the revision is never used. Refusing them while
    the default revision is in place asked the user for the commit of a model
    that has none, which is advice that cannot be followed.
    """
    captured: dict[str, dict] = {}

    def fake_run_xl_retrieval(**kwargs):
        captured["retrieval"] = kwargs
        return SimpleNamespace(
            path=tmp_path / "artifacts" / "runs" / "run-1",
            manifest=SimpleNamespace(run_id="run-1"),
        )

    def fake_run_xl_factorial(**kwargs):
        captured["factorial"] = kwargs
        return SimpleNamespace(
            path=tmp_path / "artifacts" / "factorial-runs" / "run-2",
            manifest=SimpleNamespace(run_id="run-2"),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.xl_docbench.run_xl_retrieval",
        fake_run_xl_retrieval,
    )
    monkeypatch.setattr(
        "contextbench.evaluation.factorial_xl.run_xl_factorial",
        fake_run_xl_factorial,
    )

    offline_embedding = runner.invoke(
        app,
        [
            "eval-retrieval",
            "--artifacts-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "run-1",
            "--embedding-model",
            "hash-256-v1",
        ],
    )
    offline_reranker = runner.invoke(
        app,
        [
            "eval-factorial",
            "--artifacts-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "run-2",
            "--reranker-model",
            "lexical-overlap-v1",
        ],
    )

    assert offline_embedding.exit_code == 0, offline_embedding.output
    assert offline_reranker.exit_code == 0, offline_reranker.output
    assert captured["retrieval"]["config"].retrieval.embedding_model == "hash-256-v1"
    assert (
        captured["factorial"]["config"].retrieval.reranker_model
        == "lexical-overlap-v1"
    )

    # The guard still refuses a hub model ID paired with a revision that pins
    # a different model.
    hub_mismatch = runner.invoke(
        app,
        ["eval-retrieval", "--embedding-model", "other/embedding-v2"],
    )

    assert hub_mismatch.exit_code == 1
    assert "--embedding-revision" in hub_mismatch.output


ABLATION_FIELDS = (
    "include_heading_context",
    "include_previous_sibling",
    "include_next_sibling",
    "group_adjacent_list_items",
    "preserve_tables",
    "keyed_table_join_enabled",
    "page_neighbor_radius",
)


def _captured_config(tmp_path: Path, monkeypatch, options: list[str]):
    captured = {}

    def fake_run_xl_retrieval(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            path=tmp_path / "artifacts" / "runs" / "ablation",
            manifest=SimpleNamespace(run_id="ablation"),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.xl_docbench.run_xl_retrieval",
        fake_run_xl_retrieval,
    )
    result = runner.invoke(
        app, ["eval-retrieval", *options, "--run-id", "ablation"]
    )
    assert result.exit_code == 0, result.output
    return captured["config"].compiler


def test_eval_retrieval_leaves_expansion_defaults_untouched(
    tmp_path: Path, monkeypatch
) -> None:
    """Naming none of the new options must change nothing.

    The ablation flags exist to be able to turn expansion off. If adding them
    moved any default, every published run before them would have been
    produced by a different configuration than the one a rerun would use.
    """
    compiler = _captured_config(tmp_path, monkeypatch, [])
    shipped = CompilerConfig()

    assert {field: getattr(compiler, field) for field in ABLATION_FIELDS} == {
        field: getattr(shipped, field) for field in ABLATION_FIELDS
    }
    # Every compiler field, not only the new ones. ``retrieval`` is excluded
    # because the CLI assembles it from its own options, which is pre-existing
    # and has nothing to do with the ablation switches.
    assert {
        field: getattr(compiler, field)
        for field in CompilerConfig.model_fields
        if field != "retrieval"
    } == {
        field: getattr(shipped, field)
        for field in CompilerConfig.model_fields
        if field != "retrieval"
    }


@pytest.mark.parametrize(
    ("option", "field", "expected"),
    [
        ("--no-compiler-heading-context", "include_heading_context", False),
        ("--compiler-previous-sibling", "include_previous_sibling", True),
        ("--compiler-next-sibling", "include_next_sibling", True),
        (
            "--no-compiler-group-adjacent-list-items",
            "group_adjacent_list_items",
            False,
        ),
        ("--no-compiler-preserve-tables", "preserve_tables", False),
    ],
)
def test_eval_retrieval_exposes_each_expansion_switch(
    tmp_path: Path, monkeypatch, option: str, field: str, expected: bool
) -> None:
    compiler = _captured_config(tmp_path, monkeypatch, [option])

    assert getattr(compiler, field) is expected


def test_eval_retrieval_exposes_the_page_neighbor_radius(
    tmp_path: Path, monkeypatch
) -> None:
    """An integer, not a boolean: 0 disables, and other values are reachable."""
    assert _captured_config(
        tmp_path, monkeypatch, ["--compiler-page-neighbor-radius", "0"]
    ).page_neighbor_radius == 0
    assert _captured_config(
        tmp_path, monkeypatch, ["--compiler-page-neighbor-radius", "5"]
    ).page_neighbor_radius == 5


@pytest.mark.parametrize("name", ["D1", "D2", "D3", "D4", "SHIPPED"])
def test_documented_ablations_are_what_the_command_line_produces(
    tmp_path: Path, monkeypatch, name: str
) -> None:
    """The recorded ladder and the CLI must not be able to drift apart.

    ``COMPILER_ABLATIONS`` is the durable record of what D1-D4 mean; this runs
    its own rendered command line through the CLI and checks the configuration
    that comes out. If a flag is renamed, or a mapping edited without the
    other, this fails rather than silently publishing a mislabelled ablation.
    """
    expected = CompilerConfig().model_copy(
        update=dict(COMPILER_ABLATIONS[name])
    )

    compiler = _captured_config(
        tmp_path, monkeypatch, list(ablation_command_line(name))
    )

    assert {field: getattr(compiler, field) for field in ABLATION_FIELDS} == {
        field: getattr(expected, field) for field in ABLATION_FIELDS
    }


def test_the_ablation_ladder_is_monotone_and_ends_below_the_shipped_config() -> None:
    """Each step adds one mechanism, and none of D1-D4 is what ships."""
    configs = {
        name: CompilerConfig().model_copy(update=dict(overrides))
        for name, overrides in COMPILER_ABLATIONS.items()
    }

    assert configs["D1"].include_heading_context is False
    assert configs["D2"].include_heading_context is True
    # D2 adds headings and nothing else.
    assert all(
        getattr(configs["D2"], field) == getattr(configs["D1"], field)
        for field in ABLATION_FIELDS
        if field != "include_heading_context"
    )
    # D3 adds adjacency, including list-item grouping, as documented.
    assert configs["D3"].include_previous_sibling is True
    assert configs["D3"].include_next_sibling is True
    assert configs["D3"].group_adjacent_list_items is True
    assert configs["D3"].preserve_tables is False
    # D4 adds table preservation and stops there.
    assert configs["D4"].preserve_tables is True
    assert configs["D4"].keyed_table_join_enabled is False
    assert configs["D4"].page_neighbor_radius == 0
    # The shipped configuration is strictly beyond D4, which is why it is
    # listed: none of the four is the thing the benchmark publishes.
    assert configs["SHIPPED"] == CompilerConfig()
    assert configs["SHIPPED"].keyed_table_join_enabled is True
    assert configs["SHIPPED"].page_neighbor_radius > 0
    assert configs["SHIPPED"] != configs["D4"]
    # Since the Phase 1 freeze the ladder has a clean endpoint: SHIPPED is D4
    # with exactly the two later operators added, and every D4 switch at the
    # same value. Before the freeze this was false -- SHIPPED had the paragraph
    # sibling switches off where D4 had them on.
    beyond_d4 = {"keyed_table_join_enabled", "page_neighbor_radius"}
    assert {
        field: getattr(configs["SHIPPED"], field)
        for field in ABLATION_FIELDS
        if field not in beyond_d4
    } == {
        field: getattr(configs["D4"], field)
        for field in ABLATION_FIELDS
        if field not in beyond_d4
    }


def test_ablation_settings_reach_the_published_manifest() -> None:
    """A published ablation has to be reproducible from its own manifest."""
    compiler = CompilerConfig().model_copy(update=dict(COMPILER_ABLATIONS["D1"]))
    config = RetrievalBenchmarkConfig(
        retrieval=compiler.retrieval, compiler=compiler
    )

    recorded = config.model_dump(mode="json")["compiler"]

    for field in ABLATION_FIELDS:
        assert recorded[field] == getattr(compiler, field)
    # And the ladder's rungs are distinguishable by the config hash the
    # manifest records, so two ablations cannot be confused for one another.
    hashes = {
        name: json.dumps(
            RetrievalBenchmarkConfig(
                retrieval=CompilerConfig().retrieval,
                compiler=CompilerConfig().model_copy(update=dict(overrides)),
            ).model_dump(mode="json"),
            sort_keys=True,
        )
        for name, overrides in COMPILER_ABLATIONS.items()
    }
    assert len(set(hashes.values())) == len(hashes)


def test_eval_retrieval_defaults_to_rendered_budget_accounting(
    tmp_path: Path, monkeypatch
) -> None:
    """The owner's decision is the default; content stays reachable."""
    default = _captured_config(tmp_path, monkeypatch, [])
    content = _captured_config(
        tmp_path, monkeypatch, ["--budget-accounting", "content"]
    )

    assert default.budget_accounting == "rendered_evidence"
    assert content.budget_accounting == "content"


def test_eval_factorial_passes_budget_accounting_through(
    tmp_path: Path, monkeypatch
) -> None:
    captured = {}

    def fake_run_xl_factorial(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            path=tmp_path / "artifacts" / "factorial-runs" / "run",
            manifest=SimpleNamespace(run_id="run"),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.factorial_xl.run_xl_factorial",
        fake_run_xl_factorial,
    )

    result = runner.invoke(
        app,
        ["eval-factorial", "--budget-accounting", "content", "--run-id", "run"],
    )

    assert result.exit_code == 0, result.output
    assert captured["config"].budget_accounting == "content"


def test_eval_retrieval_exposes_node_merging_and_the_mass_floor(
    tmp_path: Path, monkeypatch
) -> None:
    default = _captured_config(tmp_path, monkeypatch, [])
    merged = _captured_config(
        tmp_path,
        monkeypatch,
        [
            "--compiler-node-merge",
            "--compiler-node-merge-min-tokens",
            "32",
            "--compiler-node-merge-target-tokens",
            "96",
            "--compiler-node-merge-max-tokens",
            "200",
            "--compiler-node-merge-max-page-span",
            "2",
            "--compiler-candidate-token-mass-multiple",
            "1.5",
        ],
    )

    assert default.node_merge_policy is None
    assert default.expanded_candidate_token_mass_multiple is None
    assert (
        merged.node_merge_enabled,
        merged.node_merge_min_tokens,
        merged.node_merge_target_tokens,
        merged.node_merge_max_tokens,
        merged.node_merge_max_page_span,
        merged.expanded_candidate_token_mass_multiple,
    ) == (True, 32, 96, 200, 2, 1.5)


def test_eval_factorial_exposes_node_merging(tmp_path: Path, monkeypatch) -> None:
    captured = {}

    def fake_run_xl_factorial(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            path=tmp_path / "artifacts" / "factorial-runs" / "run",
            manifest=SimpleNamespace(run_id="run"),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.factorial_xl.run_xl_factorial",
        fake_run_xl_factorial,
    )

    result = runner.invoke(
        app,
        [
            "eval-factorial",
            "--node-merge",
            "--node-merge-min-tokens",
            "32",
            "--node-merge-target-tokens",
            "96",
            "--node-merge-max-tokens",
            "200",
            "--node-merge-max-page-span",
            "2",
            "--run-id",
            "run",
        ],
    )

    assert result.exit_code == 0, result.output
    config = captured["config"]
    assert (
        config.node_merge_enabled,
        config.node_merge_min_tokens,
        config.node_merge_target_tokens,
        config.node_merge_max_tokens,
        config.node_merge_max_page_span,
    ) == (True, 32, 96, 200, 2)

    captured.clear()
    result = runner.invoke(app, ["eval-factorial", "--run-id", "run"])
    assert result.exit_code == 0, result.output
    assert captured["config"].node_merge_policy is None
