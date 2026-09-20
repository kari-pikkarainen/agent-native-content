"""Agent-ready document enrichment and portable bundles."""

from contextbench.agentdoc.bundle import (
    AgentBundleError,
    agent_document_jsonld,
    create_agent_bundle,
    render_agent_html,
)
from contextbench.agentdoc.enrich import enrich_document, features_for_nodes
from contextbench.agentdoc.models import (
    AGENT_DOCUMENT_GENERATOR_VERSION,
    AGENT_DOCUMENT_SCHEMA_VERSION,
    AgentBundleManifest,
    AgentDocument,
    AgentEnrichmentConfig,
    AgentFeature,
    AgentFeatureKind,
)

__all__ = [
    "AGENT_DOCUMENT_GENERATOR_VERSION",
    "AGENT_DOCUMENT_SCHEMA_VERSION",
    "AgentBundleError",
    "AgentBundleManifest",
    "AgentDocument",
    "AgentEnrichmentConfig",
    "AgentFeature",
    "AgentFeatureKind",
    "agent_document_jsonld",
    "create_agent_bundle",
    "enrich_document",
    "features_for_nodes",
    "render_agent_html",
]
