"""Recorded provider endpoint and retry settings for answer experiments.

No test here makes a network call: every provider either wraps an in-memory
fake client or builds a real ``openai.OpenAI`` object without sending a
request.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from test_evaluation import _corpus, _run
from test_generation import _generation_config
from test_ir import FixtureTokenCounter
from test_representation import _config as _representation_config
from test_representation import _gold_question

from contextbench.generation import (
    GenerationConfig,
    OpenAIAnswerProvider,
    run_generation_benchmark,
)
from contextbench.generation.models import OPENAI_SDK_DEFAULT_MAX_RETRIES
from contextbench.generation.providers import (
    FORWARDED_OPENAI_ENV_VARS,
    LOCAL_PLACEHOLDER_API_KEY,
    ProviderConfigurationError,
    openai_client_kwargs,
)
from contextbench.representation import (
    RepresentationCondition,
    representation_prompt_hashes,
    run_gold_representation_benchmark,
)

LOCAL_URL = "http://127.0.0.1:1234/v1"
SECRET_KEY = "sk-test-never-recorded-0123456789"


class _Responses:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            id=f"response-{len(self.calls)}",
            model=kwargs["model"],
            output_text='{"answer":"revenue","citations":[]}',
            status="completed",
            incomplete_details=None,
            usage=SimpleNamespace(
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
                input_tokens_details=None,
                output_tokens_details=None,
            ),
        )


@pytest.fixture(autouse=True)
def _hermetic_openai_environment(monkeypatch):
    """Start every test with none of the SDK's environment inputs set."""
    for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", *FORWARDED_OPENAI_ENV_VARS):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def fake_openai(monkeypatch):
    """Replace ``openai.OpenAI`` with a recorder; the real class never runs."""
    openai = pytest.importorskip("openai")
    constructions: list[dict] = []

    def fake_client(**kwargs):
        constructions.append(kwargs)
        return SimpleNamespace(responses=_Responses())

    monkeypatch.setattr(openai, "OpenAI", fake_client)
    return constructions


def test_default_max_retries_matches_the_installed_sdk() -> None:
    constants = pytest.importorskip("openai._constants")
    assert OPENAI_SDK_DEFAULT_MAX_RETRIES == constants.DEFAULT_MAX_RETRIES


def test_defaults_build_the_client_exactly_as_before() -> None:
    # No base URL: nothing but the SDK's own retry default is passed, so the
    # SDK still requires the real key and still targets the OpenAI API.
    assert openai_client_kwargs(base_url=None, max_retries=2, environ={}) == {
        "max_retries": 2
    }
    assert openai_client_kwargs(
        base_url=None, max_retries=2, environ={"OPENAI_API_KEY": SECRET_KEY}
    ) == {"max_retries": 2}
    config = _generation_config()
    assert config.provider_base_url is None
    assert config.provider_max_retries == OPENAI_SDK_DEFAULT_MAX_RETRIES


@pytest.mark.parametrize("environ", [{}, {"OPENAI_API_KEY": SECRET_KEY}])
def test_a_configured_endpoint_only_ever_gets_the_placeholder_key(environ) -> None:
    local = openai_client_kwargs(base_url=LOCAL_URL, max_retries=0, environ=environ)
    assert local == {
        "base_url": LOCAL_URL,
        "max_retries": 0,
        "api_key": LOCAL_PLACEHOLDER_API_KEY,
    }
    # Without a base URL no placeholder is ever supplied: the SDK uses the
    # real key for the OpenAI API, as before.
    assert "api_key" not in openai_client_kwargs(
        base_url=None, max_retries=2, environ=environ
    )


def test_real_key_never_reaches_a_real_client_for_a_configured_endpoint(
    monkeypatch,
) -> None:
    pytest.importorskip("openai")
    monkeypatch.setenv("OPENAI_API_KEY", SECRET_KEY)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    for name in FORWARDED_OPENAI_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    provider = OpenAIAnswerProvider(base_url=LOCAL_URL, max_retries=0)
    # Construction only; no request is sent. The Authorization header the
    # client would send carries the placeholder, not the environment's key.
    assert provider._client.api_key == LOCAL_PLACEHOLDER_API_KEY
    assert SECRET_KEY not in repr(provider._client.auth_headers)
    assert provider._client.organization is None
    assert provider._client.project is None


@pytest.mark.parametrize("name", FORWARDED_OPENAI_ENV_VARS)
def test_forwarded_openai_variables_are_refused_for_a_configured_endpoint(
    name: str,
) -> None:
    with pytest.raises(ProviderConfigurationError, match=name):
        openai_client_kwargs(
            base_url=LOCAL_URL, max_retries=0, environ={name: "org-secret"}
        )
    # The OpenAI API itself keeps its existing behaviour.
    assert openai_client_kwargs(
        base_url=None, max_retries=2, environ={name: "org-secret"}
    ) == {"max_retries": 2}


def test_unrecorded_environment_endpoint_is_refused() -> None:
    with pytest.raises(ProviderConfigurationError, match="no provider base URL"):
        openai_client_kwargs(
            base_url=None,
            max_retries=2,
            environ={"OPENAI_BASE_URL": LOCAL_URL},
        )
    with pytest.raises(ProviderConfigurationError, match="differs"):
        openai_client_kwargs(
            base_url=LOCAL_URL,
            max_retries=2,
            environ={"OPENAI_BASE_URL": "http://127.0.0.1:9999/v1"},
        )
    # Equal up to a trailing slash is the same endpoint.
    assert openai_client_kwargs(
        base_url=LOCAL_URL,
        max_retries=2,
        environ={"OPENAI_BASE_URL": LOCAL_URL + "/"},
    )["base_url"] == LOCAL_URL


def test_provider_passes_base_url_and_retries_to_the_client(fake_openai) -> None:
    config = _generation_config().model_copy(
        update={"provider_base_url": LOCAL_URL, "provider_max_retries": 0}
    )
    provider = OpenAIAnswerProvider.from_config(config, environ={})
    assert fake_openai == [
        {
            "base_url": LOCAL_URL,
            "max_retries": 0,
            "api_key": LOCAL_PLACEHOLDER_API_KEY,
        }
    ]

    default = OpenAIAnswerProvider(environ={"OPENAI_API_KEY": SECRET_KEY})
    assert fake_openai[1] == {"max_retries": OPENAI_SDK_DEFAULT_MAX_RETRIES}

    # A config naming another endpoint than the client's is refused per call.
    with pytest.raises(ProviderConfigurationError):
        provider.generate(_request(), config=_generation_config())
    with pytest.raises(ProviderConfigurationError):
        default.generate(_request(), config=config)


def test_provider_refuses_environment_mismatch_before_building_a_client(
    fake_openai,
) -> None:
    with pytest.raises(ProviderConfigurationError):
        OpenAIAnswerProvider(environ={"OPENAI_BASE_URL": LOCAL_URL})
    assert fake_openai == []


def test_real_sdk_client_accepts_a_local_endpoint_without_a_key(monkeypatch) -> None:
    pytest.importorskip("openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    provider = OpenAIAnswerProvider(base_url=LOCAL_URL, max_retries=0)
    # Construction only; no request is sent.
    assert str(provider._client.base_url).rstrip("/") == LOCAL_URL
    assert provider._client.max_retries == 0


def _config_with_url(url: str) -> GenerationConfig:
    return GenerationConfig(
        **{**_generation_config().model_dump(), "provider_base_url": url}
    )


@pytest.mark.parametrize(
    "url",
    [
        "127.0.0.1:1234/v1",
        "ftp://127.0.0.1/v1",
        "http://user:secret@127.0.0.1:1234/v1",
        "http://secret@127.0.0.1:1234/v1",
        "http://127.0.0.1:1234/v1?key=secret",
        "http://127.0.0.1:1234/v1#secret",
        "http://127.0.0.1:99999/v1",
        "http://127.0.0.1:port/v1",
        "http://[::1/v1",
    ],
)
def test_unrecordable_base_urls_are_rejected_without_echoing_them(url: str) -> None:
    with pytest.raises(ValidationError) as caught:
        _config_with_url(url)
    assert url not in str(caught.value)
    assert "secret" not in str(caught.value)


@pytest.mark.parametrize(
    ("url", "recorded"),
    [
        ("http://127.0.0.1:1234/v1/", "http://127.0.0.1:1234/v1"),
        ("http://localhost:1234/v1", "http://localhost:1234/v1"),
        ("http://[::1]:1234/v1", "http://[::1]:1234/v1"),
        ("https://example.test/v1//", "https://example.test/v1"),
    ],
)
def test_valid_base_urls_are_accepted_and_normalised(url: str, recorded: str) -> None:
    assert _config_with_url(url).provider_base_url == recorded


def test_trailing_slash_does_not_change_the_config_hash() -> None:
    with_slash = _config_with_url(LOCAL_URL + "/").model_dump(mode="json")
    without = _config_with_url(LOCAL_URL).model_dump(mode="json")
    assert with_slash == without


def _request():
    from contextbench.generation import AnswerRequest

    return AnswerRequest(
        question_id="question-1",
        system="fixture",
        prompt="prompt",
        evidence_ids=(),
    )


def _run_generation(tmp_path: Path, config, provider, run_id: str):
    retrieval = _run(tmp_path, run_id=f"retrieval-{run_id}")
    return run_generation_benchmark(
        retrieval.path,
        _corpus(tmp_path).questions,
        config=config,
        provider=provider,
        artifacts_root=tmp_path / "artifacts",
        run_id=run_id,
        git_commit="b" * 40,
        git_dirty=False,
        clock=lambda: datetime(2026, 9, 25, tzinfo=UTC),
    )


def _run_representation(tmp_path: Path, config, provider, run_id: str):
    return run_gold_representation_benchmark(
        _corpus(tmp_path),
        config=config,
        provider=provider,
        artifacts_root=tmp_path / "artifacts",
        dataset="fixture",
        dataset_version="v1",
        dataset_revision="revision-1",
        subset_name="fixture-two",
        subset_sha256="1" * 64,
        run_id=run_id,
        tokenizer=FixtureTokenCounter(),
        git_commit="c" * 40,
        git_dirty=False,
        clock=lambda: datetime(2026, 9, 25, tzinfo=UTC),
    )


def _all_artifact_text(run_path: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(run_path.rglob("*"))
        if path.is_file()
    )


def test_generation_manifest_records_endpoint_and_never_a_key(
    tmp_path: Path, fake_openai
) -> None:
    config = _generation_config().model_copy(
        update={"provider_base_url": LOCAL_URL, "provider_max_retries": 0}
    )
    for environ, run_id in (
        ({}, "generation-local-placeholder"),
        ({"OPENAI_API_KEY": SECRET_KEY}, "generation-local-keyed"),
    ):
        provider = OpenAIAnswerProvider.from_config(config, environ=environ)
        result = _run_generation(tmp_path, config, provider, run_id)
        recorded = json.loads((result.path / "manifest.json").read_text())
        assert recorded["provider_base_url"] == LOCAL_URL
        assert recorded["provider_max_retries"] == 0
        assert recorded["config"]["provider_base_url"] == LOCAL_URL
        assert recorded["config"]["provider_max_retries"] == 0
        text = _all_artifact_text(result.path)
        assert SECRET_KEY not in text
        assert LOCAL_PLACEHOLDER_API_KEY not in text
        assert "api_key" not in text


def test_generation_defaults_record_the_sdk_endpoint_and_keep_prompt_hashes(
    tmp_path: Path, fake_openai
) -> None:
    default_config = _generation_config()
    local_config = default_config.model_copy(
        update={"provider_base_url": LOCAL_URL, "provider_max_retries": 0}
    )
    default = _run_generation(
        tmp_path,
        default_config,
        OpenAIAnswerProvider.from_config(
            default_config, environ={"OPENAI_API_KEY": SECRET_KEY}
        ),
        "generation-default-endpoint",
    )
    local = _run_generation(
        tmp_path,
        local_config,
        OpenAIAnswerProvider.from_config(local_config, environ={}),
        "generation-local-endpoint",
    )
    default_manifest = json.loads((default.path / "manifest.json").read_text())
    local_manifest = json.loads((local.path / "manifest.json").read_text())
    assert default_manifest["provider_base_url"] is None
    assert default_manifest["provider_max_retries"] == OPENAI_SDK_DEFAULT_MAX_RETRIES
    assert SECRET_KEY not in _all_artifact_text(default.path)
    # The endpoint changes the config hash, never the prompt templates.
    for key in ("prompt_sha256", "citation_entailment_prompt_sha256"):
        assert default_manifest[key] == local_manifest[key]
    assert default_manifest["config_sha256"] != local_manifest["config_sha256"]


def test_representation_manifest_records_endpoint_and_never_a_key(
    tmp_path: Path, fake_openai
) -> None:
    config = _representation_config(
        conditions=(RepresentationCondition.RAW,),
        provider_base_url=LOCAL_URL,
        provider_max_retries=0,
    )
    provider = OpenAIAnswerProvider.from_config(
        config, environ={"OPENAI_API_KEY": SECRET_KEY}
    )
    result = _run_representation(tmp_path, config, provider, "representation-local")
    recorded = json.loads((result.path / "manifest.json").read_text())
    assert recorded["provider_base_url"] == LOCAL_URL
    assert recorded["provider_max_retries"] == 0
    assert recorded["config"]["provider_base_url"] == LOCAL_URL
    assert recorded["config"]["provider_max_retries"] == 0
    text = _all_artifact_text(result.path)
    assert SECRET_KEY not in text
    assert LOCAL_PLACEHOLDER_API_KEY not in text


def test_representation_prompt_hashes_ignore_the_endpoint() -> None:
    default = _representation_config(
        answer_equivalence_judge=True, citation_entailment_judge=True
    )
    local = _representation_config(
        answer_equivalence_judge=True,
        citation_entailment_judge=True,
        provider_base_url=LOCAL_URL,
        provider_max_retries=0,
    )
    assert representation_prompt_hashes(default) == representation_prompt_hashes(
        local
    )
    assert default.provider_base_url is None
    assert default.provider_max_retries == OPENAI_SDK_DEFAULT_MAX_RETRIES


def _invoke_representation_cli(monkeypatch, *args: str):
    from typer.testing import CliRunner

    from contextbench.cli import app
    from contextbench.representation import RepresentationError

    captured: dict[str, object] = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        raise RepresentationError("stop after capture")

    questions = (_gold_question(),)
    monkeypatch.setattr("contextbench.cli.download_release", lambda _path: None)
    monkeypatch.setattr("contextbench.cli.load_subset", lambda _path: None)
    monkeypatch.setattr(
        "contextbench.cli.XLDocBenchDataset",
        lambda _path: SimpleNamespace(iter_subset=lambda _subset: iter(questions)),
    )
    monkeypatch.setattr(
        "contextbench.representation.run_xl_gold_representation", fake_run
    )
    result = CliRunner().invoke(
        app,
        [
            "eval-representation",
            "--model",
            "qwen3.6-35b-a3b",
            "--input-usd-per-million",
            "0",
            "--cached-input-usd-per-million",
            "0",
            "--output-usd-per-million",
            "0",
            "--max-calls",
            "10",
            *args,
        ],
    )
    return result, captured


def test_eval_representation_options_reach_config_and_client(
    monkeypatch, fake_openai
) -> None:
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result, captured = _invoke_representation_cli(
        monkeypatch,
        "--provider-base-url",
        LOCAL_URL,
        "--provider-max-retries",
        "0",
    )
    config = captured.get("config")
    assert config is not None, result.output
    assert config.provider_base_url == LOCAL_URL
    assert config.provider_max_retries == 0
    assert fake_openai == [
        {
            "base_url": LOCAL_URL,
            "max_retries": 0,
            "api_key": LOCAL_PLACEHOLDER_API_KEY,
        }
    ]


def test_eval_representation_defaults_keep_the_sdk_endpoint(
    monkeypatch, fake_openai
) -> None:
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", SECRET_KEY)
    result, captured = _invoke_representation_cli(monkeypatch)
    config = captured.get("config")
    assert config is not None, result.output
    assert config.provider_base_url is None
    assert config.provider_max_retries == OPENAI_SDK_DEFAULT_MAX_RETRIES
    assert fake_openai == [{"max_retries": OPENAI_SDK_DEFAULT_MAX_RETRIES}]


@pytest.mark.parametrize(
    "args",
    [(), ("--provider-base-url", "http://127.0.0.1:9999/v1")],
)
def test_eval_representation_refuses_an_unrecorded_environment_endpoint(
    monkeypatch, fake_openai, args
) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", LOCAL_URL)
    result, captured = _invoke_representation_cli(monkeypatch, *args)
    assert result.exit_code != 0
    assert "OPENAI_BASE_URL" in result.output
    assert captured == {}
    assert fake_openai == []


CREDENTIAL = "hunter2-credential"
CREDENTIAL_URL = f"http://user:{CREDENTIAL}@127.0.0.1:1234/v1"


@pytest.mark.parametrize(
    ("env_url", "args"),
    [
        (None, ("--provider-base-url", CREDENTIAL_URL)),
        (CREDENTIAL_URL, ("--provider-base-url", LOCAL_URL)),
        (CREDENTIAL_URL, ()),
    ],
)
def test_cli_never_echoes_a_credential_bearing_url(
    monkeypatch, fake_openai, env_url, args
) -> None:
    if env_url is not None:
        monkeypatch.setenv("OPENAI_BASE_URL", env_url)
    result, captured = _invoke_representation_cli(monkeypatch, *args)
    assert result.exit_code != 0
    assert captured == {}
    assert fake_openai == []
    assert CREDENTIAL not in result.output
    assert CREDENTIAL not in repr(result.exception)


def test_eval_representation_refuses_forwarded_variables_for_an_endpoint(
    monkeypatch, fake_openai
) -> None:
    monkeypatch.setenv("OPENAI_ORG_ID", "org-secret")
    result, captured = _invoke_representation_cli(
        monkeypatch, "--provider-base-url", LOCAL_URL
    )
    assert result.exit_code != 0
    assert "OPENAI_ORG_ID" in result.output
    assert "org-secret" not in result.output
    assert captured == {}
    assert fake_openai == []


def test_eval_representation_never_passes_the_real_key_to_an_endpoint(
    monkeypatch, fake_openai
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", SECRET_KEY)
    result, captured = _invoke_representation_cli(
        monkeypatch, "--provider-base-url", LOCAL_URL
    )
    assert captured.get("config") is not None, result.output
    assert fake_openai == [
        {
            "base_url": LOCAL_URL,
            "max_retries": OPENAI_SDK_DEFAULT_MAX_RETRIES,
            "api_key": LOCAL_PLACEHOLDER_API_KEY,
        }
    ]


def test_eval_generation_options_reach_config_and_client(
    tmp_path: Path, monkeypatch, fake_openai
) -> None:
    from typer.testing import CliRunner

    from contextbench.cli import app
    from contextbench.generation import GenerationError

    captured: dict[str, object] = {}

    def fake_run(*_args, **kwargs):
        captured.update(kwargs)
        raise GenerationError("stop after capture")

    monkeypatch.setattr("contextbench.generation.run_generation_benchmark", fake_run)
    monkeypatch.setattr("contextbench.cli.load_subset", lambda _path: None)
    monkeypatch.setattr(
        "contextbench.cli.XLDocBenchDataset",
        lambda _path: SimpleNamespace(iter_subset=lambda _subset: iter(())),
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    retrieval = _run(tmp_path, run_id="retrieval-cli-endpoint")

    def invoke(*args: str):
        return CliRunner().invoke(
            app,
            [
                "eval-generation",
                str(retrieval.path),
                "--model",
                "qwen3.6-35b-a3b",
                "--input-usd-per-million",
                "0",
                "--cached-input-usd-per-million",
                "0",
                "--output-usd-per-million",
                "0",
                "--max-calls",
                "1000",
                *args,
            ],
        )

    result = invoke("--provider-base-url", LOCAL_URL, "--provider-max-retries", "0")
    config = captured.get("config")
    assert config is not None, result.output
    assert config.provider_base_url == LOCAL_URL
    assert config.provider_max_retries == 0
    assert fake_openai[-1] == {
        "base_url": LOCAL_URL,
        "max_retries": 0,
        "api_key": LOCAL_PLACEHOLDER_API_KEY,
    }

    captured.clear()
    constructions = len(fake_openai)
    monkeypatch.setenv("OPENAI_BASE_URL", LOCAL_URL)
    refused = invoke()
    assert refused.exit_code != 0
    assert "OPENAI_BASE_URL" in refused.output
    assert captured == {}
    assert len(fake_openai) == constructions
