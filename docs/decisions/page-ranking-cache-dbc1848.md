# Query-scoped page-ranking cache

Date: 2026-09-20

## Decision

Reuse deterministic multi-scale page-window rankings across token budgets for
the same compiler query. Keep table handling, deduplication, and final packing
budget-specific.

The cache key binds the query, source document identities, ranked node evidence,
and complete compiler configuration. Reuse with different inputs fails
explicitly. The benchmark creates a fresh cache per question and compiler arm.

## Timing treatment

The first eligible budget measures page-window preparation normally. Later
cache-hit budgets avoid repeating that work in wall-clock execution, but add the
measured preparation duration back to their recorded latency. Per-cell latency
therefore continues to represent an independently executable query while the
benchmark loop avoids redundant inference.

## Verification

- Unit and runner tests prove that two eligible budgets invoke page-window
  ranking once rather than twice.
- Cached and uncached compiler packets are identical in unit tests.
- Production-model run `xldev1-cache-dbc1848` has zero context-item mismatches
  at 8K and 16K versus the uncached `xldev1-multiscale-backfill` run.
- Evidence recall, full coverage, token counts, and redundancy are unchanged.

The selected compiler currently enables page backfill only at 16K, so its
standard four-budget run has one eligible cell and receives no cache hit. The
optimization matters for ablations and future configurations that enable
multi-scale expansion at more than one budget. It also establishes the safe
query-scoped reuse boundary needed before broader compiler preparation caching.
