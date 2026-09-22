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

### Third factor: heading context

`FactorialConfig.heading_contexts` is a tuple of booleans crossed with
`content_units` and `selection_policies` exactly as those are crossed with each
other. Each value sets `RetrievalConfig.heading_search_context` for the index
the cell retrieves from, so each position gets its own chunks and its own
derived-index key and no cached index is reused across the factor. The value is
recorded in every record, summary row and context, in the packet metadata, and
in the manifest's system names as `unit:policy:heading-on|heading-off`.

It defaults to `(True,)`. Single-valued, the cell set and every cell's metrics
are identical to a run without the factor, so nothing already measured moves
until the ablation is asked for. `(True, False)` doubles the cell count.

What the factor controls, by unit:

| Content unit | Reads the factor | Effect of turning it off |
| --- | --- | --- |
| Fixed 512/64 chunks | No | None: rows are constant across the factor |
| Docling structural chunks | Yes | `search_text` stays `None`; heading trail leaves the indexes |
| Content IR nodes | Yes | `search_text` stays `None`; heading trail leaves the indexes |

**The fixed unit's rows are constant across this factor by construction, and an
unchanged fixed row is not evidence about heading context.** `fixed_chunks`
never reads the field. It gets heading text anyway, incidentally: it windows
over every text-bearing IR node in ordinal order, title and heading nodes
included, so heading vocabulary is already inside its chunk text in both
positions. The generated report states this wherever it reports the factor.

**A delta across this factor carries two mechanisms, not one.** Turning the
field off both removes heading vocabulary from what is matched and narrows the
candidate dedupe key, because `HybridIndex._unique_by_search_text` dedupes on
`retrieval_text`. This is already recorded in `docs/specs/retrieval.md` for the
structural unit and applies unchanged to the IR unit. Attributing a
single-factor delta wholly to heading matching would be wrong; separating them
needs a second ablation that varies the dedupe key independently, which has not
been run.

Why the factor exists on both heading-bearing units rather than one: the
compiler's node candidates have always carried heading context unconditionally.
While only the structural unit could be ablated, "IR nodes beat structural
chunks" could not be told apart from "IR nodes carry heading context". The
compiler's oversized-table fragments keep their own pin
(`heading_search_context=False` in `compiler/expand.py`) in both positions;
that pin protects rendered fragment text and is not part of this factor.

The enhanced policy uses deterministic lexical facets and the existing
coverage objective. It does not use structural expansion, heading injection,
sibling or list expansion, table preservation, keyed table joins, page-neighbor
backfill, or an answer model.

### The structural unit moved: published factorial numbers do not carry across

The `Docling structural chunks` row is built by `evaluation/factorial.py`
through `structural_chunks` with no pin, so it reads
`RetrievalConfig.heading_search_context` at whatever value its cell was
assigned, and at the live default when the factor is single-valued. That
default changed from off to on, which gives structural chunks a `search_text`
of their heading trail above their body. The field changes two things at once:
heading vocabulary becomes matchable, and the candidate dedupe key widens so
that identical bodies under different headings no longer collapse. Both are
detailed in `docs/specs/retrieval.md`.

Consequences for this experiment:

- Every published structural-unit cell -- both policies -- was measured in the
  old state and cannot be carried across, and neither can the representation
  or policy comparisons drawn against it. The fixed-chunk and IR-node rows are
  unaffected, so a partial rerun that refreshes only the structural row would
  compare cells measured under two different behaviours.
- `RetrievalConfig` is part of the derived-index key payload, so the change
  rekeys cached indexes in either direction and no stale index is reused.
- A run that deliberately reproduces the old state must set
  `heading_contexts=(False,)` and record that it did. Since the field now also
  reaches the IR unit, that run reproduces the old *structural* state while
  also removing heading context from the IR unit, which the published IR rows
  had. The two old states cannot be reproduced separately through this field.

## Interpretation

- Compare IR with the better fixed/structural unit under the same policy to
  estimate the representation effect.
- Compare enhanced with ranked within the same unit to estimate the policy
  effect.
- Treat a larger IR gain under the enhanced policy as a possible interaction,
  to be confirmed on a broader preregistered set.
- Compare units and policies only within one heading-context position. The
  report's policy and IR contrasts are emitted per position for that reason.
- Read the heading-context contrast as "heading matching plus dedupe scope",
  and read the fixed unit's zero delta as "the factor does not apply", not as
  a measurement.

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
