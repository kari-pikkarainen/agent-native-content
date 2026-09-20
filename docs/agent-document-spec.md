# Agent Document Specification

## Purpose

An agent document is a portable, query-independent encoding of one immutable
source document. It makes structure, navigation, salient source excerpts, and
table shape explicit before any question is asked. It does not replace the
source PDF or claim that query-independent salience is universally important.

The initial implementation is deterministic and extractive. It does not call
an LLM, inspect benchmark questions or answers, or create unsupported facts.

## Bundle layout

```text
<bundle>/
├── source.pdf            optional, hash-verified original bytes
├── content.json          canonical ContextBench IR
├── enrichments.jsonld    source-grounded agent affordances
├── agent.html            semantic HTML with embedded JSON-LD
└── manifest.json         identities, configuration, and file hashes
```

Creation is atomic and refuses to overwrite an existing directory. The
manifest binds the files to the source SHA-256, IR document ID, schema and
generator versions, and complete enrichment configuration.

## Feature vocabulary

- `outline`: document titles and headings in source order;
- `section_summary`: the first configured number of source sentences in a
  section, concatenated without abstractive rewriting;
- `key_fact`: source sentences containing numeric or configured normative
  signals;
- `definition`: source sentences containing deterministic definition signals;
- `entity`: conservative names with an explicitly written parenthetical alias;
- `relationship`: typed `alias_of` and `has_columns` relationships;
- `table_schema`: source caption, column labels, and row count;
- `table_row`: calculation-ready label/value mappings for source rows.

Every feature has a stable content-derived ID, bounded importance and
confidence signals, a heading path, page range, supporting IR node IDs,
supporting Docling item IDs, and type-specific attributes. A feature may be
selected for a page-scoped experiment only when all its supporting nodes are
authorized by that scope.

Importance is a deterministic prioritization hint, not a probability or a
claim of semantic relevance to every future task.

## JSON-LD and HTML

`enrichments.jsonld` uses a small `urn:contextbench:agent-document:` vocabulary
and preserves feature provenance explicitly. `agent.html` renders body nodes
as semantic headings, paragraphs, code, and tables, adds page attributes and
stable node anchors, exposes an outline, and embeds the same JSON-LD document.

These exports demonstrate that an existing web document format can carry both
human-readable content and machine-readable affordances. Consumers still need
to opt into reading embedded enrichment; format support alone does not ensure
that an AI file-ingestion service will expose it.

## Trust boundary

The canonical IR remains source truth. Agent features are derived and can be
discarded and rebuilt under another configuration or generator version. Future
abstractive summaries, entities, aliases, or relationship graphs must remain
in the derived enrichment layer and retain source provenance and generator
identity.

## Representation experiment

The gold-evidence experiment isolates representation from retrieval. For every
question with annotated pages, it selects one fixed set of source nodes and
stable evidence IDs, then renders:

1. `raw`: minimal source text;
2. `ir`: source text plus structural and provenance fields;
3. `enriched`: IR plus features whose complete node provenance is inside the
   same gold-page scope.

Enrichment is built once per document before question cells execute. Features
are ordered by their query-independent importance signal, but no query is used
to create or score them. All conditions use the same provider, model settings,
answer prompt, scoring, output limit, and pricing metadata. The experiment
records exact contexts so any improvement can be checked for leakage or merely
increased token volume.

Calculation-ready rows remain available in the bundle but are excluded from
the default inline prompt to avoid duplicating complete tables. The inline
agent index is capped at 128 features after deterministic importance/page/ID
ordering. Both policies are explicit experiment configuration.
