# Parallel parsing performance at `46c2a61`

Date: 2026-09-23

Code commit: `46c2a61` (`c44160e` contains the implementation). The worktree
was clean. This is an operational performance diagnostic, not retrieval or
answer-quality evidence.

## Question

Does parsing uncached benchmark documents with two or four spawned Docling
processes reduce the wall time of a real evaluation command, and what memory
does it cost?

## Setup

- Machine: Apple M3 Pro MacBook Pro, 12 CPU cores (6 performance and 6
  efficiency), 36 GB memory.
- OS: macOS 26.6.2 (25G83).
- Runtime: Python 3.14.7 and Docling 2.129.0.
- Input: committed `xldev6-perf` subset, six questions over six distinct
  documents.
- Run order: 1, 2, then 4 workers; one trial per setting.
- Every trial used a new empty ingestion-cache directory and a new empty
  artifact directory. Source PDFs and Docling models were already cached.
- The offline `hash-256-v1` embedder and `lexical-overlap-v1` reranker removed
  model downloads and remote inference from the measurement.
- The declared `xldev24` parent retrieval corpus was intentionally omitted:
  this diagnostic measured the six subset documents, not retrieval quality or
  the published `xldev6-perf` evaluation configuration.
- No API key, API call or network call was used.

The command shape was:

```shell
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  uv run --extra retrieval agent-native-content eval-retrieval \
  --data-dir data/raw/xl-docbench \
  --subset-file benchmarks/xl-docbench/subsets/xldev6-perf.json \
  --source-cache-dir data/cache/xl-docbench \
  --ingest-cache-dir "$FRESH_INGEST_DIR" \
  --artifacts-root "$FRESH_ARTIFACTS_DIR" \
  --embedding-model hash-256-v1 \
  --reranker-model lexical-overlap-v1 \
  --parse-workers N \
  --run-id parallel-parse-perf-wN
```

Wall time covered the complete command: dataset verification, parsing,
projection, index construction, retrieval and report generation. A sampler
polled the process tree every 0.2 seconds and summed resident memory at each
sample; the reported peak is the largest simultaneous sum, not the sum of
each process's independent maximum.

## Results

All three commands completed successfully and produced all six ingestion
entries.

| Parser workers | Wall time | Speedup vs 1 | Wall-time reduction | Peak process-tree RSS |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 1,068.549 s (17m 48.5s) | 1.00x | — | 4,507.8 MiB (4.40 GiB) |
| 2 | 833.349 s (13m 53.3s) | 1.28x | 22.0% | 6,388.9 MiB (6.24 GiB) |
| 4 | 868.141 s (14m 28.1s) | 1.23x | 18.8% | 8,011.5 MiB (7.82 GiB) |

Two workers saved 235.2 seconds (3m 55.2s) relative to one and increased peak
memory by 41.7%. Four workers were 34.8 seconds (4.2%) slower than two and used
1,622.6 MiB more peak memory.

## Decision

Use `--parse-workers 2` as the measured local default on this machine. Keep
the CLI default at one worker: it is the compatibility and low-memory setting,
and this single-machine diagnostic does not justify changing behavior for
every environment.

Do not recommend four workers from this result. The likely constraints are
unequal document parse times and contention between Docling's existing
per-process threads, but this run did not isolate those causes. Four workers
could still help a larger corpus with a different document-size distribution;
measure before adopting it.

## Limitations

- One trial per worker count, in a fixed order; thermal and background-system
  variance were not estimated.
- Six documents are enough to exercise four workers, but not enough to build a
  general scaling curve.
- The timing is deliberately end to end. It represents user-visible cold-run
  time but does not isolate parser initialization, parsing, projection or
  retrieval time.
- Temporary run artifacts were discarded after successful completion. The
  committed subset, Git SHA, environment and command are recorded here so the
  diagnostic can be repeated, but these rows are not canonical benchmark
  result artifacts.

> Rename note (2026-10-01): the package, distribution and CLI were renamed
> from `contextbench` to `agent-native-content` after this record was
> written. Commands above show the new name; the runs were made with the old
> one. Hash domains and run artifacts are unchanged.
