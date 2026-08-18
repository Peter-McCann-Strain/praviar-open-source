"""Tamper-evident receipts for supervised PATENTSCOPE Markush searches."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from pathlib import PurePath
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from praviar_pipeline.utils.patent_ids import canonical_publication_id

MarkushEvidenceStatus = Literal[
    "verified_manual",
    "not_run",
    "incomplete",
    "unavailable",
]
MarkushQueryRole = Literal["target_compound", "murcko_scaffold"]
PatentscopeChemicalSearchMode = Literal["exact", "substructure", "scaffold"]
PatentscopeMarkushMethod = Literal["enumeration", "formula_matching"]
PatentscopeMarkushMatchMode = Literal["exact", "substructure", "fuzzy"]

_MAX_ARTIFACT_BYTES = 25 * 1024 * 1024
_PATENTSCOPE_MARKUSH_URL = "https://patentscope.wipo.int/search/en/structure.jsf"
_MARKUSH_ATTESTATION_DOMAIN = b"praviar:patentscope-markush-evidence:v3\0"
PATENTSCOPE_MARKUSH_REQUIRED_LIMITATIONS = (
    "PATENTSCOPE does not document a stable chemical-search workbook schema "
    "or a supported free automation API.",
    "Complex and repeating-group standardization or interactive search limits "
    "may omit relevant candidates.",
    "This receipt proves the supervised query and selected export evidence; it "
    "does not establish legal claim construction or exhaustive recall.",
    "This is a server-attested, independently reviewed analyst assertion; it is "
    "not evidence authenticated or digitally signed by WIPO.",
)


def _canonical_json_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def markush_query_structure_sha256(query_structure: str) -> str:
    """Hash the exact non-empty structure representation used in PATENTSCOPE."""
    normalized = str(query_structure or "").strip()
    if not normalized:
        raise ValueError("Markush query structure is required")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class MarkushEvidenceReceipt(BaseModel):
    """Content-addressed evidence for one supervised PATENTSCOPE Markush search.

    PATENTSCOPE does not document a stable chemical-search Excel schema or a
    supported automation API. The original export therefore remains the
    evidence artifact while this receipt records the supervised query context
    separately. ``markush_enabled`` is explicit because it cannot be inferred
    from a general-results workbook row.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["patentscope-markush-evidence-v3"] = "patentscope-markush-evidence-v3"
    source: Literal["wipo_patentscope_manual"] = "wipo_patentscope_manual"
    source_url: Literal["https://patentscope.wipo.int/search/en/structure.jsf"] = (
        "https://patentscope.wipo.int/search/en/structure.jsf"
    )
    status: MarkushEvidenceStatus
    organization_id: str = Field(min_length=1, max_length=128)
    target_structure_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_structure_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_role: MarkushQueryRole
    chemical_search_mode: PatentscopeChemicalSearchMode
    markush_enabled: Literal[True] = True
    markush_method: PatentscopeMarkushMethod
    markush_match_mode: PatentscopeMarkushMatchMode
    wipo_query_field: Literal["ENUM"] | None = None
    family_grouping_enabled: bool
    executed_at: datetime | None = None
    server_imported_at: datetime | None = None
    analyst_identity: str | None = Field(default=None, min_length=1, max_length=320)
    reviewer_identity: str | None = Field(default=None, min_length=1, max_length=320)
    artifact_filename: str | None = Field(default=None, min_length=1, max_length=255)
    artifact_media_type: (
        Literal["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"] | None
    ) = None
    imported_artifact_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    imported_artifact_size_bytes: int | None = Field(
        default=None,
        ge=1,
        le=_MAX_ARTIFACT_BYTES,
    )
    controls_artifact_filename: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    controls_artifact_media_type: Literal["image/png"] | None = None
    controls_artifact_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    controls_artifact_size_bytes: int | None = Field(
        default=None,
        ge=32,
        le=_MAX_ARTIFACT_BYTES,
    )
    result_count: int | None = Field(default=None, ge=0)
    selected_publication_ids: list[str] = Field(default_factory=list, max_length=10000)
    selected_publication_ids_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    limitations: list[str] = Field(min_length=1, max_length=50)
    attestation_key_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
    )
    attestation_hmac_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("analyst_identity", "reviewer_identity", mode="before")
    @classmethod
    def _normalize_identity(cls, value: object) -> object:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator(
        "artifact_filename",
        "controls_artifact_filename",
        mode="before",
    )
    @classmethod
    def _validate_artifact_filename(cls, value: object) -> object:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized or PurePath(normalized).name != normalized:
            raise ValueError("artifact filename must be a basename")
        return normalized

    @field_validator("selected_publication_ids")
    @classmethod
    def _canonicalize_publication_ids(cls, values: list[str]) -> list[str]:
        canonical = [canonical_publication_id(value) for value in values]
        if len(canonical) != len(set(canonical)):
            raise ValueError("selected publication identifiers must be unique")
        return canonical

    @field_validator("limitations")
    @classmethod
    def _normalize_limitations(cls, values: list[str]) -> list[str]:
        normalized = [str(value).strip() for value in values]
        if not all(normalized):
            raise ValueError("Markush evidence limitations cannot be blank")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Markush evidence limitations must be unique")
        return normalized

    @model_validator(mode="after")
    def _verify_evidence_contract(self) -> MarkushEvidenceReceipt:
        if not set(PATENTSCOPE_MARKUSH_REQUIRED_LIMITATIONS).issubset(self.limitations):
            raise ValueError("Markush evidence omits required PATENTSCOPE limitations")
        if self.markush_method == "enumeration":
            if (
                self.chemical_search_mode != "exact"
                or self.markush_match_mode != "exact"
                or self.wipo_query_field != "ENUM"
            ):
                raise ValueError(
                    "PATENTSCOPE enumeration requires exact chemical and Markush "
                    "matching with the ENUM query field"
                )
        elif self.wipo_query_field is not None:
            raise ValueError("ENUM is valid only for PATENTSCOPE enumeration")
        expected_selection_digest = _canonical_json_sha256(self.selected_publication_ids)
        if self.selected_publication_ids_sha256 != expected_selection_digest:
            raise ValueError("selected publication identifier digest mismatch")

        artifact_fields = (
            self.artifact_filename,
            self.artifact_media_type,
            self.imported_artifact_sha256,
            self.imported_artifact_size_bytes,
            self.controls_artifact_filename,
            self.controls_artifact_media_type,
            self.controls_artifact_sha256,
            self.controls_artifact_size_bytes,
        )
        has_artifact = all(value is not None for value in artifact_fields)
        if any(value is not None for value in artifact_fields) and not has_artifact:
            raise ValueError("imported artifact metadata must be complete")

        if self.status == "verified_manual":
            required = (
                self.executed_at,
                self.server_imported_at,
                self.analyst_identity,
                self.reviewer_identity,
                *artifact_fields,
                self.result_count,
            )
            if any(value is None for value in required):
                raise ValueError("verified manual Markush evidence is incomplete")
            if self.analyst_identity == self.reviewer_identity:
                raise ValueError("Markush analyst and reviewer must be distinct")
            if self.attestation_key_id is None or self.attestation_hmac_sha256 is None:
                raise ValueError("verified manual Markush evidence must be server-attested")
            if self.result_count is not None and self.result_count < len(
                self.selected_publication_ids
            ):
                raise ValueError("selected publications exceed the recorded result count")
        elif self.status in {"not_run", "unavailable"}:
            if (
                has_artifact
                or self.executed_at is not None
                or self.server_imported_at is not None
                or self.result_count is not None
                or self.selected_publication_ids
            ):
                raise ValueError(f"{self.status} Markush evidence cannot contain search results")
        elif self.selected_publication_ids and (not has_artifact or self.result_count is None):
            raise ValueError("incomplete selected results require their original artifact")
        if (self.attestation_key_id is None) != (self.attestation_hmac_sha256 is None):
            raise ValueError("Markush evidence attestation metadata is incomplete")

        if self.executed_at is not None:
            executed_at = self.executed_at
            if executed_at.tzinfo is None or executed_at.utcoffset() is None:
                raise ValueError("Markush execution time must be timezone-aware")
            if executed_at.astimezone(UTC) > datetime.now(UTC):
                raise ValueError("Markush execution time cannot be in the future")
        if self.server_imported_at is not None:
            imported_at = self.server_imported_at
            if imported_at.tzinfo is None or imported_at.utcoffset() is None:
                raise ValueError("Markush server import time must be timezone-aware")
            if imported_at.astimezone(UTC) > datetime.now(UTC) + timedelta(minutes=1):
                raise ValueError("Markush server import time cannot be in the future")
            if self.executed_at is None:
                raise ValueError("Markush server import time requires execution time")
            execution_time = self.executed_at.astimezone(UTC)
            normalized_import_time = imported_at.astimezone(UTC)
            if execution_time > normalized_import_time:
                raise ValueError("Markush execution cannot follow server import")
            if normalized_import_time - execution_time > timedelta(hours=24):
                raise ValueError(
                    "PATENTSCOPE evidence must be imported within 24 hours of execution"
                )

        payload = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if self.receipt_sha256 != _canonical_json_sha256(payload):
            raise ValueError("Markush evidence receipt digest mismatch")
        return self


def build_markush_evidence_receipt(
    *,
    status: MarkushEvidenceStatus,
    organization_id: str,
    target_structure: str,
    query_structure: str,
    query_role: MarkushQueryRole,
    chemical_search_mode: PatentscopeChemicalSearchMode,
    markush_method: PatentscopeMarkushMethod,
    markush_match_mode: PatentscopeMarkushMatchMode,
    wipo_query_field: Literal["ENUM"] | None,
    family_grouping_enabled: bool,
    limitations: list[str],
    executed_at: datetime | None = None,
    server_imported_at: datetime | None = None,
    analyst_identity: str | None = None,
    reviewer_identity: str | None = None,
    artifact_bytes: bytes | None = None,
    artifact_filename: str | None = None,
    artifact_media_type: str | None = None,
    controls_artifact_bytes: bytes | None = None,
    controls_artifact_filename: str | None = None,
    controls_artifact_media_type: str | None = None,
    result_count: int | None = None,
    selected_publication_ids: list[str] | None = None,
    attestation_key_id: str | None = None,
    attestation_key: bytes | None = None,
) -> MarkushEvidenceReceipt:
    """Build a receipt while deriving every digest from the supplied evidence."""
    if artifact_bytes is not None:
        if not artifact_bytes:
            raise ValueError("PATENTSCOPE evidence artifact cannot be empty")
        if len(artifact_bytes) > _MAX_ARTIFACT_BYTES:
            raise ValueError("PATENTSCOPE evidence artifact exceeds 25 MiB")
        artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
        artifact_size = len(artifact_bytes)
    else:
        artifact_sha256 = None
        artifact_size = None
    if controls_artifact_bytes is not None:
        if len(controls_artifact_bytes) < 32:
            raise ValueError("PATENTSCOPE controls artifact is incomplete")
        if len(controls_artifact_bytes) > _MAX_ARTIFACT_BYTES:
            raise ValueError("PATENTSCOPE controls artifact exceeds 25 MiB")
        controls_artifact_sha256 = hashlib.sha256(controls_artifact_bytes).hexdigest()
        controls_artifact_size = len(controls_artifact_bytes)
    else:
        controls_artifact_sha256 = None
        controls_artifact_size = None

    canonical_ids = [canonical_publication_id(value) for value in (selected_publication_ids or [])]
    canonical_limitations = list(
        dict.fromkeys(
            [
                *PATENTSCOPE_MARKUSH_REQUIRED_LIMITATIONS,
                *(str(value).strip() for value in limitations if str(value).strip()),
            ]
        )
    )
    if (attestation_key_id is None) != (attestation_key is None):
        raise ValueError("Markush attestation key ID and key must be supplied together")
    if status == "verified_manual" and attestation_key is None:
        raise ValueError("verified manual Markush evidence requires server attestation")
    if attestation_key is not None and len(attestation_key) < 32:
        raise ValueError("Markush attestation key must contain at least 32 bytes")

    payload = {
        "schema_version": "patentscope-markush-evidence-v3",
        "source": "wipo_patentscope_manual",
        "source_url": _PATENTSCOPE_MARKUSH_URL,
        "status": status,
        "organization_id": str(organization_id).strip(),
        "target_structure_sha256": markush_query_structure_sha256(target_structure),
        "query_structure_sha256": markush_query_structure_sha256(query_structure),
        "query_role": query_role,
        "chemical_search_mode": chemical_search_mode,
        "markush_enabled": True,
        "markush_method": markush_method,
        "markush_match_mode": markush_match_mode,
        "wipo_query_field": wipo_query_field,
        "family_grouping_enabled": family_grouping_enabled,
        "executed_at": executed_at,
        "server_imported_at": server_imported_at,
        "analyst_identity": analyst_identity,
        "reviewer_identity": reviewer_identity,
        "artifact_filename": artifact_filename,
        "artifact_media_type": artifact_media_type,
        "imported_artifact_sha256": artifact_sha256,
        "imported_artifact_size_bytes": artifact_size,
        "controls_artifact_filename": controls_artifact_filename,
        "controls_artifact_media_type": controls_artifact_media_type,
        "controls_artifact_sha256": controls_artifact_sha256,
        "controls_artifact_size_bytes": controls_artifact_size,
        "result_count": result_count,
        "selected_publication_ids": canonical_ids,
        "selected_publication_ids_sha256": _canonical_json_sha256(canonical_ids),
        "limitations": canonical_limitations,
        "attestation_key_id": attestation_key_id,
        "attestation_hmac_sha256": None,
    }
    if attestation_key is not None:
        unsigned_payload = (
            cast("Any", MarkushEvidenceReceipt)
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
            _MARKUSH_ATTESTATION_DOMAIN + _canonical_json_bytes(unsigned_payload),
            hashlib.sha256,
        ).hexdigest()
    canonical_payload = (
        cast("Any", MarkushEvidenceReceipt)
        .model_construct(
            **payload,
            receipt_sha256="0" * 64,
        )
        .model_dump(mode="json", exclude={"receipt_sha256"})
    )
    return MarkushEvidenceReceipt.model_validate(
        {
            **payload,
            "receipt_sha256": _canonical_json_sha256(canonical_payload),
        }
    )


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def verify_markush_evidence_attestation(
    receipt: MarkushEvidenceReceipt,
    *,
    attestation_key: bytes,
) -> bool:
    """Verify the server HMAC without exposing key material in the receipt."""
    if receipt.attestation_hmac_sha256 is None or len(attestation_key) < 32:
        return False
    unsigned_payload = receipt.model_dump(
        mode="json",
        exclude={"receipt_sha256", "attestation_hmac_sha256"},
    )
    expected = hmac.new(
        attestation_key,
        _MARKUSH_ATTESTATION_DOMAIN + _canonical_json_bytes(unsigned_payload),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(receipt.attestation_hmac_sha256, expected)
