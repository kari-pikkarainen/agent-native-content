"""Query-independent compiler lookups derived once from the immutable IR."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from agent_native_content.compiler.joins import KeyedTableIndex
from agent_native_content.ir.models import IRDocument, IRNode
from agent_native_content.ir.tokenizer import TokenCounter
from agent_native_content.retrieval.chunking import fixed_chunks
from agent_native_content.retrieval.models import RetrievalChunk, RetrievalConfig


@dataclass(frozen=True)
class CompilerCorpusIndex:
    """Reusable node, adjacency, and page-window lookups for a corpus."""

    retrieval_config: RetrievalConfig
    documents_by_id: Mapping[str, IRDocument]
    nodes_by_document: Mapping[str, Mapping[str, IRNode]]
    siblings_by_node: Mapping[tuple[str, str], tuple[IRNode, ...]]
    page_chunks_by_document: Mapping[str, tuple[RetrievalChunk, ...]]
    keyed_table_index: KeyedTableIndex

    @classmethod
    def build(
        cls,
        documents: Sequence[IRDocument],
        *,
        retrieval_config: RetrievalConfig,
        tokenizer: TokenCounter,
    ) -> "CompilerCorpusIndex":
        documents_by_id = {document.id: document for document in documents}
        if len(documents_by_id) != len(documents):
            raise ValueError("compiler corpus contains duplicate document IDs")
        nodes_by_document = {
            document.id: {node.id: node for node in document.nodes}
            for document in documents
        }
        siblings_by_node: dict[tuple[str, str], tuple[IRNode, ...]] = {}
        for document in documents:
            nodes = nodes_by_document[document.id]
            roots = tuple(node for node in document.nodes if node.parent_id is None)
            for node in document.nodes:
                siblings = (
                    tuple(
                        nodes[node_id]
                        for node_id in nodes[node.parent_id].children_ids
                    )
                    if node.parent_id is not None
                    else roots
                )
                siblings_by_node[(document.id, node.id)] = siblings
        return cls(
            retrieval_config=retrieval_config,
            documents_by_id=documents_by_id,
            nodes_by_document=nodes_by_document,
            siblings_by_node=siblings_by_node,
            page_chunks_by_document={
                document.id: fixed_chunks(
                    document,
                    config=retrieval_config,
                    tokenizer=tokenizer,
                )
                for document in documents
            },
            keyed_table_index=KeyedTableIndex.build(documents),
        )

    def node(self, document_id: str, node_id: str) -> IRNode:
        """Resolve a node without rebuilding an ID map."""
        return self.nodes_by_document[document_id][node_id]

    def siblings(self, node: IRNode) -> tuple[IRNode, ...]:
        """Return precomputed siblings in source order."""
        return self.siblings_by_node[(node.document_id, node.id)]
