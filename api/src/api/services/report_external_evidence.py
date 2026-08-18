"""Adapter registry and provider policy for governed external evidence expansion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from praviar_pipeline.certification_policy import is_certified_modality

from api.schemas.report_evidence_search import EvidenceSearchProviderCapabilityResponse
from api.services.licensed_family_overlay import (
    get_licensed_family_overlay_runtime_config,
)

ProviderStatus = Literal["active", "caution_only", "declared_only"]
ProviderExecutionMode = Literal[
    "placeholder_contract",
    "report_materialized",
    "bundled_dataset",
    "live_api",
]

_US_JURISDICTIONS = frozenset({"US", "USA"})
_EP_JURISDICTIONS = frozenset({"EP", "EPC", "EU"})
_UK_JURISDICTIONS = frozenset({"UK", "GB", "GBR"})


def _text(value: object) -> str:
    return str(value or "").strip()


@dataclass(frozen=True)
class ExternalEvidenceQueryContext:
    query: str
    trust_mode: str
    org_id: str | None
    modalities: tuple[str, ...]
    jurisdictions: tuple[str, ...]
    patent_identifier: str | None
    compound_name: str
    compound_smiles: str
    compound_cid: int | None

    @property
    def modalities_lower(self) -> set[str]:
        return {value.lower() for value in self.modalities if value}

    @property
    def jurisdictions_upper(self) -> set[str]:
        return {value.upper() for value in self.jurisdictions if value}

    @property
    def looks_us_scoped(self) -> bool:
        return not self.jurisdictions_upper or bool(self.jurisdictions_upper & _US_JURISDICTIONS)

    @property
    def certified_core_chemistry(self) -> bool:
        return not self.modalities_lower or all(
            modality in {"unknown", ""} or is_certified_modality(modality)
            for modality in self.modalities_lower
        )

    @property
    def routed_specialist_modality(self) -> bool:
        return not self.certified_core_chemistry

    @property
    def primary_modality_label(self) -> str:
        return next((value for value in self.modalities if value), "unknown")


@dataclass(frozen=True)
class ExternalEvidenceProviderSpec:
    provider_id: str
    name: str
    provider_class: str
    live_retrieval_supported: bool
    governance_note: str
    configured: bool = True
    execution_mode: ProviderExecutionMode = "live_api"
    modality_allowlist: frozenset[str] | None = None
    jurisdiction_allowlist: frozenset[str] | None = None
    org_allowlist: frozenset[str] | None = None
    requires_patent_identifier: bool = False
    declared_only: bool = False
    specialist_only: bool = False

    def provider_status(self, context: ExternalEvidenceQueryContext) -> ProviderStatus:
        if self.declared_only or not self.configured:
            return "declared_only"
        if self.org_allowlist is not None and (
            not context.org_id or context.org_id not in self.org_allowlist
        ):
            return "caution_only"
        if self.specialist_only and not context.routed_specialist_modality:
            return "caution_only"
        if self.modality_allowlist is not None and not (
            context.modalities_lower & self.modality_allowlist or not context.modalities_lower
        ):
            return "caution_only"
        if self.jurisdiction_allowlist is not None and not (
            context.jurisdictions_upper & self.jurisdiction_allowlist
            or not context.jurisdictions_upper
        ):
            return "caution_only"
        return "active"

    def live_retrieval_active(self, context: ExternalEvidenceQueryContext) -> bool:
        return self.live_retrieval_supported and self.provider_status(context) == "active"

    def execution_eligible(self, context: ExternalEvidenceQueryContext) -> bool:
        if not self.live_retrieval_active(context):
            return False
        return not (self.requires_patent_identifier and not context.patent_identifier)

    def build_governance_note(self, context: ExternalEvidenceQueryContext) -> str:
        status = self.provider_status(context)
        if status == "declared_only":
            return self.governance_note

        notes = [self.governance_note]
        if status == "caution_only":
            if self.org_allowlist is not None and (
                not context.org_id or context.org_id not in self.org_allowlist
            ):
                notes.append("Configured in this workspace, but not enabled for the current org.")
            elif self.specialist_only and not context.routed_specialist_modality:
                notes.append(
                    "Held back because this query does not require the specialist modality pack."
                )
            elif self.modality_allowlist is not None and not (
                context.modalities_lower & self.modality_allowlist or not context.modalities_lower
            ):
                notes.append(
                    f"Held back for modality {context.primary_modality_label}; "
                    "Praviar degrades upward in caution outside certified packs."
                )
            elif self.jurisdiction_allowlist is not None and not (
                context.jurisdictions_upper & self.jurisdiction_allowlist
                or not context.jurisdictions_upper
            ):
                notes.append(
                    "Held back because the current jurisdiction scope is outside this "
                    "provider's certified coverage."
                )

        if self.requires_patent_identifier:
            notes.append("Executes only when the query resolves to a patent identifier.")

        return " ".join(note for note in notes if note)


def build_external_query_context(
    *,
    query: str,
    trust_mode: str,
    org_id: str | None = None,
    modalities: list[str],
    jurisdictions: list[str],
    patent_identifier: str | None,
    compound_name: str,
    compound_smiles: str,
    compound_cid: int | None,
) -> ExternalEvidenceQueryContext:
    return ExternalEvidenceQueryContext(
        query=query,
        trust_mode=trust_mode,
        org_id=_text(org_id) or None,
        modalities=tuple(dict.fromkeys(value for value in modalities if _text(value))),
        jurisdictions=tuple(dict.fromkeys(value for value in jurisdictions if _text(value))),
        patent_identifier=_text(patent_identifier) or None,
        compound_name=_text(compound_name),
        compound_smiles=_text(compound_smiles),
        compound_cid=compound_cid,
    )


def external_provider_specs() -> list[ExternalEvidenceProviderSpec]:
    licensed_family_overlay = get_licensed_family_overlay_runtime_config()

    specs = [
        ExternalEvidenceProviderSpec(
            provider_id="pubchem",
            name="pubchem",
            provider_class="public_open",
            live_retrieval_supported=True,
            governance_note=(
                "Runs fresh PubChem compound resolution, synonym expansion, and patent-link lookup "
                "for chemistry-native evidence expansion."
            ),
            execution_mode="live_api",
            modality_allowlist=frozenset({"small_molecule", "unknown", "", "combination"}),
        ),
        ExternalEvidenceProviderSpec(
            provider_id="patentsview",
            name="patentsview",
            provider_class="public_open",
            live_retrieval_supported=True,
            governance_note=(
                "Runs bounded PatentsView keyword retrieval for US patent evidence expansion."
            ),
            execution_mode="live_api",
            modality_allowlist=frozenset(
                {
                    "small_molecule",
                    "markush_candidate",
                    "formulation",
                    "process_or_synthesis",
                    "combination",
                    "unknown",
                    "",
                }
            ),
            jurisdiction_allowlist=_US_JURISDICTIONS,
        ),
        ExternalEvidenceProviderSpec(
            provider_id="uspto_odp",
            name="uspto_odp",
            provider_class="public_open",
            live_retrieval_supported=True,
            governance_note=(
                "Runs bounded USPTO ODP application search for fresh US prosecution-side evidence."
            ),
            execution_mode="live_api",
            jurisdiction_allowlist=_US_JURISDICTIONS,
        ),
        ExternalEvidenceProviderSpec(
            provider_id="epo_ops",
            name="epo_ops",
            provider_class="public_open",
            live_retrieval_supported=True,
            governance_note=(
                "Runs bounded EPO OPS retrieval for EP family, register, and publication evidence."
            ),
            execution_mode="live_api",
            modality_allowlist=frozenset(
                {
                    "small_molecule",
                    "formulation",
                    "process_or_synthesis",
                    "markush_candidate",
                    "combination",
                    "unknown",
                    "",
                }
            ),
            jurisdiction_allowlist=frozenset({*_EP_JURISDICTIONS, *_UK_JURISDICTIONS}),
        ),
        ExternalEvidenceProviderSpec(
            provider_id="patentscope",
            name="patentscope",
            provider_class="public_open",
            live_retrieval_supported=True,
            governance_note=(
                "Runs bounded PatentScope retrieval for WO, EP, and UK publication monitoring."
            ),
            execution_mode="live_api",
            modality_allowlist=frozenset(
                {
                    "small_molecule",
                    "formulation",
                    "process_or_synthesis",
                    "markush_candidate",
                    "combination",
                    "unknown",
                    "",
                }
            ),
            jurisdiction_allowlist=frozenset({*_EP_JURISDICTIONS, *_UK_JURISDICTIONS}),
        ),
        ExternalEvidenceProviderSpec(
            provider_id="ptab",
            name="ptab",
            provider_class="public_open",
            live_retrieval_supported=True,
            governance_note=("Runs PTAB proceeding lookup for US patent challenges and outcomes."),
            execution_mode="live_api",
            jurisdiction_allowlist=_US_JURISDICTIONS,
            requires_patent_identifier=True,
        ),
        ExternalEvidenceProviderSpec(
            provider_id="orange_book",
            name="orange_book",
            provider_class="public_open",
            live_retrieval_supported=False,
            governance_note=(
                "Uses the FDA Orange Book dataset bundled with the workspace for "
                "regulatory linkage checks."
            ),
            execution_mode="bundled_dataset",
            modality_allowlist=frozenset(
                {"small_molecule", "formulation", "combination", "unknown", ""}
            ),
            jurisdiction_allowlist=_US_JURISDICTIONS,
            requires_patent_identifier=True,
        ),
        ExternalEvidenceProviderSpec(
            provider_id="purple_book",
            name="purple_book",
            provider_class="public_open",
            live_retrieval_supported=False,
            governance_note=(
                "Uses the FDA Purple Book dataset bundled with the workspace for "
                "biologic product checks."
            ),
            execution_mode="bundled_dataset",
            modality_allowlist=frozenset({"biologic_or_sequence"}),
            jurisdiction_allowlist=_US_JURISDICTIONS,
        ),
        ExternalEvidenceProviderSpec(
            provider_id="licensed_markush_overlay",
            name="licensed_markush_overlay",
            provider_class="licensed_overlay",
            live_retrieval_supported=False,
            governance_note=(
                "Vendor-agnostic adapter contract reserved for commercial Markush "
                "or specialist structure overlays. "
                "No licensed provider is configured in this workspace yet."
            ),
            configured=False,
            execution_mode="placeholder_contract",
            declared_only=True,
            modality_allowlist=frozenset(
                {
                    "markush_candidate",
                    "biologic_or_sequence",
                    "formulation",
                    "process_or_synthesis",
                }
            ),
        ),
    ]

    if licensed_family_overlay.configured:
        specs.append(
            ExternalEvidenceProviderSpec(
                provider_id="licensed_family_overlay",
                name="licensed_family_overlay",
                provider_class="licensed_overlay",
                live_retrieval_supported=True,
                governance_note=(
                    "Runs governed commercial family/legal-status retrieval through the configured "
                    f"{licensed_family_overlay.provider_name} adapter."
                ),
                configured=True,
                execution_mode="live_api",
                org_allowlist=licensed_family_overlay.allowed_org_ids,
            )
        )
    else:
        specs.append(
            ExternalEvidenceProviderSpec(
                provider_id="licensed_family_overlay",
                name="licensed_family_overlay",
                provider_class="licensed_overlay",
                live_retrieval_supported=False,
                governance_note=(
                    "Vendor-agnostic adapter contract reserved for commercial "
                    "family/legal-status overlays. "
                    "No licensed provider is configured in this workspace yet."
                ),
                configured=False,
                execution_mode="placeholder_contract",
                declared_only=True,
            )
        )

    return specs


def build_external_provider_capabilities(
    context: ExternalEvidenceQueryContext,
) -> list[EvidenceSearchProviderCapabilityResponse]:
    capabilities: list[EvidenceSearchProviderCapabilityResponse] = []
    for spec in external_provider_specs():
        allowlist = spec.modality_allowlist
        if (
            allowlist is not None
            and context.modalities_lower
            and not (
                context.modalities_lower & allowlist
                or spec.declared_only
                or spec.provider_class == "licensed_overlay"
            )
        ):
            continue
        jurisdictions = list(context.jurisdictions)
        if spec.jurisdiction_allowlist is not None:
            jurisdictions = (
                sorted(context.jurisdictions_upper & spec.jurisdiction_allowlist)
                if context.jurisdictions_upper
                else sorted(spec.jurisdiction_allowlist)
            )
        source_as_of = ""
        dataset_version = ""
        if spec.execution_mode == "live_api":
            source_as_of = "Provider live endpoint"
        elif spec.execution_mode == "bundled_dataset":
            source_as_of = "Workspace bundled dataset"
            dataset_version = "workspace_bundle"
        elif spec.execution_mode == "placeholder_contract":
            source_as_of = "Declared provider contract"
        capabilities.append(
            EvidenceSearchProviderCapabilityResponse(
                provider_id=spec.provider_id,
                provider_name=spec.name,
                provider_class=spec.provider_class,
                provider_status=spec.provider_status(context),
                live_retrieval_supported=spec.live_retrieval_active(context),
                configured=spec.configured,
                configured_for_org=spec.org_allowlist is None
                or bool(context.org_id and context.org_id in spec.org_allowlist),
                materialized_in_report=False,
                execution_mode=spec.execution_mode,
                modality_coverage=list(context.modalities)
                if not allowlist
                else sorted(value for value in context.modalities if value.lower() in allowlist)
                or sorted(allowlist),
                jurisdiction_coverage=jurisdictions,
                governance_note=spec.build_governance_note(context),
                source_as_of=source_as_of,
                dataset_version=dataset_version,
            )
        )
    return capabilities


def active_external_provider_specs(
    context: ExternalEvidenceQueryContext,
) -> list[ExternalEvidenceProviderSpec]:
    return [spec for spec in external_provider_specs() if spec.execution_eligible(context)]


def build_external_caution_notes(context: ExternalEvidenceQueryContext) -> list[str]:
    notes: list[str] = []
    if context.routed_specialist_modality:
        notes.append(
            "External expansion is running in supervised screening mode for modality "
            f"{context.primary_modality_label}; specialist validation remains incomplete "
            "and unsupported providers stay in caution-only state."
        )
    if context.jurisdictions_upper and not context.looks_us_scoped:
        notes.append(
            "Current jurisdiction scope is non-US, so US-only sources remain declared "
            "or caution-only instead of executing."
        )
    return notes
