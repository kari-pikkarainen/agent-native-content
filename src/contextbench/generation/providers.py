"""Answer provider protocol and optional OpenAI Responses implementation."""

import os
from collections.abc import Mapping
from typing import Any, Protocol

from contextbench.generation.models import (
    OPENAI_SDK_DEFAULT_CONNECT_TIMEOUT_SECONDS,
    OPENAI_SDK_DEFAULT_MAX_RETRIES,
    OPENAI_SDK_DEFAULT_TIMEOUT_SECONDS,
    AnswerModelConfig,
    AnswerRequest,
    ProviderAnswer,
)


class AnswerProvider(Protocol):
    """Provider-neutral answer-generation boundary."""

    name: str
    version: str

    def generate(
        self,
        request: AnswerRequest,
        *,
        config: AnswerModelConfig,
    ) -> ProviderAnswer:
        """Generate one answer and return provider-reported usage."""
        ...


class ProviderConfigurationError(RuntimeError):
    """The provider would not make exactly the calls the config records."""


# The only key a configured, non-default endpoint ever receives. The SDK
# refuses to build a client without some key, and passing one explicitly also
# stops it reading OPENAI_API_KEY, so the real key never reaches that endpoint
# (possibly over plaintext http). Local OpenAI-compatible servers ignore it. It
# is never written to any artifact.
LOCAL_PLACEHOLDER_API_KEY = "local-no-key"

# Variables the SDK (openai 2.x ``OpenAI.__init__``) reads and forwards as
# request headers whatever base URL is configured. Passing ``None`` makes it
# read the environment and an empty string sends an empty header, so they
# cannot be suppressed per client. With a configured endpoint they are
# therefore refused rather than leaked.
FORWARDED_OPENAI_ENV_VARS = (
    "OPENAI_ORG_ID",
    "OPENAI_PROJECT_ID",
    "OPENAI_ADMIN_KEY",
    "OPENAI_CUSTOM_HEADERS",
)

# The Responses API has no seed parameter: the SDK's ``Responses.create``
# rejects ``seed=`` with a TypeError, and a seed sent through ``extra_body``
# was measured to be accepted but ignored by LM Studio. A configured seed
# could therefore only be recorded, never applied, so it is refused. The
# config field stays (default ``None``) so earlier configs still parse.
SEED_UNSUPPORTED_MESSAGE = (
    "seed is not supported: the OpenAI Responses API has no seed parameter, "
    "so a configured seed would be recorded but never applied; leave seed "
    "unset and use --temperature 0 for repeatable answers"
)


def refuse_unsupported_seed(seed: int | None) -> None:
    """Refuse a configured sampling seed before any provider call."""
    if seed is not None:
        raise ProviderConfigurationError(SEED_UNSUPPORTED_MESSAGE)


def responses_create_kwargs(
    request: AnswerRequest,
    config: AnswerModelConfig,
) -> dict[str, Any]:
    """Build the ``responses.create`` arguments for one answer call.

    Every name returned must be a parameter of the installed SDK's
    ``Responses.create``; a unit test checks this against its real signature,
    because fake clients accept any keyword.
    """
    params: dict[str, Any] = {
        "model": config.model,
        "input": request.prompt,
        "max_output_tokens": config.max_output_tokens,
        "store": False,
    }
    if config.reasoning_effort is not None:
        params["reasoning"] = {"effort": config.reasoning_effort}
    # Sent only when configured: several reasoning models reject an
    # explicit temperature, so an unset value must not become a default.
    if config.temperature is not None:
        params["temperature"] = config.temperature
    return params


def openai_client_kwargs(
    *,
    base_url: str | None,
    max_retries: int,
    environ: Mapping[str, str],
    timeout_seconds: float = OPENAI_SDK_DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Build ``openai.OpenAI`` arguments that match the recorded config.

    The SDK silently falls back to ``OPENAI_BASE_URL`` when no base URL is
    passed, and an explicit argument silently overrides it. Either way the
    environment could name an endpoint the manifest does not, so any
    disagreement between the two is refused rather than resolved. Error
    messages never echo either URL, which could carry credentials.

    ``timeout`` is returned as plain seconds; the provider wraps it in the
    SDK's timeout object, keeping the SDK's own connect limit.
    """
    env_base_url = environ.get("OPENAI_BASE_URL")
    if env_base_url is not None:
        if base_url is None:
            raise ProviderConfigurationError(
                "OPENAI_BASE_URL is set but no provider base URL is configured; "
                "pass the same value with --provider-base-url so the endpoint is "
                "recorded, or unset OPENAI_BASE_URL"
            )
        if env_base_url.rstrip("/") != base_url.rstrip("/"):
            raise ProviderConfigurationError(
                "OPENAI_BASE_URL differs from the configured provider base URL; "
                "unset it or make them equal"
            )
    kwargs: dict[str, Any] = {
        "max_retries": max_retries,
        "timeout": timeout_seconds,
    }
    if base_url is not None:
        forwarded = [name for name in FORWARDED_OPENAI_ENV_VARS if name in environ]
        if forwarded:
            raise ProviderConfigurationError(
                f"{', '.join(forwarded)} would be forwarded to the configured "
                "provider base URL; unset it for a custom endpoint"
            )
        kwargs["base_url"] = base_url
        kwargs["api_key"] = LOCAL_PLACEHOLDER_API_KEY
    return kwargs


class OpenAIAnswerProvider:
    """OpenAI Responses API adapter, imported lazily for optional installation."""

    name = "openai"

    def __init__(
        self,
        client: Any | None = None,
        *,
        base_url: str | None = None,
        max_retries: int = OPENAI_SDK_DEFAULT_MAX_RETRIES,
        timeout_seconds: float = OPENAI_SDK_DEFAULT_TIMEOUT_SECONDS,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        if client is None:
            try:
                import openai
            except ImportError as exc:
                raise RuntimeError(
                    "OpenAI generation requires `uv sync --extra generation`"
                ) from exc
            kwargs = openai_client_kwargs(
                base_url=base_url,
                max_retries=max_retries,
                environ=os.environ if environ is None else environ,
                timeout_seconds=timeout_seconds,
            )
            # Only the read/write/pool limits are configured; connecting keeps
            # the SDK's own limit, so the default equals the SDK default.
            kwargs["timeout"] = openai.Timeout(
                kwargs["timeout"],
                connect=OPENAI_SDK_DEFAULT_CONNECT_TIMEOUT_SECONDS,
            )
            client = openai.OpenAI(**kwargs)
            self.version = openai.__version__
        else:
            self.version = "injected"
        self._client = client
        self.base_url = base_url
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_config(
        cls,
        config: AnswerModelConfig,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> "OpenAIAnswerProvider":
        """Build a client for exactly the endpoint, retries and timeout recorded."""
        refuse_unsupported_seed(config.seed)
        return cls(
            base_url=config.provider_base_url,
            max_retries=config.provider_max_retries,
            timeout_seconds=config.provider_timeout_seconds,
            environ=environ,
        )

    def generate(
        self,
        request: AnswerRequest,
        *,
        config: AnswerModelConfig,
    ) -> ProviderAnswer:
        # The client was built once; a config recording another endpoint or
        # retry count or timeout would make the manifest describe calls it
        # did not make.
        if (
            config.provider_base_url,
            config.provider_max_retries,
            config.provider_timeout_seconds,
        ) != (self.base_url, self.max_retries, self.timeout_seconds):
            raise ProviderConfigurationError(
                "provider was built for a different base URL, max_retries or "
                "timeout than the run config records"
            )
        refuse_unsupported_seed(config.seed)
        response = self._client.responses.create(
            **responses_create_kwargs(request, config)
        )
        text, text_error = _response_text(response)
        usage = response.usage
        input_details = getattr(usage, "input_tokens_details", None)
        output_details = getattr(usage, "output_tokens_details", None)
        cached_tokens = getattr(input_details, "cached_tokens", 0) or 0
        reasoning_tokens = getattr(output_details, "reasoning_tokens", 0) or 0
        if usage is None:
            usage_value: dict[str, Any] = {}
            input_tokens = 0
            output_tokens = 0
        else:
            usage_value = (
                usage.model_dump(mode="json")
                if hasattr(usage, "model_dump")
                else {
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                }
            )
            input_tokens = usage.input_tokens
            output_tokens = usage.output_tokens
        return ProviderAnswer(
            # A truncated response can carry no text at all; an empty string
            # keeps the failed cell recorded instead of raising mid-run.
            text=text,
            model_id=response.model,
            response_id=response.id,
            input_tokens=input_tokens,
            cached_input_tokens=cached_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            provider_usage=usage_value,
            status=getattr(response, "status", None),
            incomplete_reason=_incomplete_reason(
                getattr(response, "incomplete_details", None)
            ),
            text_error=text_error,
        )


def _response_text(response: Any) -> tuple[str, str | None]:
    """Read the response text, recording rather than raising on failure.

    ``output_text`` is a computed property that walks ``response.output``, so
    a partial response can in principle raise inside it. Letting that escape
    would abort the whole run and lose every call already paid for, while
    swallowing it would make an unreadable response indistinguishable from a
    model that said nothing. The reason is therefore returned alongside the
    empty text and recorded on the cell, which ``provider_valid`` then marks
    as a failure.
    """
    try:
        text = response.output_text
    except Exception as exc:  # noqa: BLE001 - the SDK property is opaque here
        return "", f"{type(exc).__name__}: {exc}"
    return (text or ""), None


def _incomplete_reason(details: Any) -> str | None:
    """Read the provider's stated reason for a non-completed response."""
    if details is None:
        return None
    reason = (
        details.get("reason")
        if isinstance(details, Mapping)
        else getattr(details, "reason", None)
    )
    return None if reason is None else str(reason)
