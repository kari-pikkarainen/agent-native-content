"""Warm the ingestion cache with a pool of parser processes.

This is only a pre-step. Callers keep their sequential fetch-and-ingest loop
unchanged; after this has run, that loop finds every entry already in the
cache and loads it. With one worker this does nothing at all, so the loop
runs exactly as before -- same order, same first-failure-raises behaviour.

Why processes: Docling parsing is CPU-bound Python holding the GIL, so
threads would serialize.

Why ``spawn`` everywhere, not only where it is the default (macOS): forking a
parent that has already imported PyTorch, or started any thread, can deadlock
or inherit a half-initialised thread pool. A spawned worker starts from a
clean interpreter and initialises Docling itself, as a sequential run does.

Why threads are left alone: each worker inherits the parent's environment
unchanged, so Docling resolves ``AcceleratorOptions`` (``num_threads`` from
``DOCLING_NUM_THREADS`` or ``OMP_NUM_THREADS``, default 4; ``device``
``auto``) exactly as a sequential parse in the same shell does. Setting a
per-worker thread count would change the intra-op thread count of the
layout, table and OCR models, and floating-point reductions split across a
different number of threads can round differently. That could move a
borderline layout or cell decision and so change a cached parse whose key
does not record threads. Oversubscription (N workers x 4 threads on 12
cores) costs throughput only, never output, so the choice of N is left to
the operator.

Models should already be local before N > 1: run one document sequentially
first, or pass ``--docling-artifacts-dir``. Otherwise every worker can start
the same model download at once.
"""

import multiprocessing
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from agent_native_content.ingest.cache import IngestionCache, IngestionError


class _Source(Protocol):
    id: str


class _SourceCache(Protocol):
    def fetch(self, source: _Source, /) -> object: ...


class ParallelIngestionError(IngestionError):
    """One or more documents could not be fetched or parsed.

    Raised only after every other document has finished, so one run reports
    every failure at once. ``failures`` maps document id to message, in the
    caller's document order.
    """

    def __init__(self, failures: dict[str, str]) -> None:
        self.failures = dict(failures)
        lines = "\n".join(
            f"  {document_id}: {message}" for document_id, message in failures.items()
        )
        super().__init__(
            f"{len(failures)} document(s) could not be prepared; "
            f"refusing to continue without them:\n{lines}"
        )

    def __reduce__(self):  # keep picklable across process boundaries
        return (type(self), (self.failures,))


@dataclass(frozen=True)
class WarmCacheSummary:
    """What the pre-step did, for progress reporting and tests."""

    parsed: tuple[str, ...]
    already_cached: tuple[str, ...]
    duplicate_content: tuple[str, ...]


def warm_ingestion_cache(
    sources: Sequence[_Source],
    *,
    source_cache: _SourceCache,
    ingestion_cache: IngestionCache,
    workers: int,
    progress: Callable[[str], None] | None = None,
) -> WarmCacheSummary:
    """Fetch every source, then parse the uncached ones in ``workers`` processes.

    Fetching stays in this process and sequential: downloads are cheap next
    to parsing, and it keeps ``SourceDocumentCache`` -- including its failure
    log -- single-writer. Each cache entry is scheduled at most once: sources
    are keyed by their ingestion-cache entry (source bytes plus parser config),
    so two document ids with identical bytes are parsed once, and anything
    already cached is not scheduled at all.

    Failures do not stop the other documents. Once all have finished, any
    failure raises ``ParallelIngestionError`` naming every failed document, so
    the caller never reaches its loop without a document it needs.
    """
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if workers == 1:
        return WarmCacheSummary(parsed=(), already_cached=(), duplicate_content=())
    report = progress or (lambda _message: None)

    order = {source.id: position for position, source in enumerate(sources)}
    failures: dict[str, str] = {}
    scheduled: dict[Path, tuple[str, Path]] = {}
    already_cached: list[str] = []
    duplicates: list[str] = []
    for source in sources:
        try:
            cached = source_cache.fetch(source)
            path = Path(cached.path)  # type: ignore[attr-defined]
            entry = ingestion_cache.entry_dir(path)
        except Exception as exc:
            failures[source.id] = f"source: {exc}"
            continue
        if ingestion_cache.has_entry(entry):
            already_cached.append(source.id)
        elif entry in scheduled:
            duplicates.append(source.id)
        else:
            scheduled[entry] = (source.id, path)

    parsed: list[str] = []
    if scheduled:
        pool_size = min(workers, len(scheduled))
        report(
            f"pre-ingesting {len(scheduled)} uncached documents with "
            f"{pool_size} parser processes"
        )
        # Not a ``with`` block: its exit is ``shutdown(wait=True)`` without
        # cancelling, so Ctrl-C (or any error here) would sit and parse every
        # queued document first. On any exception the queue is cancelled and
        # control returns at once; parses already running finish in their
        # workers, and each publishes its entry whole or not at all.
        pool = ProcessPoolExecutor(
            max_workers=pool_size,
            mp_context=multiprocessing.get_context("spawn"),
        )
        futures: dict = {}
        try:
            futures = {
                pool.submit(_ingest_in_worker, ingestion_cache, str(path)): document_id
                for document_id, path in scheduled.values()
            }
            for done, future in enumerate(as_completed(futures), 1):
                document_id = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    # Includes a worker killed mid-parse (BrokenProcessPool),
                    # which fails every document still pending in that pool.
                    failures[document_id] = f"ingest: {exc}"
                    report(f"[{done}/{len(futures)}] {document_id}: failed")
                else:
                    parsed.append(document_id)
                    report(f"[{done}/{len(futures)}] {document_id}: parsed")
        except BaseException:
            # Cancel here, in this thread. ``cancel_futures`` alone is not
            # enough: the executor's manager thread applies it through a weak
            # reference to the executor, which is usually collected as this
            # exception unwinds before that thread wakes, and then nothing is
            # cancelled (measured: all 12 of 12 queued parses still ran). A
            # future cancelled here is skipped when the manager next feeds a
            # worker; only the ones already running or handed over continue.
            for future in futures:
                future.cancel()
            pool.shutdown(wait=False, cancel_futures=True)
            raise
        pool.shutdown(wait=True)

    if failures:
        raise ParallelIngestionError(
            dict(sorted(failures.items(), key=lambda item: order[item[0]]))
        )
    return WarmCacheSummary(
        parsed=tuple(sorted(parsed, key=order.__getitem__)),
        already_cached=tuple(already_cached),
        duplicate_content=tuple(duplicates),
    )


def _ingest_in_worker(ingestion_cache: IngestionCache, source: str) -> None:
    """Parse one source into the cache. Returns nothing: the caller reloads it.

    The cache arrives pickled -- its root and its parser, whose ``config`` is
    the recorded cache key -- so the worker writes exactly the entry the
    parent's loop will look up.
    """
    ingestion_cache.ingest(Path(source))
