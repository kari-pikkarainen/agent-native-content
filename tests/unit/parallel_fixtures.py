"""Picklable parser and source fixtures for parallel ingestion tests.

Spawned workers import this module by name (``spawn`` sends the parent's
``sys.path``), so everything a worker touches lives at module level here.
"""

import hashlib
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.base import Size
from docling_core.types.doc.labels import DocItemLabel
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def write_pdf(path: Path, lines: list[str]) -> Path:
    """A small real PDF: one page, one line of text per entry."""
    pdf = canvas.Canvas(str(path), pagesize=letter, invariant=1, pageCompression=0)
    y = 720
    for line in lines:
        pdf.drawString(72, y, line)
        y -= 18
    pdf.showPage()
    pdf.save()
    return path


class RecordingParser:
    """Deterministic stand-in for Docling that records every parse.

    Each parse leaves a marker file in ``log_dir`` naming the source and the
    process that parsed it, so parses can be counted across processes. A
    source whose bytes contain ``FAIL`` raises; one containing ``CRASH`` kills
    its process outright, as the OOM killer would.
    """

    name = "recording-parser"

    def __init__(self, log_dir: Path, events: list | None = None) -> None:
        self.log_dir = log_dir
        self.events = events

    def __getstate__(self) -> dict[str, Any]:
        # The in-process event list does not cross a process boundary.
        return {"log_dir": self.log_dir, "events": None}

    @property
    def version(self) -> str:
        return "1"

    @property
    def core_version(self) -> str:
        return "1"

    @property
    def config(self) -> dict[str, Any]:
        return {"fixture": True}

    def parse(self, source: Path) -> DoclingDocument:
        data = source.read_bytes()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        (self.log_dir / f"{source.name}.{os.getpid()}.{uuid.uuid4().hex}").touch()
        if self.events is not None:
            self.events.append(("parse", source.name))
        if b"CRASH" in data:
            os._exit(3)
        if b"FAIL" in data:
            raise RuntimeError(f"fixture parse failure for {source.name}")
        document = DoclingDocument(name=source.stem)
        document.add_page(1, Size(width=612, height=792))
        document.add_text(
            label=DocItemLabel.TEXT,
            text=hashlib.sha256(data).hexdigest(),
        )
        return document

    def parses(self) -> list[tuple[str, int]]:
        """(source name, pid) for every parse so far, in any process."""
        if not self.log_dir.exists():
            return []
        result = []
        for marker in self.log_dir.iterdir():
            name, pid, _unique = marker.name.rsplit(".", 2)
            result.append((name, int(pid)))
        return sorted(result)


class SlowParser(RecordingParser):
    """A parser that takes ``delay`` seconds, so work can still be queued."""

    def __init__(self, log_dir: Path, delay: float) -> None:
        super().__init__(log_dir)
        self.delay = delay

    def __getstate__(self) -> dict[str, Any]:
        return {**super().__getstate__(), "delay": self.delay}

    def parse(self, source: Path) -> DoclingDocument:
        time.sleep(self.delay)
        return super().parse(source)


class RacingParser(RecordingParser):
    """While this parse runs, a competing writer publishes the same entry."""

    def __init__(self, log_dir: Path, root: Path) -> None:
        super().__init__(log_dir)
        self.root = root

    def parse(self, source: Path) -> DoclingDocument:
        from agent_native_content.ingest import IngestionCache

        IngestionCache(self.root, RecordingParser(self.log_dir)).ingest(source)
        return super().parse(source)


def ingest_then_die_before_publish(root: str, log_dir: str, source: str) -> None:
    """Run in a spawned process: parse, write document.json, then get killed.

    The process exits hard where ``metadata.json`` would be written -- after
    ``document.json`` is on disk, before the entry is published -- as a
    SIGKILL or an out-of-memory kill between the two writes would.
    """
    import agent_native_content.ingest.cache as cache_module

    def die(_path: Path, _value: dict[str, Any]) -> None:
        os._exit(9)

    cache_module._write_json_atomic = die
    cache_module.IngestionCache(Path(root), RecordingParser(Path(log_dir))).ingest(
        Path(source)
    )


@dataclass(frozen=True)
class FixtureSource:
    id: str
    url: str


@dataclass(frozen=True)
class FixtureCached:
    path: Path


class FixtureSourceCache:
    """Stubbed fetch: maps document ids to local fixture PDFs, no network."""

    def __init__(
        self,
        paths: dict[str, Path],
        *,
        fail: frozenset[str] = frozenset(),
        events: list | None = None,
    ) -> None:
        self.paths = paths
        self.fail = fail
        self.events = events
        self.fetched: list[str] = []

    def fetch(self, source: FixtureSource) -> FixtureCached:
        self.fetched.append(source.id)
        if self.events is not None:
            self.events.append(("fetch", source.id))
        if source.id in self.fail:
            raise RuntimeError(f"fixture download failure for {source.id}")
        return FixtureCached(self.paths[source.id])
