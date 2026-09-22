# Content IR Specification

Status: implemented schema version `1.0.0`.

The intermediate representation (IR) is a small, deterministic projection of
an authoritative Docling `DoclingDocument`. It contains only source-derived
structure, content, provenance, and token counts needed by the benchmark's
retrieval experiments. It does not replace or mutate the Docling artifact.

## Document schema

`IRDocument` contains:

| Field | Meaning |
| --- | --- |
| `schema_version` | IR contract version; currently `1.0.0` |
| `id` | `doc_` followed by the source SHA-256 |
| `source_uri` | Original source URI, or the absolute local path as a file URI |
| `source_sha256` | SHA-256 of the immutable source bytes |
| `parser_name` | Parser implementation name |
| `parser_version` | Parser package version |
| `parser_core_version` | Docling Core/schema package version |
| `tokenizer_name` | Encoding used for all node token counts |
| `tokenizer_version` | Tokenizer implementation version |
| `page_count` | Number of pages in `page_numbers` |
| `page_numbers` | Sorted, unique source page numbers |
| `nodes` | Nodes in deterministic source traversal order |

An `IRNode` contains:

| Field | Meaning |
| --- | --- |
| `id` | Stable node identifier |
| `document_id` | Owning `IRDocument.id` |
| `kind` | Normalized source kind |
| `content_layer` | Docling `body` or `furniture` layer |
| `parent_id` | Parent IR node, or null for a root |
| `children_ids` | Direct child IR nodes in source order |
| `ordinal` | Contiguous zero-based traversal position |
| `text` | Source text or deterministic textual table rendering |
| `heading_path` | Active title and section headings, outermost first |
| `page_start`, `page_end` | Inclusive source page span, or null without provenance |
| `bounding_boxes` | Source boxes with their page and coordinate origin |
| `source_item_ids` | Docling self-references that support the node |
| `token_count` | Tokens in `text` under the document tokenizer |
| `table` | Logical table metadata for table nodes; otherwise null |

Unknown fields are rejected during deserialization. The models are immutable
after validation.

## Node kinds

The closed vocabulary is:

```text
title, heading, paragraph, list, list_item, table, table_chunk,
caption, figure, code, other
```

The projection maps Docling titles, section/field headings, paragraph-like
text, list groups and items, tables, captions, pictures/charts, and code to the
corresponding kinds. Unsupported groups or item labels map to `other` so the
source structure is retained. `table_chunk` is reserved for later structural
chunk construction; projecting an authoritative document does not synthesize
chunks.

## Identity and ordering

Document identity is the source byte identity:

```text
document ID = "doc_" + source_sha256
```

Node identity is the SHA-256 of a domain separator, the document ID, and the
Docling source reference, joined with NUL bytes:

```text
node ID = "node_" + sha256("contextbench-ir-v1\0" + document_id + "\0" + source_ref)
```

This makes IDs stable across repeated projections of the same authoritative
source structure without depending on Python hash randomization. Node identity
does not depend on `ordinal`, so a change to traversal order leaves every node
ID unchanged.

**`ordinal` must reflect source order.** Nodes are traversed depth-first in
Docling child order from the body root, then from the legacy furniture root.
The traversal asks Docling for *everything*: `traverse_pictures=True`, so the
text items nested under a full-page `PictureItem` are reached, and all content
layers, so furniture inside the body tree is reached. Both are non-default in
`iterate_items` and both hide content that the document itself places in the
middle of a page.

This matters because consumers read `document.nodes` as a stream. `fixed_chunks`
concatenates node text in ordinal order, and `_chunk_from_nodes` reports a
window's page span as the min and max page of the nodes it touches, so an item
delivered out of order splices unrelated pages into one window and inflates its
claimed span. Before this was repaired, 29,785 of 72,745 items across the 28
cached benchmark documents (40.9%, in every document, up to 69.8% in one) were
reached only after the walk, giving each document a page inversion at that
boundary and 445 of 4,895 fixed windows a claimed span over three pages, one of
them the full 314 pages of its source.

Any source item still not reachable from either root is retained afterward in
deterministic Docling collection order and receives a trailing ordinal. That
path is a safety net against content loss, not a routine one: it should yield
nothing for a well-formed document.

## Hierarchy and heading paths

Docling parent references become `parent_id` links and the inverse links become
`children_ids`. The synthetic Docling body and furniture roots are not emitted,
so their direct children are IR roots.

PDF parser output often places headings and paragraphs as siblings beneath the
body root. Heading paths are therefore resolved from source traversal order and
Docling heading levels, rather than only by following parent links. A heading
at a level replaces the active heading at that level and all deeper headings.
An active title prefixes the path. Furniture nodes receive an empty heading
path.

Furniture is projected, never dropped. Running headers, footers and page
numbers keep their text, provenance and node IDs in the IR; which retrieval
surfaces index them is a separate decision, recorded in
`docs/specs/retrieval.md`. Excluding them at ingestion instead would make the
choice unauditable and irreversible.

## Text and tables

Text items retain their normalized source text. If Docling emits an empty
normalized `text` value but preserves non-empty source-derived `orig` text, the
projection uses `orig` rather than creating an evidence-free node. A figure
uses its source caption text when present. A list group uses its source name,
if any.

A table preserves:

- optional source caption;
- per-column header text when Docling marks header cells;
- the logical cell matrix as rows.

Its searchable `text` is generated deterministically: caption first, then one
line per row, with cells separated by ` | `. The structured `table` value is
the source of truth for later table-aware retrieval.

## Page provenance

Every Docling provenance box is copied without coordinate conversion:

```text
page_no, left, top, right, bottom, coord_origin
```

`coord_origin` is explicitly retained as `TOPLEFT` or `BOTTOMLEFT`.
`page_start` and `page_end` are the minimum and maximum box page numbers. Nodes
without source page boxes use null page bounds and an empty box list.

## Token accounting

The default counter is the explicit tiktoken encoding `o200k_base`. Projection
records both the encoding name and installed tiktoken version, and counts the
exact `text` stored on each node. The encoding is named directly rather than
inferred from a model alias so model-name mapping changes cannot silently alter
benchmark budgets. Tests inject a deterministic local counter and require no
network access.

## Serialization and validation

IR JSON is UTF-8, key-sorted, two-space indented, newline-terminated, and
written atomically. Loading always re-runs model and graph validation.

Validation rejects:

- duplicate node IDs or non-contiguous ordinals;
- wrong document references;
- unknown or non-reciprocal parent/child links;
- cycles or nodes unreachable from an IR root;
- duplicate source references within a node;
- page bounds or boxes that reference unknown pages;
- page bounds that disagree with bounding boxes;
- malformed table dimensions or table metadata on non-table nodes.

Multiple future nodes may cite the same source item, which permits derived
structural table chunks to remain traceable to their source table.

## Explicit exclusions

Schema version `1.0.0` does not contain embeddings, sparse-index statistics,
retrieval scores, generated summaries, keywords, entities, relationships,
graphs, LLM annotations, or task-specific metadata. These are derived indexes
or experiment outputs and must remain separate from the canonical IR.
