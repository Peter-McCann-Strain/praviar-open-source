"""Structured customer facts for legally material accused acts.

Free-form launch prose is useful reviewer context, but it is not a reliable
decision boundary: negation, hypotheticals, territory, timing, and regulatory
purpose cannot safely be inferred with keyword matching.  These records are
therefore the only customer-supplied act facts that may establish an accused
act in deterministic clearance decisioning.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AccusedActType = Literal[
    "manufacture",
    "import",
    "offer_for_sale",
    "sale",
    "use",
    "regulatory_submission",
]
AccusedActStatus = Literal["planned", "actual", "denied", "hypothetical"]
AccusedActPurpose = Literal[
    "commercial",
    "regulatory_approval",
    "clinical_research",
    "experimental",
    "internal_research",
    "other",
    "unknown",
]
RegulatorySubmissionPath = Literal[
    "none",
    "anda",
    "nda_505_b_1",
    "nda_505_b_2",
    "bla_351_a",
    "abla",
    "biosimilar_351_k",
    "unknown",
]
AccusedActLiabilityTheory = Literal[
    "direct",
    "induced",
    "contributory",
    "artificial_infringement",
    "unknown",
]
LabelCarveOutState = Literal["none", "partial", "complete", "unknown"]

_JURISDICTION_ALIASES = {
    "USA": "US",
    "UNITED STATES": "US",
    "UNITED STATES OF AMERICA": "US",
    "EU": "EP",
    "EPC": "EP",
    "EUROPE": "EP",
    "EUROPEAN UNION": "EP",
}
_CLAIMED_USE_ATTESTATION_DOMAIN = b"praviar:claimed-use-match:v3\0"


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _canonical_json_sha256(payload: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _text_sha256(value: object) -> str:
    normalized = " ".join(str(value or "").strip().casefold().split())
    if not normalized:
        raise ValueError("Receipt-bound text cannot be blank")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def resolved_compound_identity_sha256(compound: object) -> str:
    """Bind receipts to the exact resolved product/biologic identity."""
    model_dump = getattr(compound, "model_dump", None)
    raw = model_dump(mode="json") if callable(model_dump) else {}
    if not isinstance(raw, dict):
        raw = {}
    payload = {
        key: str(raw.get(key) or "").strip()
        for key in (
            "compound_type",
            "name",
            "canonical_smiles",
            "inchi_key",
            "original_input",
        )
    }
    if not any(payload.values()):
        raise ValueError("Resolved compound identity is unavailable")
    return _canonical_json_sha256(payload)


class ClaimedUseMatchReceipt(BaseModel):
    """Server-attested counsel verification for one patent claim and proposed use."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["claimed-use-match-v3"]
    analysis_id: UUID
    org_id: UUID
    report_id: Annotated[str, Field(min_length=1, max_length=64)]
    report_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    accused_act_index: int = Field(ge=0)
    accused_act_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    patent_id: Annotated[str, Field(min_length=4, max_length=64)]
    claim_number: int = Field(ge=1)
    controlling_claim_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_claim_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    controlling_claim_document_ids: list[Annotated[str, Field(min_length=1, max_length=500)]] = (
        Field(min_length=1, max_length=20)
    )
    declared_target_product_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    resolved_compound_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposed_indication_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposed_label_use_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    label_carve_out_state: LabelCarveOutState
    claimed_use_match: Literal[True]
    product_identity_match: Literal[True]
    issuer_user_id: UUID
    reviewer_role: Literal["attorney"]
    attestation_statement_version: Literal["claimed-use-counsel-affirmation-v1"]
    verified_at: datetime
    evidence_references: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        min_length=1, max_length=50
    )
    attestation_key_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    attestation_hmac_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("patent_id", mode="before")
    @classmethod
    def normalize_patent_id(cls, value: object) -> str:
        return "".join(str(value or "").strip().upper().split())

    @model_validator(mode="after")
    def validate_receipt_integrity(self) -> ClaimedUseMatchReceipt:
        if self.verified_at.tzinfo is None or self.verified_at.utcoffset() is None:
            raise ValueError("Claimed-use verification time must be timezone-aware")
        if self.verified_at.astimezone(UTC) > datetime.now(UTC) + timedelta(minutes=1):
            raise ValueError("Claimed-use verification time cannot be in the future")
        normalized_document_ids = [
            str(document_id).strip() for document_id in self.controlling_claim_document_ids
        ]
        if self.controlling_claim_document_ids != normalized_document_ids or len(
            normalized_document_ids
        ) != len(set(normalized_document_ids)):
            raise ValueError("Controlling claim document identities must be normalized and unique")
        expected = _canonical_json_sha256(self.model_dump(mode="json", exclude={"receipt_sha256"}))
        if not hmac.compare_digest(self.receipt_sha256, expected):
            raise ValueError("Claimed-use receipt digest mismatch")
        return self


def create_claimed_use_match_receipt(
    *,
    analysis_id: UUID,
    org_id: UUID,
    report_id: str,
    report_fingerprint: str,
    accused_act_index: int,
    accused_act_sha256: str,
    patent_id: str,
    claim_number: int,
    controlling_claim_text: str,
    current_claim_receipt_sha256: str,
    controlling_claim_document_ids: list[str],
    target_product_identity: str,
    compound: object,
    proposed_indication: str,
    proposed_label_use: str,
    label_carve_out_state: LabelCarveOutState,
    issuer_user_id: UUID,
    verified_at: datetime,
    evidence_references: list[str],
    attestation_key_id: str,
    attestation_key: bytes,
) -> ClaimedUseMatchReceipt:
    """Create a content-addressed, server-attested claimed-use receipt."""
    if len(attestation_key) < 32:
        raise ValueError("Claimed-use attestation key must contain at least 32 bytes")
    payload: dict[str, object] = {
        "schema_version": "claimed-use-match-v3",
        "analysis_id": analysis_id,
        "org_id": org_id,
        "report_id": report_id,
        "report_fingerprint": report_fingerprint,
        "accused_act_index": accused_act_index,
        "accused_act_sha256": accused_act_sha256,
        "patent_id": "".join(str(patent_id).strip().upper().split()),
        "claim_number": claim_number,
        "controlling_claim_text_sha256": _text_sha256(controlling_claim_text),
        "current_claim_receipt_sha256": current_claim_receipt_sha256,
        "controlling_claim_document_ids": controlling_claim_document_ids,
        "declared_target_product_sha256": _text_sha256(target_product_identity),
        "resolved_compound_identity_sha256": resolved_compound_identity_sha256(compound),
        "proposed_indication_sha256": _text_sha256(proposed_indication),
        "proposed_label_use_sha256": _text_sha256(proposed_label_use),
        "label_carve_out_state": label_carve_out_state,
        "claimed_use_match": True,
        "product_identity_match": True,
        "issuer_user_id": issuer_user_id,
        "reviewer_role": "attorney",
        "attestation_statement_version": "claimed-use-counsel-affirmation-v1",
        "verified_at": verified_at,
        "evidence_references": evidence_references,
        "attestation_key_id": attestation_key_id,
        "attestation_hmac_sha256": "0" * 64,
    }
    unsigned = (
        cast("Any", ClaimedUseMatchReceipt)
        .model_construct(
            **payload,
            receipt_sha256="0" * 64,
        )
        .model_dump(
            mode="json",
            exclude={"receipt_sha256", "attestation_hmac_sha256"},
        )
    )
    payload["attestation_hmac_sha256"] = hmac.new(
        attestation_key,
        _CLAIMED_USE_ATTESTATION_DOMAIN + _canonical_json_bytes(unsigned),
        hashlib.sha256,
    ).hexdigest()
    canonical = (
        cast("Any", ClaimedUseMatchReceipt)
        .model_construct(
            **payload,
            receipt_sha256="0" * 64,
        )
        .model_dump(mode="json", exclude={"receipt_sha256"})
    )
    return ClaimedUseMatchReceipt.model_validate(
        {
            **payload,
            "receipt_sha256": _canonical_json_sha256(canonical),
        }
    )


def verify_claimed_use_match_receipt(
    receipt: ClaimedUseMatchReceipt,
    *,
    attestation_key: bytes,
    patent_id: str,
    claim_number: int,
    controlling_claim_text: str,
    current_claim_receipt_sha256: str,
    controlling_claim_document_ids: list[str],
    target_product_identity: str,
    compound: object,
    proposed_indication: str,
    proposed_label_use: str,
    label_carve_out_state: LabelCarveOutState,
) -> bool:
    """Verify signature and every decisive subject/context binding."""
    expected_values = (
        receipt.patent_id == "".join(str(patent_id).strip().upper().split()),
        receipt.claim_number == claim_number,
        receipt.controlling_claim_text_sha256 == _text_sha256(controlling_claim_text),
        receipt.current_claim_receipt_sha256 == current_claim_receipt_sha256,
        receipt.controlling_claim_document_ids == controlling_claim_document_ids,
        receipt.declared_target_product_sha256 == _text_sha256(target_product_identity),
        receipt.resolved_compound_identity_sha256 == resolved_compound_identity_sha256(compound),
        receipt.proposed_indication_sha256 == _text_sha256(proposed_indication),
        receipt.proposed_label_use_sha256 == _text_sha256(proposed_label_use),
        receipt.label_carve_out_state == label_carve_out_state,
        receipt.label_carve_out_state != "complete",
    )
    if not all(expected_values):
        return False
    return verify_claimed_use_match_attestation(
        receipt,
        attestation_key=attestation_key,
    )


def verify_claimed_use_match_attestation(
    receipt: ClaimedUseMatchReceipt,
    *,
    attestation_key: bytes,
) -> bool:
    """Verify the server attestation independently of external subject context."""
    if len(attestation_key) < 32:
        return False
    unsigned = receipt.model_dump(
        mode="json",
        exclude={"receipt_sha256", "attestation_hmac_sha256"},
    )
    expected_hmac = hmac.new(
        attestation_key,
        _CLAIMED_USE_ATTESTATION_DOMAIN + _canonical_json_bytes(unsigned),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(receipt.attestation_hmac_sha256, expected_hmac)


class AccusedActRecord(BaseModel):
    """One explicit act, actor, place, time, status, and purpose assertion."""

    model_config = ConfigDict(extra="forbid")

    act: AccusedActType
    jurisdiction: Annotated[str, Field(min_length=2, max_length=40)]
    start_date: date
    end_date: date | None = None
    actor: Annotated[str, Field(min_length=1, max_length=240)]
    status: AccusedActStatus
    purpose: AccusedActPurpose
    regulatory_path: RegulatorySubmissionPath = "none"
    instrumentality: Annotated[str, Field(min_length=1, max_length=500)]
    liability_theory: AccusedActLiabilityTheory = "unknown"
    performs_all_claim_steps: bool | None = None
    direct_infringer: Annotated[str, Field(min_length=1, max_length=240)] | None = None
    knowledge_of_patent: bool | None = None
    affirmative_encouragement: bool | None = None
    manufacturing_jurisdiction: Annotated[str, Field(min_length=2, max_length=40)] | None = None
    process_used: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    process_use_verified: bool | None = None
    materially_changed_after_process: bool | None = None
    trivial_component_after_process: bool | None = None
    target_product_identity: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    proposed_indication: Annotated[str, Field(min_length=1, max_length=1000)] | None = None
    proposed_label_use: Annotated[str, Field(min_length=1, max_length=4000)] | None = None
    label_carve_out_state: LabelCarveOutState | None = None
    claimed_use_match_receipts: list[ClaimedUseMatchReceipt] = Field(
        default_factory=list,
        max_length=100,
    )

    @field_validator("jurisdiction", "manufacturing_jurisdiction", mode="before")
    @classmethod
    def normalize_jurisdiction(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Jurisdiction must be text")
        normalized = " ".join(value.strip().upper().replace("_", " ").split())
        if not normalized:
            raise ValueError("Jurisdiction is required")
        return _JURISDICTION_ALIASES.get(normalized, normalized)

    @field_validator(
        "actor",
        "instrumentality",
        "direct_infringer",
        "process_used",
        "target_product_identity",
        "proposed_indication",
        "proposed_label_use",
        mode="before",
    )
    @classmethod
    def normalize_required_text(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Expected a text value")
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("Value is required")
        return normalized

    @model_validator(mode="after")
    def validate_temporal_and_regulatory_contract(self) -> AccusedActRecord:
        today = date.today()
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if self.status == "actual" and self.start_date > today:
            raise ValueError("actual acts cannot start in the future")
        if self.status == "planned" and self.start_date < today:
            raise ValueError(
                "planned acts with an elapsed start date require reconfirmation as actual"
            )
        if self.act == "regulatory_submission" and self.regulatory_path == "none":
            raise ValueError("regulatory_submission acts require an explicit regulatory_path")
        if self.act != "regulatory_submission" and self.regulatory_path != "none":
            raise ValueError("regulatory_path is only valid for regulatory_submission acts")
        if self.act == "regulatory_submission" and self.purpose != "regulatory_approval":
            raise ValueError("regulatory_submission acts require purpose=regulatory_approval")
        if (
            self.act == "regulatory_submission"
            and self.liability_theory != "artificial_infringement"
        ):
            raise ValueError(
                "regulatory_submission acts require liability_theory=artificial_infringement"
            )
        if self.act == "regulatory_submission" and any(
            value is None
            for value in (
                self.target_product_identity,
                self.proposed_indication,
                self.proposed_label_use,
                self.label_carve_out_state,
            )
        ):
            raise ValueError(
                "regulatory_submission acts require target product, proposed "
                "indication, proposed label use, and carve-out state"
            )
        if self.act != "regulatory_submission" and (
            self.target_product_identity is not None
            or self.proposed_indication is not None
            or self.proposed_label_use is not None
            or self.label_carve_out_state is not None
            or self.claimed_use_match_receipts
        ):
            raise ValueError("submission-use facts are only valid for regulatory submissions")
        if (
            self.act != "regulatory_submission"
            and self.liability_theory == "artificial_infringement"
        ):
            raise ValueError("artificial_infringement is only valid for regulatory submissions")
        return self

    @property
    def can_establish_exposure(self) -> bool:
        """Only affirmative actual or planned facts may govern a decision."""
        return self.status in {"actual", "planned"}


__all__ = [
    "AccusedActLiabilityTheory",
    "AccusedActPurpose",
    "AccusedActRecord",
    "AccusedActStatus",
    "AccusedActType",
    "ClaimedUseMatchReceipt",
    "LabelCarveOutState",
    "RegulatorySubmissionPath",
    "create_claimed_use_match_receipt",
    "resolved_compound_identity_sha256",
    "verify_claimed_use_match_attestation",
    "verify_claimed_use_match_receipt",
]
