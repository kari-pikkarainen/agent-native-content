# Content-Unit × Selection-Policy Factorial Specification

## Purpose

The primary retrieval benchmark changes representation and selection behavior
at the same time. This controlled experiment asks whether the observed gain
comes from IR nodes, from faceted retrieval and coverage-aware packing, or from
an interaction between them.

## Factor matrix

| Content unit | Ranked control | Enhanced policy |
| --- | --- | --- |
| Fixed 512/64 chunks | Single query + ranked packing | Faceted retrieval + coverage packing |
| Docling structural chunks | Single query + ranked packing | Faceted retrieval + coverage packing |
| Content IR nodes | Single query + ranked packing | Faceted retrieval + coverage packing |

All six cells share the same documents, document scope, tokenizer, BM25
configuration, embedding model, reciprocal-rank fusion, cross-encoder,
candidate limits, and token budgets. Both policies apply the same exact source
provenance deduplication before packing.

The enhanced policy uses deterministic lexical facets and the existing
coverage objective. It does not use structural expansion, heading injection,
sibling or list expansion, table preservation, keyed table joins, page-neighbor
backfill, or an answer model.

## Interpretation

- Compare IR with the better fixed/structural unit under the same policy to
  estimate the representation effect.
- Compare enhanced with ranked within the same unit to estimate the policy
  effect.
- Treat a larger IR gain under the enhanced policy as a possible interaction,
  to be confirmed on a broader preregistered set.

The initial two-question table subset is diagnostic only. It keeps the full
XLDev24 retrieval corpus fixed so index statistics and candidate competition
match development runs.

## Command and outputs

```shell
uv run --extra retrieval contextbench eval-factorial \
  --subset-file benchmarks/xl-docbench/subsets/xldev2-tables.json \
  --retrieval-corpus-subset-file benchmarks/xl-docbench/subsets/xldev24.json \
  --run-id xldev2-factorial
```

The safe defaults select those same files. Runs are atomically published under
`artifacts/factorial-runs/<run-id>/` and contain a complete manifest,
per-question metrics, contexts, summary, and Markdown report. Existing run IDs
are never overwritten.

The shared evaluator reports both provenance page recall and conservative
content-verified page recall. The latter credits a source node's pages only
when its full normalized text is present in the emitted context, preventing a
partial multi-page chunk from inheriting all of the node's pages.
