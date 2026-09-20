"""Answer provider protocol and optional OpenAI Responses implementation."""

from typing import Any, Protocol

from contextbench.generation.models import (
    AnswerRequest,
    GenerationConfig,
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
        config: GenerationConfig,
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
        config: GenerationConfig,
    ) -> ProviderAnswer:
        params: dict[str, Any] = {
            "model": config.model,
            "input": request.prompt,
            "max_output_tokens": config.max_output_tokens,
            "store": False,
        }
        if config.reasoning_effort is not None:
            params["reasoning"] = {"effort": config.reasoning_effort}
        response = self._client.responses.create(**params)
        usage = response.usage
        input_details = getattr(usage, "input_tokens_details", None)
        output_details = getattr(usage, "output_tokens_details", None)
        cached_tokens = getattr(input_details, "cached_tokens", 0) or 0
        reasoning_tokens = getattr(output_details, "reasoning_tokens", 0) or 0
        usage_value = (
            usage.model_dump(mode="json")
            if hasattr(usage, "model_dump")
            else {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
            }
        )
        return ProviderAnswer(
            text=response.output_text,
            model_id=response.model,
            response_id=response.id,
            input_tokens=usage.input_tokens,
            cached_input_tokens=cached_tokens,
            output_tokens=usage.output_tokens,
            reasoning_tokens=reasoning_tokens,
            provider_usage=usage_value,
        )
