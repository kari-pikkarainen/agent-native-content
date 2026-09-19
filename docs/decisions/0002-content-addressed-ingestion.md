# ADR 0002: Content-address parsed document artifacts

- Status: Accepted
- Date: 2026-09-19

## Decision

Cache each serialized `DoclingDocument` under the full SHA-256 of its source
bytes and the full SHA-256 of the parser identity and configuration. Store a
separate immutable metadata record containing source, parser, schema, artifact,
and structural integrity fields.

Require complete Docling conversion success. Do not cache partial results.

## Rationale

A filename cache would silently reuse stale output after a source document
changes. Keying only by source content would silently reuse output produced by
an older parser or different pipeline. The two-part content address makes both
changes explicit while allowing identical source bytes to be reused regardless
of their local filename.

The complete serialized `DoclingDocument` remains the authoritative parsed
artifact. The project-specific IR will be a replaceable projection built in a
later milestone.
