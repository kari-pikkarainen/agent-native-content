"""Agent-ready document enrichment and portable bundles."""

from agent_native_content.agentdoc.bundle import (
    AgentBundleError,
    agent_document_jsonld,
    create_agent_bundle,
    render_agent_html,
)
from agent_native_content.agentdoc.enrich import enrich_document, features_for_nodes
from agent_native_content.agentdoc.models import (
    AGENT_DOCUMENT_GENERATOR_VERSION,
    AGENT_DOCUMENT_SCHEMA_VERSION,
    AgentBundleManifest,
    AgentDocument,
    AgentEnrichmentConfig,
    AgentFeature,
    AgentFeatureKind,
)
from agent_native_content.agentdoc.select import (
    SelectedAgentFeature,
    compact_feature_text,
    feature_type_counts,
    select_agent_features,
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
    "SelectedAgentFeature",
    "agent_document_jsonld",
    "create_agent_bundle",
    "compact_feature_text",
    "enrich_document",
    "features_for_nodes",
    "feature_type_counts",
    "render_agent_html",
    "select_agent_features",
]
