"""Portable JSON-LD and semantic HTML agent-document bundles."""

import hashlib
import html
import json
import shutil
import tempfile
from pathlib import Path

from contextbench.agentdoc.enrich import enrich_document
from contextbench.agentdoc.models import (
    AgentBundleManifest,
    AgentDocument,
    AgentEnrichmentConfig,
    AgentFeatureKind,
)
from contextbench.ir.models import IRDocument, IRNode, IRNodeKind


class AgentBundleError(RuntimeError):
    """Raised when an agent-document bundle cannot be safely created."""


def create_agent_bundle(
    document: IRDocument,
    output_dir: Path,
    *,
    config: AgentEnrichmentConfig | None = None,
    source_path: Path | None = None,
    include_source: bool = False,
) -> AgentBundleManifest:
    """Atomically create a self-describing agent-document directory."""
    if output_dir.exists():
        raise AgentBundleError(f"agent bundle already exists: {output_dir}")
    if include_source and source_path is None:
        raise AgentBundleError("include_source requires source_path")
    if source_path is not None:
        source_hash = _file_hash(source_path)
        if source_hash != document.source_sha256:
            raise AgentBundleError("source file hash does not match the IR document")

    enrichment = enrich_document(document, config=config)
    content_bytes = _canonical_json(document.model_dump(mode="json"))
    jsonld_bytes = _canonical_json(agent_document_jsonld(enrichment))
    html_bytes = render_agent_html(document, enrichment).encode("utf-8")
    source_file = (
        f"source{source_path.suffix.lower()}"
        if include_source and source_path
        else None
    )
    manifest = AgentBundleManifest(
        document_id=document.id,
        source_uri=document.source_uri,
        source_sha256=document.source_sha256,
        ir_sha256=hashlib.sha256(content_bytes).hexdigest(),
        enrichments_sha256=hashlib.sha256(jsonld_bytes).hexdigest(),
        html_sha256=hashlib.sha256(html_bytes).hexdigest(),
        source_file=source_file,
        generator=enrichment.generator,
        generator_version=enrichment.generator_version,
        config=enrichment.config,
    )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".agentdoc-", dir=output_dir.parent))
    try:
        (staging / "content.json").write_bytes(content_bytes)
        (staging / "enrichments.jsonld").write_bytes(jsonld_bytes)
        (staging / "agent.html").write_bytes(html_bytes)
        (staging / "manifest.json").write_bytes(
            _canonical_json(manifest.model_dump(mode="json"))
        )
        if source_file is not None and source_path is not None:
            shutil.copyfile(source_path, staging / source_file)
        staging.replace(output_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return manifest


def agent_document_jsonld(enrichment: AgentDocument) -> dict[str, object]:
    """Return a standards-compatible JSON-LD projection of enrichment."""
    return {
        "@context": {
            "cb": "urn:contextbench:agent-document:",
            "document": {"@id": "cb:document", "@type": "@id"},
            "features": {"@id": "cb:features", "@container": "@set"},
            "sourceNodes": {"@id": "cb:sourceNodes", "@container": "@set"},
        },
        "@id": enrichment.source_uri,
        "@type": "cb:AgentDocument",
        "cb:schemaVersion": enrichment.schema_version,
        "cb:generator": enrichment.generator,
        "cb:generatorVersion": enrichment.generator_version,
        "cb:documentId": enrichment.document_id,
        "cb:sourceSha256": enrichment.source_sha256,
        "features": [
            {
                "@id": f"urn:contextbench:{feature.id}",
                "@type": f"cb:{_feature_type(feature.kind)}",
                "cb:text": feature.text,
                "cb:importance": feature.importance,
                "cb:headingPath": list(feature.heading_path),
                "cb:pageStart": feature.page_start,
                "cb:pageEnd": feature.page_end,
                "sourceNodes": list(feature.source_node_ids),
                "cb:sourceItems": list(feature.source_item_ids),
                "cb:attributes": feature.attributes,
            }
            for feature in enrichment.features
        ],
    }


def render_agent_html(document: IRDocument, enrichment: AgentDocument) -> str:
    """Render source content as semantic HTML with embedded JSON-LD features."""
    jsonld = json.dumps(
        agent_document_jsonld(enrichment),
        ensure_ascii=False,
        sort_keys=True,
    ).replace("</", "<\\/")
    outline = [
        node
        for node in document.nodes
        if node.content_layer == "body"
        and node.kind in {IRNodeKind.TITLE, IRNodeKind.HEADING}
        and node.text.strip()
    ]
    navigation = "\n".join(
        f'<li><a href="#{html.escape(node.id)}">{html.escape(node.text)}</a></li>'
        for node in outline
    )
    content = "\n".join(
        _render_node(node)
        for node in sorted(document.nodes, key=lambda value: value.ordinal)
        if node.content_layer == "body" and node.text.strip()
    )
    title = outline[0].text if outline else document.source_uri
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">\n"
        f"<title>{html.escape(title)}</title>\n"
        f'<meta name="source-sha256" content="{document.source_sha256}">\n'
        f'<script type="application/ld+json">{jsonld}</script>\n'
        "</head><body>\n"
        f'<nav aria-label="Document outline"><ol>{navigation}</ol></nav>\n'
        f"<article>{content}</article>\n"
        "</body></html>\n"
    )


def _render_node(node: IRNode) -> str:
    identifier = html.escape(node.id)
    text = html.escape(node.text)
    provenance = (
        f' data-page-start="{node.page_start}" data-page-end="{node.page_end}"'
        if node.page_start is not None
        else ""
    )
    if node.kind == IRNodeKind.TITLE:
        return f'<h1 id="{identifier}"{provenance}>{text}</h1>'
    if node.kind == IRNodeKind.HEADING:
        level = min(max(len(node.heading_path) + 1, 2), 6)
        return f'<h{level} id="{identifier}"{provenance}>{text}</h{level}>'
    if node.kind == IRNodeKind.LIST:
        return ""
    if node.kind == IRNodeKind.LIST_ITEM:
        return f'<p id="{identifier}" role="listitem"{provenance}>{text}</p>'
    if node.kind == IRNodeKind.TABLE and node.table is not None:
        return _render_table(node)
    if node.kind == IRNodeKind.CODE:
        return f'<pre id="{identifier}"{provenance}><code>{text}</code></pre>'
    tag = "figcaption" if node.kind == IRNodeKind.CAPTION else "p"
    return f'<{tag} id="{identifier}"{provenance}>{text}</{tag}>'


def _render_table(node: IRNode) -> str:
    assert node.table is not None
    caption = (
        f"<caption>{html.escape(node.table.caption)}</caption>"
        if node.table.caption
        else ""
    )
    rows = []
    for row_index, row in enumerate(node.table.rows):
        cell_tag = "th" if row_index == 0 and node.table.column_headers else "td"
        cells = "".join(
            f"<{cell_tag}>{html.escape(value)}</{cell_tag}>" for value in row
        )
        rows.append(f"<tr>{cells}</tr>")
    provenance = (
        f' data-page-start="{node.page_start}" data-page-end="{node.page_end}"'
        if node.page_start is not None
        else ""
    )
    return (
        f'<table id="{html.escape(node.id)}"{provenance}>{caption}'
        f"{''.join(rows)}</table>"
    )


def _feature_type(kind: AgentFeatureKind) -> str:
    return "".join(part.title() for part in kind.value.split("_"))


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
