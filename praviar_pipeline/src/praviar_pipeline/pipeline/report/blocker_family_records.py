"""Canonical governed blocker-family decision projection."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from praviar_pipeline.models.report import BlockerClaimRecord, BlockerFamilyRecord
from praviar_pipeline.models.report_decisioning_core import blocker_family_record_id


def _claim_identity(claim_id: str) -> tuple[str, int]:
    patent_id, separator, number = claim_id.partition("#claim")
    if not separator or not patent_id or not number.isdigit() or int(number) < 1:
        raise ValueError(f"invalid governed blocking claim identity: {claim_id}")
    return patent_id, int(number)


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _claim_record(claim_id: str, decisions: list[Any]) -> BlockerClaimRecord:
    patent_id, claim_number = _claim_identity(claim_id)
    matching = [
        decision
        for decision in decisions
        if decision.patent_id == patent_id
        and int(getattr(decision, "claim_number", 0)) == claim_number
    ]
    if len(matching) != 1:
        raise ValueError(f"governed blocker {claim_id} requires exactly one claim decision")
    decision = matching[0]
    if not bool(getattr(decision, "evidence_sufficient", False)):
        raise ValueError(f"governed blocker {claim_id} lacks sufficient evidence")
    if not bool(getattr(decision, "legal_status_provenance_verified", False)):
        raise ValueError(f"governed blocker {claim_id} lacks verified legal status")
    if str(getattr(decision, "prospective_enforceability", "") or "").lower() != "active":
        raise ValueError(f"governed blocker {claim_id} is not actively enforceable")
    if str(getattr(decision, "legal_status", "") or "").strip().lower() != "active":
        raise ValueError(f"governed blocker {claim_id} lacks active legal status")
    if not bool(getattr(decision, "accused_acts_verified", False)):
        raise ValueError(f"governed blocker {claim_id} lacks verified accused acts")
    accused_acts = _unique_sorted(list(getattr(decision, "accused_acts", []) or []))
    record_basis = _unique_sorted(list(getattr(decision, "record_basis", []) or []))
    if not accused_acts or not record_basis:
        raise ValueError(f"governed blocker {claim_id} lacks accused-act or record basis")
    return BlockerClaimRecord(
        claim_id=claim_id,
        patent_id=patent_id,
        claim_number=claim_number,
        jurisdiction=str(getattr(decision, "jurisdiction", "") or "").strip(),
        literal_risk=str(getattr(decision, "literal_risk", "") or "").strip(),
        doe_risk=str(getattr(decision, "doe_risk", "") or "").strip(),
        invalidity_strength=str(getattr(decision, "invalidity_strength", "") or "").strip(),
        legal_status="active",
        legal_status_provenance_verified=True,
        prospective_enforceability="active",
        accused_acts=accused_acts,
        accused_acts_verified=True,
        evidence_sufficient=True,
        record_basis=record_basis,
    )


def build_blocker_family_records(
    *,
    decision: Any,
    claim_program_summary: Any,
    claim_program_decisions: list[Any],
    matter_evidence_index: Any,
) -> list[BlockerFamilyRecord]:
    """Build exact blocker families or reject an inconsistent blocked decision."""
    decision_value = str(getattr(decision, "value", decision) or "").lower()
    if decision_value != "blocked":
        return []

    blocking_claim_ids = _unique_sorted(
        list(getattr(claim_program_summary, "blocking_claim_ids", []) or [])
    )
    blocking_patent_ids = _unique_sorted(
        list(getattr(claim_program_summary, "blocking_patent_ids", []) or [])
    )
    if not blocking_claim_ids or not blocking_patent_ids:
        raise ValueError("blocked decisions require exact blocking claim and patent identities")

    claim_records = [
        _claim_record(claim_id, claim_program_decisions) for claim_id in blocking_claim_ids
    ]
    claim_patent_ids = sorted({claim.patent_id for claim in claim_records})
    if claim_patent_ids != blocking_patent_ids:
        raise ValueError("blocking claim and patent identifiers disagree in decision summary")

    patent_family_ids: dict[str, str] = {}
    for record in list(getattr(matter_evidence_index, "patent_records", []) or []):
        patent_id = str(getattr(record, "patent_id", "") or "").strip()
        if not patent_id:
            raise ValueError("matter evidence contains a patent record without an identity")
        if patent_id in patent_family_ids:
            raise ValueError(f"matter evidence contains duplicate patent record {patent_id}")
        patent_family_ids[patent_id] = str(getattr(record, "family_id", "") or "").strip()

    family_by_id: dict[str, Any] = {}
    for record in list(getattr(matter_evidence_index, "family_records", []) or []):
        family_id = str(getattr(record, "family_id", "") or "").strip()
        if not family_id:
            raise ValueError("matter evidence contains a family record without an identity")
        if family_id in family_by_id:
            raise ValueError(f"matter evidence contains duplicate family record {family_id}")
        family_by_id[family_id] = record
    claims_by_family: dict[str, list[BlockerClaimRecord]] = defaultdict(list)
    for claim in claim_records:
        family_id = patent_family_ids.get(claim.patent_id, "")
        if not family_id or family_id not in family_by_id:
            raise ValueError(
                f"governed blocker {claim.claim_id} lacks authoritative family membership"
            )
        claims_by_family[family_id].append(claim)

    records: list[BlockerFamilyRecord] = []
    for family_id in sorted(claims_by_family):
        family = family_by_id[family_id]
        claims = sorted(
            claims_by_family[family_id],
            key=lambda claim: (claim.patent_id, claim.claim_number),
        )
        family_blocking_patent_ids = sorted({claim.patent_id for claim in claims})
        material_family_patent_ids = _unique_sorted(
            list(getattr(family, "material_patent_ids", []) or [])
        )
        if not set(family_blocking_patent_ids).issubset(material_family_patent_ids):
            raise ValueError(f"family {family_id} omits a governed blocking patent")
        records.append(
            BlockerFamilyRecord(
                blocker_id=blocker_family_record_id(family_id),
                family_id=family_id,
                primary_blocking_patent_id=family_blocking_patent_ids[0],
                material_family_patent_ids=material_family_patent_ids,
                blocking_patent_ids=family_blocking_patent_ids,
                jurisdictions=sorted({claim.jurisdiction for claim in claims}),
                blocking_claims=claims,
            )
        )

    if (
        sorted(patent_id for record in records for patent_id in record.blocking_patent_ids)
        != blocking_patent_ids
    ):
        raise ValueError("canonical blocker families do not cover every blocker")
    return sorted(records, key=lambda record: record.blocker_id)


__all__ = ["build_blocker_family_records"]
