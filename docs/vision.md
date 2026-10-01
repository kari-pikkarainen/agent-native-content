# Agent-Native Content Vision

## The idea

AI systems repeatedly decode the same source content into temporary chunks,
embeddings, summaries, and prompt fragments. Agent-Native Content explores a
different boundary: decode a source once into a durable, structure-preserving,
provenance-aware representation, then derive task-specific views from it.

The representation is not intended to replace source formats. A PDF, web page,
spreadsheet, presentation, transcript, or image remains the source of truth.
Content IR (intermediate representation) is a verified intermediate layer that exposes the source's useful
structure to search systems, tools, and agents.

## Design principles

1. **Preserve source truth.** Every node and derived feature must trace back to
   an immutable source and location.
2. **Prepare once, reuse often.** Parsing, normalization, structural indexing,
   and question-independent enrichment belong outside the query path.
3. **Keep derived state replaceable.** Embeddings, rankings, summaries, and
   agent features must not become canonical content.
4. **Compile for the task.** Consumers should receive a bounded evidence view,
   not an undifferentiated document dump.
5. **Measure against strong alternatives.** Better chunking, ordinary retrieval-augmented generation (RAG), and
   long context are required controls.
6. **Make failure informative.** Experiments must be able to reject the added
   representation or compilation layer.

## What exists today

The reference implementation supports PDFs through Docling, a canonical JSON
IR, portable HTML and JSON-LD (JSON for Linked Data) agent bundles, local hybrid retrieval, a
deterministic context compiler, and controlled retrieval and representation
benchmarks.

## Directions beyond the current prototype

- decoders for HTML, office documents, spreadsheets, presentations, audio, and
  video transcripts;
- typed content relationships shared across formats;
- addressable multimodal regions and derived descriptions;
- incremental updates that preserve stable identities;
- interoperable schemas and validation tools;
- agent tools for selective traversal instead of prompt-only delivery; and
- benchmarks covering answer quality, citations, cost, latency, and reuse.

These are research directions, not claims that the current implementation
already supports them. The [benchmark specification](specs/benchmark.md)
defines the implemented hypothesis and its falsification criteria.
