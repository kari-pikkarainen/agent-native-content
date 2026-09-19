"""Fixed tokenizer abstraction for reproducible IR token counts."""

from importlib.metadata import version
from typing import Protocol

DEFAULT_ENCODING = "o200k_base"


class TokenCounter(Protocol):
    """Minimal token counter required by IR projection and later packing."""

    @property
    def name(self) -> str:
        """Return the tokenizer or encoding name."""
        ...

    @property
    def version(self) -> str:
        """Return the tokenizer implementation version."""
        ...

    def count(self, text: str) -> int:
        """Return the number of tokens in text."""
        ...


class TiktokenTokenCounter:
    """Count tokens with one explicitly named tiktoken encoding."""

    def __init__(self, encoding_name: str = DEFAULT_ENCODING) -> None:
        import tiktoken

        self._encoding = tiktoken.get_encoding(encoding_name)
        self._name = encoding_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return version("tiktoken")

    def count(self, text: str) -> int:
        return len(self._encoding.encode(text, disallowed_special=()))
