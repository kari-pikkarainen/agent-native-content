# Architecture

This document will describe the implemented system boundaries and data flow.
The authoritative target architecture is currently defined in
[`benchmark-spec.md`](benchmark-spec.md).

The benchmark will compare four independent arms while sharing retrieval
models, token accounting, and evaluation machinery wherever fairness requires
it. The canonical parsed document and normalized IR will remain separate from
derived retrieval indexes and immutable experiment outputs.

Architecture decisions should favor the smallest implementation capable of
testing the research hypothesis.

## Ingestion boundary

Source documents are immutable inputs identified by SHA-256. The ingestion
layer converts each local PDF into Docling's complete `DoclingDocument` JSON;
this remains the authoritative parsed artifact. A separate metadata record
captures:

- source path, size, and SHA-256;
- Docling and Docling Core versions;
- the complete intentional parser configuration and its SHA-256;
- serialized document SHA-256 and Docling schema version;
- page, text, heading, and table counts.

The cache key is:

```text
source SHA-256 / parser-and-configuration SHA-256
```

A source-byte, parser-version, Docling Core version, model-artifact location,
or pipeline-setting change therefore selects a new cache entry. Cache hits
verify document integrity and structural counts before deserialization. Partial
Docling conversions are rejected rather than cached.

The normalized benchmark IR is a separate deterministic projection from this
artifact. It must not replace or mutate the serialized `DoclingDocument`.

## IR boundary

The IR projection normalizes Docling items into a small validated graph while
preserving source references, hierarchy, heading context, tables, page boxes,
and token counts. Document and node identities derive from immutable source
identity and Docling references, making repeated builds stable. Canonical JSON
round-trips through the same validation rules.

The IR contains source truth only. Embeddings, lexical statistics, retrieval
scores, generated annotations, and later experiment outputs are derived state
and remain outside it. See [`ir-spec.md`](ir-spec.md) for the normative schema.
