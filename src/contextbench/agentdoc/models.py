"""Schemas for deterministic, source-grounded agent-document enrichment."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AGENT_DOCUMENT_SCHEMA_VERSION = "1.0.0"
AGENT_DOCUMENT_GENERATOR_VERSION = "0.1.0"


class AgentFeatureKind(StrEnum):
    """Bounded vocabulary for query-independent document affordances."""

    OUTLINE = "outline"
    SECTION_SUMMARY = "section_summary"
    KEY_FACT = "key_fact"
    DEFINITION = "definition"
    ENTITY = "entity"
    RELATIONSHIP = "relationship"
    TABLE_SCHEMA = "table_schema"
    TABLE_ROW = "table_row"
    QUANTITY = "quantity"


class AgentEnrichmentConfig(BaseModel):
    """Deterministic extraction controls captured in every bundle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary_sentences: int = Field(default=2, ge=1, le=10)
    max_key_facts: int = Field(default=2000, ge=1)
    include_numeric_facts: bool = True
    include_normative_facts: bool = True
    include_definitions: bool = True
    include_explicit_aliases: bool = True
    include_table_schemas: bool = True
    include_table_rows: bool = True
    include_relationships: bool = True
    include_quantities: bool = True
    include_explicit_references: bool = True
    max_table_rows: int = Field(default=2000, ge=1)


class AgentFeature(BaseModel):
    """One source-traceable affordance intended for machine consumption."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    kind: AgentFeatureKind
    document_id: str
    text: str
    importance: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    heading_path: tuple[str, ...] = ()
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    source_node_ids: tuple[str, ...]
    source_item_ids: tuple[str, ...]
    attributes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def provenance_is_complete(self) -> "AgentFeature":
        if not self.text.strip():
            raise ValueError("agent features require non-empty text")
        if not self.source_node_ids or not self.source_item_ids:
            raise ValueError("agent features require source provenance")
        if (self.page_start is None) != (self.page_end is None):
            raise ValueError("page_start and page_end must both be set or null")
        if self.page_start is not None and self.page_start > self.page_end:
            raise ValueError("page_start must not exceed page_end")
        return self


class AgentDocument(BaseModel):
    """Question-independent enrichment derived from one immutable IR document."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = AGENT_DOCUMENT_SCHEMA_VERSION
    generator: str = "contextbench-deterministic-enrichment"
    generator_version: str = AGENT_DOCUMENT_GENERATOR_VERSION
    document_id: str
    source_uri: str
    source_sha256: str
    ir_schema_version: str
    config: AgentEnrichmentConfig
    features: tuple[AgentFeature, ...]

    @model_validator(mode="after")
    def identities_are_unique_and_local(self) -> "AgentDocument":
        ids = [feature.id for feature in self.features]
        if len(ids) != len(set(ids)):
            raise ValueError("agent feature IDs must be unique")
        if any(feature.document_id != self.document_id for feature in self.features):
            raise ValueError("agent features must belong to their document")
        return self


class AgentBundleManifest(BaseModel):
    """Hashes binding a portable bundle to its source and derived files."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = AGENT_DOCUMENT_SCHEMA_VERSION
    document_id: str
    source_uri: str
    source_sha256: str
    ir_sha256: str
    enrichments_sha256: str
    html_sha256: str
    source_file: str | None = None
    generator: str
    generator_version: str
    config: AgentEnrichmentConfig
