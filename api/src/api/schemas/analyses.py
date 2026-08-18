"""Request/response schemas for analyses."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any, Literal

from praviar_pipeline.models.accused_acts import AccusedActRecord
from praviar_pipeline.models.markush_evidence import MarkushEvidenceReceipt
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from api.schemas.review_status import ReviewStatusValue

TrustMode = Literal["explorer", "counsel", "monitor"]
DevelopmentStage = Literal[
    "discovery",
    "lead_optimization",
    "preclinical",
    "clinical",
    "commercial",
]
JurisdictionBundle = Literal["us_europe", "europe_uk", "major_markets", "custom"]
AssetTypeHint = Literal[
    "small_molecule",
    "markush_candidate",
    "biologic_or_sequence",
    "formulation",
    "process_or_synthesis",
    "combination",
    "unknown",
]
IntendedAction = Literal[
    "manufacture_import",
    "commercial_launch",
    "formulation_review",
    "method_of_use_review",
    "design_around",
    "diligence_screen",
    "monitor_continuations",
]
SubmittedInputType = Literal["name", "smiles", "cas", "inchi", "inchikey"]

_ECMASCRIPT_TRIM_CHARACTERS = (
    "\u0009\u000a\u000b\u000c\u000d\u0020\u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000\ufeff"
)
_ECMASCRIPT_WHITESPACE_PATTERN = (
    r"[\u0009-\u000d\u0020\u00a0\u1680\u2000-\u200a"
    r"\u2028\u2029\u202f\u205f\u3000\ufeff]"
)
_CAS_INPUT_PATTERN = re.compile(
    rf"^(?:CAS(?:{_ECMASCRIPT_WHITESPACE_PATTERN}*(?:RN|No\.?|#|:))?"
    rf"{_ECMASCRIPT_WHITESPACE_PATTERN}*)?[0-9]{{2,7}}-[0-9]{{2}}-[0-9]$",
    re.ASCII | re.IGNORECASE,
)
_INCHIKEY_INPUT_PATTERN = re.compile(
    r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$",
    re.ASCII | re.IGNORECASE,
)
_SMILES_ORGANIC_ATOMS = frozenset("BCNOPSFI")
_SMILES_AROMATIC_ATOMS = frozenset("bcnops")
_SMILES_STRUCTURE_MARKERS = frozenset("-=#$:/\\.()")


def normalize_compound_identifier(value: str) -> str:
    """Apply the exact boundary trimming used by ECMAScript String.trim()."""
    return value.strip(_ECMASCRIPT_TRIM_CHARACTERS)


def _is_likely_smiles(value: str) -> bool:
    """Mirror the launch UI's conservative token-by-token SMILES classifier."""
    if not value or any(character in _ECMASCRIPT_TRIM_CHARACTERS for character in value):
        return False

    atom_count = 0
    has_structure_marker = False
    index = 0
    while index < len(value):
        character = value[index]

        if character == "[":
            close_index = value.find("]", index + 1)
            if close_index == -1:
                return False
            atom_count += 1
            has_structure_marker = True
            index = close_index + 1
            continue

        token = value[index : index + 2]
        if token in {"Cl", "Br"}:
            atom_count += 1
            index += 2
            continue

        if character in _SMILES_ORGANIC_ATOMS or character in _SMILES_AROMATIC_ATOMS:
            atom_count += 1
            index += 1
            continue

        if character in _SMILES_STRUCTURE_MARKERS:
            has_structure_marker = True
            index += 1
            continue

        if character == "%":
            ring_id = value[index + 1 : index + 3]
            if len(ring_id) != 2 or any(digit not in "0123456789" for digit in ring_id):
                return False
            has_structure_marker = True
            index += 3
            continue

        if character in "123456789":
            has_structure_marker = True
            index += 1
            continue

        if character == "*":
            atom_count += 1
            has_structure_marker = True
            index += 1
            continue

        return False

    return atom_count >= 2 or (atom_count == 1 and has_structure_marker)


def detect_submitted_input_type(value: str) -> SubmittedInputType:
    """Classify submitted syntax without asserting any resolved identity."""
    normalized = normalize_compound_identifier(value)
    if _CAS_INPUT_PATTERN.fullmatch(normalized):
        return "cas"
    if normalized.startswith("InChI="):
        return "inchi"
    if _INCHIKEY_INPUT_PATTERN.fullmatch(normalized):
        return "inchikey"
    if _is_likely_smiles(normalized):
        return "smiles"
    return "name"


_TRUST_MODE_DEFAULTS: dict[str, dict[str, object]] = {
    "explorer": {
        "clearance_threshold_profile": "screening",
        "source_authority_policy": "official_plus_licensed",
        "required_record_components": [],
        "search_loop_enabled": False,
    },
    "counsel": {
        "clearance_threshold_profile": "world_class_us_ep",
        "source_authority_policy": "official_plus_licensed",
        "required_record_components": [
            "claims_text",
            "claim_level_analysis",
            "authoritative_records",
            "family_context",
            "verification",
        ],
        "search_loop_enabled": True,
        "citation_traversal_enabled": True,
        "thinking_effort_analysis": "high",
        "thinking_effort_triage": "high",
        "thinking_effort_report": "high",
    },
    "monitor": {
        "clearance_threshold_profile": "screening",
        "source_authority_policy": "official_plus_licensed",
        "required_record_components": [
            "claims_text",
            "family_context",
        ],
        "search_loop_enabled": True,
        "citation_traversal_enabled": True,
    },
}

_JURISDICTION_BUNDLE_MAP: dict[str, list[str]] = {
    "us_europe": ["US", "EP"],
    "europe_uk": ["EP", "UK"],
    "major_markets": ["US", "EP", "UK", "IN", "JP", "CN"],
    "custom": [],
}

_ASSET_HINT_TO_MATTER_TYPE: dict[str, str] = {
    "small_molecule": "small_molecule",
    "markush_candidate": "markush_candidate",
    "biologic_or_sequence": "biologic",
    "formulation": "formulation",
    "process_or_synthesis": "process",
    "combination": "combination",
    "unknown": "unknown",
}

_PRODUCT_CONTEXT_TEXT_FIELDS = (
    "product_name",
    "dosage_form",
    "route_of_administration",
    "strength",
    "release_profile",
    "salt_polymorph_form",
    "indication",
    "patient_population",
    "reference_product",
    "manufacturing_route",
    "commercial_action",
    "decision_deadline",
    "owned_or_licensed_ip",
)

_PRODUCT_CONTEXT_LIST_FIELDS = (
    "key_excipients",
    "combination_assets",
    "commercial_territories",
    "known_patents_or_assignees",
)


class AnalysisConfigSchema(BaseModel):
    """Pipeline configuration for a new analysis."""

    model_config = ConfigDict(extra="forbid")

    # Search depth
    search_max_ranked_results: int = Field(default=200, ge=50, le=500)
    search_tanimoto_threshold: float = Field(default=0.55, gt=0.0, le=1.0)
    include_expired: bool = True
    search_jurisdictions: list[str] = Field(
        default_factory=lambda: ["US", "EP", "WO"], max_length=20
    )

    # Sources
    enable_pubchem: bool = True
    enable_bigquery: bool = True
    enable_surechembl: bool = True
    enable_patcid: bool = True

    # Analysis scope and cost controls
    max_analysis_patents: int = Field(default=20, ge=5, le=30)
    max_doe_candidates: int = Field(default=15, ge=5, le=20)
    triage_batch_size: int = Field(default=10, ge=5, le=15)

    # Citation & expired patent settings
    citation_traversal_enabled: bool = False
    citation_max_depth: int = Field(default=1, ge=1, le=3)
    search_expired_grace_years: int = Field(default=3, ge=1, le=10)

    # LLM thinking budget and effort
    analysis_thinking_budget_tokens: int = Field(default=12000, ge=4000, le=32000)
    thinking_effort_analysis: str = "high"
    thinking_effort_triage: str = "medium"
    thinking_effort_report: str = "high"

    # Execution flags
    search_loop_enabled: bool = False
    hitl_enabled: bool = False
    hitl_checkpoints: list[str] = Field(default_factory=list, max_length=20)
    hitl_auto_skip_minutes: int = Field(default=60, ge=1, le=120)

    # Clearance policy
    matter_type: str = "small_molecule"
    jurisdiction_policy: str = "us_ep_core"
    clearance_threshold_profile: str = "world_class_us_ep"
    max_run_duration_hours: int = Field(default=24, ge=1, le=72)
    source_authority_policy: str = "official_plus_licensed"
    required_record_components: list[str] = Field(default_factory=list, max_length=20)
    require_verified_manual_markush: Literal[True] = True
    markush_evidence_max_age_days: Literal[35] = 35
    markush_evidence_receipt: MarkushEvidenceReceipt | None = None


class ProductContext(BaseModel):
    """Product, use, process, and known-art context for a launch request."""

    model_config = ConfigDict(extra="forbid")

    product_name: str | None = Field(default=None, max_length=240)
    dosage_form: str | None = Field(default=None, max_length=240)
    route_of_administration: str | None = Field(default=None, max_length=240)
    strength: str | None = Field(default=None, max_length=240)
    release_profile: str | None = Field(default=None, max_length=240)
    salt_polymorph_form: str | None = Field(default=None, max_length=240)
    key_excipients: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(
        default_factory=list, max_length=30
    )
    indication: str | None = Field(default=None, max_length=500)
    patient_population: str | None = Field(default=None, max_length=500)
    combination_assets: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(
        default_factory=list, max_length=30
    )
    reference_product: str | None = Field(default=None, max_length=240)
    manufacturing_route: str | None = Field(default=None, max_length=1000)
    commercial_action: str | None = Field(default=None, max_length=500)
    decision_deadline: str | None = Field(default=None, max_length=120)
    commercial_territories: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list, max_length=30
    )
    accused_acts: list[AccusedActRecord] = Field(
        default_factory=list,
        max_length=50,
        description=(
            "Structured act/actor/place/time/status/purpose facts. Free-form "
            "commercial_action text is reviewer context only."
        ),
    )
    known_patents_or_assignees: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(
        default_factory=list, max_length=50
    )
    owned_or_licensed_ip: str | None = Field(default=None, max_length=1000)

    @field_validator(*_PRODUCT_CONTEXT_TEXT_FIELDS, mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Expected a text value")
        normalized = value.strip()
        return normalized or None

    @field_validator(*_PRODUCT_CONTEXT_LIST_FIELDS, mode="before")
    @classmethod
    def normalize_text_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw_items = value.replace("\n", ",").split(",")
        elif isinstance(value, list):
            raw_items = value
        else:
            raise ValueError("Expected a list of text values")

        normalized_items: list[str] = []
        for raw in raw_items:
            if not isinstance(raw, str):
                raise ValueError("Expected a list of text values")
            item = raw.strip()
            if item:
                normalized_items.append(item)
        return normalized_items

    def normalized_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json", exclude_none=True)
        return {
            key: value
            for key, value in payload.items()
            if not (isinstance(value, list) and len(value) == 0)
        }


class CreateAnalysisRequest(BaseModel):
    """Start a new FTO analysis."""

    compound_input: str = Field(..., min_length=1, max_length=5000)
    input_type: SubmittedInputType
    submitted_identity_confirmed: Literal[True]
    submitted_identity_value: str = Field(..., min_length=1, max_length=5000)
    trust_mode: TrustMode = "explorer"
    intended_actions: list[IntendedAction] = Field(default_factory=list, max_length=20)
    target_jurisdictions: list[Annotated[str, Field(min_length=2, max_length=10)]] = Field(
        default_factory=list, max_length=30
    )
    jurisdiction_bundle: JurisdictionBundle = "custom"
    development_stage: DevelopmentStage = "discovery"
    asset_type_hint: AssetTypeHint | None = None
    product_context: ProductContext | None = None
    config: AnalysisConfigSchema = Field(default_factory=AnalysisConfigSchema)

    model_config = ConfigDict(extra="forbid")

    @field_validator("compound_input", mode="before")
    @classmethod
    def normalize_compound_input(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Compound input must be text")
        normalized = normalize_compound_identifier(value)
        if not normalized:
            raise ValueError("Compound input is required")
        return normalized

    @field_validator("submitted_identity_value", mode="before")
    @classmethod
    def normalize_submitted_identity_value(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Submitted identity value must be text")
        normalized = normalize_compound_identifier(value)
        if not normalized:
            raise ValueError("Submitted identity value is required")
        return normalized

    @model_validator(mode="after")
    def validate_submitted_identity_confirmation(self) -> CreateAnalysisRequest:
        if self.submitted_identity_value != self.compound_input:
            raise ValueError(
                "Submitted identity confirmation must match the normalized compound input"
            )
        detected_input_type = detect_submitted_input_type(self.compound_input)
        if self.input_type != detected_input_type:
            raise ValueError(
                "Declared input_type does not match submitted compound syntax; "
                f"expected {detected_input_type}"
            )
        return self

    def normalized_idempotency_payload(self) -> dict[str, Any]:
        """Return the complete validated launch request used for replay matching."""
        return self.model_dump(mode="json", exclude_none=False)

    def _normalized_config(
        self,
        *,
        org_default_config: Mapping[str, Any] | None = None,
    ) -> tuple[AnalysisConfigSchema, set[str]]:
        request_config_fields = set(self.config.model_fields_set)
        if org_default_config is None:
            return self.config, request_config_fields

        default_config = AnalysisConfigSchema.model_validate(dict(org_default_config))
        default_config_fields = set(default_config.model_fields_set)
        default_config_values = default_config.model_dump(
            include=default_config_fields,
            exclude_none=True,
        )
        request_config_values = self.config.model_dump(
            include=request_config_fields,
            exclude_none=True,
        )
        merged_config = AnalysisConfigSchema.model_validate(
            {
                **default_config_values,
                **request_config_values,
            }
        )
        return merged_config, default_config_fields | request_config_fields

    def runtime_config(
        self,
        *,
        org_default_config: Mapping[str, Any] | None = None,
    ) -> dict:
        """Build the persisted runtime config payload for this analysis request."""
        normalized_config, _explicit_config_fields = self._normalized_config(
            org_default_config=org_default_config,
        )
        config = normalized_config.model_dump(exclude_none=True)
        trust_defaults = dict(_TRUST_MODE_DEFAULTS[self.trust_mode])
        bundled_targets = _JURISDICTION_BUNDLE_MAP.get(self.jurisdiction_bundle, [])
        target_jurisdictions = [
            code.strip().upper()
            for code in (
                self.target_jurisdictions
                if self.jurisdiction_bundle == "custom"
                else bundled_targets + self.target_jurisdictions
            )
            if code
        ]
        target_jurisdictions = list(dict.fromkeys(target_jurisdictions))
        if not target_jurisdictions:
            target_jurisdictions = [
                code.strip().upper() for code in config.get("search_jurisdictions", []) if code
            ]
        search_jurisdictions = [
            code.strip().upper() for code in config.get("search_jurisdictions", []) if code
        ]
        if self.jurisdiction_bundle != "custom":
            search_jurisdictions = list(dict.fromkeys([*target_jurisdictions, "WO"]))
        elif target_jurisdictions:
            search_jurisdictions = list(
                dict.fromkeys([*search_jurisdictions, *target_jurisdictions, "WO"])
            )
        raw_asset_type_hint = (self.asset_type_hint or "").strip().lower()
        asset_type_hint = raw_asset_type_hint or "unknown"
        configured_matter_type = str(config.get("matter_type") or "small_molecule").strip().lower()
        matter_type = (
            _ASSET_HINT_TO_MATTER_TYPE.get(asset_type_hint, asset_type_hint)
            if raw_asset_type_hint and asset_type_hint != "unknown"
            else configured_matter_type or "small_molecule"
        )
        jurisdiction_policy = "us_ep_core"
        if any(code in {"UK", "CN", "IN", "JP"} for code in target_jurisdictions):
            jurisdiction_policy = "major_markets_parallel"

        config.update(
            trust_defaults,
            identity_review_required=True,
            trust_mode=self.trust_mode,
            intended_actions=[action.strip() for action in self.intended_actions if action.strip()],
            target_jurisdictions=target_jurisdictions or config.get("search_jurisdictions", []),
            jurisdiction_bundle=self.jurisdiction_bundle,
            development_stage=self.development_stage,
            asset_type_hint=asset_type_hint,
            matter_type=matter_type,
            jurisdiction_policy=jurisdiction_policy,
            search_jurisdictions=search_jurisdictions or target_jurisdictions,
        )
        if self.product_context is not None:
            product_context = self.product_context.normalized_payload()
            if product_context:
                config["product_context"] = product_context
        required_components = config.get("required_record_components", [])
        if "US" not in target_jurisdictions:
            required_components = [
                component
                for component in required_components
                if not str(component).startswith("us_")
            ]
        if "EP" not in target_jurisdictions:
            required_components = [
                component
                for component in required_components
                if not str(component).startswith("ep_")
            ]
        config["required_record_components"] = required_components
        return config


class AnalysisReviewStatusSummary(BaseModel):
    """Compact review workflow snapshot embedded on analysis list/detail responses."""

    model_config = ConfigDict(extra="forbid")

    status: ReviewStatusValue = "pending"
    is_persisted: bool = False
    note: str | None = None
    reviewer_name: str | None = None
    reviewer_email: str | None = None
    reviewed_at: datetime | None = None
    updated_at: datetime | None = None


class AnalysisProductContextSummary(BaseModel):
    """Safe product-context read model for analysis list/detail responses."""

    model_config = ConfigDict(extra="forbid")

    product_name: str | None = None
    dosage_form: str | None = None
    route_of_administration: str | None = None
    strength: str | None = None
    release_profile: str | None = None
    salt_polymorph_form: str | None = None
    key_excipients: list[str] = Field(default_factory=list)
    indication: str | None = None
    patient_population: str | None = None
    combination_assets: list[str] = Field(default_factory=list)
    reference_product: str | None = None
    manufacturing_route: str | None = None
    commercial_action: str | None = None
    decision_deadline: str | None = None
    commercial_territories: list[str] = Field(default_factory=list)
    accused_acts: list[AccusedActRecord] = Field(default_factory=list)
    known_patents_or_assignees: list[str] = Field(default_factory=list)


class AnalysisLaunchContextSummary(BaseModel):
    """Launch-time scope and product context carried onto analysis responses."""

    model_config = ConfigDict(extra="forbid")

    trust_mode: str | None = None
    jurisdiction_bundle: str | None = None
    target_jurisdictions: list[str] = Field(default_factory=list)
    development_stage: str | None = None
    asset_type_hint: str | None = None
    matter_type: str | None = None
    intended_actions: list[str] = Field(default_factory=list)
    product_context: AnalysisProductContextSummary = Field(
        default_factory=AnalysisProductContextSummary
    )


class AnalysisResponse(BaseModel):
    """Analysis list/detail response."""

    id: uuid.UUID
    compound_input: str
    compound_name: str
    compound_smiles: str
    input_type: SubmittedInputType
    submitted_identity_confirmed: bool = False
    submitted_identity_value: str | None = None
    status: str
    current_step: int
    progress_pct: float
    development_fixture: bool = False
    invalidity_assessments_count: int | None = None
    overall_risk: str | None
    blocking_patents_count: int | None
    total_patents_found: int
    executive_summary: str
    risk_ratings_restricted: bool = False
    estimated_cost_usd: float
    pipeline_duration_seconds: float | None
    flagged_for_review: bool
    review_status: AnalysisReviewStatusSummary | None = None
    launch_context: AnalysisLaunchContextSummary | None = None
    current_user_role: str | None = None
    share_active: bool = False
    share_recipient_bound: bool = False
    share_view_count: int = 0
    share_last_viewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnalysisListResponse(BaseModel):
    """Paginated list of analyses."""

    items: list[AnalysisResponse]
    total: int
    page: int
    per_page: int
    status_counts: dict[str, int] = Field(default_factory=dict)


class AnalysisCursorListResponse(BaseModel):
    """Cursor-paginated list of analyses.

    Use ``next_cursor`` as the ``cursor`` query parameter on the next request.
    When ``next_cursor`` is null there are no further pages.
    """

    items: list[AnalysisResponse]
    next_cursor: str | None = None
