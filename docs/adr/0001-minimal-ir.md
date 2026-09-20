# ADR 0001: Keep the canonical Content IR minimal

- Status: Accepted
- Date: 2026-09-19

## Decision

The canonical IR will contain only source-derived structure and provenance
needed to test structure-aware retrieval. Embeddings and other retrieval data
will be stored as derived indexes.

## Rationale

Separating source truth from replaceable indexes keeps the experiment valid
when embedding models, rerankers, or retrieval algorithms change. It also
prevents untested features from obscuring the hypothesis.
