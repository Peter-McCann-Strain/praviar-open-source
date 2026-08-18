"""Declarative settings mixins for the Praviar Pipeline runtime config."""

from __future__ import annotations

import enum
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator

from praviar_pipeline.clients.http_identity import normalize_source_contact_email
from praviar_pipeline.errors import ConfigurationError
from praviar_pipeline.model_supply_chain import (
    DEFAULT_ML_BOM_PATH,
    REQUIRED_DOC2SAR_MODEL_IDS,
    require_resolved_drawing_model_supply_chain,
)

DrawingRolloutState = Literal["internal", "shadow", "beta", "production"]


class DrawingPreprocessingStep(enum.StrEnum):
    """Preprocessing operations accepted by the drawing runtime."""

    DENOISE = "denoise"
    CLAHE = "clahe"
    BINARIZE = "binarize"
    SAUVOLA = "sauvola"
    CONNECTED_COMPONENTS = "connected_components"
    DESKEW = "deskew"
    SHARPEN = "sharpen"
    PAD = "pad"
    RESIZE_512 = "resize_512"


_SUPPORTED_DRAWING_JURISDICTIONS = {"US", "EP", "WO", "JP", "CN", "KR"}
_LIVE_DRAWING_ROLLOUT_STATES = {"beta", "production"}
_SPECIALIST_DRAWING_ROLLOUT_FIELDS = (
    (
        "drawing_markushgrapher_enabled",
        "drawing_markush_rollout_state",
        "MarkushGrapher recognition",
    ),
    ("drawing_doc2sar_enabled", "drawing_doc2sar_rollout_state", "Doc2SAR extraction"),
)


class TransportAndClientSettingsMixin:
    # --- HTTP client defaults ---
    source_contact_email: str = Field(
        default="",
        max_length=254,
        description=(
            "Optional deployment-operator email supplied to external scientific "
            "sources that request a contact identity. The research-preview source "
            "tree does not publish or assume an operator mailbox."
        ),
    )

    @field_validator("source_contact_email")
    @classmethod
    def validate_source_contact_email(cls, value: str) -> str:
        """Reject mailbox bytes that can corrupt HTTP identity syntax."""
        return normalize_source_contact_email(value)

    http_timeout_default: float = Field(default=30.0, ge=5.0)
    http_timeout_long: float = Field(default=60.0, ge=10.0)
    http_connect_timeout: float = Field(default=10.0, ge=2.0)
    http_max_connections: int = Field(default=10, ge=1)
    http_max_keepalive: int = Field(default=5, ge=1)
    http_retry_attempts: int = Field(default=3, ge=1)
    http_retry_initial_wait: float = Field(default=1.0, ge=0.1)
    http_retry_max_wait: float = Field(default=10.0, ge=1.0)

    # --- Claude client ---
    claude_max_retries: int = Field(default=3, ge=1)
    claude_max_connections: int = Field(default=20, ge=1)
    claude_keepalive_connections: int = Field(default=10, ge=1)
    claude_keepalive_expiry: int = Field(default=30, ge=5)

    # --- Source-specific ---
    pubchem_sdq_page_size: int = Field(default=10000, ge=100)
    pubchem_poll_max_attempts: int = Field(default=10, ge=1)
    pubchem_poll_sleep_seconds: float = Field(default=1.5, ge=0.5)
    openfda_requests_per_second: float = Field(
        default=4.0,
        ge=0.1,
        le=4.0,
        description="Operator-configured local request-rate cap for openFDA.",
    )
    identity_tautomer_max_enumerated: int = Field(default=32, ge=2, le=256)
    identity_tautomer_max_transforms: int = Field(default=64, ge=2, le=1024)
    identity_tautomer_max_search_candidates: int = Field(default=8, ge=1, le=32)
    identity_prodrug_max_search_candidates: int = Field(default=4, ge=1, le=12)
    identity_prodrug_min_parent_heavy_atom_fraction: float = Field(
        default=0.60,
        ge=0.5,
        le=0.95,
    )
    orange_book_cache_max_age_days: int = Field(default=30, ge=1)
    orange_book_patent_txt_path: str = Field(
        default="",
        description="Path to local Orange Book patent.txt for PTE fallback lookup",
    )
    pte_certificates_csv_path: str = Field(
        default="",
        description="Path to local USPTO PTE certificates CSV for PTE fallback lookup",
    )
    search_surechembl_max_results: int = Field(default=500, ge=10)
    search_bigquery_max_results: int = Field(default=500, ge=10)
    bigquery_dataset: str = Field(
        default="patents",
        description=(
            "BigQuery dataset name used for the hybrid indexed lexical+dense retrieval path."
        ),
    )
    bigquery_table: str = Field(
        default="patents",
        description="BigQuery table name within bigquery_dataset for hybrid retrieval.",
    )
    citation_examiner_max_refs: int = Field(default=10, ge=1)
    input_max_length: int = Field(default=5000, ge=100)


class DrawingPipelineSettingsMixin:
    # --- Drawing analysis (Step 2.75) ---
    drawing_analysis_enabled: bool = Field(
        default=True,
        description="Enable patent drawing OCSR analysis between search and triage",
    )
    drawing_analysis_rollout_state: DrawingRolloutState = Field(
        default="shadow",
        description=(
            "Drawing-analysis rollout state. internal/shadow may run extraction but "
            "must not influence customer-visible triage or risk decisions; beta and "
            "production may influence decisions after the relevant evidence gates pass."
        ),
    )
    drawing_analysis_evidence_gate_passed: bool = Field(
        default=False,
        description=(
            "Set true only after configured production-evidence gates, checksums, "
            "benchmarks, shadow-leakage tests, rollback paths, and human approvals "
            "allow drawing evidence to influence beta/production decisions."
        ),
    )
    drawing_analysis_ml_bom_path: str = Field(
        default=DEFAULT_ML_BOM_PATH,
        description=(
            "Repo-relative or absolute ML-BOM manifest path used to fail closed before "
            "drawing evidence can influence beta/production decisions."
        ),
    )
    drawing_analysis_vision_roster_path: str = Field(
        default="",
        description=(
            "Path to the immutable production vision roster. An empty value selects "
            "the packaged roster; live calibration still binds its exact SHA-256."
        ),
    )
    drawing_analysis_calibration_artifact_path: str = Field(
        default="",
        description=(
            "Path to the signed, versioned OCSR calibration artifact. Live drawing "
            "evidence cannot influence decisions while this is absent or invalid."
        ),
    )
    drawing_analysis_calibration_artifact_sha256: str = Field(
        default="",
        description=(
            "Exact SHA-256 pin for the signed calibration artifact bytes. Live "
            "drawing evidence rejects an unpinned or substituted artifact."
        ),
    )
    drawing_analysis_calibration_min_revision: int = Field(
        default=1,
        ge=1,
        description="Minimum monotonic calibration artifact revision accepted live.",
    )
    drawing_analysis_calibration_revocation_epoch: int = Field(
        default=0,
        ge=0,
        description="Minimum calibration revocation epoch accepted by this deployment.",
    )
    drawing_analysis_revoked_calibration_artifact_ids: tuple[str, ...] = Field(
        default=(),
        description="Explicit denylist of signed calibration artifact IDs.",
    )
    drawing_analysis_calibration_public_key: SecretStr = Field(
        default=SecretStr(""),
        description="Base64 Ed25519 public key for the signed OCSR calibration artifact.",
    )
    drawing_analysis_calibration_key_id: str = Field(
        default="",
        description="Pinned key identifier accepted for the OCSR calibration artifact.",
    )
    drawing_analysis_calibration_corpus_sha256: str = Field(
        default="",
        description="Pinned SHA-256 of the independent calibration corpus.",
    )
    drawing_analysis_container_image_digests: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Per-tool immutable OCI image digests. Live calibration requires exact "
            "coverage of the configured OCSR tool set."
        ),
    )
    drawing_analysis_jurisdictions: list[str] = Field(
        default_factory=list,
        description=(
            "Explicit jurisdiction allowlist for staged drawing-analysis rollout. "
            "Empty disables drawing selection and prevents drawing evidence from "
            "influencing decisions."
        ),
    )
    drawing_max_patents: int = Field(
        default=50,
        ge=0,
        description="Max patents to fetch drawings for (0 = unlimited, process all)",
    )
    drawing_max_pages_per_patent: int = Field(
        default=30,
        ge=0,
        description=(
            "Max drawing pages to fetch per patent. Zero uses the runtime hard safety ceiling."
        ),
    )
    drawing_pdf_max_bytes: int = Field(
        default=100 * 1024 * 1024,
        ge=1024,
        le=100 * 1024 * 1024,
        description="Maximum decoded byte length accepted for one drawing fallback PDF",
    )
    drawing_max_pixels_per_page: int = Field(
        default=40_000_000,
        ge=1_000_000,
        le=40_000_000,
        description="Maximum rendered pixel count accepted for one drawing PDF page",
    )
    drawing_max_total_pixels_per_patent: int = Field(
        default=250_000_000,
        ge=1_000_000,
        le=250_000_000,
        description="Maximum total rendered pixels accepted across one patent PDF",
    )
    drawing_ocsr_tool: str = Field(
        default="molscribe",
        description="Primary OCSR tool: 'molscribe', 'decimer', 'ensemble', 'markushgrapher'",
    )
    drawing_segmentation_tool: Literal["decimer", "moldet", "chemsam"] = Field(
        default="decimer",
        description=(
            "Page-detector backend. decimer is the reviewed default; moldet is "
            "non-commercial-only and blocked from beta/production use; chemsam is "
            "an optional specialist integration. Selection is not a performance claim."
        ),
    )
    drawing_ensemble_tools: list[str] = Field(
        default_factory=lambda: ["molscribe", "molsight"],
        description=(
            "Primary OCSR tools used in ensemble mode. Defaults match the immutable "
            "production roster; research-only tools must be explicitly selected and "
            "cannot pass the live calibration contract."
        ),
    )
    drawing_preprocessing: list[DrawingPreprocessingStep] = Field(
        default_factory=lambda: [
            DrawingPreprocessingStep.CLAHE,
            DrawingPreprocessingStep.BINARIZE,
        ],
        description=(
            "Ordered drawing preprocessing steps. Values are strictly validated "
            "before a run starts."
        ),
    )
    drawing_confidence_threshold: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
        description="MolScribe confidence threshold for auto-accept",
    )
    drawing_pubchem_crossref: bool = Field(
        default=True,
        description="Enable PubChem InChI key cross-reference verification",
    )
    drawing_llm_verify: bool = Field(
        default=True,
        description="Enable Claude render-and-compare verification",
    )
    drawing_llm_verify_model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Model for render-and-compare binary screening",
    )
    drawing_llm_verify_detail_model: str = Field(
        default="claude-sonnet-4-6",
        description="Model for detailed diff on flagged mismatches",
    )
    drawing_tanimoto_high: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Tanimoto threshold for HIGH drawing risk signal",
    )
    drawing_tanimoto_medium: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Tanimoto threshold for MEDIUM drawing risk signal",
    )
    drawing_concurrency: int = Field(
        default=5,
        ge=1,
        description="Max concurrent patent drawing analyses",
    )
    drawing_timeout_per_patent_s: float = Field(
        default=300.0,
        ge=30.0,
        description="Max seconds per patent drawing analysis before timeout",
    )
    drawing_super_resolution: bool = Field(
        default=False,
        description="Enable Real-ESRGAN super-resolution preprocessing",
    )
    drawing_super_resolution_scale: int = Field(
        default=2,
        ge=2,
        le=4,
        description="Super-resolution upscale factor (2 or 4)",
    )
    drawing_markushgrapher_enabled: bool = Field(
        default=False,
        description=(
            "Enable MarkushGrapher 2.0 for Markush structure recognition (isolated venv). "
            "Defaults off until its model directory is covered by ML-BOM checksum and "
            "license evidence. The classifier_v2 routing only fires this path when "
            "category == MARKUSH."
        ),
    )
    drawing_markush_rollout_state: DrawingRolloutState = Field(
        default="shadow",
        description=(
            "Markush recognition rollout state. Defaults to shadow until license, "
            "multi-jurisdiction benchmark, and reviewer-abstention gates are green."
        ),
    )
    drawing_doc2sar_enabled: bool = Field(
        default=False,
        description=(
            "Enable Doc2SAR Markush-table extraction. Off by default because table "
            "enumeration is a specialist path and must be opted in per run."
        ),
    )
    drawing_doc2sar_rollout_state: DrawingRolloutState = Field(
        default="internal",
        description="Doc2SAR rollout state; beta/production require benchmark and license gates.",
    )
    drawing_doc2sar_max_enumerations: int = Field(
        default=500,
        ge=1,
        description="Maximum enumerated species Doc2SAR may emit before marking overflow.",
    )

    # --- Confidence cascade (adaptive model routing) ---
    drawing_cascade_enabled: bool = Field(
        default=False,
        description=(
            "Enable confidence cascade: run the primary recognizer first and escalate "
            "when configured evidence gates require it. Disabled by default so the "
            "governed ensemble path, not an unvalidated speed/accuracy assumption, "
            "controls routing."
        ),
    )
    drawing_cascade_high_threshold: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Confidence above this: accept MolScribe alone (skip other models)",
    )
    drawing_cascade_medium_threshold: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Confidence above this: run 2 more models. Below: run all 5",
    )
    drawing_cascade_min_resolved_conf: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
        description="Floor on fused confidence. Below this, the prediction is "
        "downgraded to unresolved rather than emitted as wrong-resolved. "
        "Catches catastrophic miscalls at low ensemble agreement.",
    )
    drawing_max_resolved_atoms: int = Field(
        default=100,
        ge=10,
        description="Heavy-atom ceiling for resolved predictions. Predictions "
        "above this (e.g. polysaccharide hallucinations from out-of-distribution "
        "macromolecules) are flagged unresolved.",
    )

    # --- Image classification ---
    drawing_classifier_enabled: bool = Field(
        default=True,
        description="Enable image classifier to route molecule/reaction/Markush/non-chemical",
    )

    # --- Text cross-validation ---
    drawing_text_validation_enabled: bool = Field(
        default=True,
        description="Enable text cross-validation (OPSIN + formula + PubChem)",
    )
    drawing_text_smiles_enabled: bool = Field(
        default=False,
        description=(
            "Resolve conservative text-derived SMILES and use it as an ensemble "
            "cross-check signal. Disabled by default until a run explicitly opts in."
        ),
    )
    drawing_text_smiles_max_names: int = Field(
        default=3,
        ge=0,
        description="Maximum chemical names to try when resolving text-derived SMILES.",
    )
    drawing_text_smiles_max_cas: int = Field(
        default=5,
        ge=0,
        description="Maximum CAS numbers to try when resolving text-derived SMILES.",
    )
    drawing_text_smiles_opsin_timeout_s: float = Field(
        default=10.0,
        ge=1.0,
        description="Per-run timeout budget for OPSIN-backed text SMILES resolution.",
    )

    # --- Jurisdiction-aware preprocessing ---
    drawing_jurisdiction_aware: bool = Field(
        default=True,
        description="Adapt preprocessing based on patent jurisdiction (JP gets stronger denoising)",
    )

    # --- Drawing-based triage auto-filter ---
    triage_drawing_auto_relevant_tanimoto: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Tanimoto threshold for auto-RELEVANT (skip LLM triage)",
    )
    triage_drawing_auto_relevant_require_substructure: bool = Field(
        default=True,
        description="Require substructure match for auto-RELEVANT classification",
    )
    triage_drawing_auto_not_relevant_tanimoto: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description="Max Tanimoto threshold for auto-NOT_RELEVANT (skip LLM triage)",
    )
    triage_drawing_auto_not_relevant_min_structures: int = Field(
        default=3,
        ge=1,
        description="Min structures extracted to trust auto-NOT_RELEVANT",
    )
    triage_drawing_auto_not_relevant_min_confidence: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
        description="Min avg OCSR confidence to trust auto-NOT_RELEVANT",
    )

    # --- Caching ---
    drawing_image_cache_dir: str = Field(
        default="",
        description="Directory to cache EPO drawing images. Empty = temp dir",
    )
    drawing_result_cache_enabled: bool = Field(
        default=True,
        description="Cache OCSR results by image content hash",
    )

    # --- Ensemble fusion thresholds (previously hardcoded magic numbers) ---
    drawing_ensemble_molscribe_high_conf: float = Field(
        default=0.90,
        ge=0.0,
        le=1.0,
        description="MolScribe confidence above which it wins outright in confidence_cascade",
    )
    drawing_ensemble_agreement_ratio_min: float = Field(
        default=0.40,
        ge=0.0,
        le=1.0,
        description="Below this agreement ratio, the majority vote gets a low-agreement penalty",
    )
    drawing_ensemble_low_agreement_penalty: float = Field(
        default=0.50,
        gt=0.0,
        le=1.0,
        description="Multiplier applied to confidence when agreement ratio < min",
    )
    drawing_cascade_plausibility_threshold: float = Field(
        default=0.50,
        ge=0.0,
        le=1.0,
        description="Plausibility floor below which MolScribe primary triggers fallback ladder",
    )
    drawing_ensemble_formula_boost: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description=(
            "Weight bonus added to a voter when its RDKit formula matches patent text formula"
        ),
    )
    drawing_text_confirm_conf_bump: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description="Confidence bump when text_smiles canonicalises to a voter prediction",
    )
    drawing_text_validation_tanimoto_threshold: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Tanimoto cutoff for accepting CAS/name PubChem match in text validation",
    )

    # --- MolClassifier triage worker ---
    drawing_classifier_box_score_thresh: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
        description="MolClassifier (Mask R-CNN) per-detection score threshold. "
        "Raise to be stricter; lower to admit weaker detections.",
    )
    drawing_classifier_non_chemical_min_conf: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description=(
            "Below this task-local confidence, a non_chemical prediction is "
            "conservatively reclassified as molecule so weak negative evidence cannot "
            "silently discard a crop."
        ),
    )

    # --- Multi-molecule bbox splitter ---
    drawing_split_enabled: bool = Field(
        default=True,
        description="Enable ChemSAM-style multi-molecule splitting on tall/wide DECIMER crops",
    )
    drawing_split_min_height_trigger_px: int = Field(
        default=500,
        ge=100,
        description=(
            "Only attempt splitting when crop height exceeds this "
            "(smaller crops are single-molecule)"
        ),
    )
    drawing_split_kernel_fraction: float = Field(
        default=0.02,
        gt=0.0,
        le=0.5,
        description="Dilation kernel size as a fraction of the crop's smaller dimension",
    )
    drawing_split_min_component_area: int = Field(
        default=5000,
        ge=100,
        description="Connected components below this pixel area are discarded as noise",
    )
    drawing_split_max_aspect: float = Field(
        default=8.0,
        gt=1.0,
        description=(
            "Reject components above this aspect ratio (likely lines/labels, not molecules)"
        ),
    )
    drawing_split_min_gap_px: int = Field(
        default=30,
        ge=5,
        description="Minimum projection-profile white-space gap to trigger a hard split",
    )
    drawing_markush_scope_agent_enabled: bool = Field(
        default=False,
        description=(
            "Enable the experimental Markush scope agent for internal/shadow evidence "
            "collection only. Its bounded R-group enumeration is not permitted to "
            "influence beta or production decisions."
        ),
    )

    @property
    def drawing_analysis_shadow_mode(self) -> bool:
        """Legacy boolean view of the rollout-state contract."""
        return self.drawing_analysis_rollout_state in {"internal", "shadow"}

    @field_validator("drawing_analysis_jurisdictions", mode="before")
    @classmethod
    def _parse_drawing_analysis_jurisdictions(cls, value):
        if value in (None, ""):
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @model_validator(mode="after")
    def _validate_drawing_thresholds(self) -> DrawingPipelineSettingsMixin:
        normalized_jurisdictions: list[str] = []
        seen_jurisdictions: set[str] = set()
        for raw_value in self.drawing_analysis_jurisdictions:
            jurisdiction = str(raw_value or "").strip().upper()
            if not jurisdiction:
                continue
            if jurisdiction not in _SUPPORTED_DRAWING_JURISDICTIONS:
                raise ValueError(
                    "drawing_analysis_jurisdictions contains unsupported jurisdiction "
                    f"'{jurisdiction}'. Supported values: "
                    f"{', '.join(sorted(_SUPPORTED_DRAWING_JURISDICTIONS))}"
                )
            if jurisdiction not in seen_jurisdictions:
                normalized_jurisdictions.append(jurisdiction)
                seen_jurisdictions.add(jurisdiction)
        object.__setattr__(
            self,
            "drawing_analysis_jurisdictions",
            normalized_jurisdictions,
        )

        drawing_rollout_is_live = (
            self.drawing_analysis_rollout_state in _LIVE_DRAWING_ROLLOUT_STATES
        )
        if drawing_rollout_is_live and not self.drawing_analysis_evidence_gate_passed:
            raise ValueError(
                "drawing_analysis_evidence_gate_passed must be true before "
                "drawing_analysis_rollout_state can be beta or production"
            )
        if drawing_rollout_is_live and self.drawing_markush_scope_agent_enabled:
            raise ValueError(
                "drawing_markush_scope_agent_enabled must be false for beta or "
                "production drawing evidence; the experimental scope agent is "
                "shadow-only"
            )
        if drawing_rollout_is_live and self.drawing_doc2sar_enabled:
            raise ValueError(
                "drawing_doc2sar_enabled must be false for beta or production "
                "drawing evidence until its SAR-table output is integrated into "
                "the governed evidence model and independently calibrated"
            )
        if drawing_rollout_is_live and self.drawing_analysis_evidence_gate_passed:
            extra_required_model_ids: set[str] = set()
            if (
                self.drawing_doc2sar_enabled
                and self.drawing_doc2sar_rollout_state in _LIVE_DRAWING_ROLLOUT_STATES
            ):
                extra_required_model_ids.update(REQUIRED_DOC2SAR_MODEL_IDS)
            try:
                require_resolved_drawing_model_supply_chain(
                    self.drawing_analysis_ml_bom_path,
                    extra_required_model_ids=extra_required_model_ids,
                    segmentation_tool=self.drawing_segmentation_tool,
                )
            except ConfigurationError:
                raise ValueError("Drawing model supply-chain validation failed") from None

        for enabled_field, rollout_field, tool_label in _SPECIALIST_DRAWING_ROLLOUT_FIELDS:
            specialist_is_enabled = bool(getattr(self, enabled_field))
            specialist_state = getattr(self, rollout_field)
            specialist_rollout_is_live = specialist_state in _LIVE_DRAWING_ROLLOUT_STATES
            if specialist_rollout_is_live and not drawing_rollout_is_live:
                raise ValueError(
                    f"{rollout_field} can be beta or production only when "
                    "drawing_analysis_rollout_state is beta or production"
                )
            if drawing_rollout_is_live and specialist_is_enabled and not specialist_rollout_is_live:
                raise ValueError(
                    f"{rollout_field} must be beta or production before {tool_label} "
                    "can emit into beta/production drawing evidence"
                )

        if self.drawing_cascade_high_threshold <= self.drawing_cascade_medium_threshold:
            raise ValueError(
                "drawing_cascade_high_threshold must be > drawing_cascade_medium_threshold "
                f"(got high={self.drawing_cascade_high_threshold}, "
                f"medium={self.drawing_cascade_medium_threshold})"
            )
        if self.drawing_tanimoto_high <= self.drawing_tanimoto_medium:
            raise ValueError(
                "drawing_tanimoto_high must be > drawing_tanimoto_medium "
                f"(got high={self.drawing_tanimoto_high}, medium={self.drawing_tanimoto_medium})"
            )
        return self


class OutputAndStorageSettingsMixin:
    # Output directory — all pipeline outputs (JSON, Markdown, PDF) go here
    output_dir: str = Field(
        default="",
        description="Directory for pipeline output files. Defaults to <PROJECT_ROOT>/output/",
    )

    # Database URL — when set, CLI runs are registered in PostgreSQL so the web app can see them.
    # Uses the same DB as the API. Leave empty for file-only mode.
    database_url: str = Field(
        default="",
        description="PostgreSQL URL for registering CLI runs in the web app database.",
    )
