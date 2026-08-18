"""Shared test fixtures for the Praviar Pipeline test suite."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import SecretStr

from praviar_pipeline.config import clear_settings_cache
from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.compound import RelatedCompound, ResolvedCompound
from praviar_pipeline.models.equivalents import DoEAssessment, EstoppelResult, FWRAssessment
from praviar_pipeline.models.invalidity import (
    InvalidityAssessment,
    PTABResult,
)
from praviar_pipeline.models.patent import LegalStatus, PatentHit, PatentSource
from praviar_pipeline.models.report import FTOReport, RiskSummary
from praviar_pipeline.models.triage import Relevance, TriageResult
from praviar_pipeline.models.verification import VerificationCheck, VerificationResult
from praviar_pipeline.ocsr.calibration_contract import (
    CALIBRATION_DOMAIN,
    EXACTNESS_DEFINITION,
    sign_calibration_artifact,
)
from praviar_pipeline.vision_production import DEFAULT_ROSTER_PATH, load_roster


@pytest.fixture(autouse=True)
def _ensemble_env_defaults() -> None:
    """Install canonical task-local fusion defaults for each test."""
    from praviar_pipeline.ocsr.ensemble import set_thresholds_from_settings

    set_thresholds_from_settings(
        SimpleNamespace(
            drawing_analysis_rollout_state="shadow",
            drawing_ensemble_molscribe_high_conf=0.90,
            drawing_ensemble_agreement_ratio_min=0.40,
            drawing_ensemble_low_agreement_penalty=0.50,
            drawing_ensemble_formula_boost=0.15,
            drawing_text_confirm_conf_bump=0.10,
            drawing_cascade_plausibility_threshold=0.50,
            drawing_cascade_min_resolved_conf=0.65,
            drawing_max_resolved_atoms=100,
        )
    )
    # Fake key so config_validators.check_api_keys() passes in unit tests.
    os.environ["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_API_KEY", "sk-ant-test-key")


@pytest.fixture
def verified_calibration_config(tmp_path) -> dict[str, object]:
    """Build a real signed calibration contract for live drawing-evidence tests."""
    roster, roster_sha256 = load_roster(DEFAULT_ROSTER_PATH)
    tools = ("molscribe", "molsight")
    primary_components = {
        component.component_id.removeprefix("ocsr."): component
        for component in roster.components
        if component.role == "primary_ocsr"
    }
    ml_bom_entries: list[dict[str, str]] = []
    tool_bindings: list[dict[str, object]] = []
    container_digests: dict[str, str] = {}
    worker_image_digest = "sha256:" + hashlib.sha256(b"test-vision-worker-container").hexdigest()
    for index, tool_id in enumerate(tools):
        models: list[dict[str, str]] = []
        for model in primary_components[tool_id].models:
            model_sha = hashlib.sha256(model.model_id.encode()).hexdigest()
            ml_bom_entries.append({"model_id": model.model_id, "sha256": model_sha})
            models.append({"model_id": model.model_id, "sha256": model_sha})
        container_digest = worker_image_digest
        container_digests[tool_id] = container_digest
        tool_bindings.append(
            {
                "tool_id": tool_id,
                "models": models,
                "container_image_digest": container_digest,
                "calibration_method": "platt",
                "platt_a": 1.1 + index,
                "platt_b": -0.2 + index,
            }
        )

    ml_bom_path = tmp_path / "verified-calibration-ml-bom.json"
    ml_bom_path.write_text(
        json.dumps({"entries": ml_bom_entries}),
        encoding="utf-8",
    )
    private_key = Ed25519PrivateKey.generate()
    public_key_b64 = base64.b64encode(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode()
    corpus_sha256 = hashlib.sha256(b"test-live-calibration-corpus").hexdigest()
    now = datetime.now(UTC)
    artifact_payload = {
        "schema_version": "praviar-ocsr-calibration/v1",
        "artifact_id": "test-live-calibration-v1",
        "artifact_revision": 1,
        "revocation_epoch": 0,
        "issued_at": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(days=1)).isoformat(),
        "calibration_corpus_sha256": corpus_sha256,
        "runtime_roster_sha256": roster_sha256,
        "ml_bom_sha256": hashlib.sha256(ml_bom_path.read_bytes()).hexdigest(),
        "exactness_definition": EXACTNESS_DEFINITION,
        "domain": CALIBRATION_DOMAIN,
        "jurisdictions": ["US"],
        "minimum_resolved_confidence": 0.65,
        "tools": tool_bindings,
    }
    artifact_path = tmp_path / "verified-calibration.json"
    artifact_path.write_text(
        json.dumps(
            sign_calibration_artifact(
                artifact_payload,
                private_key=private_key,
                key_id="test-live-calibration-key",
            )
        ),
        encoding="utf-8",
    )
    return {
        "drawing_analysis_calibration_artifact_path": str(artifact_path),
        "drawing_analysis_calibration_artifact_sha256": hashlib.sha256(
            artifact_path.read_bytes()
        ).hexdigest(),
        "drawing_analysis_calibration_min_revision": 1,
        "drawing_analysis_calibration_revocation_epoch": 0,
        "drawing_analysis_revoked_calibration_artifact_ids": (),
        "drawing_analysis_calibration_public_key": SecretStr(public_key_b64),
        "drawing_analysis_calibration_key_id": "test-live-calibration-key",
        "drawing_analysis_calibration_corpus_sha256": corpus_sha256,
        "drawing_analysis_vision_roster_path": str(DEFAULT_ROSTER_PATH),
        "drawing_analysis_ml_bom_path": str(ml_bom_path),
        "drawing_analysis_container_image_digests": container_digests,
        "drawing_ensemble_tools": list(tools),
        "drawing_segmentation_tool": "decimer",
        "drawing_classifier_enabled": True,
        "certification_worker_oci_image_digest": worker_image_digest,
        "drawing_cascade_min_resolved_conf": 0.65,
    }


# ---------------------------------------------------------------------------
# Compound fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def succinic_acid() -> ResolvedCompound:
    """Succinic acid — the canonical test compound."""
    return ResolvedCompound(
        name="succinic acid",
        canonical_smiles="OC(=O)CCC(O)=O",
        inchi="InChI=1S/C4H6O4/c5-3(6)1-2-4(7)8/h1-2H2,(H,5,6)(H,7,8)",
        inchi_key="KDYFGRWQOYBRFD-UHFFFAOYSA-N",
        pubchem_cid=1110,
        synonyms=["butanedioic acid", "amber acid"],
        cas_numbers=["110-15-6"],
        molecular_formula="C4H6O4",
        molecular_weight=118.09,
        morgan_fp="0101010",
        maccs_keys="1100110",
        functional_groups=["carboxylic_acid"],
        related_compounds=[
            RelatedCompound(
                cid=444972,
                name="malic acid",
                canonical_smiles="OC(CC(O)=O)C(O)=O",
                tanimoto_similarity=0.8,
            ),
        ],
        original_input="succinic acid",
        input_type="name",
    )


# ---------------------------------------------------------------------------
# Patent fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_patent_hit() -> PatentHit:
    return PatentHit(
        patent_id="US7851188B2",
        title="Methods for producing succinic acid from fermentation",
        abstract="A method for bio-based production of succinic acid...",
        claims_text="1. A method for producing succinic acid comprising fermenting...",
        sources=[PatentSource.PUBCHEM, PatentSource.BIGQUERY],
        confidence_score=0.9,
        filing_date=date(2008, 3, 15),
        expiry_date=date(2028, 3, 15),
        assignees=["BioAmber Inc."],
        legal_status=LegalStatus.ACTIVE,
        match_type="exact",
    )


@pytest.fixture
def sample_patent_hits(sample_patent_hit: PatentHit) -> list[PatentHit]:
    """Multiple patent hits for search/triage testing."""
    return [
        sample_patent_hit,
        PatentHit(
            patent_id="US6265190B1",
            title="Succinic acid production and purification",
            abstract="Methods for purification of bio-based succinic acid...",
            sources=[PatentSource.BIGQUERY],
            confidence_score=0.75,
            filing_date=date(1999, 6, 10),
            expiry_date=date(2019, 6, 10),
            legal_status=LegalStatus.EXPIRED,
            match_type="text",
        ),
        PatentHit(
            patent_id="US9999999B2",
            title="Unrelated polymer processing method",
            abstract="A method for processing thermoplastic polymers...",
            sources=[PatentSource.SURECHEMBL],
            confidence_score=0.2,
            match_type="text",
        ),
    ]


# ---------------------------------------------------------------------------
# Triage fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_triage_results() -> list[TriageResult]:
    return [
        TriageResult(
            patent_id="US7851188B2",
            relevance=Relevance.RELEVANT,
            reason="Directly covers succinic acid fermentation methods",
            blocking_potential="High — claim 1 covers the target process",
            key_claims=[1, 3, 7],
            confidence=0.95,
        ),
        TriageResult(
            patent_id="US6265190B1",
            relevance=Relevance.POSSIBLY_RELEVANT,
            reason="Related purification method, expired patent",
            blocking_potential="Low — patent has expired",
            key_claims=[1],
            confidence=0.6,
        ),
    ]


# ---------------------------------------------------------------------------
# Analysis fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_claim_element_met() -> ClaimElement:
    return ClaimElement(
        element_number=1,
        element_text="A method for producing succinic acid",
        status=ElementStatus.MET,
        reasoning="Target compound is succinic acid",
        confidence=0.95,
    )


@pytest.fixture
def sample_claim_element_not_met() -> ClaimElement:
    return ClaimElement(
        element_number=2,
        element_text="comprising fermenting a microorganism of genus Mannheimia",
        status=ElementStatus.NOT_MET,
        reasoning="Target process uses E. coli, not Mannheimia",
        confidence=0.9,
    )


@pytest.fixture
def sample_analysis(
    sample_claim_element_met: ClaimElement,
    sample_claim_element_not_met: ClaimElement,
) -> PatentAnalysis:
    return PatentAnalysis(
        patent_id="US7851188B2",
        title="Methods for producing succinic acid from fermentation",
        assignee="BioAmber Inc.",
        expiry_date=date(2028, 3, 15),
        claims_analyzed=[
            ClaimAnalysis(
                claim_number=1,
                claim_type="independent",
                elements=[sample_claim_element_met, sample_claim_element_not_met],
                overall_status=ElementStatus.NOT_MET,
                overall_confidence=0.9,
            ),
        ],
        risk_level=RiskLevel.MEDIUM,
        risk_summary="One element not met but compound directly covered",
        input_tokens=500,
        output_tokens=300,
    )


@pytest.fixture
def sample_high_risk_analysis() -> PatentAnalysis:
    """A HIGH risk analysis where all elements are MET."""
    return PatentAnalysis(
        patent_id="US8888888B2",
        title="Bio-based succinic acid process",
        assignee="GreenChem Corp",
        expiry_date=date(2035, 1, 1),
        claims_analyzed=[
            ClaimAnalysis(
                claim_number=1,
                claim_type="independent",
                elements=[
                    ClaimElement(
                        element_number=1,
                        element_text="producing succinic acid",
                        status=ElementStatus.MET,
                        reasoning="Exact match",
                        confidence=0.99,
                    ),
                ],
                overall_status=ElementStatus.MET,
                overall_confidence=0.99,
            ),
        ],
        risk_level=RiskLevel.HIGH,
        risk_summary="All claim elements met — direct infringement risk",
        input_tokens=600,
        output_tokens=400,
    )


# ---------------------------------------------------------------------------
# Equivalents / Invalidity / Verification fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_doe_assessment() -> DoEAssessment:
    return DoEAssessment(
        patent_id="US7851188B2",
        claim_number=1,
        element_number=2,
        element_text="comprising fermenting a microorganism of genus Mannheimia",
        estoppel=EstoppelResult(
            estoppel_applies=False,
            file_wrapper_available=False,
        ),
        fwr=FWRAssessment(
            same_function=True,
            function_reasoning="Both produce succinic acid",
            same_way=False,
            way_reasoning="Different microbial genus",
            same_result=True,
            result_reasoning="Same end product",
            equivalent=False,
        ),
        overall_equivalent=False,
        confidence=0.7,
        reasoning="Different genus — way prong fails",
    )


@pytest.fixture
def sample_ptab_result() -> PTABResult:
    return PTABResult(has_been_challenged=False)


@pytest.fixture
def sample_invalidity_assessment(sample_ptab_result: PTABResult) -> InvalidityAssessment:
    return InvalidityAssessment(
        patent_id="US7851188B2",
        claim_numbers=[1, 3],
        ptab=sample_ptab_result,
        overall_invalidity_strength="weak",
        reasoning="No prior PTAB challenges; limited prior art identified",
        confidence=0.4,
    )


@pytest.fixture
def sample_verification_result() -> VerificationResult:
    return VerificationResult(
        checks=[
            VerificationCheck(
                check_name="citation_grounding",
                passed=True,
                details="All patent IDs found in search results",
            ),
        ],
        all_citations_valid=True,
        all_claims_grounded=False,
        all_entities_valid=True,
        dates_consistent=True,
        risk_levels_justified=True,
    )


# ---------------------------------------------------------------------------
# Report fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_report(
    succinic_acid: ResolvedCompound,
    sample_analysis: PatentAnalysis,
    sample_verification_result: VerificationResult,
) -> FTOReport:
    return FTOReport(
        report_id="test-report-001",
        compound=succinic_acid,
        risk_summary=RiskSummary(
            overall_risk=RiskLevel.MEDIUM,
            blocking_patents_count=1,
            total_patents_analyzed=1,
            key_risks=["US7851188B2: medium risk"],
            executive_summary="Moderate FTO risk identified for succinic acid.",
        ),
        patent_analyses=[sample_analysis],
        verification=sample_verification_result,
        total_patents_found=3,
        patents_after_triage=1,
        search_sources_used=["pubchem", "bigquery"],
        total_input_tokens=500,
        total_output_tokens=300,
    )


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings():
    """Provide test-safe settings via environment variables.

    This sets real env vars so that *any* code path calling get_settings()
    (even via a locally-imported reference) constructs a valid Settings
    object that passes the API key validator.
    """
    from praviar_pipeline.config import get_settings

    test_env = {
        "ANTHROPIC_API_KEY": "sk-ant-test-key",
        "PATENTSVIEW_API_KEY": "test-pv-key",
        "USPTO_ODP_API_KEY": "test-odp-key",
        "BIGQUERY_PROJECT_ID": "",
        "PUBCHEM_REQUESTS_PER_SECOND": "100.0",
        "SURECHEMBL_REQUESTS_PER_SECOND": "100.0",
        "PATENTSVIEW_REQUESTS_PER_MINUTE": "1000.0",
        "SEARCH_MAX_SDQ_PATENTS": "50000",
        "SEARCH_MAX_RANKED_RESULTS": "200",
        "SEARCH_INCLUDE_EXPIRED": "true",
        "SEARCH_EXPIRED_GRACE_YEARS": "5",
        "OPS_CONSUMER_KEY": "test-ops-key",
        "OPS_CONSUMER_SECRET": "test-ops-secret",
        "OPS_REQUESTS_PER_MINUTE": "1000.0",
        "SEMANTIC_SCHOLAR_API_KEY": "test-s2-key",
        "SEMANTIC_SCHOLAR_REQUESTS_PER_SECOND": "100.0",
        "OPENALEX_API_KEY": "test@example.com",
        "OPENALEX_REQUESTS_PER_SECOND": "100.0",
        "LENS_API_KEY": "test-lens-key",
        "KIPRIS_API_KEY": "test-kipris-key",
        "PATENTSCOPE_USERNAME": "test-patentscope-user",
        "PATENTSCOPE_PASSWORD": "test-patentscope-pass",
        "EMBEDDING_RANKING_ENABLED": "false",
        "SEARCH_CITATION_TRAVERSAL_ENABLED": "false",
        "BIGQUERY_CACHE_ENABLED": "false",
        "LOG_LEVEL": "WARNING",
    }

    clear_settings_cache()
    with (
        patch.dict("os.environ", test_env),
        patch("praviar_pipeline.config.get_settings", wraps=get_settings) as mock,
    ):
        yield mock
    clear_settings_cache()
