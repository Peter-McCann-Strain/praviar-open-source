"""Source capability registry for Step 2 search planning and coverage gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from praviar_pipeline.models.report import SourceHealthEntry, SourceStatus

NON_ENGLISH_JURISDICTIONS = frozenset({"JP", "KR", "CN", "IN", "DE", "FR"})
DEFAULT_REQUESTED_JURISDICTIONS = frozenset({"US", "WO", "EP", "JP", "KR", "CN", "IN", "CA", "AU"})

SourceRole = Literal[
    "structure_identity",
    "genus_expansion",
    "sequence_identity",
    "bibliographic_legal",
    "expanded",
    "global",
]
SourceCriticality = Literal["core", "optional"]


@dataclass(frozen=True, slots=True)
class SourceCapability:
    """Declarative source capability used before any network/client work."""

    name: str
    roles: tuple[SourceRole, ...]
    enabled_attr: str | None = None
    required_settings: tuple[str, ...] = ()
    jurisdictions: frozenset[str] | None = None
    requires_non_english: bool = False
    criticality: SourceCriticality = "optional"


SOURCE_CAPABILITIES: dict[str, SourceCapability] = {
    "pubchem_sdq": SourceCapability(
        name="pubchem_sdq",
        roles=("structure_identity",),
        enabled_attr="search_enable_pubchem",
        criticality="core",
    ),
    "surechembl": SourceCapability(
        name="surechembl",
        roles=("structure_identity",),
        enabled_attr="search_enable_surechembl",
    ),
    "bigquery": SourceCapability(
        name="bigquery",
        roles=("bibliographic_legal",),
        enabled_attr="search_enable_bigquery",
        criticality="core",
    ),
    "bigquery_annotations": SourceCapability(
        name="bigquery_annotations",
        roles=("structure_identity", "bibliographic_legal"),
        enabled_attr="search_enable_bigquery",
    ),
    "patcid": SourceCapability(
        name="patcid",
        roles=("structure_identity",),
        enabled_attr="search_enable_patcid",
    ),
    "pubchem_similar": SourceCapability(
        name="pubchem_similar",
        roles=("structure_identity",),
        enabled_attr="search_enable_pubchem",
    ),
    "pubchem_genus": SourceCapability(
        name="pubchem_genus",
        roles=("genus_expansion", "structure_identity"),
        enabled_attr="search_enable_pubchem_genus",
        criticality="core",
    ),
    "cpc_search": SourceCapability(
        name="cpc_search",
        roles=("expanded", "bibliographic_legal"),
        enabled_attr="search_enable_bigquery",
    ),
    "assignee_search": SourceCapability(
        name="assignee_search",
        roles=("expanded", "bibliographic_legal"),
        enabled_attr="search_enable_bigquery",
    ),
    "epo_search": SourceCapability(
        name="epo_search",
        roles=("expanded", "bibliographic_legal"),
        required_settings=("ops_consumer_key", "ops_consumer_secret"),
    ),
    "kipris": SourceCapability(
        name="kipris",
        roles=("global", "bibliographic_legal"),
        required_settings=("kipris_api_key",),
        jurisdictions=frozenset({"KR"}),
    ),
    "patentscope": SourceCapability(
        name="patentscope",
        roles=("global", "bibliographic_legal"),
        required_settings=("patentscope_username", "patentscope_password"),
        jurisdictions=frozenset({"WO"}),
    ),
    "bigquery_translated": SourceCapability(
        name="bigquery_translated",
        roles=("bibliographic_legal",),
        enabled_attr="search_enable_bigquery",
        requires_non_english=True,
    ),
    "patentsview": SourceCapability(
        name="patentsview",
        roles=("bibliographic_legal",),
        required_settings=("patentsview_api_key",),
        jurisdictions=frozenset({"US"}),
    ),
    "ncbi_patent_sequence": SourceCapability(
        name="ncbi_patent_sequence",
        roles=("sequence_identity", "bibliographic_legal", "global"),
        enabled_attr="search_enable_ncbi_patent_sequence",
        jurisdictions=frozenset({"US", "EP", "JP"}),
        criticality="core",
    ),
}

STRUCTURE_IDENTITY_SOURCES = frozenset(
    name
    for name, capability in SOURCE_CAPABILITIES.items()
    if "structure_identity" in capability.roles
)
BIBLIOGRAPHIC_LEGAL_SOURCES = frozenset(
    name
    for name, capability in SOURCE_CAPABILITIES.items()
    if "bibliographic_legal" in capability.roles
)
SEQUENCE_IDENTITY_SOURCES = frozenset(
    name
    for name, capability in SOURCE_CAPABILITIES.items()
    if "sequence_identity" in capability.roles
)
GENUS_EXPANSION_SOURCES = frozenset(
    name
    for name, capability in SOURCE_CAPABILITIES.items()
    if "genus_expansion" in capability.roles
)


def allowed_jurisdictions(settings: Any) -> set[str]:
    configured = getattr(settings, "search_allowed_jurisdictions", None)
    if configured is None:
        return set(DEFAULT_REQUESTED_JURISDICTIONS)
    return set(configured or [])


def source_is_requested(capability: SourceCapability, settings: Any) -> bool:
    """Return whether the source is relevant for the requested jurisdictions."""
    requested = allowed_jurisdictions(settings)
    if capability.jurisdictions is not None and not capability.jurisdictions.intersection(
        requested
    ):
        return False
    return not (
        capability.requires_non_english and not NON_ENGLISH_JURISDICTIONS.intersection(requested)
    )


def missing_required_settings(capability: SourceCapability, settings: Any) -> list[str]:
    missing: list[str] = []
    for field_name in capability.required_settings:
        if not getattr(settings, field_name, ""):
            missing.append(field_name)
    return missing


def source_is_enabled(capability: SourceCapability, settings: Any) -> bool:
    if capability.enabled_attr is None:
        return True
    return bool(getattr(settings, capability.enabled_attr, False))


def source_not_configured_entry(
    capability: SourceCapability,
    *,
    missing_fields: list[str],
) -> SourceHealthEntry:
    field_text = ", ".join(missing_fields)
    return SourceHealthEntry(
        source=capability.name,
        status=SourceStatus.NOT_CONFIGURED,
        error_message=f"Missing required setting(s): {field_text}",
    )


def source_skipped_entry(capability: SourceCapability, *, reason: str) -> SourceHealthEntry:
    return SourceHealthEntry(
        source=capability.name,
        status=SourceStatus.SKIPPED,
        error_message=reason,
    )
