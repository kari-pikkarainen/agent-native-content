"""Answer provider protocol and optional OpenAI Responses implementation."""

from collections.abc import Mapping
from typing import Any, Protocol

from contextbench.generation.models import (
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


class OpenAIAnswerProvider:
    """OpenAI Responses API adapter, imported lazily for optional installation."""

    name = "openai"

    def __init__(self, client: Any | None = None) -> None:
        if client is None:
            try:
                import openai
            except ImportError as exc:
                raise RuntimeError(
                    "OpenAI generation requires `uv sync --extra generation`"
                ) from exc
            client = openai.OpenAI()
            self.version = openai.__version__
        else:
            self.version = "injected"
        self._client = client

    def generate(
        self,
        request: AnswerRequest,
        *,
        config: AnswerModelConfig,
    ) -> ProviderAnswer:
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
        if config.seed is not None:
            params["seed"] = config.seed
        response = self._client.responses.create(**params)
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
