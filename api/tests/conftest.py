"""Shared fixtures for API tests.

Overrides FastAPI dependencies so no real database, Clerk auth, or
external services are needed.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncGenerator
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from certification_keyring_fixtures import (
    TEST_REPORT_CERTIFICATION_PUBLIC_KEYRING,
    TEST_REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET,
)
from httpx import ASGITransport
from praviar_pipeline.checkpoint import (
    DEV_CHECKPOINT_HMAC_KEYRING_SECRET,
    CheckpointIntegrityKeyRing,
)
from praviar_pipeline.config import clear_settings_cache as clear_pipeline_settings_cache
from praviar_pipeline.models.patent import PatentSource, build_claim_text_provenance
from praviar_pipeline.models.report_source_spans import (
    SourceSpanReference,
    issue_source_span_attestation,
)
from praviar_pipeline.pipeline.runtime.evidence_policy import COMPONENT_TO_CATEGORY
from praviar_pipeline.report_certification_binding import (
    ReportCertificationSigner,
    sign_report_certification_binding,
)
from praviar_pipeline.utils.patent_ids import canonical_publication_id

from api.config import get_settings
from api.db.models import AnalysisStatus, UserRole

# ---------------------------------------------------------------------------
# Time anchor — fixture data uses relative dates so tests stay valid as the
# clock advances.  Anchored once per test process so a single run sees a
# consistent "now" across every fixture invocation.
# ---------------------------------------------------------------------------
_FIXTURE_NOW = datetime.now(UTC)
_DEFAULT_TEST_ORG_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


@pytest.fixture(autouse=True)
def _configure_ephemeral_report_certification_keys(
    monkeypatch: pytest.MonkeyPatch,
):
    """Keep report signing material test-only while exercising real settings."""
    monkeypatch.setenv(
        "REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET",
        TEST_REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET,
    )
    monkeypatch.setenv(
        "REPORT_CERTIFICATION_PUBLIC_KEYRING",
        TEST_REPORT_CERTIFICATION_PUBLIC_KEYRING,
    )
    # The history-free public snapshot intentionally contains no local .env.
    # Pipeline-backed API tests therefore install an unmistakably fake key in
    # process rather than depending on developer state or CI secrets.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    get_settings.cache_clear()
    clear_pipeline_settings_cache()
    yield
    get_settings.cache_clear()
    clear_pipeline_settings_cache()


def _rel_date(*, days_ago: int | None = None, days_from_now: int | None = None) -> str:
    """Return an ISO-8601 date string offset from the fixture anchor."""
    if days_ago is not None and days_from_now is not None:
        raise ValueError("specify only one of days_ago / days_from_now")
    if days_ago is not None:
        return (_FIXTURE_NOW - timedelta(days=days_ago)).date().isoformat()
    if days_from_now is not None:
        return (_FIXTURE_NOW + timedelta(days=days_from_now)).date().isoformat()
    return _FIXTURE_NOW.date().isoformat()


def _rel_datetime(*, days_ago: int = 0) -> str:
    """Return an ISO-8601 datetime string offset from the fixture anchor."""
    return (_FIXTURE_NOW - timedelta(days=days_ago)).isoformat()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_user(
    *,
    role: UserRole = UserRole.SCIENTIST,
    user_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
    email: str = "test@praviar.io",
    full_name: str = "Test User",
    clerk_user_id: str = "clerk_test_user",
) -> MagicMock:
    """Create a mock ``User`` ORM object with the requested attributes."""
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.org_id = org_id or _DEFAULT_TEST_ORG_ID
    user.role = role
    user.clerk_user_id = clerk_user_id
    user.email = email
    user.full_name = full_name
    user.preferences = {}
    user.last_active_at = None
    user.created_at = datetime.now(UTC)
    # ORM user principals are Clerk users. Explicitly set API-key-only fields so
    # MagicMock cannot synthesize a truthy ``api_key_id`` during actor binding.
    user.api_key_id = None
    user.api_key_scopes = ()
    return user


def make_mock_db() -> AsyncMock:
    """Return an ``AsyncMock`` that behaves like an ``AsyncSession``.

    Callers can customise return values via the mock's attributes, e.g.::

        db.execute.return_value.scalar_one_or_none.return_value = some_obj
        db.execute.return_value.scalars.return_value.all.return_value = [...]
        db.execute.return_value.scalar_one.return_value = 5
    """
    db = AsyncMock()
    # Pre-wire the most common result-chain patterns so tests only need to
    # override the final return value.
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    result_mock.scalar_one.return_value = 0
    result_mock.scalars.return_value.all.return_value = []

    db.execute.return_value = result_mock
    # Identity authority code uses PostgreSQL clock_timestamp() under row
    # locks. Individual hostile skew tests override this deterministic clock.
    db.scalar.return_value = datetime(2100, 1, 1, tzinfo=UTC)

    def _simulate_add(obj):
        """Simulate column defaults that SQLAlchemy would set on flush/insert.

        With a mock DB, neither Python-side ``default=`` nor ``server_default``
        values are applied.  We introspect the mapper to apply them so routes
        that return the ORM object pass Pydantic response-model validation.
        """
        try:
            from sqlalchemy import inspect as sa_inspect

            mapper = sa_inspect(type(obj))
            for col_attr in mapper.column_attrs:
                col = col_attr.columns[0]
                attr_name = col_attr.key
                current_val = getattr(obj, attr_name, None)
                if current_val is not None:
                    continue
                # Python-side default
                if col.default is not None:
                    if col.default.is_callable:
                        setattr(obj, attr_name, col.default.arg(None))
                    elif col.default.is_scalar:
                        setattr(obj, attr_name, col.default.arg)
                # Server-side default (approximate func.now() as datetime)
                elif col.server_default is not None and "now" in str(col.server_default.arg):
                    setattr(obj, attr_name, datetime.now(UTC))
        except Exception:
            # Fallback for non-mapped objects
            if hasattr(obj, "created_at") and obj.created_at is None:
                obj.created_at = datetime.now(UTC)
            if hasattr(obj, "updated_at") and obj.updated_at is None:
                obj.updated_at = datetime.now(UTC)

    db.add = MagicMock(side_effect=_simulate_add)
    db.delete = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def bind_report_data(
    report_data: dict,
    *,
    analysis_id: uuid.UUID | str,
    org_id: uuid.UUID | str = _DEFAULT_TEST_ORG_ID,
) -> dict:
    """Bind a test report to the exact owner context used by the API verifier."""
    report_data["report_certification_binding"] = sign_report_certification_binding(
        report_data,
        signer=ReportCertificationSigner.from_secret(
            TEST_REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET
        ),
        analysis_id=str(analysis_id),
        org_id=str(org_id),
    )
    return report_data


def make_analysis_mock(**kw) -> MagicMock:
    """Create a mock Analysis ORM object.  Superset of all test needs."""
    a = MagicMock()
    a.id = kw.get("id", uuid.uuid4())
    a.org_id = kw.get("org_id", _DEFAULT_TEST_ORG_ID)
    a.compound_input = kw.get("compound_input", "aspirin")
    a.compound_name = kw.get("compound_name", "Aspirin")
    a.compound_smiles = kw.get("compound_smiles", "CC(=O)Oc1ccccc1C(=O)O")
    a.status = kw.get("status", AnalysisStatus.COMPLETED)
    a.current_step = kw.get("current_step", 8)
    a.progress_pct = kw.get("progress_pct", 100.0)
    a.overall_risk = kw.get("overall_risk", "medium")
    a.blocking_patents_count = kw.get("blocking_patents_count", 3)
    a.total_patents_found = kw.get("total_patents_found", 42)
    a.executive_summary = kw.get("executive_summary", "Some summary")
    a.estimated_cost_usd = kw.get("estimated_cost_usd", 1.23)
    a.pipeline_duration_seconds = kw.get("pipeline_duration_seconds", 45.0)
    a.flagged_for_review = kw.get("flagged_for_review", False)
    a.config = kw.get("config", {})
    a.report_data = kw.get("report_data")
    if (
        isinstance(a.report_data, dict)
        and a.report_data.get("report_id")
        and "report_certification_binding" not in a.report_data
    ):
        bind_report_data(
            a.report_data,
            analysis_id=a.id,
            org_id=a.org_id,
        )
    a.share_active_grant_count = kw.get("share_active_grant_count", 0)
    a.share_active_until = kw.get("share_active_until")
    a.share_view_count = kw.get("share_view_count", 0)
    a.share_last_viewed_at = kw.get("share_last_viewed_at")
    a.created_at = kw.get("created_at", datetime.now(UTC))
    a.updated_at = kw.get("updated_at", datetime.now(UTC))
    a.pipeline_execution_id = kw.get("pipeline_execution_id")
    a.pipeline_reconciliation_generation = kw.get(
        "pipeline_reconciliation_generation",
        0,
    )
    a.pipeline_reconciliation_dispatched_at = kw.get("pipeline_reconciliation_dispatched_at")
    return a


def make_compound_mock(**kw) -> MagicMock:
    """Create a mock Compound ORM object."""
    c = MagicMock()
    c.id = kw.get("id", uuid.uuid4())
    c.canonical_smiles = kw.get("canonical_smiles", "CC(=O)Oc1ccccc1C(=O)O")
    c.inchi_key = kw.get("inchi_key", "BSYNRYMUTXBXSQ-UHFFFAOYSA-N")
    c.name = kw.get("name", "Aspirin")
    c.molecular_formula = kw.get("molecular_formula", "C9H8O4")
    c.molecular_weight = kw.get("molecular_weight", 180.16)
    c.functional_groups = kw.get("functional_groups", ["carboxyl", "ester"])
    c.pubchem_cid = kw.get("pubchem_cid", 2244)
    c.first_analyzed_at = kw.get("first_analyzed_at", datetime.now(UTC))
    c.analysis_count = kw.get("analysis_count", 3)
    return c


def make_comment_mock(**kw) -> MagicMock:
    """Create a mock Comment ORM object."""
    c = MagicMock()
    c.id = kw.get("id", uuid.uuid4())
    c.analysis_id = kw.get("analysis_id", uuid.uuid4())
    c.org_id = kw.get("org_id", uuid.uuid4())
    c.user_id = kw.get("user_id", uuid.uuid4())
    c.parent_id = kw.get("parent_id")
    c.target_type = kw.get("target_type", "analysis")
    c.target_id = kw.get("target_id", "")
    c.body = kw.get("body", "This looks like a high-risk patent.")
    c.mentions = kw.get("mentions", [])
    c.resolved = kw.get("resolved", False)
    c.resolved_by = kw.get("resolved_by")
    c.resolved_at = kw.get("resolved_at")
    c.assigned_to = kw.get("assigned_to")
    c.assigned_by = kw.get("assigned_by")
    c.assigned_at = kw.get("assigned_at")
    c.created_at = kw.get("created_at", datetime.now(UTC))
    return c


def make_preset_mock(**kw) -> MagicMock:
    """Create a mock ConfigPreset ORM object."""
    p = MagicMock()
    p.id = kw.get("id", uuid.uuid4())
    p.org_id = kw.get("org_id", uuid.uuid4())
    p.created_by = kw.get("created_by", uuid.uuid4())
    p.name = kw.get("name", "Standard FTO")
    p.description = kw.get("description", "Default config preset")
    p.config = kw.get("config", {"max_analysis_patents": 20})
    p.is_default = kw.get("is_default", False)
    p.created_at = kw.get("created_at", datetime.now(UTC))
    return p


def _sync_authority_coverage(report: dict) -> None:
    """Mirror authority counts/categories from the canonical evidence index."""
    evidence_index = report["matter_evidence_index"]
    patent_records = evidence_index.get("patent_records") or []
    authoritative_categories = sorted(
        {
            category
            for record in patent_records
            if isinstance(record, dict)
            for category in record.get("authoritative_record_categories") or []
            if isinstance(category, str) and category.strip()
        }
    )
    required_categories = {
        COMPONENT_TO_CATEGORY[component]
        for component in report["record_completeness"].get("required_components", [])
        if component in COMPONENT_TO_CATEGORY
    }
    patents_with_authority = sum(
        1
        for record in patent_records
        if isinstance(record, dict)
        and any(
            isinstance(category, str) and category.strip()
            for category in record.get("authoritative_record_categories") or []
        )
    )
    material_patent_count = int(evidence_index.get("material_patent_count") or 0)
    report["authority_coverage"] = {
        "policy": "official_plus_licensed",
        "authoritative_source_names": list(evidence_index.get("authoritative_source_names") or []),
        "supporting_source_names": list(evidence_index.get("supporting_source_names") or []),
        "authoritative_categories_covered": authoritative_categories,
        "authoritative_categories_missing": sorted(
            required_categories - set(authoritative_categories)
        ),
        "patents_with_authoritative_records": patents_with_authority,
        "patents_without_authoritative_records": max(
            0, material_patent_count - patents_with_authority
        ),
        "clearance_grade_ready_patents": len(
            {
                patent_id
                for patent_id in evidence_index.get("clearance_grade_ready_patent_ids", [])
                if isinstance(patent_id, str) and patent_id.strip()
            }
        ),
    }


def _canonical_fixture_patent_id(value: object) -> str:
    """Canonicalize valid fixture IDs while preserving hostile inputs for rejection tests."""
    patent_id = str(value or "").strip()
    try:
        return canonical_publication_id(patent_id)
    except ValueError:
        return patent_id


def valid_report_data(**overrides) -> dict:
    """Return a minimal but schema-valid FTO report dict."""
    report_id = str(uuid.uuid4())
    claims_text = "1. Representative claim text and evidence span for tests."
    claim_provenance = build_claim_text_provenance(
        patent_id="US12345678A1",
        claims_text=claims_text,
        source=PatentSource.PATENTSVIEW,
        artifact_locator=("https://search.patentsview.org/api/v1/patent/?patent_id=US12345678A1"),
        collector_identity="runtime.patentsview_claims",
        retrieved_at=_FIXTURE_NOW,
    ).model_dump(mode="json")
    fixture_keyring = CheckpointIntegrityKeyRing.from_secret(DEV_CHECKPOINT_HMAC_KEYRING_SECRET)
    verified_claim_span = issue_source_span_attestation(
        SourceSpanReference(
            span_id="span-test-1",
            source_type="verified_claim_text",
            patent_id="US12345678A1",
            claim_number=1,
            element_number=1,
            citation="US12345678A1 claim 1",
            excerpt=claims_text,
            source_document_id="US12345678A1",
            source_name="patentsview",
            source_text_sha256=claim_provenance["artifact_sha256"],
            source_retrieved_at=claim_provenance["retrieved_at"],
            source_artifact_locator=claim_provenance["artifact_locator"],
            collector_identity=claim_provenance["collector_identity"],
            collector_version=claim_provenance["collector_version"],
            provenance_schema_version=claim_provenance["schema_version"],
            claim_numbers=claim_provenance["claim_numbers"],
            independent_claim_numbers=claim_provenance["independent_claim_numbers"],
            retrieval_complete=claim_provenance["retrieval_complete"],
            provenance_cassette_sha256=claim_provenance["cassette_sha256"],
        ),
        signing_key=fixture_keyring.active_key(),
        key_id=fixture_keyring.active_key_id,
        subject_id=report_id,
    ).model_dump(mode="json")
    report = {
        "report_id": report_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "praviar_pipeline_version": "0.1.0-test",
        "compound": {
            "name": "aspirin",
            "canonical_smiles": "CC(=O)Oc1ccccc1C(O)=O",
            "inchi": "InChI=1S/C9H8O4/c1-6(10)13-8-5-3-2-4-7(8)9(11)12/h2-5H,1H3,(H,11,12)",
            "inchi_key": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
            "pubchem_cid": 2244,
            "molecular_formula": "C9H8O4",
            "original_input": "aspirin",
            "input_type": "name",
        },
        "risk_summary": {
            "overall_risk": "medium",
            "blocking_patents_count": 0,
            "total_patents_analyzed": 1,
            "key_risks": ["Patent US12345678 covers core structure"],
            "executive_summary": (
                "Clearance decision: UNCLEAR. 0 blocking patents identified from 1 analyzed."
            ),
        },
        "clearance_decision": {
            "decision": "unclear",
            "decision_confidence": 0.62,
            "evidence_quality": 0.71,
            "decision_reasoning": ["Evidence remains mixed."],
            "decision_audit": {
                "queried_sources_count": 2,
                "successful_sources_count": 1,
                "material_patents_reviewed": 1,
                "material_us_patents": 1,
                "material_ep_patents": 0,
                "patents_with_claims": 1,
                "patents_with_family": 1,
                "us_patents_with_prosecution_context": 1,
                "us_patents_with_file_wrapper_dossier": 0,
                "ep_patents_with_register_context": 0,
                "analysis_failures_count": 1,
                "authoritative_sources_count": 1,
                "clearance_grade_ready_patents": 0,
                "incomplete_material_patents": 1,
                "clearance_grade_ready_families": 0,
                "incomplete_material_families": 1,
                "failed_sources": ["bigquery"],
                "evidence_sufficient_for_clearance": False,
                "insufficiency_reasons": [],
                "evidence_warnings": [],
                "search_iterations": 2,
                "coverage_summary": {
                    "queried_source_names": ["pubchem_sdq", "bigquery"],
                    "successful_source_names": ["pubchem_sdq"],
                    "failed_source_names": ["bigquery"],
                    "authoritative_source_names": ["patentsview"],
                    "supporting_source_names": ["bigquery", "pubchem_sdq"],
                    "reviewed_patent_ids": ["US12345678A1"],
                    "reviewed_us_patent_ids": ["US12345678A1"],
                    "reviewed_ep_patent_ids": [],
                    "patents_missing_claims": [],
                    "patents_missing_claim_level_analysis": [],
                    "patents_missing_authoritative_records": [],
                    "patents_missing_family_context": [],
                    "us_patents_missing_prosecution_context": [],
                    "us_patents_missing_file_wrapper_dossier": ["US12345678A1"],
                    "ep_patents_missing_register_context": [],
                    "failed_analysis_patent_ids": ["EP0000001A1"],
                    "clearance_grade_ready_patent_ids": [],
                    "incomplete_patent_ids": ["US12345678A1"],
                    "clearance_grade_ready_family_ids": [],
                    "incomplete_family_ids": ["fam-123"],
                    "verification_gaps": [],
                    "required_record_components": [
                        "claims_text",
                        "claim_level_analysis",
                        "authoritative_records",
                        "family_context",
                        "us_file_wrapper_dossier",
                        "verification",
                    ],
                },
                "claim_program_summary": {
                    "total_claim_programs_reviewed": 1,
                    "patent_level_fallback_count": 0,
                    "blocking_claim_ids": [],
                    "contested_claim_ids": [],
                    "medium_risk_claim_ids": ["US12345678A1#claim1"],
                    "claims_with_strong_invalidity": [],
                    "claims_with_insufficient_evidence": ["US12345678A1#claim1"],
                    "blocking_patent_ids": [],
                    "contested_patent_ids": [],
                    "medium_risk_patent_ids": ["US12345678A1"],
                },
                "decisive_references": [
                    {
                        "category": "prosecution_signal",
                        "summary": "file-wrapper context available, amendment signal detected",
                        "patent_id": "US12345678A1",
                        "jurisdiction": "US",
                        "source_name": "",
                        "signal": "narrowing_signal,pending_family_signal",
                    }
                ],
            },
        },
        "decision_scope": {
            "matter_type": "small_molecule",
            "jurisdictions": ["US"],
            "asset_classes": ["compound", "formulation", "process"],
            "supports_positive_clearance": True,
            "summary": "US evidence is within the certified decision scope for this matter.",
        },
        "supporting_scope": {
            "matter_type": "small_molecule",
            "jurisdictions": [],
            "asset_classes": ["compound", "formulation", "process"],
            "supports_positive_clearance": False,
            "summary": "No supporting-only jurisdictions were material in this matter.",
        },
        "certification_scope": {
            "certified_jurisdictions": ["US", "EP"],
            "supported_jurisdictions": ["US", "EP", "UK", "IN", "JP", "CN"],
            "certified_matter_types": ["small_molecule", "formulation", "process"],
            "certified_asset_classes": ["compound", "formulation", "process"],
            "attorney_supervised_matter_types": [],
            "attorney_supervised_asset_classes": [],
            "supporting_only_jurisdictions": [],
            "current_matter_type_certified": True,
            "attorney_supervision_required": False,
            "evidence_verified": True,
            "evidence_verification_status": "valid",
            "evidence_receipt_id": "test-release-receipt",
            "evidence_receipt_sha256": "a" * 64,
            "evidence_pipeline_git_sha": "b" * 40,
            "evidence_source_tree_sha256": "c" * 64,
            "evidence_expires_at": "2099-01-01T00:00:00Z",
            "evidence_issuer_verifier_id": "test-release-verifier",
            "evidence_key_id": "test-release-key",
            "evidence_gate_run_id": "test-gate-run",
            "evidence_benchmark_aggregate_sha256": "d" * 64,
            "verified_lane_ids": ["us-small-molecule-compound-adaptive-v1"],
            "evidence_failures": [],
            "summary": "Direct-clearance certification currently covers US and EP small-molecule, formulation, and process cohorts.",
        },
        "cohort_status": "certified",
        "jurisdiction_decisions": [
            {
                "jurisdiction": "US",
                "decision": "unclear",
                "decision_confidence": 0.62,
                "evidence_quality": 0.71,
                "evidence_sufficient_for_clearance": False,
                "supports_positive_clearance": True,
                "lane_status": "counsel_ready",
                "local_review_required": False,
                "authority_grade": "authoritative",
                "gate_failures": ["Evidence remains mixed across the reviewed US record."],
                "reviewed_patent_ids": ["US12345678A1"],
                "blocking_patent_ids": [],
                "reasoning": ["Reviewed 1 material US patent."],
            }
        ],
        "patent_analyses": [],
        "claim_source_span_map": {
            "generated_from": "test_fixture",
            "entries": [
                {
                    "assertion_id": "assertion-test-supported-1",
                    "patent_id": "US12345678A1",
                    "claim_number": 1,
                    "element_number": 1,
                    "report_section": "claim_element_analysis",
                    "assertion_text": "Claim 1 element 1 was assessed as partially_met.",
                    "source_span_ids": ["span-test-1"],
                    "support_status": "supported",
                    "customer_visible": True,
                    "review_required": False,
                }
            ],
            "spans": {"span-test-1": verified_claim_span},
            "unsupported_customer_visible_claim_count": 0,
            "needs_review_count": 0,
        },
        "patent_details": {
            "US12345678A1": {
                "claims_text": claims_text,
                "claims_text_source": "patentsview",
                "claims_text_provenance": claim_provenance,
            }
        },
        "doe_assessments": [],
        "invalidity_assessments": [],
        "verification": {
            "checks": [
                {
                    "check_name": "citations",
                    "passed": True,
                    "severity": "pass",
                    "details": "All cited patent IDs resolved against the final matter record.",
                },
                {
                    "check_name": "claims_grounded",
                    "passed": True,
                    "severity": "pass",
                    "details": "Quoted claim text matched the retrieved source text.",
                },
                {
                    "check_name": "risk_levels_justified",
                    "passed": True,
                    "severity": "pass",
                    "details": "Risk labels remained consistent with element-level findings.",
                },
            ],
            "all_citations_valid": True,
            "all_claims_grounded": True,
            "all_entities_valid": True,
            "dates_consistent": True,
            "risk_levels_justified": True,
            "issues": [],
        },
        "prosecution_findings": [
            {
                "patent_id": "US12345678A1",
                "jurisdiction": "US",
                "application_number": "12/345678",
                "prosecution_history_available": True,
                "transaction_count": 4,
                "amendment_event_count": 1,
                "office_action_count": 1,
                "continuity_entry_count": 1,
                "narrowing_signal": True,
                "terminal_disclaimer": False,
                "terminal_disclaimer_linked_patent": "",
                "ptab_challenged": False,
                "ptab_proceeding_count": 0,
                "pending_family_signal": True,
                "pending_family_member_count": 1,
                "office_action_types": ["non_final_office_action"],
                "amendment_types": ["after_final_response", "rce"],
                "continuity_types": ["continuation"],
                "rejection_bases": ["103", "prior_art"],
                "estoppel_risk_flags": [
                    "after_final_response_history",
                    "rce_history",
                    "continuation_lineage",
                    "prior_art_rejection_history",
                ],
                "continuation_parent_count": 1,
                "continuation_child_count": 0,
                "divisional_parent_count": 0,
                "divisional_child_count": 0,
                "cip_parent_count": 0,
                "cip_child_count": 0,
                "response_after_final_count": 1,
                "rce_count": 1,
                "interview_event_count": 0,
                "appeal_event_count": 0,
                "record_basis": [
                    "application_number",
                    "uspto_transactions",
                    "family_members",
                ],
                "summary": "file-wrapper context available, 4 prosecution transactions captured, 1 amendment signal(s) detected, 1 pending family member(s) detected",
            }
        ],
        "prosecution_dossiers": [
            {
                "patent_id": "US12345678A1",
                "jurisdiction": "US",
                "application_number": "12/345678",
                "source_name": "uspto_odp",
                "sections_available": ["office_actions", "continuity", "amendments"],
                "office_actions_summary": f"- [CTNF] Non-final office action ({_rel_date(days_ago=480)})",
                "continuity_summary": f"- Parent: 11/111111 (CON, filed {_rel_date(days_ago=1095)})",
                "amendments_summary": f"- [AMND] Amendment after final ({_rel_date(days_ago=420)})",
                "office_action_events": [
                    {
                        "document_code": "CTNF",
                        "description": "Non-final office action under 35 U.S.C. 103",
                        "event_date": _rel_date(days_ago=480),
                        "office_action_type": "non_final_office_action",
                        "rejection_bases": ["103", "prior_art"],
                    }
                ],
                "continuity_entries": [
                    {
                        "relationship": "parent",
                        "application_number": "11/111111",
                        "related_application_number": "",
                        "continuity_type": "continuation",
                        "filing_date": _rel_date(days_ago=1095),
                    }
                ],
                "amendment_events": [
                    {
                        "transaction_code": "AMND",
                        "description": "Amendment after final",
                        "event_date": _rel_date(days_ago=420),
                        "event_type": "after_final_response",
                    },
                    {
                        "transaction_code": "RCE",
                        "description": "Request for Continued Examination",
                        "event_date": _rel_date(days_ago=390),
                        "event_type": "rce",
                    },
                ],
                "office_action_count": 1,
                "continuity_entry_count": 1,
                "amendment_entry_count": 2,
                "office_action_types": ["non_final_office_action"],
                "amendment_types": ["after_final_response", "rce"],
                "continuity_types": ["continuation"],
                "rejection_bases": ["103", "prior_art"],
                "estoppel_risk_flags": [
                    "after_final_response_history",
                    "rce_history",
                    "continuation_lineage",
                    "prior_art_rejection_history",
                ],
                "continuation_parent_count": 1,
                "continuation_child_count": 0,
                "divisional_parent_count": 0,
                "divisional_child_count": 0,
                "cip_parent_count": 0,
                "cip_child_count": 0,
                "response_after_final_count": 1,
                "rce_count": 1,
                "interview_event_count": 0,
                "appeal_event_count": 0,
                "narrowing_signal": True,
                "terminal_disclaimer": False,
                "terminal_disclaimer_linked_patent": "",
                "ptab_challenged": False,
                "pending_family_signal": True,
                "record_basis": [
                    "uspto_odp",
                    "application_number",
                    "uspto_transactions",
                    "family_members",
                ],
                "summary": "1 office action record(s) summarized, 1 continuity record(s) summarized, 1 amendment/response record(s) summarized, pending family member signal present",
            }
        ],
        "claim_construction_record": {
            "standard": "Phillips claim construction for U.S. infringement-risk assessment",
            "jurisdictions": ["US"],
            "assumptions": ["Issued claim text was prioritized."],
            "disputed_terms": [],
            "summary": "Conservative claim construction defaults were applied.",
        },
        "future_risk": [
            {
                "patent_id": "US12345678A1",
                "jurisdiction": "US",
                "risk_type": "pending_family",
                "severity": "high",
                "monitoring_required": True,
                "related_patent_ids": ["US12345678A1"],
                "record_basis": ["family_members"],
                "summary": "Pending family members remain open.",
            }
        ],
        "commercial_exposure": {
            "damages_injunction_risk": "elevated",
            "business_severity": "high",
            "blocking_patent_ids": [],
            "rationale": ["Monitoring and escalation remain required."],
            "summary": "Commercial launch posture remains non-clearance-grade.",
        },
        "claim_program_decisions": [
            {
                "patent_id": "US12345678A1",
                "claim_number": 1,
                "jurisdiction": "US",
                "literal_outcome": "partially_met",
                "literal_risk": "medium",
                "doe_risk": "not_assessed",
                "invalidity_strength": "",
                "prosecution_risk_flags": ["narrowing_signal", "pending_family_signal"],
                "prosecution_risk_level": "medium",
                "post_grant_risk_level": "",
                "scope_constrained": False,
                "future_risk_flags": ["pending_family"],
                "commercial_severity": "medium",
                "evidence_sufficient": False,
                "missing_components": ["us_file_wrapper_dossier"],
                "record_basis": ["application_number", "family_members"],
                "rationale": [
                    "Independent claim partially overlaps the target compound profile.",
                    "Claim remains only screening-grade because the record is incomplete.",
                ],
            }
        ],
        "evidence_artifacts": [
            {
                "artifact_id": "US12345678A1:search_hit",
                "artifact_type": "search_hit",
                "source_name": "pubchem_sdq,bigquery",
                "authority_tier": "authoritative",
                "jurisdiction": "US",
                "patent_id": "US12345678A1",
                "family_id": "fam-123",
                "summary": "Patent was retained as a material record in the final matter.",
                "record_basis": ["pubchem_sdq", "bigquery"],
                "linked_node_ids": ["patent:US12345678A1", "family:fam-123"],
            }
        ],
        "evidence_adapter_results": [
            {
                "adapter_name": "pubchem_sdq",
                "adapter_kind": "search",
                "authority_tier": "supporting",
                "status": "ok",
                "collection_state": "collected",
                "required_before_clear": False,
                "target_patent_ids": ["US12345678A1"],
                "covered_patent_ids": ["US12345678A1"],
                "missing_patent_ids": [],
                "artifacts": [],
                "warnings": [],
                "freshness_note": "Record captured during the current pipeline run.",
                "artifact_count": 0,
                "covered_components": [],
                "expected_components": [],
                "missing_components": [],
                "supports_authoritative_findings": False,
            },
            {
                "adapter_name": "patentsview",
                "adapter_kind": "search",
                "authority_tier": "authoritative",
                "status": "ok",
                "collection_state": "missing",
                "required_before_clear": True,
                "target_patent_ids": ["US12345678A1"],
                "covered_patent_ids": [],
                "missing_patent_ids": ["US12345678A1"],
                "artifacts": [],
                "warnings": [],
                "freshness_note": "",
                "artifact_count": 0,
                "covered_components": [],
                "expected_components": ["claims_text"],
                "missing_components": ["claims_text"],
                "supports_authoritative_findings": True,
            },
        ],
        "collector_runs": [
            {
                "definition": {
                    "collector_name": "pubchem_sdq",
                    "adapter_kind": "search",
                    "authority_tier": "supporting",
                    "supports_authoritative_findings": False,
                    "expected_components": [],
                },
                "collection_state": "collected",
                "required_before_clear": False,
                "target_patent_ids": ["US12345678A1"],
                "covered_patent_ids": ["US12345678A1"],
                "missing_patent_ids": [],
                "expected_components": [],
                "covered_components": [],
                "missing_components": [],
                "retry_budget_remaining": 0,
                "freshness_note": "Record captured during the current pipeline run.",
                "triggered_directive_ids": [],
                "collection_targets": [
                    {
                        "patent_id": "US12345678A1",
                        "jurisdiction": "US",
                        "required_components": [],
                        "covered_components": [],
                        "missing_components": [],
                        "required_before_clear": False,
                    }
                ],
                "attempts": [
                    {
                        "attempt_number": 1,
                        "status": "ok",
                        "collection_state": "collected",
                        "artifact_count": 0,
                        "warnings": [],
                        "rate_limit_remaining": None,
                        "retry_after_seconds": None,
                        "summary": "Collector satisfied the currently targeted matter records.",
                    }
                ],
            },
            {
                "definition": {
                    "collector_name": "patentsview",
                    "adapter_kind": "search",
                    "authority_tier": "authoritative",
                    "supports_authoritative_findings": True,
                    "expected_components": ["claims_text"],
                },
                "collection_state": "missing",
                "required_before_clear": True,
                "target_patent_ids": ["US12345678A1"],
                "covered_patent_ids": [],
                "missing_patent_ids": ["US12345678A1"],
                "expected_components": ["claims_text"],
                "covered_components": [],
                "missing_components": ["claims_text"],
                "retry_budget_remaining": 0,
                "freshness_note": "",
                "triggered_directive_ids": [],
                "collection_targets": [
                    {
                        "patent_id": "US12345678A1",
                        "jurisdiction": "US",
                        "required_components": ["claims_text"],
                        "covered_components": [],
                        "missing_components": ["claims_text"],
                        "required_before_clear": True,
                    }
                ],
                "attempts": [
                    {
                        "attempt_number": 1,
                        "status": "ok",
                        "collection_state": "missing",
                        "artifact_count": 0,
                        "warnings": [],
                        "rate_limit_remaining": None,
                        "retry_after_seconds": None,
                        "summary": "Collector has not yet satisfied all required targets.",
                    }
                ],
            },
        ],
        "evidence_collection_plan": [
            {
                "directive_id": "collect_us_file_wrapper_dossier:US12345678A1:",
                "directive_type": "collect_us_file_wrapper_dossier",
                "priority": "critical",
                "required_before_clear": True,
                "target_patent_ids": ["US12345678A1"],
                "target_claim_ids": [],
                "target_jurisdictions": ["US"],
                "recommended_adapters": ["uspto_odp"],
                "summary": "Collect dossier-grade U.S. file-wrapper records for material patents still missing them.",
                "rationale": "A positive U.S. clearance conclusion requires dossier-grade prosecution coverage.",
            }
        ],
        "coverage_gaps": [
            {
                "gap_type": "missing_us_file_wrapper_dossier",
                "description": "A dossier-grade U.S. file wrapper is required for a clearance-grade record.",
                "suggested_action": "Collect and normalize us_file_wrapper_dossier before issuing a positive clearance conclusion.",
            }
        ],
        "matter_graph": {
            "nodes": [
                {
                    "node_id": "compound:aspirin",
                    "node_type": "compound_variant",
                    "label": "aspirin",
                },
                {
                    "node_id": "patent:US12345678A1",
                    "node_type": "patent",
                    "label": "US12345678A1",
                    "jurisdiction": "US",
                    "patent_id": "US12345678A1",
                    "family_id": "fam-123",
                    "application_number": "12/345678",
                },
                {
                    "node_id": "family:fam-123",
                    "node_type": "family",
                    "label": "fam-123",
                    "family_id": "fam-123",
                },
            ],
            "edges": [
                {
                    "edge_type": "roots",
                    "from_node_id": "compound:aspirin",
                    "to_node_id": "patent:US12345678A1",
                    "summary": "material patent",
                },
                {
                    "edge_type": "belongs_to_family",
                    "from_node_id": "patent:US12345678A1",
                    "to_node_id": "family:fam-123",
                    "summary": "family context",
                },
            ],
        },
        "matter_graph_summary": {
            "root_compound": "aspirin",
            "node_count": 5,
            "edge_count": 4,
            "node_counts_by_type": {
                "compound_variant": 1,
                "patent": 1,
                "family": 1,
                "application": 1,
                "claim": 1,
            },
            "edge_counts_by_type": {
                "roots": 1,
                "belongs_to_family": 1,
                "prosecuted_as": 1,
                "contains_claim": 1,
            },
            "patent_node_ids": ["patent:US12345678A1"],
            "family_node_ids": ["family:fam-123"],
        },
        "matter_store": {
            "matter_graph": {
                "nodes": [
                    {
                        "node_id": "compound:aspirin",
                        "node_type": "compound_variant",
                        "label": "aspirin",
                    },
                    {
                        "node_id": "patent:US12345678A1",
                        "node_type": "patent",
                        "label": "US12345678A1",
                        "jurisdiction": "US",
                        "patent_id": "US12345678A1",
                        "family_id": "fam-123",
                        "application_number": "12/345678",
                    },
                    {
                        "node_id": "family:fam-123",
                        "node_type": "family",
                        "label": "fam-123",
                        "family_id": "fam-123",
                    },
                ],
                "edges": [
                    {
                        "edge_type": "roots",
                        "from_node_id": "compound:aspirin",
                        "to_node_id": "patent:US12345678A1",
                        "summary": "material patent",
                    },
                    {
                        "edge_type": "belongs_to_family",
                        "from_node_id": "patent:US12345678A1",
                        "to_node_id": "family:fam-123",
                        "summary": "family context",
                    },
                ],
            },
            "matter_graph_summary": {
                "root_compound": "aspirin",
                "node_count": 5,
                "edge_count": 4,
                "node_counts_by_type": {
                    "compound_variant": 1,
                    "patent": 1,
                    "family": 1,
                    "application": 1,
                    "claim": 1,
                },
                "edge_counts_by_type": {
                    "roots": 1,
                    "belongs_to_family": 1,
                    "prosecuted_as": 1,
                    "contains_claim": 1,
                },
                "patent_node_ids": ["patent:US12345678A1"],
                "family_node_ids": ["family:fam-123"],
            },
            "matter_evidence_index": {
                "source_names": ["pubchem_sdq", "bigquery"],
                "authoritative_source_names": ["patentsview"],
                "supporting_source_names": ["bigquery", "pubchem_sdq"],
                "material_patent_count": 1,
                "family_count": 1,
                "analysis_failure_patent_ids": ["EP0000001A1"],
                "critic_flagged_patent_ids": ["US12345678A1"],
                "clearance_grade_ready_patent_ids": [],
                "incomplete_patent_ids": ["US12345678A1"],
                "clearance_grade_ready_family_ids": [],
                "incomplete_family_ids": ["fam-123"],
                "patent_records": [],
                "family_records": [],
            },
            "prosecution_dossiers": [
                {
                    "patent_id": "US12345678A1",
                    "jurisdiction": "US",
                    "application_number": "12/345678",
                    "source_name": "uspto_odp",
                    "sections_available": ["office_actions", "continuity", "amendments"],
                    "office_actions_summary": "- [CTNF] Non-final rejection",
                    "continuity_summary": "- [CONT] Continuation from parent application",
                    "amendments_summary": "- [AMND] Amendment after final",
                    "office_action_events": [
                        {
                            "document_code": "CTNF",
                            "description": "Non-final rejection under 35 U.S.C. 103",
                            "event_date": _rel_date(days_ago=470),
                            "office_action_type": "non_final_office_action",
                            "rejection_bases": ["103", "prior_art"],
                        }
                    ],
                    "continuity_entries": [
                        {
                            "relationship_type": "continuation",
                            "related_application_number": "11/111111",
                            "status": "pending",
                            "jurisdiction": "US",
                        }
                    ],
                    "amendment_events": [
                        {
                            "transaction_code": "AMND",
                            "description": "Amendment after final",
                            "event_date": _rel_date(days_ago=440),
                            "event_type": "after_final_response",
                        }
                    ],
                    "office_action_count": 1,
                    "continuity_entry_count": 1,
                    "amendment_entry_count": 1,
                    "office_action_types": ["non_final_office_action"],
                    "amendment_types": ["after_final_response"],
                    "rejection_bases": ["103", "prior_art"],
                    "estoppel_risk_flags": [
                        "after_final_response_history",
                        "continuation_lineage",
                    ],
                    "response_after_final_count": 1,
                    "rce_count": 0,
                    "record_basis": [
                        "uspto_odp",
                        "application_number",
                        "uspto_transactions",
                        "family_members",
                    ],
                    "summary": "Structured prosecution dossier captured from the runtime cache.",
                }
            ],
            "claim_program_decisions": [
                {
                    "patent_id": "US12345678A1",
                    "claim_number": 1,
                    "jurisdiction": "US",
                    "literal_outcome": "partially_met",
                    "literal_risk": "medium",
                    "doe_risk": "not_assessed",
                    "invalidity_strength": "",
                    "prosecution_risk_flags": [
                        "narrowing_signal",
                        "pending_family_signal",
                    ],
                    "future_risk_flags": ["pending_family"],
                    "commercial_severity": "medium",
                    "evidence_sufficient": False,
                    "missing_components": ["us_file_wrapper_dossier"],
                    "rationale": [
                        "Independent claim partially overlaps the target compound profile."
                    ],
                }
            ],
            "evidence_artifacts": [
                {
                    "artifact_id": "US12345678A1:search_hit",
                    "artifact_type": "search_hit",
                    "source_name": "pubchem_sdq,bigquery",
                    "authority_tier": "authoritative",
                    "jurisdiction": "US",
                    "patent_id": "US12345678A1",
                    "family_id": "fam-123",
                    "summary": "Patent was retained as a material record in the final matter.",
                    "record_basis": ["pubchem_sdq", "bigquery"],
                    "linked_node_ids": ["patent:US12345678A1", "family:fam-123"],
                }
            ],
            "evidence_adapter_results": [
                {
                    "adapter_name": "pubchem_sdq",
                    "adapter_kind": "search",
                    "authority_tier": "supporting",
                    "status": "ok",
                    "collection_state": "collected",
                    "required_before_clear": False,
                    "target_patent_ids": ["US12345678A1"],
                    "covered_patent_ids": ["US12345678A1"],
                    "missing_patent_ids": [],
                    "artifacts": [],
                    "warnings": [],
                    "freshness_note": "Record captured during the current pipeline run.",
                    "artifact_count": 0,
                    "covered_components": [],
                    "expected_components": [],
                    "missing_components": [],
                    "supports_authoritative_findings": False,
                }
            ],
            "collector_runs": [
                {
                    "definition": {
                        "collector_name": "pubchem_sdq",
                        "adapter_kind": "search",
                        "authority_tier": "supporting",
                        "supports_authoritative_findings": False,
                        "expected_components": [],
                    },
                    "collection_state": "collected",
                    "required_before_clear": False,
                    "target_patent_ids": ["US12345678A1"],
                    "covered_patent_ids": ["US12345678A1"],
                    "missing_patent_ids": [],
                    "expected_components": [],
                    "covered_components": [],
                    "missing_components": [],
                    "retry_budget_remaining": 0,
                    "freshness_note": "Record captured during the current pipeline run.",
                    "triggered_directive_ids": [],
                    "collection_targets": [
                        {
                            "patent_id": "US12345678A1",
                            "jurisdiction": "US",
                            "required_components": [],
                            "covered_components": [],
                            "missing_components": [],
                            "required_before_clear": False,
                        }
                    ],
                    "attempts": [
                        {
                            "attempt_number": 1,
                            "status": "ok",
                            "collection_state": "collected",
                            "artifact_count": 0,
                            "warnings": [],
                            "rate_limit_remaining": None,
                            "retry_after_seconds": None,
                            "summary": "Collector satisfied the currently targeted matter records.",
                        }
                    ],
                }
            ],
            "evidence_collection_plan": [
                {
                    "directive_id": "collect_us_file_wrapper_dossier:US12345678A1:",
                    "directive_type": "collect_us_file_wrapper_dossier",
                    "priority": "critical",
                    "required_before_clear": True,
                    "target_patent_ids": ["US12345678A1"],
                    "target_claim_ids": [],
                    "target_jurisdictions": ["US"],
                    "recommended_adapters": ["uspto_odp"],
                    "summary": "Collect dossier-grade U.S. file-wrapper records for material patents still missing them.",
                    "rationale": "A positive U.S. clearance conclusion requires dossier-grade prosecution coverage.",
                }
            ],
            "coverage_gaps": [
                {
                    "gap_type": "missing_us_file_wrapper_dossier",
                    "description": "A dossier-grade U.S. file wrapper is required for a clearance-grade record.",
                    "suggested_action": "Collect and normalize us_file_wrapper_dossier before issuing a positive clearance conclusion.",
                }
            ],
            "authority_coverage": {
                "policy": "official_plus_licensed",
                "authoritative_source_names": ["patentsview"],
                "supporting_source_names": ["bigquery", "pubchem_sdq"],
                "authoritative_categories_covered": [
                    "authoritative_search_source",
                    "family_record",
                    "priority_record",
                    "us_prosecution_record",
                ],
                "authoritative_categories_missing": ["us_file_wrapper_dossier"],
                "patents_with_authoritative_records": 1,
                "patents_without_authoritative_records": 0,
                "clearance_grade_ready_patents": 0,
            },
            "record_completeness": {
                "profile": "world_class_us_ep",
                "matter_type": "small_molecule",
                "jurisdictions": ["US"],
                "required_components": [
                    "claims_text",
                    "claim_level_analysis",
                    "authoritative_records",
                    "family_context",
                    "us_file_wrapper_dossier",
                    "verification",
                ],
                "missing_components": ["us_file_wrapper_dossier"],
                "blocking_gaps": [
                    "A dossier-grade U.S. file wrapper is required for a clearance-grade record."
                ],
                "clearance_grade_ready": False,
            },
            "run_observability": {
                "authoritative_source_hit_rate": 0.0,
                "claims_text_coverage": 1.0,
                "family_context_coverage": 1.0,
                "us_file_wrapper_dossier_coverage": 0.0,
                "ep_register_coverage": 1.0,
                "failed_adapter_names": [],
                "false_clear_risk_flags": ["medium_risk_claims", "record_incomplete"],
                "unresolved_contradictions": [],
            },
            "record_contradictions": [],
        },
        "authority_coverage": {
            "policy": "official_plus_licensed",
            "authoritative_source_names": ["patentsview"],
            "supporting_source_names": ["bigquery", "pubchem_sdq"],
            "authoritative_categories_covered": [
                "authoritative_search_source",
                "family_record",
                "priority_record",
                "us_prosecution_record",
            ],
            "authoritative_categories_missing": ["us_file_wrapper_dossier"],
            "patents_with_authoritative_records": 1,
            "patents_without_authoritative_records": 0,
            "clearance_grade_ready_patents": 0,
        },
        "record_completeness": {
            "profile": "world_class_us_ep",
            "matter_type": "small_molecule",
            "jurisdictions": ["US"],
            "required_components": [
                "claims_text",
                "claim_level_analysis",
                "authoritative_records",
                "family_context",
                "us_file_wrapper_dossier",
                "verification",
            ],
            "missing_components": ["us_file_wrapper_dossier"],
            "blocking_gaps": [
                "A dossier-grade U.S. file wrapper is required for a clearance-grade record."
            ],
            "clearance_grade_ready": False,
        },
        "run_observability": {
            "authoritative_source_hit_rate": 0.0,
            "claims_text_coverage": 1.0,
            "family_context_coverage": 1.0,
            "us_file_wrapper_dossier_coverage": 0.0,
            "ep_register_coverage": 1.0,
            "failed_adapter_names": [],
            "false_clear_risk_flags": [
                "medium_risk_claims",
                "record_incomplete",
            ],
            "unresolved_contradictions": [],
        },
        "matter_evidence_index": {
            "source_names": ["pubchem_sdq", "bigquery"],
            "authoritative_source_names": ["patentsview"],
            "supporting_source_names": ["bigquery", "pubchem_sdq"],
            "material_patent_count": 1,
            "family_count": 1,
            "analysis_failure_patent_ids": ["EP0000001A1"],
            "critic_flagged_patent_ids": ["US12345678A1"],
            "clearance_grade_ready_patent_ids": [],
            "incomplete_patent_ids": ["US12345678A1"],
            "clearance_grade_ready_family_ids": [],
            "incomplete_family_ids": ["fam-123"],
            "patent_records": [
                {
                    "patent_id": "US12345678A1",
                    "title": "Aspirin formulation patent",
                    "jurisdiction": "US",
                    "legal_status": "active",
                    "is_granted": False,
                    "source_names": ["pubchem_sdq", "bigquery"],
                    "authoritative_source_names": ["patentsview"],
                    "supporting_source_names": ["bigquery", "pubchem_sdq"],
                    "assignees": ["Example Pharma"],
                    "family_id": "fam-123",
                    "family_member_count": 3,
                    "family_jurisdictions": ["US", "EP"],
                    "family_broadest": True,
                    "application_number": "12/345678",
                    "has_claims_text": True,
                    "has_family_context": True,
                    "has_us_prosecution_context": True,
                    "has_ep_register_context": False,
                    "has_assignments": False,
                    "has_priority_claims": True,
                    "has_ptab_proceedings": False,
                    "has_orange_book_listing": False,
                    "has_opposition_events": False,
                    "authoritative_record_categories": [
                        "authoritative_search_source",
                        "family_record",
                        "priority_record",
                        "us_prosecution_record",
                    ],
                    "component_statuses": [
                        {
                            "component": "claims_text",
                            "status": "collected",
                            "source_name": "patentsview",
                            "authority_expected": True,
                            "required_before_clear": True,
                            "note": "Claims text is present for this patent.",
                        },
                        {
                            "component": "family_context",
                            "status": "collected",
                            "source_name": "family_record",
                            "authority_expected": True,
                            "required_before_clear": True,
                            "note": "Family context is available for this patent.",
                        },
                        {
                            "component": "authoritative_records",
                            "status": "collected",
                            "source_name": "authoritative_record",
                            "authority_expected": True,
                            "required_before_clear": True,
                            "note": "Authoritative record support is available for this patent.",
                        },
                        {
                            "component": "claim_level_analysis",
                            "status": "collected",
                            "source_name": "step4_analyze",
                            "authority_expected": False,
                            "required_before_clear": True,
                            "note": "Claim-level analysis completed.",
                        },
                        {
                            "component": "doe_assessment",
                            "status": "missing",
                            "source_name": "step5_doe",
                            "authority_expected": False,
                            "required_before_clear": False,
                            "note": "Doctrine of equivalents assessment is not present.",
                        },
                        {
                            "component": "invalidity_assessment",
                            "status": "missing",
                            "source_name": "step6_invalidity",
                            "authority_expected": False,
                            "required_before_clear": False,
                            "note": "Invalidity assessment is not present.",
                        },
                        {
                            "component": "ptab_record",
                            "status": "not_applicable",
                            "source_name": "ptab",
                            "authority_expected": True,
                            "required_before_clear": False,
                            "note": "No PTAB record is currently associated with this patent.",
                        },
                        {
                            "component": "orange_book_record",
                            "status": "not_applicable",
                            "source_name": "orange_book",
                            "authority_expected": True,
                            "required_before_clear": False,
                            "note": "No Orange Book record is currently associated with this patent.",
                        },
                        {
                            "component": "us_prosecution_context",
                            "status": "collected",
                            "source_name": "uspto_odp",
                            "authority_expected": True,
                            "required_before_clear": False,
                            "note": "U.S. prosecution context is available.",
                        },
                        {
                            "component": "us_file_wrapper_dossier",
                            "status": "missing",
                            "source_name": "uspto_odp",
                            "authority_expected": True,
                            "required_before_clear": True,
                            "note": "A dossier-grade U.S. file wrapper is still missing.",
                        },
                        {
                            "component": "ep_register_context",
                            "status": "not_applicable",
                            "source_name": "epo_register",
                            "authority_expected": True,
                            "required_before_clear": True,
                            "note": "EP register context is not applicable to this patent.",
                        },
                    ],
                    "analysis_completed": True,
                    "analysis_failed": False,
                    "claims_analyzed_count": 2,
                    "risk_level": "medium",
                    "doe_assessed": False,
                    "invalidity_assessed": False,
                    "clearance_grade_ready": False,
                    "gate_failures": [
                        "blocking_patent_missing_doe_assessment",
                        "blocking_patent_missing_invalidity_assessment",
                        "critic_major_issue",
                    ],
                    "critic_issue_count": 1,
                    "critic_issue_severities": ["major"],
                    "prosecution_signals": ["narrowing_signal", "pending_family_signal"],
                    "future_risk_signals": ["pending_family"],
                }
            ],
            "family_records": [
                {
                    "family_id": "fam-123",
                    "material_patent_ids": ["US12345678A1"],
                    "jurisdictions": ["US", "EP"],
                    "broadest_patent_id": "US12345678A1",
                    "member_count": 3,
                    "pending_member_count": 1,
                    "blocking_patent_ids": ["US12345678A1"],
                    "orange_book_listed_patent_ids": [],
                    "authoritative_record_categories": [
                        "authoritative_search_source",
                        "family_record",
                        "priority_record",
                        "us_prosecution_record",
                    ],
                    "component_statuses": [
                        {
                            "component": "family_context",
                            "status": "collected",
                            "source_name": "family_record",
                            "authority_expected": True,
                            "required_before_clear": True,
                            "note": "Family context is collected across the material family.",
                        },
                        {
                            "component": "claims_text",
                            "status": "collected",
                            "source_name": "patentsview",
                            "authority_expected": True,
                            "required_before_clear": True,
                            "note": "Claims text is collected across the material family.",
                        },
                        {
                            "component": "claim_level_analysis",
                            "status": "collected",
                            "source_name": "step4_analyze",
                            "authority_expected": False,
                            "required_before_clear": True,
                            "note": "Claim-level analysis is complete across the material family.",
                        },
                        {
                            "component": "authoritative_records",
                            "status": "collected",
                            "source_name": "family_record",
                            "authority_expected": True,
                            "required_before_clear": True,
                            "note": "Authoritative record coverage exists across the material family.",
                        },
                    ],
                    "clearance_grade_ready": False,
                    "gate_failures": ["incomplete_material_patent_records"],
                    "clearance_grade_ready_patent_ids": [],
                    "incomplete_patent_ids": ["US12345678A1"],
                }
            ],
        },
        "total_patents_found": 42,
        "patents_after_triage": 2,
        "search_sources_used": ["pubchem_sdq"],
        "source_health": {
            "entries": [
                {
                    "source": "pubchem_sdq",
                    "status": "ok",
                    "patent_count": 12,
                    "error_message": "",
                },
                {
                    "source": "bigquery",
                    "status": "failed",
                    "patent_count": 0,
                    "error_message": "temporary upstream timeout",
                },
            ]
        },
        "analysis_failures": [
            {
                "patent_id": "EP0000001A1",
                "step": "step4",
                "error_type": "TimeoutError",
                "error_message": "analysis timed out",
                "recoverable": True,
            }
        ],
        "data_limitations": [
            {
                "category": "coverage_gap",
                "description": "One EP register record remained incomplete.",
                "impact": "moderate",
            }
        ],
        "audit_trail": {
            "search_funnel": [
                {
                    "patent_id": "US12345678A1",
                    "sources_found_in": ["pubchem_sdq", "bigquery"],
                    "passed_hard_filter": True,
                    "filter_reason": "",
                    "composite_score": 0.87,
                    "bm25_score": 11.2,
                    "final_blend_score": 0.83,
                    "final_rank": 1,
                    "included_in_triage": True,
                }
            ],
            "triage_audit": [
                {
                    "patent_id": "US12345678A1",
                    "relevance": "high",
                    "reason": "Core scaffold overlap remained plausible.",
                    "confidence": 0.79,
                    "passed_triage": True,
                }
            ],
            "analysis_audit": [
                {
                    "patent_id": "US12345678A1",
                    "selected_for_analysis": True,
                    "selection_reason": "Top-ranked US family member with live exposure.",
                    "risk_level": "medium",
                    "selected_for_doe": True,
                    "selected_for_invalidity": False,
                }
            ],
            "timing_data": [
                {
                    "step_name": "step3_triage",
                    "started_at": datetime.now(UTC).isoformat(),
                    "completed_at": datetime.now(UTC).isoformat(),
                    "duration_seconds": 4.2,
                    "items_processed": 12,
                    "items_output": 3,
                }
            ],
            "total_patents_discovered": 42,
            "patents_after_hard_filter": 24,
            "patents_after_ranking": 12,
            "patents_after_triage": 2,
            "patents_analyzed": 1,
        },
        "patent_narratives": {},
        "critic_report": {
            "overall_quality_score": 0.82,
            "findings": [
                {
                    "issue_type": "confidence_calibration",
                    "patent_id": "US12345678A1",
                    "severity": "minor",
                    "description": "Confidence remains slightly overstated relative to evidence depth.",
                    "suggested_correction": "Downgrade to unclear unless prosecution context is complete.",
                    "claim_numbers": [1],
                    "related_patent_ids": [],
                }
            ],
            "patents_reviewed": 10,
            "patents_flagged_for_revision": ["US12345678A1"],
            "portfolio_level_observations": ["Evidence quality is mixed."],
            "input_tokens": 120,
            "output_tokens": 45,
        },
        "disclaimer": "Test disclaimer",
        "llm_models_used": {},
        "search_loop_result": {
            "iterations_completed": 2,
            "iteration_logs": [
                {
                    "iteration_number": 1,
                    "patents_found_new": 12,
                    "patents_found_total": 12,
                    "triage_relevant_new": 3,
                    "queries_used": {
                        "patent_synonyms": ["acetylsalicylic acid"],
                        "cpc_codes": ["A61K31/00"],
                        "key_assignees": ["Example Pharma"],
                        "process_keywords": ["formulation"],
                        "compound_class_terms": ["salicylate"],
                    },
                    "assessment": {
                        "coverage_adequate": False,
                        "confidence": 0.61,
                        "gaps_identified": [
                            {
                                "gap_type": "missing_assignee",
                                "description": "Assignee coverage is thin in the initial pass.",
                                "suggested_action": "Expand assignee-driven queries.",
                            }
                        ],
                        "evidence_collection_directives": [
                            {
                                "directive_id": "collect_authoritative_records:US12345678A1",
                                "directive_type": "collect_authoritative_records",
                                "priority": "critical",
                                "required_before_clear": True,
                                "target_patent_ids": ["US12345678A1"],
                                "target_claim_ids": [],
                                "target_jurisdictions": ["US"],
                                "recommended_adapters": ["patentsview", "epo_search"],
                                "summary": "Collect authoritative legal-record support.",
                                "rationale": "Discovery-only support is not enough.",
                            }
                        ],
                        "suggested_queries": {
                            "patent_synonyms": ["acetylsalicylic acid"],
                            "cpc_codes": ["A61K31/00"],
                            "key_assignees": ["Example Pharma", "GenericCo"],
                            "process_keywords": ["formulation", "tablet"],
                            "compound_class_terms": ["salicylate"],
                        },
                        "iteration_summary": "Initial pass found relevant patents but left assignee coverage thin.",
                        "assignee_distribution": {"Example Pharma": 2},
                        "cpc_distribution": {"A61K31/00": 3},
                    },
                    "input_tokens": 60,
                    "output_tokens": 24,
                }
            ],
            "final_assessment": {
                "coverage_adequate": True,
                "confidence": 0.78,
                "gaps_identified": [],
                "evidence_collection_directives": [],
                "suggested_queries": None,
                "iteration_summary": "Coverage reached an acceptable stopping point.",
                "assignee_distribution": {"Example Pharma": 2, "GenericCo": 1},
                "cpc_distribution": {"A61K31/00": 4},
            },
            "pending_collection_directives": [],
            "termination_reason": "coverage_adequate",
            "total_input_tokens": 123,
            "total_output_tokens": 45,
        },
        "trust_mode": "explorer",
        "intended_actions": [],
        "target_jurisdictions": ["US"],
        "jurisdiction_bundle": "custom",
        "development_stage": "discovery",
        "asset_type_hint": "small_molecule",
        "routing_profile": {},
        "opinion_readiness": {},
        "data_coverage": {},
        "search_strategy_log": [],
        "negative_search_log": [],
        "source_convergence": {},
        "jurisdiction_matrix": [],
        "jurisdiction_certification": [],
        "jurisdiction_source_coverage": [],
        "jurisdiction_local_review_required": [],
        "uncertainty_register": [],
        "reasoning_traces": [],
        "action_items": [],
        "report_pipeline": "world_class_adaptive",
        "bibliography": [
            {
                "ref_type": "patent",
                "patent_id": "US12345678A1",
                "title": "Aspirin formulation patent",
                "assignee": "Example Pharma",
                "filing_date": _rel_date(days_ago=1460),
                "grant_date": _rel_date(days_ago=730),
                "expiry_date": _rel_date(days_from_now=4380),
                "url": "https://example.com/patent/US12345678A1",
            }
        ],
        "verification_summary": {
            "total_claims_checked": 8,
            "claims_correct": 8,
            "claims_incorrect": 0,
            "claims_unverifiable": 0,
            "factual_accuracy_rate": 1.0,
            "corrections_needed": [],
            "omissions_found": [],
            "overall_assessment": "PASS",
        },
        "factual_accuracy_rate": 1.0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "estimated_cost_usd": 0.0,
        "step_token_usage": [
            {
                "step_name": "step3_triage",
                "model_role": "triage",
                "model_name": "claude-haiku",
                "input_tokens": 110,
                "output_tokens": 22,
            }
        ],
    }
    report.update(overrides)
    if "report_id" in overrides and "claim_source_span_map" not in overrides:
        keyring = CheckpointIntegrityKeyRing.from_secret(DEV_CHECKPOINT_HMAC_KEYRING_SECRET)
        for span_id, span_payload in report["claim_source_span_map"]["spans"].items():
            span = SourceSpanReference.model_validate(span_payload)
            if span.source_type != "verified_claim_text":
                continue
            report["claim_source_span_map"]["spans"][span_id] = issue_source_span_attestation(
                span,
                signing_key=keyring.active_key(),
                key_id=keyring.active_key_id,
                subject_id=str(report["report_id"]),
            ).model_dump(mode="json")
    if "authority_coverage" not in overrides:
        _sync_authority_coverage(report)
    if "matter_store" not in overrides:
        report["matter_store"]["matter_evidence_index"] = deepcopy(report["matter_evidence_index"])
        report["matter_store"]["claim_program_decisions"] = deepcopy(
            report["claim_program_decisions"]
        )
        report["matter_store"]["authority_coverage"] = deepcopy(report["authority_coverage"])
        report["matter_store"]["record_completeness"] = deepcopy(report["record_completeness"])
    return report


def valid_report_data_for_patents(
    patent_analyses: list[dict],
    **overrides,
) -> dict:
    """Return a valid report whose patent rows have matching source-span support."""
    patent_analyses = [dict(item) for item in patent_analyses]
    for patent_analysis in patent_analyses:
        patent_id = str(patent_analysis.get("patent_id") or "").strip()
        if patent_id:
            patent_analysis["patent_id"] = _canonical_fixture_patent_id(patent_id)
        patent_analysis.setdefault("risk_level", "low")
        patent_analysis.setdefault("risk_summary", "No material blocking exposure identified.")
        patent_analysis.setdefault("claims_analyzed", [])
    report = valid_report_data(patent_analyses=patent_analyses, **overrides)
    patent_ids = [
        _canonical_fixture_patent_id(patent_analysis.get("patent_id"))
        for patent_analysis in patent_analyses
        if str(patent_analysis.get("patent_id") or "").strip()
    ]
    if patent_ids:
        primary_patent_id = patent_ids[0]
        high_risk_patent_ids = [
            _canonical_fixture_patent_id(item.get("patent_id"))
            for item in patent_analyses
            if str(item.get("risk_level") or "").strip().lower() == "high"
        ]
        medium_risk_patent_ids = [
            _canonical_fixture_patent_id(item.get("patent_id"))
            for item in patent_analyses
            if str(item.get("risk_level") or "").strip().lower() == "medium"
        ]
        us_patent_ids = [
            patent_id for patent_id in patent_ids if patent_id.upper().startswith("US")
        ]
        ep_patent_ids = [
            patent_id for patent_id in patent_ids if patent_id.upper().startswith("EP")
        ]
        jurisdiction_patent_ids: dict[str, list[str]] = {}
        for patent_id in patent_ids:
            jurisdiction_patent_ids.setdefault(patent_id[:2].upper(), []).append(patent_id)
        decision_audit = report["clearance_decision"]["decision_audit"]
        coverage_summary = decision_audit["coverage_summary"]
        coverage_summary["reviewed_patent_ids"] = list(patent_ids)
        coverage_summary["reviewed_us_patent_ids"] = list(us_patent_ids)
        coverage_summary["reviewed_ep_patent_ids"] = list(ep_patent_ids)
        coverage_summary["us_patents_missing_file_wrapper_dossier"] = list(us_patent_ids)
        coverage_summary["ep_patents_missing_register_context"] = []
        coverage_summary["incomplete_patent_ids"] = list(patent_ids)
        decision_audit["material_patents_reviewed"] = len(patent_ids)
        decision_audit["material_us_patents"] = len(us_patent_ids)
        decision_audit["material_ep_patents"] = len(ep_patent_ids)
        decision_audit["incomplete_material_patents"] = len(patent_ids)
        decision_audit["patents_with_claims"] = len(patent_ids)
        decision_audit["patents_with_family"] = len(patent_ids)
        decision_audit["us_patents_with_prosecution_context"] = len(us_patent_ids)
        decision_audit["us_patents_with_file_wrapper_dossier"] = 0
        decision_audit["ep_patents_with_register_context"] = len(ep_patent_ids)
        report["claim_program_decisions"] = [
            {
                "patent_id": patent_id,
                "claim_number": 1,
                "jurisdiction": patent_id[:2].upper(),
                "literal_outcome": "met" if patent_id in high_risk_patent_ids else "partially_met",
                "literal_risk": (
                    "high"
                    if patent_id in high_risk_patent_ids
                    else "medium"
                    if patent_id in medium_risk_patent_ids
                    else "clear"
                ),
                "doe_risk": "not_assessed",
                "invalidity_strength": "",
                "legal_status": "active" if patent_id in high_risk_patent_ids else "unknown",
                "legal_status_provenance_verified": patent_id in high_risk_patent_ids,
                "prospective_enforceability": (
                    "active" if patent_id in high_risk_patent_ids else "unresolved"
                ),
                "accused_acts": ["sale"] if patent_id in high_risk_patent_ids else [],
                "accused_acts_verified": patent_id in high_risk_patent_ids,
                "evidence_sufficient": patent_id in high_risk_patent_ids,
                "missing_components": (
                    [] if patent_id in high_risk_patent_ids else ["fixture_incomplete_evidence"]
                ),
                "record_basis": (
                    ["fixture_verified_claim_text"] if patent_id in high_risk_patent_ids else []
                ),
            }
            for patent_id in patent_ids
        ]
        report["matter_store"]["claim_program_decisions"] = [
            dict(item) for item in report["claim_program_decisions"]
        ]
        claim_program = decision_audit["claim_program_summary"]
        claim_program.update(
            {
                "total_claim_programs_reviewed": len(patent_ids),
                "blocking_claim_ids": [f"{patent_id}#claim1" for patent_id in high_risk_patent_ids],
                "contested_claim_ids": [],
                "medium_risk_claim_ids": [
                    f"{patent_id}#claim1" for patent_id in medium_risk_patent_ids
                ],
                "claims_with_insufficient_evidence": [
                    f"{patent_id}#claim1"
                    for patent_id in patent_ids
                    if patent_id not in high_risk_patent_ids
                ],
                "blocking_patent_ids": high_risk_patent_ids,
                "contested_patent_ids": [],
                "medium_risk_patent_ids": medium_risk_patent_ids,
            }
        )
        fixture_family_records = report["matter_evidence_index"]["family_records"]
        fixture_family_id = str(fixture_family_records[0]["family_id"])
        sorted_blocking_patent_ids = sorted(high_risk_patent_ids)
        decision_audit["blocker_families"] = (
            [
                {
                    "blocker_id": (
                        "bf_" + hashlib.sha256(fixture_family_id.encode()).hexdigest()[:16]
                    ),
                    "family_id": fixture_family_id,
                    "primary_blocking_patent_id": sorted_blocking_patent_ids[0],
                    "material_family_patent_ids": sorted(patent_ids),
                    "blocking_patent_ids": sorted_blocking_patent_ids,
                    "jurisdictions": sorted(
                        {patent_id[:2].upper() for patent_id in sorted_blocking_patent_ids}
                    ),
                    "blocking_claims": [
                        {
                            "claim_id": f"{patent_id}#claim1",
                            "patent_id": patent_id,
                            "claim_number": 1,
                            "jurisdiction": patent_id[:2].upper(),
                            "literal_risk": "high",
                            "doe_risk": "not_assessed",
                            "invalidity_strength": "",
                            "legal_status": "active",
                            "legal_status_provenance_verified": True,
                            "prospective_enforceability": "active",
                            "accused_acts": ["sale"],
                            "accused_acts_verified": True,
                            "evidence_sufficient": True,
                            "record_basis": ["fixture_verified_claim_text"],
                        }
                        for patent_id in sorted_blocking_patent_ids
                    ],
                }
            ]
            if sorted_blocking_patent_ids
            else []
        )
        if high_risk_patent_ids:
            decision_audit["decisive_references"] = [
                {
                    "category": "blocking_patent",
                    "summary": "Material blocking exposure remained in the decision layer.",
                    "patent_id": patent_id,
                    "jurisdiction": patent_id[:2].upper(),
                    "source_name": "patentsview",
                    "signal": "high",
                }
                for patent_id in high_risk_patent_ids
            ]
        else:
            decision_audit["decisive_references"] = [
                {
                    "category": "prosecution_signal",
                    "summary": "file-wrapper context available, amendment signal detected",
                    "patent_id": primary_patent_id,
                    "jurisdiction": "US",
                    "source_name": "",
                    "signal": "narrowing_signal,pending_family_signal",
                }
            ]
        decision = "blocked" if high_risk_patent_ids else "unclear"
        report["clearance_decision"]["decision"] = decision
        blocker_count = len(high_risk_patent_ids)
        report["risk_summary"].update(
            {
                "overall_risk": "high" if decision == "blocked" else "medium",
                "blocking_patents_count": blocker_count,
                "total_patents_analyzed": len(patent_ids),
                "executive_summary": (
                    f"Clearance decision: {decision.upper()}. {blocker_count} blocking "
                    f"patent{'s' if blocker_count != 1 else ''} identified from "
                    f"{len(patent_ids)} analyzed."
                ),
            }
        )
        report["commercial_exposure"]["blocking_patent_ids"] = high_risk_patent_ids
        report["jurisdiction_decisions"] = [
            {
                "jurisdiction": jurisdiction,
                "decision": (
                    "blocked"
                    if any(patent_id in high_risk_patent_ids for patent_id in reviewed_ids)
                    else "unclear"
                ),
                "decision_confidence": 0.62,
                "evidence_quality": 0.71,
                "evidence_sufficient_for_clearance": False,
                "supports_positive_clearance": jurisdiction in {"US", "EP"},
                "lane_status": "counsel_ready",
                "local_review_required": False,
                "authority_grade": "authoritative",
                "gate_failures": ["Evidence remains mixed."],
                "reviewed_patent_ids": reviewed_ids,
                "blocking_patent_ids": [
                    patent_id for patent_id in high_risk_patent_ids if patent_id in reviewed_ids
                ],
                "reasoning": [f"Reviewed {len(reviewed_ids)} material patents."],
            }
            for jurisdiction, reviewed_ids in jurisdiction_patent_ids.items()
            if reviewed_ids
        ]
        report["patents_after_triage"] = len(patent_ids) + len(report["analysis_failures"])
        report["audit_trail"]["patents_after_triage"] = report["patents_after_triage"]
        report["audit_trail"]["patents_analyzed"] = len(patent_ids)
        report["audit_trail"]["patents_after_ranking"] = max(
            report["patents_after_triage"], report["audit_trail"]["patents_after_ranking"]
        )
        report["audit_trail"]["patents_after_hard_filter"] = max(
            report["audit_trail"]["patents_after_ranking"],
            report["audit_trail"]["patents_after_hard_filter"],
        )
        for artifact in report.get("evidence_artifacts", []):
            artifact["patent_id"] = primary_patent_id
        for dossier in report.get("prosecution_dossiers", []):
            dossier["patent_id"] = primary_patent_id
        evidence_index = report.get("matter_evidence_index") or {}
        evidence_index["material_patent_count"] = len(patent_ids)
        evidence_index["incomplete_patent_ids"] = list(patent_ids)
        evidence_index["clearance_grade_ready_patent_ids"] = []
        patent_record_template = next(
            (
                deepcopy(record)
                for record in evidence_index.get("patent_records", [])
                if isinstance(record, dict)
            ),
            None,
        )
        if patent_record_template is not None:
            evidence_index["patent_records"] = []
            risk_by_patent = {
                str(item["patent_id"]): str(item.get("risk_level") or "low")
                for item in patent_analyses
            }
            for patent_id in patent_ids:
                patent_record = deepcopy(patent_record_template)
                patent_record["patent_id"] = patent_id
                patent_record["jurisdiction"] = patent_id[:2].upper()
                patent_record["risk_level"] = risk_by_patent[patent_id]
                evidence_index["patent_records"].append(patent_record)
        for record in evidence_index.get("family_records", []):
            record["material_patent_ids"] = list(patent_ids)
            record["broadest_patent_id"] = primary_patent_id
            record["blocking_patent_ids"] = high_risk_patent_ids

    entries = []
    spans = {}
    patent_details = {}
    for index, patent_analysis in enumerate(patent_analyses, start=1):
        patent_id = _canonical_fixture_patent_id(patent_analysis.get("patent_id"))
        if not patent_id:
            continue
        span_id = f"span-supported-patent-{index}"
        entries.append(
            {
                "assertion_id": f"assertion-supported-patent-{index}",
                "patent_id": patent_id,
                "claim_number": 1,
                "element_number": index,
                "report_section": "claim_element_analysis",
                "assertion_text": f"{patent_id} claim support is evidence backed.",
                "source_span_ids": [span_id],
                "support_status": "supported",
                "customer_visible": True,
                "review_required": False,
            }
        )
        claims_text = f"1. Evidence-grade claim span for {patent_id}."
        claim_provenance = build_claim_text_provenance(
            patent_id=patent_id,
            claims_text=claims_text,
            source=PatentSource.PATENTSVIEW,
            artifact_locator=(
                f"https://search.patentsview.org/api/v1/patent/?patent_id={patent_id}"
            ),
            collector_identity="runtime.patentsview_claims",
            retrieved_at=_FIXTURE_NOW,
        ).model_dump(mode="json")
        keyring = CheckpointIntegrityKeyRing.from_secret(DEV_CHECKPOINT_HMAC_KEYRING_SECRET)
        spans[span_id] = issue_source_span_attestation(
            SourceSpanReference(
                span_id=span_id,
                source_type="verified_claim_text",
                patent_id=patent_id,
                claim_number=1,
                element_number=index,
                citation=f"{patent_id} claim 1",
                excerpt=claims_text,
                source_document_id=patent_id,
                source_name="patentsview",
                source_text_sha256=claim_provenance["artifact_sha256"],
                source_retrieved_at=claim_provenance["retrieved_at"],
                source_artifact_locator=claim_provenance["artifact_locator"],
                collector_identity=claim_provenance["collector_identity"],
                collector_version=claim_provenance["collector_version"],
                provenance_schema_version=claim_provenance["schema_version"],
                claim_numbers=claim_provenance["claim_numbers"],
                independent_claim_numbers=claim_provenance["independent_claim_numbers"],
                retrieval_complete=claim_provenance["retrieval_complete"],
                provenance_cassette_sha256=claim_provenance["cassette_sha256"],
            ),
            signing_key=keyring.active_key(),
            key_id=keyring.active_key_id,
            subject_id=str(report["report_id"]),
        ).model_dump(mode="json")
        patent_details[patent_id] = {
            "claims_text": claims_text,
            "claims_text_source": "patentsview",
            "claims_text_provenance": claim_provenance,
        }
    report["claim_source_span_map"] = {
        "generated_from": "test_fixture_patent_rows",
        "entries": entries,
        "spans": spans,
        "unsupported_customer_visible_claim_count": 0,
        "needs_review_count": 0,
    }
    report["patent_details"] = patent_details
    _sync_authority_coverage(report)
    report["matter_store"]["matter_evidence_index"] = deepcopy(report["matter_evidence_index"])
    report["matter_store"]["claim_program_decisions"] = deepcopy(report["claim_program_decisions"])
    report["matter_store"]["authority_coverage"] = deepcopy(report["authority_coverage"])
    report["matter_store"]["record_completeness"] = deepcopy(report["record_completeness"])
    return report


def mock_org_check_pass(db: AsyncMock) -> None:
    """Set up db.execute to pass the org isolation check."""
    org_check_result = MagicMock()
    org_check_result.scalar_one_or_none.return_value = uuid.uuid4()
    db.execute = AsyncMock(return_value=org_check_result)


def make_paginated_result(count: int, items: list) -> tuple[MagicMock, MagicMock]:
    """Create (count_result, items_result) mocks for paginated list endpoints.

    Usage::

        count_result, items_result = make_paginated_result(2, [obj1, obj2])
        db.execute = AsyncMock(side_effect=[count_result, items_result])
    """
    count_result = MagicMock()
    count_result.scalar_one.return_value = count

    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = items
    return count_result, items_result


# ---------------------------------------------------------------------------
# App + client fixtures
# ---------------------------------------------------------------------------


def _build_app(user: MagicMock, db: AsyncMock):
    """Create a FastAPI app with dependency overrides for the given user/db.

    We patch ``api.main.engine`` so that the lifespan ``engine.dispose()``
    hits a mock instead of a real asyncpg pool.  The patch object is
    returned so callers can keep it alive for the duration of the test.
    """
    from api.main import create_app

    app = create_app()

    from api.db.session import get_db
    from api.deps import get_current_user
    from api.middleware.rate_limit import rate_limit_analysis, rate_limit_api

    async def _override_get_current_user():
        return user

    async def _override_get_db():
        yield db

    async def _override_rate_limit_analysis():
        return None

    async def _override_rate_limit_api():
        return None

    app.dependency_overrides[get_current_user] = _override_get_current_user
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[rate_limit_analysis] = _override_rate_limit_analysis
    app.dependency_overrides[rate_limit_api] = _override_rate_limit_api
    return app


from contextlib import contextmanager


@contextmanager
def _disabled_rate_limiter():
    """Disable slowapi rate limiting for the duration of the block.

    Wrapped in a context manager with try/finally so the previous ``enabled``
    flag is always restored — even if the test crashes inside the ``with``
    block.  Without this, a single crashing test could leak ``limiter.enabled
    = False`` into subsequent tests and silently mask rate-limit regressions.
    """
    from api.ratelimit import limiter

    prev_enabled = limiter.enabled
    limiter.enabled = False
    try:
        yield limiter
    finally:
        limiter.enabled = prev_enabled


async def _make_client(
    role: UserRole, db: AsyncMock | None = None
) -> AsyncGenerator[tuple[httpx.AsyncClient, AsyncMock]]:
    """Yield ``(httpx.AsyncClient, mock_db)`` with engine patched."""
    if db is None:
        db = make_mock_db()
    user = make_user(role=role)
    # Expose auth user on db so tests can align make_analysis_mock(org_id=db._auth_user.org_id)
    db._auth_user = user
    app = _build_app(user, db)

    # Patch infrastructure so the lifespan startup checks don't hit real DB/Redis
    mock_engine = AsyncMock()  # mock for engine.dispose()

    # Mock the session factory used in lifespan startup DB check
    mock_startup_session = AsyncMock()
    mock_startup_session.__aenter__ = AsyncMock(return_value=mock_startup_session)
    mock_startup_session.__aexit__ = AsyncMock(return_value=False)

    # Mock redis used in lifespan startup check
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock()
    mock_redis.aclose = AsyncMock()

    # Mock cache layer to avoid real Redis calls in route handlers
    async def _no_cache(*_args, **_kwargs):
        return None

    # Disable rate limiting in tests — slowapi decorators corrupt FastAPI's
    # signature introspection when the storage backend (Redis) isn't available.
    with (
        _disabled_rate_limiter(),
        patch("api.main.engine", mock_engine),
        patch("api.db.session.async_session_factory", return_value=mock_startup_session),
        patch("redis.asyncio.from_url", return_value=mock_redis),
        patch("api.cache.get_cached_report", side_effect=_no_cache),
        patch("api.cache.set_cached_report", side_effect=_no_cache),
    ):
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c, db


@pytest.fixture
async def public_client():
    """Client without auth -- the /share endpoint is public."""
    from api.main import create_app

    app = create_app()
    mock_engine = AsyncMock()

    mock_startup_session = AsyncMock()
    mock_startup_session.__aenter__ = AsyncMock(return_value=mock_startup_session)
    mock_startup_session.__aexit__ = AsyncMock(return_value=False)
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock()
    mock_redis.aclose = AsyncMock()

    with (
        _disabled_rate_limiter(),
        patch("api.main.engine", mock_engine),
        patch("api.db.session.async_session_factory", return_value=mock_startup_session),
        patch("redis.asyncio.from_url", return_value=mock_redis),
    ):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as c:
            yield c


@pytest.fixture
def mock_db() -> AsyncMock:
    """A standalone mock DB session for manual wiring."""
    return make_mock_db()


@pytest.fixture
def scientist_user() -> MagicMock:
    return make_user(role=UserRole.SCIENTIST)


@pytest.fixture
def attorney_user() -> MagicMock:
    return make_user(role=UserRole.ATTORNEY)


@pytest.fixture
def admin_user() -> MagicMock:
    return make_user(role=UserRole.ADMIN)


@pytest.fixture
def client_role_user() -> MagicMock:
    return make_user(role=UserRole.CLIENT)


# Generic client (scientist by default)
@pytest.fixture
async def client(mock_db) -> AsyncGenerator[tuple[httpx.AsyncClient, AsyncMock]]:
    async for item in _make_client(UserRole.SCIENTIST, mock_db):
        yield item


@pytest.fixture
async def scientist_client(mock_db) -> AsyncGenerator[tuple[httpx.AsyncClient, AsyncMock]]:
    async for item in _make_client(UserRole.SCIENTIST, mock_db):
        yield item


@pytest.fixture
async def attorney_client() -> AsyncGenerator[tuple[httpx.AsyncClient, AsyncMock]]:
    async for item in _make_client(UserRole.ATTORNEY):
        yield item


@pytest.fixture
async def admin_client() -> AsyncGenerator[tuple[httpx.AsyncClient, AsyncMock]]:
    async for item in _make_client(UserRole.ADMIN):
        yield item


@pytest.fixture
async def client_role_client() -> AsyncGenerator[tuple[httpx.AsyncClient, AsyncMock]]:
    async for item in _make_client(UserRole.CLIENT):
        yield item
