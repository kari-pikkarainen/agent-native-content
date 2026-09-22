"""Fixed and Docling-native structural chunk construction."""

import hashlib
from typing import Any

from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from docling_core.types.doc import DoclingDocument
from pydantic import ConfigDict, PrivateAttr

from contextbench.ir.models import IRDocument
from contextbench.ir.tokenizer import TiktokenTokenCounter, TokenCounter
from contextbench.retrieval.models import RetrievalArm, RetrievalChunk, RetrievalConfig


class TiktokenChunkTokenizer(BaseTokenizer):
    """Docling tokenizer adapter using the benchmark's explicit encoding."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    encoding_name: str = "o200k_base"
    max_tokens: int = 512
    _counter: TiktokenTokenCounter = PrivateAttr()

    def model_post_init(self, __context: Any) -> None:
        self._counter = TiktokenTokenCounter(self.encoding_name)

    def count_tokens(self, text: str) -> int:
        return self._counter.count(text)

    def get_max_tokens(self) -> int:
        return self.max_tokens

    def get_tokenizer(self) -> Any:
        return self._counter.count


class CounterChunkTokenizer(BaseTokenizer):
    """Adapt an injected benchmark counter for offline structural tests."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    counter: Any
    max_tokens: int = 512

    def count_tokens(self, text: str) -> int:
        return self.counter.count(text)

    def get_max_tokens(self) -> int:
        return self.max_tokens

    def get_tokenizer(self) -> Any:
        return self.counter.count


def contextual_search_text(text: str, heading_path: tuple[str, ...]) -> str:
    """Join a heading trail above chunk text for search only, never for output.

    Shared by the compiler candidates and the structural arm so both index the
    same contextual string. The last heading is dropped when it duplicates the
    text itself, so a heading node is not repeated against itself.
    """
    headings = heading_path
    if headings and headings[-1].strip().casefold() == text.strip().casefold():
        headings = headings[:-1]
    return "\n".join((*headings, text))


def fixed_chunks(
    document: IRDocument,
    *,
    config: RetrievalConfig,
    tokenizer: TokenCounter | None = None,
) -> tuple[RetrievalChunk, ...]:
    """Create overlapping fixed-token windows over body nodes in ordinal order.

    Furniture -- running headers, footers, page numbers -- is excluded, which
    is what every other retrieval surface already does: ``node_chunks`` for the
    compiler, ``long_context``, the representation runner, the agentdoc bundle,
    and Docling's own ``HybridChunker`` behind ``structural_chunks``, whose
    traversal is body-only by default. Fixed windows were the one surface
    carrying it, so the exemption ran the wrong way: the baseline paid for
    text the compiler never had to. Across the 28 cached documents furniture
    is 5,804 nodes and 40,132 tokens, 1.9% of text, and reads like
    ``'2018 l Annual Report'`` repeated once per page. The nodes stay in the
    IR with their provenance; this is a retrieval-surface decision only.
    """
    counter = tokenizer or TiktokenTokenCounter(config.tokenizer_name)
    streams: list[tuple[list[Any], str]] = []
    for node in document.nodes:
        if node.text and node.content_layer != "furniture":
            encoded = _encode(node.text, counter)
            streams.append((encoded, node.id))
    if not streams:
        return ()

    tokens: list[Any] = []
    source_for_token: list[str | None] = []
    for index, (encoded, node_id) in enumerate(streams):
        if index:
            separator = _encode("\n", counter)
            tokens.extend(separator)
            source_for_token.extend([None] * len(separator))
        tokens.extend(encoded)
        source_for_token.extend([node_id] * len(encoded))

    size = config.fixed_chunk_tokens
    step = size - config.fixed_overlap_tokens
    chunks: list[RetrievalChunk] = []
    for start in range(0, len(tokens), step):
        window = tokens[start : start + size]
        if not window:
            break
        text = _decode(window, counter).strip()
        source_node_ids = tuple(
            dict.fromkeys(
                source for source in source_for_token[start : start + size] if source
            )
        )
        if not text or not source_node_ids:
            if start + size >= len(tokens):
                break
            continue
        chunks.append(
            _chunk_from_nodes(
                document,
                text=text,
                source_node_ids=source_node_ids,
                arm=RetrievalArm.FIXED,
                ordinal=len(chunks),
                token_count=counter.count(text),
            )
        )
        if start + size >= len(tokens):
            break
    return tuple(chunks)


def structural_chunks(
    document: IRDocument,
    source: DoclingDocument,
    *,
    config: RetrievalConfig,
    tokenizer: TokenCounter | None = None,
    chunk_tokenizer: BaseTokenizer | None = None,
) -> tuple[RetrievalChunk, ...]:
    """Create source-traceable chunks with Docling's HybridChunker."""
    counter = tokenizer or TiktokenTokenCounter(config.tokenizer_name)
    if chunk_tokenizer is None:
        chunk_tokenizer = (
            TiktokenChunkTokenizer(
                encoding_name=config.tokenizer_name,
                max_tokens=config.structural_chunk_tokens,
            )
            if hasattr(counter, "encode")
            else CounterChunkTokenizer(
                counter=counter,
                max_tokens=config.structural_chunk_tokens,
            )
        )
    chunker = HybridChunker(
        tokenizer=chunk_tokenizer,
        repeat_table_header=True,
        merge_peers=True,
    )
    node_by_ref = {
        source_ref: node
        for node in document.nodes
        for source_ref in node.source_item_ids
    }
    chunks: list[RetrievalChunk] = []
    for raw_chunk in chunker.chunk(source):
        source_refs = tuple(
            item.self_ref
            for item in raw_chunk.meta.doc_items
            if item.self_ref in node_by_ref
        )
        node_ids = tuple(dict.fromkeys(node_by_ref[ref].id for ref in source_refs))
        if not node_ids or not raw_chunk.text.strip():
            continue
        heading_path = tuple(raw_chunk.meta.headings or ())
        # Search-only context. The emitted ``text`` stays ``raw_chunk.text``,
        # so token counts, budgets and the string a model reads are unchanged;
        # only what the indexes read gains the heading trail.
        search_text = (
            contextual_search_text(raw_chunk.text, heading_path)
            if config.structural_heading_search_context and heading_path
            else None
        )
        chunks.append(
            _chunk_from_nodes(
                document,
                text=raw_chunk.text,
                source_node_ids=node_ids,
                source_item_ids=source_refs,
                arm=RetrievalArm.STRUCTURAL,
                ordinal=len(chunks),
                token_count=counter.count(raw_chunk.text),
                heading_path=heading_path,
                search_text=search_text,
            )
        )
    return tuple(chunks)


def _chunk_from_nodes(
    document: IRDocument,
    *,
    text: str,
    source_node_ids: tuple[str, ...],
    arm: RetrievalArm,
    ordinal: int,
    token_count: int,
    source_item_ids: tuple[str, ...] | None = None,
    heading_path: tuple[str, ...] | None = None,
    search_text: str | None = None,
) -> RetrievalChunk:
    nodes = [document.node_by_id[node_id] for node_id in source_node_ids]
    source_refs = source_item_ids or tuple(
        source_ref for node in nodes for source_ref in node.source_item_ids
    )
    pages = [
        page for node in nodes for box in node.bounding_boxes for page in (box.page_no,)
    ]
    payload = "\0".join(
        (arm.value, document.id, str(ordinal), text, *source_refs)
    ).encode()
    chunk_id = f"chunk_{hashlib.sha256(payload).hexdigest()}"
    return RetrievalChunk(
        id=chunk_id,
        arm=arm,
        document_id=document.id,
        text=text,
        search_text=search_text,
        token_count=token_count,
        heading_path=heading_path
        if heading_path is not None
        else tuple(
            next((node.heading_path for node in nodes if node.heading_path), ())
        ),
        page_start=min(pages) if pages else None,
        page_end=max(pages) if pages else None,
        source_node_ids=source_node_ids,
        source_item_ids=tuple(dict.fromkeys(source_refs)),
    )


def _encode(text: str, counter: TokenCounter) -> list[Any]:
    encode = getattr(counter, "encode", None)
    if encode is not None:
        return list(encode(text))
    return text.split()


def _decode(tokens: list[Any], counter: TokenCounter) -> str:
    decode = getattr(counter, "decode", None)
    if decode is not None:
        return decode(tokens)
    return " ".join(str(token) for token in tokens)
