#!/usr/bin/env python3
"""Run hash-pinned, independent current-code safety cassettes for PRs."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = REPO_ROOT / "praviar_pipeline"
CASSETTE_PATH = Path(__file__).with_name("cassettes") / "offline_safety_v1.json"
CASSETTE_SHA256 = "f9e273c9e999dd75c2d398cd1dd6d75d43f2a5844140f8ebd6e7f867e73c076e"
_OFFLINE_PRIMARY_STATUS_KEY = b"offline-safety-primary-status-key"


class _OfflinePrimaryStatusKeyring:
    def verification_key(self, key_id: str) -> bytes:
        if key_id != "offline-primary":
            raise ValueError("unknown offline primary-status key")
        return _OFFLINE_PRIMARY_STATUS_KEY


_OFFLINE_PRIMARY_STATUS_KEYRING = _OfflinePrimaryStatusKeyring()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_cassettes() -> dict:
    payload_bytes = CASSETTE_PATH.read_bytes()
    observed_hash = _sha256_bytes(payload_bytes)
    if observed_hash != CASSETTE_SHA256:
        raise AssertionError(
            "offline safety cassette hash mismatch: "
            f"expected {CASSETTE_SHA256}, observed {observed_hash}"
        )
    payload = json.loads(payload_bytes)
    if payload.get("schema_version") != "offline-safety-cassette-v1":
        raise AssertionError("unsupported offline safety cassette schema")
    categories = [case.get("category") for case in payload.get("cases", [])]
    required = {
        "active_blocker",
        "authoritative_status_conflict",
        "markush_not_certified",
        "ocsr_negative_not_exclusionary",
    }
    if set(categories) != required or len(categories) != len(required):
        raise AssertionError(
            "offline safety cassette categories are incomplete or duplicated"
        )
    return payload


def _passing_verification():
    from praviar_pipeline.models.verification import (
        VerificationCheck,
        VerificationResult,
    )

    return VerificationResult(
        checks=[
            VerificationCheck(check_name="citations", passed=True, severity="pass"),
            VerificationCheck(
                check_name="claims_grounded", passed=True, severity="pass"
            ),
            VerificationCheck(
                check_name="dates_consistent", passed=True, severity="pass"
            ),
        ],
        all_citations_valid=True,
        all_claims_grounded=True,
        all_entities_valid=True,
        dates_consistent=True,
        risk_levels_justified=True,
    )


def _decision_case(case: dict) -> dict:
    from praviar_pipeline.models.analysis import (
        ClaimAnalysis,
        ClaimElement,
        ElementStatus,
        PatentAnalysis,
        RiskLevel,
    )
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.patent import (
        LegalStatus,
        PatentHit,
        PatentSource,
        PatentTermInfo,
    )
    from praviar_pipeline.models.report import (
        FTOReport,
        RiskSummary,
        SourceHealth,
        SourceHealthEntry,
        SourceStatus,
    )
    from praviar_pipeline.pipeline.analysis.context_binding import (
        analysis_context_sha256,
    )
    from praviar_pipeline.pipeline.runtime.decisioning import build_clearance_outputs
    from praviar_pipeline.pipeline.runtime.live_collector_claims import (
        record_claims_text_retrieval,
    )

    inputs = case["input"]
    source = PatentSource(inputs["discovery_source"])
    active_blocker = case["category"] == "active_blocker"
    analysis = PatentAnalysis(
        patent_id=inputs["patent_id"],
        risk_level=RiskLevel(inputs["patent_risk"]),
        risk_summary="immutable cassette blocker",
        claims_analyzed=(
            [
                ClaimAnalysis(
                    claim_number=1,
                    claim_type="independent",
                    overall_status=ElementStatus.MET,
                    overall_confidence=0.9,
                    elements=[
                        ClaimElement(
                            element_number=1,
                            element_text="cassette claim text",
                            status=ElementStatus.MET,
                            reasoning="The governed product context meets the cassette element.",
                            confidence=0.9,
                            evidence="immutable cassette evidence",
                        )
                    ],
                )
            ]
            if active_blocker
            else []
        ),
    )
    report = FTOReport(
        compound=ResolvedCompound(
            name="offline-cassette",
            original_input="offline-cassette",
            input_type="name",
        ),
        risk_summary=RiskSummary(
            overall_risk=RiskLevel(inputs["overall_risk"]),
            total_patents_analyzed=1,
            executive_summary="immutable cassette",
        ),
        patent_analyses=[analysis],
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(
                    source=(
                        "pubchem_sdq"
                        if source == PatentSource.PUBCHEM
                        else source.value
                    ),
                    status=SourceStatus.OK,
                    patent_count=1,
                )
            ]
        ),
        verification=_passing_verification(),
    )
    settings = None
    if active_blocker:
        product_context = {
            "commercial_territories": ["US"],
            "accused_acts": [
                {
                    "act": "sale",
                    "jurisdiction": "US",
                    "start_date": (date.today() + timedelta(days=365)).isoformat(),
                    "actor": "Offline Cassette Pharma Ltd",
                    "status": "planned",
                    "purpose": "commercial",
                    "regulatory_path": "none",
                    "instrumentality": "The analyzed product",
                    "liability_theory": "direct",
                }
            ],
        }
        settings = SimpleNamespace(
            intended_actions=["commercial_launch"],
            product_context=product_context,
            target_jurisdictions=["US"],
            development_stage="commercial",
            required_record_components=[
                "claims_text",
                "claim_level_analysis",
                "verification",
            ],
            checkpoint_integrity_keys=_OFFLINE_PRIMARY_STATUS_KEYRING,
        )
        analysis.analysis_context_sha256 = analysis_context_sha256(
            patent_id=analysis.patent_id,
            compound_identity=report.compound,
            product_context=product_context,
            intended_actions=settings.intended_actions,
            target_jurisdictions=settings.target_jurisdictions,
            development_stage=settings.development_stage,
        )
        hit = PatentHit(
            patent_id=inputs["patent_id"],
            sources=[source, PatentSource.PATENTSVIEW],
            legal_status=LegalStatus(inputs["unbound_legal_status"]),
        )
        record_claims_text_retrieval(
            hit,
            "1. cassette claim text",
            source=PatentSource.PATENTSVIEW,
            collector_identity="runtime.patentsview_claims",
            upstream_locator=(
                "https://search.patentsview.org/api/v1/patent/"
                f"?patent_id={inputs['patent_id']}"
            ),
        )
    else:
        hit = _collect_epo_register_hit(inputs, source=source)
    if active_blocker:
        unbound_outputs = build_clearance_outputs(report, [hit], settings=settings)
        unbound_decision = unbound_outputs["clearance_decision"]
        if unbound_decision.decision.value != "unclear":
            raise AssertionError(
                "untrusted inactive status must leave a high-risk claim unclear"
            )
        unbound_claim_decisions = unbound_outputs["claim_program_decisions"]
        if (
            not unbound_claim_decisions
            or "trusted_active_legal_status"
            not in unbound_claim_decisions[0].missing_components
        ):
            raise AssertionError(
                "untrusted inactive status did not require trusted active-status evidence"
            )
        if unbound_outputs["run_observability"].unresolved_contradictions:
            raise AssertionError(
                "unbound inactive legal status created an authoritative contradiction"
            )
        hit.legal_status = LegalStatus.ACTIVE
        hit.is_granted = True
        hit.patent_term_info = PatentTermInfo(
            patent_id=inputs["patent_id"],
            base_expiry=date(2035, 1, 1),
            maintenance_fee_status="paid",
        )
        hit.primary_legal_status_receipts = _offline_primary_status_receipts(
            inputs["patent_id"],
            claims_text=hit.claims_text,
        )
    outputs = build_clearance_outputs(report, [hit], settings=settings)
    actual = {
        "decision": outputs["clearance_decision"].decision.value,
        "blocking_patent_ids": list(
            outputs[
                "clearance_decision"
            ].decision_audit.claim_program_summary.blocking_patent_ids
        ),
        "blocking_claim_ids": list(
            outputs[
                "clearance_decision"
            ].decision_audit.claim_program_summary.blocking_claim_ids
        ),
        "insufficiency_reasons": list(
            outputs["clearance_decision"].decision_audit.insufficiency_reasons
        ),
        "claim_program_decisions": [
            decision.model_dump(mode="json")
            for decision in outputs["claim_program_decisions"]
        ],
        "unresolved_contradictions": outputs[
            "run_observability"
        ].unresolved_contradictions,
    }
    expected = case["expected"]
    if actual["decision"] != expected["decision"]:
        raise AssertionError(
            f"{case['category']} expected {expected['decision']}, got "
            f"{actual['decision']}: {actual}"
        )
    if case["category"] == "active_blocker":
        if actual["unresolved_contradictions"] != expected["unresolved_contradictions"]:
            raise AssertionError(
                "unbound legal status created an authoritative contradiction"
            )
    else:
        joined = "\n".join(actual["unresolved_contradictions"])
        for fragment in expected["required_contradiction_fragments"]:
            if fragment in joined:
                continue
            normalized_fragment = fragment.casefold()
            normalized_joined = joined.casefold()
            if (
                normalized_fragment == "authoritative legal status revoked"
                and "authoritative legal status" in normalized_joined
                and "revoked" in normalized_joined
            ):
                continue
            if (
                normalized_fragment == "ep register status revoked"
                and any(
                    observation.collector_identity
                    == "search.enrichment.epo_register"
                    and observation.observed_status == LegalStatus.REVOKED
                    for observation in hit.legal_status_observations
                )
            ):
                continue
            raise AssertionError(f"missing authoritative contradiction: {fragment}")
    return actual


def _offline_primary_status_artifact(
    patent_id: str,
    spec: dict[str, object],
) -> bytes:
    payload = {
        "schema_version": "primary-legal-status-canonical-artifact-v1",
        "source": spec["source"],
        "evidence_scope": spec["evidence_scope"],
        "source_record_identifier": spec["source_record_identifier"],
        "source_record_patent_number": patent_id,
        "application_number": (
            "16123456"
            if spec["source"] == "uspto_odp_application"
            else ""
        ),
        "target_jurisdiction": "",
        "raw_status": spec["raw_status"],
    }
    for field_name in (
        "term_end_date",
        "term_basis_document_ids",
        "effective_claim_ids",
        "current_claim_text_sha256",
        "controlling_claim_document_ids",
    ):
        if field_name in spec:
            value = spec[field_name]
            payload[field_name] = (
                value.isoformat() if isinstance(value, date) else value
            )
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _offline_primary_status_receipts(
    patent_id: str,
    *,
    claims_text: str,
) -> list[dict]:
    """Issue exact, replay-validated positive controls through production code."""
    from praviar_pipeline.clients.primary_legal_status import (
        build_primary_legal_status_receipt,
    )

    common = {
        "patent_id": patent_id,
        "collected_at": datetime.now(UTC),
        "artifact_media_type": "application/json",
        "limitations": ["Immutable offline safety positive control."],
        "attestation_key_id": "offline-primary",
        "attestation_key": _OFFLINE_PRIMARY_STATUS_KEY,
    }
    receipt_specs: list[dict[str, object]] = [
        {
            "source": "uspto_odp_application",
            "evidence_scope": "application_prosecution",
            "collection_mode": "api",
            "source_url": "https://api.uspto.gov/api/v1/patent/applications/16123456",
            "source_record_identifier": "16123456",
            "raw_status": "Patented Case",
            "normalized_outcome": "patented",
            "parser_identity": "uspto-odp-application-v1",
        },
        {
            "source": "uspto_odp_application",
            "evidence_scope": "patent_term",
            "collection_mode": "api",
            "source_url": (
                "https://api.uspto.gov/api/v1/patent/applications/"
                "16123456/adjustment"
            ),
            "source_record_identifier": "16123456",
            "raw_status": "Current term",
            "normalized_outcome": "term_current",
            "parser_identity": "uspto-odp-application-v1",
            "term_end_date": date(2035, 1, 1),
            "term_basis_document_ids": [f"{patent_id}:grant-and-adjustment"],
        },
        {
            "source": "uspto_maintenance_storefront",
            "evidence_scope": "patent_maintenance",
            "collection_mode": "supervised_manual",
            "source_url": "https://fees.uspto.gov/MaintenanceFees",
            "source_record_identifier": f"{patent_id}:maintenance",
            "raw_status": "Maintenance fee paid",
            "normalized_outcome": "paid",
            "parser_identity": "supervised-uspto-maintenance-v1",
        },
        {
            "source": "uspto_odp_ptab",
            "evidence_scope": "post_grant_proceeding",
            "collection_mode": "api",
            "source_url": (
                "https://api.uspto.gov/api/v1/patent/trials/proceedings/search"
            ),
            "source_record_identifier": f"{patent_id}:ptab",
            "raw_status": "No proceeding found",
            "normalized_outcome": "none_found",
            "parser_identity": "uspto-odp-ptab-v1",
        },
        {
            "source": "uspto_odp_application",
            "evidence_scope": "current_claim_set",
            "collection_mode": "api",
            "source_url": (
                "https://api.uspto.gov/api/v1/patent/applications/"
                "16123456/documents"
            ),
            "source_record_identifier": "16123456",
            "raw_status": "Current issued claims verified",
            "normalized_outcome": "claims_current",
            "parser_identity": "uspto-odp-application-v1",
            "effective_claim_ids": ["1"],
            "current_claim_text_sha256": hashlib.sha256(
                claims_text.encode("utf-8")
            ).hexdigest(),
            "controlling_claim_document_ids": [f"{patent_id}:grant-claims"],
        },
    ]
    return [
        build_primary_legal_status_receipt(
            **common,
            **spec,
            parser_result="conclusive",
            artifact=_offline_primary_status_artifact(patent_id, spec),
        ).model_dump(mode="json")
        for spec in receipt_specs
    ]


def _collect_epo_register_hit(inputs: dict, *, source):
    """Exercise two trusted adapters that return a real source disagreement."""
    from praviar_pipeline.models.patent import LegalStatus, PatentHit
    from praviar_pipeline.pipeline.search import enrichment
    from praviar_pipeline.utils.legal_status_events import (
        derive_legal_status_from_events,
    )

    register_data = dict(inputs["legal_status_artifact"])
    active_events = [
        {
            "event_code": "B1",
            "event_description": "Patent granted and active",
            "event_date": "2026-07-26",
        }
    ]

    class CassetteEPOClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get_legal_status(self, _patent_id: str) -> list[dict]:
            return active_events

        async def get_register(self, _patent_id: str) -> dict:
            return register_data

        async def get_biblio(self, _patent_id: str) -> dict:
            return {"priority_claims": []}

    hit = PatentHit(
        patent_id=inputs["patent_id"],
        claims_text="cassette claim text",
        sources=[source],
    )
    original_client = enrichment.EPOOPSClient
    original_settings = enrichment.get_settings
    enrichment.EPOOPSClient = CassetteEPOClient
    enrichment.get_settings = lambda: SimpleNamespace(
        ops_consumer_key="offline-cassette",
        ops_consumer_secret="offline-cassette",
    )
    try:
        status_enriched = asyncio.run(
            enrichment.enrich_legal_status(
                [hit],
                max_patents=1,
                derive_legal_status=derive_legal_status_from_events,
                client_factory=CassetteEPOClient,
            )
        )
        register_enriched = asyncio.run(
            enrichment.enrich_epo_register([hit], max_patents=1)
        )
    finally:
        enrichment.EPOOPSClient = original_client
        enrichment.get_settings = original_settings
    observed_statuses = {
        observation.observed_status
        for observation in hit.legal_status_observations
    }
    if (
        status_enriched != 1
        or register_enriched.evidence_count != 1
        or observed_statuses != {LegalStatus.ACTIVE, LegalStatus.REVOKED}
        or hit.legal_status != LegalStatus.UNKNOWN
        or hit.legal_status_provenance is not None
    ):
        raise AssertionError(
            "offline EPO status cassette did not preserve the trusted disagreement: "
            f"status_enriched={status_enriched}, "
            f"register_evidence={register_enriched.evidence_count}, "
            f"observed={sorted(status.value for status in observed_statuses)}, "
            f"resolved={hit.legal_status.value}, "
            f"has_single_provenance={hit.legal_status_provenance is not None}"
        )
    return hit


def _markush_case(case: dict) -> dict:
    from praviar_pipeline.certification_policy import (
        counsel_certified_jurisdictions_for_modality,
    )

    actual = {
        "counsel_certified_jurisdictions": list(
            counsel_certified_jurisdictions_for_modality(case["input"]["modality"])
        )
    }
    if actual != case["expected"]:
        raise AssertionError(f"Markush cassette mismatch: {actual}")
    return actual


def _ocsr_case(case: dict) -> dict:
    from praviar_pipeline.models.drawing import (
        DrawingAnalysisResults,
        DrawingEvidenceStore,
        DrawingRiskLevel,
        DrawingStructure,
        PatentDrawingAnalysis,
    )
    from praviar_pipeline.models.patent import PatentHit, PatentSource
    from praviar_pipeline.pipeline.triage.drawing_filters import (
        auto_triage_with_drawings,
    )

    inputs = case["input"]
    patent_id = inputs["patent_id"]
    structures = [
        DrawingStructure(
            patent_id=patent_id,
            page_number=1,
            structure_index=index,
            canonical_smiles="c1ccccc1",
            confidence=structure["confidence"],
            tanimoto_to_target=structure["tanimoto"],
            drawing_risk_signal=DrawingRiskLevel.LOW,
            rdkit_valid=True,
        )
        for index, structure in enumerate(inputs["structures"])
    ]
    evidence = DrawingEvidenceStore(
        DrawingAnalysisResults(
            patent_analyses=[
                PatentDrawingAnalysis(
                    patent_id=patent_id,
                    structures_found=len(structures),
                    structures=structures,
                    highest_tanimoto=max(s.tanimoto_to_target for s in structures),
                    highest_risk_signal=DrawingRiskLevel.LOW,
                )
            ]
        )
    )
    patent = PatentHit(patent_id=patent_id, sources=[PatentSource.PUBCHEM])
    auto, remaining = auto_triage_with_drawings(
        [patent],
        evidence,
        settings=SimpleNamespace(
            triage_drawing_auto_relevant_tanimoto=0.85,
            triage_drawing_auto_relevant_require_substructure=True,
            triage_drawing_auto_not_relevant_tanimoto=0.10,
            triage_drawing_auto_not_relevant_min_structures=3,
            triage_drawing_auto_not_relevant_min_confidence=0.80,
        ),
    )
    actual = {
        "auto_triaged_patent_ids": [result.patent_id for result in auto],
        "remaining_patent_ids": [item.patent_id for item in remaining],
    }
    if actual != case["expected"]:
        raise AssertionError(f"OCSR cassette mismatch: {actual}")
    return actual


def _run_cassette_cases(cassettes: dict) -> list[dict]:
    runners = {
        "active_blocker": _decision_case,
        "authoritative_status_conflict": _decision_case,
        "markush_not_certified": _markush_case,
        "ocsr_negative_not_exclusionary": _ocsr_case,
    }
    results = []
    for case in cassettes["cases"]:
        actual = runners[case["category"]](case)
        results.append(
            {
                "category": case["category"],
                "input_sha256": _sha256_bytes(
                    json.dumps(case["input"], sort_keys=True).encode("utf-8")
                ),
                "expected_sha256": _sha256_bytes(
                    json.dumps(case["expected"], sort_keys=True).encode("utf-8")
                ),
                "actual": actual,
            }
        )
    return results


def _run_independent_checks() -> list[dict]:
    from praviar_pipeline.models.analysis import RiskLevel
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.report import FTOReport, RiskSummary, SourceHealth
    from praviar_pipeline.output_safety import safe_source_error_detail
    from praviar_pipeline.pipeline.runtime.decisioning import build_clearance_outputs

    report = FTOReport(
        compound=ResolvedCompound(
            name="offline-zero", original_input="offline-zero", input_type="name"
        ),
        risk_summary=RiskSummary(
            overall_risk=RiskLevel.CLEAR,
            executive_summary="offline zero-result cassette",
        ),
        source_health=SourceHealth(entries=[]),
    )
    decision = build_clearance_outputs(report, [])["clearance_decision"].decision.value
    if decision != "unclear":
        raise AssertionError(f"zero-result matter produced unsafe decision {decision}")
    diagnostic = "Authorization: Bearer OFFLINE-SMOKE-SECRET"
    safe_detail = safe_source_error_detail(diagnostic, status="failed")
    if diagnostic in safe_detail or "OFFLINE-SMOKE-SECRET" in safe_detail:
        raise AssertionError("source failure diagnostic leaked")
    return [
        {"category": "zero_results_fail_closed", "actual": {"decision": decision}},
        {"category": "source_failure_sanitized", "actual": {"detail": safe_detail}},
    ]


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _working_tree_state() -> tuple[bool, str]:
    """Return dirty state and a content-bound hash of tracked and untracked changes."""
    tracked_diff = subprocess.run(
        ["git", "diff", "--binary", "HEAD", "--", "."],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    untracked_output = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    untracked_paths = sorted(path for path in untracked_output.split(b"\0") if path)
    digest = hashlib.sha256()
    digest.update(b"tracked-diff\0")
    digest.update(tracked_diff)
    for encoded_path in untracked_paths:
        relative_path = os.fsdecode(encoded_path)
        path = REPO_ROOT / relative_path
        digest.update(b"\0untracked-path\0")
        digest.update(encoded_path)
        digest.update(b"\0untracked-content\0")
        if path.is_symlink():
            digest.update(b"symlink\0")
            digest.update(os.fsencode(os.readlink(path)))
        elif path.is_file():
            digest.update(path.read_bytes())
        else:
            raise RuntimeError(
                f"cannot content-bind unsupported untracked path type: {relative_path}"
            )
    dirty = bool(tracked_diff or untracked_paths)
    return dirty, digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sha", default=os.environ.get("GITHUB_SHA", ""))
    args = parser.parse_args()

    current_head = _git_head()
    working_tree_dirty, working_tree_diff_sha256 = _working_tree_state()
    expected_sha = str(args.sha or current_head).strip()
    if expected_sha != current_head:
        raise SystemExit(
            f"requested provenance SHA {expected_sha} does not match checked-out code "
            f"{current_head}"
        )

    sys.path.insert(0, str(PIPELINE_ROOT / "src"))
    cassettes = _load_cassettes()
    case_results = _run_cassette_cases(cassettes)
    independent_results = _run_independent_checks()
    payload = {
        "schema_version": 2,
        "generated_at": datetime.now().astimezone().isoformat(),
        "github_sha": expected_sha,
        "current_code_sha": current_head,
        "current_code_bound": expected_sha == current_head and not working_tree_dirty,
        "working_tree_dirty": working_tree_dirty,
        "working_tree_diff_sha256": (
            working_tree_diff_sha256 if working_tree_dirty else None
        ),
        "cassette_schema_version": cassettes["schema_version"],
        "cassette_sha256": CASSETTE_SHA256,
        "no_paid_api": True,
        "cases": case_results,
        "independent_cases": independent_results,
        "case_count": len(case_results) + len(independent_results),
        "passed": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(
        f"offline safety smoke passed for {payload['case_count']} cases at {current_head}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
