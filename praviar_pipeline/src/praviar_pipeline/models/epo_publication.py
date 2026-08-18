"""High-assurance evidence models for the European Publication Server.

The European Publication Server (EPS) is the EPO's legally authoritative
publication medium for modern EP A and B documents.  These models deliberately
keep publication identity, procedure evidence, and the exact downloaded media
together.  A document kind code by itself is never treated as a chronology or
as proof that a central opposition, limitation, or appeal has concluded.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Literal
from urllib.parse import parse_qs, urlsplit

from defusedxml import ElementTree
from pydantic import BaseModel, ConfigDict, Field, model_validator

EPS_XML_MAX_BYTES = 32 * 1024 * 1024
EPS_PDF_MAX_BYTES = 100 * 1024 * 1024
EPS_ARTIFACT_MAX_BYTES = EPS_XML_MAX_BYTES + EPS_PDF_MAX_BYTES
EP_ACQUISITION_MANIFEST_MAX_BYTES = 4 * 1024 * 1024
EP_CHECKPOINT_SOURCE_STREAM_ID = "epo-central-claims"
EP_CHECKPOINT_SCHEMA_EPOCH = 1


class EPCentralProcedureState(StrEnum):
    """Current central EPO procedure state supplied by retained register evidence."""

    CLEAR = "clear"
    OPPOSITION_PENDING = "opposition_pending"
    LIMITATION_PENDING = "limitation_pending"
    APPEAL_PENDING = "appeal_pending"
    CENTRALLY_REVOKED = "centrally_revoked"
    UNKNOWN = "unknown"


class EPSuspensiveAppealState(StrEnum):
    """Whether an appeal can still prevent a central decision taking effect."""

    NOT_APPLICABLE = "not_applicable"
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


class EPClaimsResolutionStatus(StrEnum):
    """Whether exact current central claims were resolved."""

    RESOLVED = "resolved"
    INDETERMINATE = "indeterminate"
    NO_CENTRAL_CLAIMS = "no_central_claims"


class EPClaimsResolutionReason(StrEnum):
    """Stable, machine-readable fail-closed resolution reason."""

    RESOLVED = "resolved"
    AUTHORITY_MANIFEST_INCOMPLETE = "authority_manifest_incomplete"
    AUTHORITY_EVIDENCE_UNTRUSTED = "authority_evidence_untrusted"
    AUTHORITY_CONTENT_MISMATCH = "authority_content_mismatch"
    AUTHORITY_EXCEPTION_PRESENT = "authority_exception_present"
    PROCEDURE_EVIDENCE_MISSING = "procedure_evidence_missing"
    PROCEDURE_EVIDENCE_UNTRUSTED = "procedure_evidence_untrusted"
    PROCEDURE_CONTENT_MISMATCH = "procedure_content_mismatch"
    CENTRAL_PROCEEDING_PENDING = "central_proceeding_pending"
    CENTRAL_PROCEEDING_UNKNOWN = "central_proceeding_unknown"
    SUSPENSIVE_APPEAL_UNRESOLVED = "suspensive_appeal_unresolved"
    CENTRALLY_REVOKED = "centrally_revoked"
    PROCEDURE_SUBJECT_MISMATCH = "procedure_subject_mismatch"
    PUBLICATION_SET_EMPTY = "publication_set_empty"
    BASE_GRANT_MISSING = "base_grant_missing"
    DUPLICATE_PUBLICATION = "duplicate_publication"
    CONFLICTING_PUBLICATION = "conflicting_publication"
    EFFECTIVE_DATE_MISSING = "effective_date_missing"
    CORRECTION_TARGET_MISSING = "correction_target_missing"
    CORRECTION_CHAIN_INCOMPLETE = "correction_chain_incomplete"
    CURRENT_EVIDENCE_STALE = "current_evidence_stale"
    HIGH_WATER_EVIDENCE_MISSING = "high_water_evidence_missing"
    CHECKPOINT_STORE_UNAVAILABLE = "checkpoint_store_unavailable"
    EVIDENCE_ROLLBACK_DETECTED = "evidence_rollback_detected"
    RESOLUTION_AS_OF_MISMATCH = "resolution_as_of_mismatch"
    RESOURCE_LIMIT_EXCEEDED = "resource_limit_exceeded"


def _canonical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("signature timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def build_ep_acquisition_signature_payload(
    *,
    manifest_type: Literal["authority", "register"],
    manifest_schema_version: str,
    signing_key_id: str,
    key_revocation_epoch: int,
    signed_at: datetime,
    manifest_bytes: bytes,
) -> bytes:
    """Build the domain-separated Ed25519 payload for an acquisition manifest."""
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    metadata = _canonical_json_bytes(
        {
            "envelope_version": "praviar-epo-acquisition-envelope-v1",
            "key_revocation_epoch": key_revocation_epoch,
            "manifest_length": len(manifest_bytes),
            "manifest_schema_version": manifest_schema_version,
            "manifest_sha256": manifest_sha256,
            "manifest_type": manifest_type,
            "signed_at": _utc_iso(signed_at),
            "signing_key_id": signing_key_id,
        }
    )
    return (
        b"praviar:epo-acquisition-receipt:v1\0"
        + len(metadata).to_bytes(4, "big")
        + metadata
        + len(manifest_bytes).to_bytes(8, "big")
        + manifest_bytes
    )


def build_ep_snapshot_high_water_signature_payload(
    *,
    source_stream_id: str,
    schema_epoch: int,
    manifest_type: Literal["authority", "register"],
    subject: str,
    required_as_of: date,
    checkpoint_batch_sha256: str,
    checkpoint_generation: int,
    counterpart_source_acquisition_envelope_sha256: str,
    prior_checkpoint_envelope_sha256: str | None,
    minimum_snapshot_sequence: int,
    source_acquisition_envelope_sha256: str,
    signing_key_id: str,
    key_revocation_epoch: int,
    signed_at: datetime,
) -> bytes:
    """Build the domain-separated payload for a monotonic snapshot floor."""
    statement = _canonical_json_bytes(
        {
            "envelope_version": "praviar-epo-high-water-envelope-v1",
            "source_stream_id": source_stream_id,
            "schema_epoch": schema_epoch,
            "checkpoint_batch_sha256": checkpoint_batch_sha256,
            "counterpart_source_acquisition_envelope_sha256": (
                counterpart_source_acquisition_envelope_sha256
            ),
            "key_revocation_epoch": key_revocation_epoch,
            "manifest_type": manifest_type,
            "checkpoint_generation": checkpoint_generation,
            "minimum_snapshot_sequence": minimum_snapshot_sequence,
            "prior_checkpoint_envelope_sha256": prior_checkpoint_envelope_sha256,
            "required_as_of": required_as_of.isoformat(),
            "signed_at": _utc_iso(signed_at),
            "signing_key_id": signing_key_id,
            "source_acquisition_envelope_sha256": source_acquisition_envelope_sha256,
            "subject": subject,
        }
    )
    return b"praviar:epo-snapshot-high-water:v1\0" + len(statement).to_bytes(4, "big") + statement


def build_ep_snapshot_checkpoint_batch_sha256(
    *,
    source_stream_id: str,
    schema_epoch: int,
    authority_subject: str,
    register_subject: str,
    required_as_of: date,
    authority_checkpoint_generation: int,
    register_checkpoint_generation: int,
    authority_prior_checkpoint_envelope_sha256: str | None,
    register_prior_checkpoint_envelope_sha256: str | None,
    authority_minimum_snapshot_sequence: int,
    register_minimum_snapshot_sequence: int,
    authority_source_acquisition_envelope_sha256: str,
    register_source_acquisition_envelope_sha256: str,
) -> str:
    """Digest the complete causal identity of one authority/Register checkpoint batch."""
    statement = _canonical_json_bytes(
        {
            "source_stream_id": source_stream_id,
            "schema_epoch": schema_epoch,
            "authority_checkpoint_generation": authority_checkpoint_generation,
            "authority_minimum_snapshot_sequence": authority_minimum_snapshot_sequence,
            "authority_prior_checkpoint_envelope_sha256": (
                authority_prior_checkpoint_envelope_sha256
            ),
            "authority_source_acquisition_envelope_sha256": (
                authority_source_acquisition_envelope_sha256
            ),
            "authority_subject": authority_subject,
            "batch_version": "praviar-epo-checkpoint-batch-v1",
            "register_checkpoint_generation": register_checkpoint_generation,
            "register_minimum_snapshot_sequence": register_minimum_snapshot_sequence,
            "register_prior_checkpoint_envelope_sha256": (
                register_prior_checkpoint_envelope_sha256
            ),
            "register_source_acquisition_envelope_sha256": (
                register_source_acquisition_envelope_sha256
            ),
            "register_subject": register_subject,
            "required_as_of": required_as_of.isoformat(),
        }
    )
    envelope = b"praviar:epo-checkpoint-batch:v1\0" + len(statement).to_bytes(4, "big") + statement
    return hashlib.sha256(envelope).hexdigest()


def _is_official_register_locator(locator: str, source_document_id: str) -> bool:
    parsed = urlsplit(locator)
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.fragment
    ):
        return False
    if parsed.hostname == "register.epo.org" and parsed.path == "/application":
        try:
            query = parse_qs(parsed.query, strict_parsing=True)
        except ValueError:
            return False
        return query == {"number": [source_document_id]}
    expected_ops_path = (
        "/3.2/rest-services/register/publication/epodoc/"
        f"{source_document_id}/biblio,events,procedural-steps"
    )
    return (
        parsed.hostname == "ops.epo.org" and parsed.path == expected_ops_path and not parsed.query
    )


def _is_official_authority_locator(locator: str) -> bool:
    parsed = urlsplit(locator)
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.fragment
    ):
        return False
    if parsed.hostname == "data.epo.org":
        return parsed.path.startswith("/publication-server/rest/v1.2/publication-dates/")
    if parsed.hostname == "link.epo.org":
        return parsed.path.startswith("/web/publication-server/authority-file/")
    return False


def build_ep_procedure_evidence_binding_sha256(
    *,
    source_document_id: str,
    source_locator: str,
    as_of: date,
    retained_register_sha256: str,
) -> str:
    """Bind one retained EPO Register artifact to its subject and as-of date."""
    return _canonical_sha256(
        {
            "as_of": as_of.isoformat(),
            "retained_register_sha256": retained_register_sha256,
            "source_document_id": source_document_id,
            "source_locator": source_locator,
        }
    )


def build_ep_authority_evidence_binding_sha256(
    *,
    publication_number: str,
    coverage_method: str,
    source_locator: str,
    coverage_from: date,
    coverage_through: date,
    record_count: int,
    retained_authority_sha256: str,
) -> str:
    """Bind retained authority/weekly coverage to one publication record set."""
    return _canonical_sha256(
        {
            "coverage_from": coverage_from.isoformat(),
            "coverage_method": coverage_method,
            "coverage_through": coverage_through.isoformat(),
            "publication_number": publication_number,
            "record_count": record_count,
            "retained_authority_sha256": retained_authority_sha256,
            "source_locator": source_locator,
        }
    )


def _xml_local_name(element: object) -> str:
    return str(getattr(element, "tag", "")).rsplit("}", 1)[-1]


def _xml_text(element: object) -> str:
    return " ".join("".join(element.itertext()).split())  # type: ignore[attr-defined]


def _reparse_eps_artifact(
    record: EPSPublicationRecord,
    raw_xml: bytes,
) -> dict[str, object]:
    """Deterministically derive every artifact field from retained XML bytes."""
    try:
        root = ElementTree.fromstring(raw_xml)
    except Exception as exc:
        raise ValueError("retained EPS XML is unsafe or malformed") from exc
    if _xml_local_name(root).lower() != "ep-patent-document":
        raise ValueError("retained EPS XML root is invalid")
    xml_document_id = str(root.attrib.get("id", "")).strip()
    xml_file_name = str(root.attrib.get("file", "")).strip()
    xml_number = str(root.attrib.get("doc-number", "")).strip().zfill(7)
    xml_kind = str(root.attrib.get("kind", "")).strip().upper()
    xml_root_language = str(root.attrib.get("lang", "")).strip().lower()
    raw_date = str(root.attrib.get("date-publ", "")).strip()
    try:
        xml_publication_date = datetime.strptime(raw_date, "%Y%m%d").date()
    except ValueError:
        raise ValueError("retained EPS XML publication date is invalid") from None
    if (
        not xml_document_id
        or not xml_file_name
        or xml_number != record.publication_number
        or xml_kind != record.kind
        or xml_publication_date != record.publication_date
        or xml_root_language not in {"en", "de", "fr"}
        or not xml_file_name.upper().endswith(f"{record.kind}.XML")
    ):
        raise ValueError("retained EPS XML identity does not match the publication record")

    procedure_languages = {
        _xml_text(element).lower()
        for element in root.iter()
        if _xml_local_name(element).upper() == "B251EP" and _xml_text(element)
    }
    if len(procedure_languages) != 1:
        raise ValueError("retained EPS XML procedure language is missing or ambiguous")
    proceedings_language = next(iter(procedure_languages))
    if proceedings_language not in {"en", "de", "fr"}:
        raise ValueError("retained EPS XML procedure language is invalid")

    if record.kind == "B9":
        correction_matches: set[tuple[int, str]] = set()
        pattern = re.compile(r"\bW([1-9][0-9]*)(B[123])\b")
        for element in root.iter():
            local = _xml_local_name(element).lower()
            candidates: list[str] = []
            if "correction" in local or local.startswith("b015"):
                candidates.extend(str(value) for value in element.attrib.values())
                candidates.append(_xml_text(element))
            for key, value in element.attrib.items():
                if "correction" in str(key).lower():
                    candidates.append(str(value))
            for candidate in candidates:
                correction_matches.update(
                    (int(match.group(1)), match.group(2))
                    for match in pattern.finditer(candidate.upper())
                )
        target = str(record.correction_of_document_id or "")
        if (
            len(correction_matches) != 1
            or next(iter(correction_matches))[0] != record.correction_sequence
            or not target.endswith(next(iter(correction_matches))[1])
        ):
            raise ValueError("retained B9 XML correction linkage does not match record")

    containers = [
        element
        for element in root.iter()
        if _xml_local_name(element).lower() == "claims"
        and str(element.attrib.get("lang", "")).strip().lower() == proceedings_language
    ]
    if len(containers) != 1:
        raise ValueError("retained EPS XML lacks one proceedings-language claims section")
    claims: list[tuple[int, str]] = []
    for element in containers[0].iter():
        if _xml_local_name(element).lower() != "claim":
            continue
        if len(claims) >= 1_000:
            raise ValueError("retained EPS XML exceeds the claim-count limit")
        raw_number = str(
            element.attrib.get("num")
            or element.attrib.get("number")
            or element.attrib.get("id")
            or ""
        ).strip()
        number_match = re.search(r"([0-9]+)$", raw_number)
        if number_match is None:
            raise ValueError("retained EPS XML claim number is invalid")
        number = int(number_match.group(1))
        text = re.sub(
            rf"^\s*(?:claim\s+)?0*{number}\s*[.:]\s*",
            "",
            _xml_text(element),
            count=1,
            flags=re.IGNORECASE,
        ).strip()
        if not text:
            raise ValueError("retained EPS XML contains an empty claim")
        claims.append((number, text))
    claim_numbers = tuple(number for number, _text in claims)
    if claim_numbers != tuple(range(1, len(claim_numbers) + 1)):
        raise ValueError("retained EPS XML claim numbering is incomplete")
    claims_text = "\n\n".join(f"{number}. {text}" for number, text in claims)
    return {
        "claim_numbers": claim_numbers,
        "claims_text": claims_text,
        "claims_text_sha256": hashlib.sha256(claims_text.encode("utf-8")).hexdigest(),
        "proceedings_language": proceedings_language,
        "xml_document_id": xml_document_id,
        "xml_file_name": xml_file_name,
        "xml_root_language": xml_root_language,
    }


class EPSPublicationRecord(BaseModel):
    """One exact B-document record from a complete official publication manifest.

    ``eps_document_id`` is the path identifier used by EPS REST v1.2.  It is
    intentionally retained separately from the XML root's ``id`` and ``file``
    attributes because those identifiers are not interchangeable.

    ``effective_date`` must come from authoritative procedure evidence.  The
    resolver never substitutes the publication date and never infers chronology
    by sorting kind codes.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    country_code: Literal["EP"] = "EP"
    publication_number: str = Field(pattern=r"^[0-9]{7}$")
    eps_document_id: str = Field(pattern=r"^EP[0-9]{7}[A-Z0-9]{2,8}B[1239]$")
    kind: Literal["B1", "B2", "B3", "B9"]
    publication_date: date
    effective_date: date | None
    authority_as_of: date
    authority_exception_code: str = Field(default="", max_length=1)
    correction_of_document_id: str | None = None
    correction_sequence: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _validate_identity_and_correction(self) -> EPSPublicationRecord:
        if not self.eps_document_id.startswith(f"EP{self.publication_number}"):
            raise ValueError("EPS document id does not match publication number")
        if not self.eps_document_id.endswith(self.kind):
            raise ValueError("EPS document id does not match kind code")
        if self.publication_date > self.authority_as_of:
            raise ValueError("publication date is later than authority manifest")
        if self.effective_date is not None and self.effective_date > self.authority_as_of:
            raise ValueError("effective date is later than authority manifest")
        if self.kind == "B9":
            if not self.correction_of_document_id or self.correction_sequence is None:
                raise ValueError("B9 record requires an exact correction target and sequence")
            if self.correction_of_document_id == self.eps_document_id:
                raise ValueError("B9 record cannot correct itself")
        elif self.correction_of_document_id is not None or self.correction_sequence is not None:
            raise ValueError("only B9 records may carry correction metadata")
        return self


class EPSMediaArtifact(BaseModel):
    """Exact bytes and content address for one EPS REST response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    media_format: Literal["xml", "pdf"]
    source_url: str = Field(
        pattern=(
            r"^https://data\.epo\.org/publication-server/rest/v1\.2/"
            r"patents/EP[0-9]{7}[A-Z0-9]{2,8}B[1239]/document\.(xml|pdf)$"
        )
    )
    content_type: str = Field(min_length=1)
    retrieved_at: datetime
    raw_bytes: bytes = Field(
        min_length=1,
        max_length=EPS_PDF_MAX_BYTES,
        repr=False,
    )
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _validate_exact_bytes(self) -> EPSMediaArtifact:
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("EPS media retrieved_at must be timezone-aware")
        if self.retrieved_at.astimezone(UTC) > datetime.now(UTC):
            raise ValueError("EPS media retrieved_at is in the future")
        expected_suffix = f"document.{self.media_format}"
        if not self.source_url.endswith(expected_suffix):
            raise ValueError("EPS media URL does not match media format")
        media_limit = EPS_XML_MAX_BYTES if self.media_format == "xml" else EPS_PDF_MAX_BYTES
        if len(self.raw_bytes) > media_limit:
            raise ValueError("EPS media exceeds its model-level byte limit")
        if hashlib.sha256(self.raw_bytes).hexdigest() != self.sha256:
            raise ValueError("EPS media SHA-256 does not match retained bytes")
        return self


class EPSPublicationArtifact(BaseModel):
    """A verified EPS publication with exact XML, PDF, and extracted claims."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record: EPSPublicationRecord
    xml: EPSMediaArtifact
    pdf: EPSMediaArtifact
    xml_document_id: str = Field(min_length=1)
    xml_file_name: str = Field(min_length=1)
    xml_root_language: str = Field(min_length=2, max_length=3)
    proceedings_language: Literal["en", "de", "fr"]
    claims_text: str = Field(min_length=1)
    claim_numbers: tuple[int, ...] = Field(min_length=1)
    claims_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _validate_artifact_binding(self) -> EPSPublicationArtifact:
        if len(self.xml.raw_bytes) + len(self.pdf.raw_bytes) > EPS_ARTIFACT_MAX_BYTES:
            raise ValueError("EPS artifact exceeds its model-level aggregate byte limit")
        if self.xml.media_format != "xml" or self.pdf.media_format != "pdf":
            raise ValueError("EPS artifact media formats are not correctly bound")
        expected_prefix = (
            "https://data.epo.org/publication-server/rest/v1.2/patents/"
            f"{self.record.eps_document_id}/"
        )
        if not self.xml.source_url.startswith(expected_prefix):
            raise ValueError("EPS XML is not bound to the publication record")
        if not self.pdf.source_url.startswith(expected_prefix):
            raise ValueError("EPS PDF is not bound to the publication record")
        if hashlib.sha256(self.claims_text.encode("utf-8")).hexdigest() != (
            self.claims_text_sha256
        ):
            raise ValueError("claims text SHA-256 does not match extracted text")
        if self.claim_numbers != tuple(range(1, len(self.claim_numbers) + 1)):
            raise ValueError("claim numbering is incomplete or non-contiguous")
        reparsed = _reparse_eps_artifact(self.record, self.xml.raw_bytes)
        supplied = {
            "claim_numbers": self.claim_numbers,
            "claims_text": self.claims_text,
            "claims_text_sha256": self.claims_text_sha256,
            "proceedings_language": self.proceedings_language,
            "xml_document_id": self.xml_document_id,
            "xml_file_name": self.xml_file_name,
            "xml_root_language": self.xml_root_language,
        }
        if supplied != reparsed:
            raise ValueError("EPS artifact derived fields do not match retained XML")
        return self


class EPSignedAcquisitionReceipt(BaseModel):
    """Domain-separated Ed25519 envelope over one canonical acquisition manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    envelope_version: Literal["praviar-epo-acquisition-envelope-v1"]
    manifest_type: Literal["authority", "register"]
    manifest_schema_version: Literal[
        "epo-authority-acquisition-v1",
        "epo-register-acquisition-v1",
    ]
    signing_key_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    key_revocation_epoch: int = Field(ge=0)
    signed_at: datetime
    manifest_bytes: bytes = Field(
        min_length=2,
        max_length=EP_ACQUISITION_MANIFEST_MAX_BYTES,
        repr=False,
    )
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature: bytes = Field(min_length=64, max_length=64, repr=False)

    @model_validator(mode="after")
    def _validate_manifest_hash(self) -> EPSignedAcquisitionReceipt:
        if self.signed_at.tzinfo is None or self.signed_at.utcoffset() is None:
            raise ValueError("acquisition receipt signed_at must be timezone-aware")
        if hashlib.sha256(self.manifest_bytes).hexdigest() != self.manifest_sha256:
            raise ValueError("acquisition manifest SHA-256 does not match retained bytes")
        expected_schema = (
            "epo-authority-acquisition-v1"
            if self.manifest_type == "authority"
            else "epo-register-acquisition-v1"
        )
        if self.manifest_schema_version != expected_schema:
            raise ValueError("acquisition manifest schema does not match its purpose")
        return self


def build_ep_acquisition_envelope_sha256(
    receipt: EPSignedAcquisitionReceipt,
) -> str:
    """Digest the complete signed envelope, including the Ed25519 signature."""
    signed_payload = build_ep_acquisition_signature_payload(
        manifest_type=receipt.manifest_type,
        manifest_schema_version=receipt.manifest_schema_version,
        signing_key_id=receipt.signing_key_id,
        key_revocation_epoch=receipt.key_revocation_epoch,
        signed_at=receipt.signed_at,
        manifest_bytes=receipt.manifest_bytes,
    )
    envelope = (
        b"praviar:epo-signed-acquisition-envelope:v1\0"
        + len(signed_payload).to_bytes(8, "big")
        + signed_payload
        + len(receipt.signature).to_bytes(2, "big")
        + receipt.signature
    )
    return hashlib.sha256(envelope).hexdigest()


class EPTrustedAcquisitionKey(BaseModel):
    """Single-purpose EPO trust key with an explicit validity lifecycle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    public_key: bytes = Field(min_length=32, max_length=32, repr=False)
    purpose: Literal[
        "authority_acquisition",
        "register_acquisition",
        "authority_checkpoint",
        "register_checkpoint",
    ]
    not_before: datetime
    not_after: datetime
    status: Literal["active", "revoked"]
    revocation_epoch: int = Field(ge=0)
    revoked_at: datetime | None = None

    @model_validator(mode="after")
    def _validate_trust_window(self) -> EPTrustedAcquisitionKey:
        for value in (self.not_before, self.not_after):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("trusted key validity timestamps must be timezone-aware")
        if self.not_before >= self.not_after:
            raise ValueError("trusted key validity window is empty or reversed")
        if self.status == "revoked":
            if self.revoked_at is None:
                raise ValueError("revoked trusted key requires a revocation timestamp")
        elif self.revoked_at is not None:
            raise ValueError("active trusted key cannot carry a revocation timestamp")
        if self.revoked_at is not None and (
            self.revoked_at.tzinfo is None or self.revoked_at.utcoffset() is None
        ):
            raise ValueError("trusted key revoked_at must be timezone-aware")
        if self.revoked_at is not None and self.revoked_at < self.not_before:
            raise ValueError("trusted key revocation predates its validity window")
        return self


class EPSignedSnapshotHighWaterReceipt(BaseModel):
    """Signed monotonic floor supplied by trusted collector persistence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    envelope_version: Literal["praviar-epo-high-water-envelope-v1"]
    source_stream_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    schema_epoch: int = Field(ge=1)
    manifest_type: Literal["authority", "register"]
    subject: str = Field(pattern=r"^(?:[0-9]{7}|EP[0-9]{7})$")
    required_as_of: date
    checkpoint_batch_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    checkpoint_generation: int = Field(ge=1)
    counterpart_source_acquisition_envelope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prior_checkpoint_envelope_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    minimum_snapshot_sequence: int = Field(ge=1)
    source_acquisition_envelope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signing_key_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    key_revocation_epoch: int = Field(ge=0)
    signed_at: datetime
    signature: bytes = Field(min_length=64, max_length=64, repr=False)

    @model_validator(mode="after")
    def _validate_high_water(self) -> EPSignedSnapshotHighWaterReceipt:
        if self.signed_at.tzinfo is None or self.signed_at.utcoffset() is None:
            raise ValueError("high-water receipt signed_at must be timezone-aware")
        expected_subject = (
            self.subject.removeprefix("EP") if self.manifest_type == "authority" else self.subject
        )
        if expected_subject != self.subject:
            raise ValueError("authority high-water subject must omit the EP prefix")
        if self.manifest_type == "register" and not self.subject.startswith("EP"):
            raise ValueError("Register high-water subject must include the EP prefix")
        if (self.checkpoint_generation == 1) != (self.prior_checkpoint_envelope_sha256 is None):
            raise ValueError("checkpoint lineage is incomplete or malformed")
        return self


def build_ep_snapshot_checkpoint_envelope_sha256(
    receipt: EPSignedSnapshotHighWaterReceipt,
) -> str:
    """Digest a complete signed checkpoint for causal lineage persistence."""
    signed_payload = build_ep_snapshot_high_water_signature_payload(
        source_stream_id=receipt.source_stream_id,
        schema_epoch=receipt.schema_epoch,
        manifest_type=receipt.manifest_type,
        subject=receipt.subject,
        required_as_of=receipt.required_as_of,
        checkpoint_batch_sha256=receipt.checkpoint_batch_sha256,
        checkpoint_generation=receipt.checkpoint_generation,
        counterpart_source_acquisition_envelope_sha256=(
            receipt.counterpart_source_acquisition_envelope_sha256
        ),
        prior_checkpoint_envelope_sha256=receipt.prior_checkpoint_envelope_sha256,
        minimum_snapshot_sequence=receipt.minimum_snapshot_sequence,
        source_acquisition_envelope_sha256=(receipt.source_acquisition_envelope_sha256),
        signing_key_id=receipt.signing_key_id,
        key_revocation_epoch=receipt.key_revocation_epoch,
        signed_at=receipt.signed_at,
    )
    envelope = (
        b"praviar:epo-signed-checkpoint-envelope:v1\0"
        + len(signed_payload).to_bytes(8, "big")
        + signed_payload
        + len(receipt.signature).to_bytes(2, "big")
        + receipt.signature
    )
    return hashlib.sha256(envelope).hexdigest()


class EPAuthorityManifestRecord(BaseModel):
    """One exact publication identity derived by the acquisition collector."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    publication_number: str = Field(pattern=r"^[0-9]{7}$")
    eps_document_id: str = Field(pattern=r"^EP[0-9]{7}[A-Z0-9]{2,8}B[1239]$")
    kind: Literal["B1", "B2", "B3", "B9"]
    publication_date: date
    authority_exception_code: str = Field(default="", max_length=1)
    correction_of_document_id: str | None = None
    correction_sequence: int | None = Field(default=None, ge=1)


class EPWeeklyPublicationAcquisition(BaseModel):
    """One official weekly patent-list artifact; one URL never implies a range."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    publication_date: date
    source_locator: str = Field(min_length=1)
    source_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _validate_weekly_locator(self) -> EPWeeklyPublicationAcquisition:
        expected = (
            "https://data.epo.org/publication-server/rest/v1.2/"
            f"publication-dates/{self.publication_date:%Y%m%d}/patents"
        )
        if self.source_locator != expected:
            raise ValueError("weekly publication locator does not match its exact date")
        return self


class EPAuthorityAcquisitionManifest(BaseModel):
    """Strict signed semantics derived from retained authority/weekly bytes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["epo-authority-acquisition-v1"]
    snapshot_sequence: int = Field(ge=1)
    acquired_at: datetime
    publication_number: str = Field(pattern=r"^[0-9]{7}$")
    source_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_snapshot_locator: str = Field(min_length=1)
    snapshot_coverage_from: date
    snapshot_coverage_through: date
    publication_calendar_locator: str | None = None
    publication_calendar_artifact_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    calendar_observed_at: date | None = None
    publication_dates_after_snapshot: tuple[date, ...] = ()
    weekly_acquisitions: tuple[EPWeeklyPublicationAcquisition, ...] = ()
    records: tuple[EPAuthorityManifestRecord, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _validate_coverage_semantics(self) -> EPAuthorityAcquisitionManifest:
        if self.acquired_at.tzinfo is None or self.acquired_at.utcoffset() is None:
            raise ValueError("authority acquisition timestamp must be timezone-aware")
        if self.acquired_at.date() < self.snapshot_coverage_through:
            raise ValueError("authority acquisition predates snapshot coverage")
        if not (
            self.authority_snapshot_locator.startswith(
                "https://link.epo.org/web/publication-server/authority-file/"
            )
            and self.snapshot_coverage_from <= self.snapshot_coverage_through
        ):
            raise ValueError("authority snapshot metadata is invalid")
        calendar_fields = (
            self.publication_calendar_locator,
            self.publication_calendar_artifact_sha256,
            self.calendar_observed_at,
        )
        if all(value is None for value in calendar_fields):
            if self.publication_dates_after_snapshot or self.weekly_acquisitions:
                raise ValueError("weekly acquisitions require retained publication calendar")
            return self
        if any(value is None for value in calendar_fields):
            raise ValueError("publication calendar evidence is incomplete")
        if self.publication_calendar_locator != (
            "https://data.epo.org/publication-server/rest/v1.2/publication-dates"
        ):
            raise ValueError("publication calendar locator is not canonical")
        calendar_observed_at = self.calendar_observed_at
        if calendar_observed_at is None:
            raise ValueError("publication calendar observation date is missing")
        dates = self.publication_dates_after_snapshot
        if (
            not dates
            or dates != tuple(sorted(set(dates)))
            or dates[0] <= self.snapshot_coverage_through
            or dates[-1] > calendar_observed_at
        ):
            raise ValueError("publication calendar dates are incomplete or unordered")
        weekly_dates = tuple(item.publication_date for item in self.weekly_acquisitions)
        if weekly_dates != dates:
            raise ValueError("every publication calendar date requires one weekly artifact")
        return self

    @property
    def derived_coverage_through(self) -> date:
        return self.calendar_observed_at or self.snapshot_coverage_through


class EPRegisterProcedureEvent(BaseModel):
    """One ordered semantic event derived from the exact Register response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1, le=10_000)
    event_code: str = Field(min_length=1, max_length=64)
    event_date: date
    resulting_state: EPCentralProcedureState
    suspensive_appeal_state: EPSuspensiveAppealState
    affected_document_id: str | None = Field(
        default=None,
        pattern=r"^EP[0-9]{7}[A-Z0-9]{2,8}B[1239]$",
    )
    effective_date: date | None = None

    @model_validator(mode="after")
    def _validate_effective_subject(self) -> EPRegisterProcedureEvent:
        if (self.affected_document_id is None) != (self.effective_date is None):
            raise ValueError("effective publication identity and date must be derived together")
        return self


class EPRegisterAcquisitionManifest(BaseModel):
    """Strict signed procedure semantics derived from retained Register bytes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["epo-register-acquisition-v1"]
    snapshot_sequence: int = Field(ge=1)
    acquired_at: datetime
    source_document_id: str = Field(pattern=r"^EP[0-9]{7}$")
    source_locator: str = Field(min_length=1)
    as_of: date
    source_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    events: tuple[EPRegisterProcedureEvent, ...] = Field(min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def _validate_event_semantics(self) -> EPRegisterAcquisitionManifest:
        if self.acquired_at.tzinfo is None or self.acquired_at.utcoffset() is None:
            raise ValueError("Register acquisition timestamp must be timezone-aware")
        if self.acquired_at.date() < self.as_of:
            raise ValueError("Register acquisition predates its as-of date")
        if not _is_official_register_locator(self.source_locator, self.source_document_id):
            raise ValueError("Register acquisition locator is not canonical")
        sequences = tuple(event.sequence for event in self.events)
        dates = tuple(event.event_date for event in self.events)
        if sequences != tuple(range(1, len(sequences) + 1)):
            raise ValueError("Register events are truncated or unordered")
        if dates != tuple(sorted(dates)):
            raise ValueError("Register event chronology is retrograde")
        if any(
            event.event_date > self.as_of
            or (event.effective_date is not None and event.effective_date > self.as_of)
            for event in self.events
        ):
            raise ValueError("Register events cannot postdate the manifest as-of date")
        affected_document_ids = [
            str(event.affected_document_id)
            for event in self.events
            if event.affected_document_id is not None
        ]
        if len(affected_document_ids) != len(set(affected_document_ids)):
            raise ValueError("Register manifest has duplicate effective assignments")
        if any(
            not document_id.startswith(self.source_document_id)
            for document_id in affected_document_ids
        ):
            raise ValueError("Register event publication is not bound to its EP subject")
        if any(
            event.effective_date is not None and event.effective_date > event.event_date
            for event in self.events
        ):
            raise ValueError("Register effective chronology is impossible")
        if any(
            event.resulting_state == EPCentralProcedureState.APPEAL_PENDING
            and event.suspensive_appeal_state != EPSuspensiveAppealState.UNRESOLVED
            for event in self.events
        ):
            raise ValueError("Register appeal state is inconsistent")
        revoked_positions = [
            index
            for index, event in enumerate(self.events)
            if event.resulting_state == EPCentralProcedureState.CENTRALLY_REVOKED
        ]
        if revoked_positions and revoked_positions != [len(self.events) - 1]:
            raise ValueError("central revocation is a terminal Register state")
        allowed_transitions = {
            EPCentralProcedureState.CLEAR: frozenset(EPCentralProcedureState),
            EPCentralProcedureState.OPPOSITION_PENDING: frozenset(
                {
                    EPCentralProcedureState.OPPOSITION_PENDING,
                    EPCentralProcedureState.APPEAL_PENDING,
                    EPCentralProcedureState.CLEAR,
                    EPCentralProcedureState.CENTRALLY_REVOKED,
                    EPCentralProcedureState.UNKNOWN,
                }
            ),
            EPCentralProcedureState.LIMITATION_PENDING: frozenset(
                {
                    EPCentralProcedureState.LIMITATION_PENDING,
                    EPCentralProcedureState.APPEAL_PENDING,
                    EPCentralProcedureState.CLEAR,
                    EPCentralProcedureState.CENTRALLY_REVOKED,
                    EPCentralProcedureState.UNKNOWN,
                }
            ),
            EPCentralProcedureState.APPEAL_PENDING: frozenset(
                {
                    EPCentralProcedureState.APPEAL_PENDING,
                    EPCentralProcedureState.CLEAR,
                    EPCentralProcedureState.CENTRALLY_REVOKED,
                    EPCentralProcedureState.LIMITATION_PENDING,
                    EPCentralProcedureState.UNKNOWN,
                }
            ),
            EPCentralProcedureState.CENTRALLY_REVOKED: frozenset(
                {EPCentralProcedureState.CENTRALLY_REVOKED}
            ),
            EPCentralProcedureState.UNKNOWN: frozenset(EPCentralProcedureState),
        }
        if any(
            later.resulting_state not in allowed_transitions[earlier.resulting_state]
            for earlier, later in zip(self.events, self.events[1:], strict=False)
        ):
            raise ValueError("Register procedure state transition is impossible")
        return self

    @property
    def derived_state(self) -> EPCentralProcedureState:
        return self.events[-1].resulting_state

    @property
    def derived_suspensive_appeal_state(self) -> EPSuspensiveAppealState:
        return self.events[-1].suspensive_appeal_state

    @property
    def derived_effective_dates(self) -> dict[str, date]:
        return {
            str(event.affected_document_id): event.effective_date
            for event in self.events
            if event.affected_document_id is not None and event.effective_date is not None
        }


class EPAuthorityCoverageEvidence(BaseModel):
    """Content-bound proof that the relevant official publication set was covered.

    This is deliberately stronger than a caller-supplied ``complete=True`` flag:
    the coverage window, expected relevant-record count, official source locator,
    and exact retained authority/weekly-list bytes are bound by one digest.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    publication_number: str = Field(pattern=r"^[0-9]{7}$")
    coverage_method: Literal["ep_authority_file", "eps_weekly_publication_lists"]
    source_locator: str = Field(min_length=1)
    coverage_from: date
    coverage_through: date
    retrieved_at: datetime
    record_count: int = Field(ge=1, le=64)
    retained_authority_bytes: bytes = Field(min_length=1, max_length=64 * 1024 * 1024, repr=False)
    retained_authority_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_binding_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    acquisition_receipt: EPSignedAcquisitionReceipt

    @model_validator(mode="after")
    def _validate_authority_evidence(self) -> EPAuthorityCoverageEvidence:
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("authority evidence retrieved_at must be timezone-aware")
        if self.retrieved_at.astimezone(UTC) > datetime.now(UTC):
            raise ValueError("authority evidence retrieved_at is in the future")
        if self.retrieved_at.date() < self.coverage_through:
            raise ValueError("authority evidence predates its claimed coverage")
        if self.coverage_from > self.coverage_through:
            raise ValueError("authority evidence coverage window is reversed")
        if not _is_official_authority_locator(self.source_locator):
            raise ValueError("authority evidence locator is not an official EPO source")
        actual_artifact_sha256 = hashlib.sha256(self.retained_authority_bytes).hexdigest()
        if actual_artifact_sha256 != self.retained_authority_sha256:
            raise ValueError("authority evidence SHA-256 does not match retained bytes")
        expected_binding = build_ep_authority_evidence_binding_sha256(
            publication_number=self.publication_number,
            coverage_method=self.coverage_method,
            source_locator=self.source_locator,
            coverage_from=self.coverage_from,
            coverage_through=self.coverage_through,
            record_count=self.record_count,
            retained_authority_sha256=self.retained_authority_sha256,
        )
        if self.evidence_binding_sha256 != expected_binding:
            raise ValueError("authority evidence binding does not match subject and coverage")
        if self.acquisition_receipt.manifest_type != "authority":
            raise ValueError("authority evidence requires an authority acquisition receipt")
        return self


class EPCentralProcedureEvidence(BaseModel):
    """Retained EP Register evidence governing central-claims resolution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_document_id: str = Field(pattern=r"^EP[0-9]{7}$")
    source_locator: str = Field(min_length=1)
    as_of: date
    retrieved_at: datetime
    register_complete: bool
    authority_coverage: EPAuthorityCoverageEvidence | None = None
    central_state: EPCentralProcedureState
    suspensive_appeal_state: EPSuspensiveAppealState
    retained_register_bytes: bytes | None = Field(
        default=None,
        max_length=16 * 1024 * 1024,
        repr=False,
    )
    retained_register_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    evidence_binding_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    acquisition_receipt: EPSignedAcquisitionReceipt | None = None

    @model_validator(mode="after")
    def _validate_register_evidence(self) -> EPCentralProcedureEvidence:
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("procedure evidence retrieved_at must be timezone-aware")
        if self.retrieved_at.astimezone(UTC) > datetime.now(UTC):
            raise ValueError("procedure evidence retrieved_at is in the future")
        if self.retrieved_at.date() < self.as_of:
            raise ValueError("procedure evidence predates its as-of date")
        if not _is_official_register_locator(self.source_locator, self.source_document_id):
            raise ValueError("procedure evidence locator is not bound to the official EP record")
        if self.register_complete and (
            self.retained_register_bytes is None
            or self.retained_register_sha256 is None
            or self.evidence_binding_sha256 is None
            or self.acquisition_receipt is None
        ):
            raise ValueError("complete procedure evidence requires retained register bytes")
        if (self.retained_register_bytes is None) != (self.retained_register_sha256 is None):
            raise ValueError("procedure evidence bytes and SHA-256 must be retained together")
        if (self.retained_register_bytes is None) != (self.evidence_binding_sha256 is None):
            raise ValueError("procedure evidence bytes and binding must be retained together")
        if (
            self.retained_register_bytes is not None
            and hashlib.sha256(self.retained_register_bytes).hexdigest()
            != self.retained_register_sha256
        ):
            raise ValueError("procedure evidence SHA-256 does not match retained bytes")
        if self.retained_register_sha256 is not None:
            expected_binding = build_ep_procedure_evidence_binding_sha256(
                source_document_id=self.source_document_id,
                source_locator=self.source_locator,
                as_of=self.as_of,
                retained_register_sha256=self.retained_register_sha256,
            )
            if self.evidence_binding_sha256 != expected_binding:
                raise ValueError("procedure evidence binding does not match EP subject")
        if (
            self.authority_coverage is not None
            and self.authority_coverage.publication_number
            != self.source_document_id.removeprefix("EP")
        ):
            raise ValueError("authority coverage is not bound to the procedure subject")
        if (
            self.acquisition_receipt is not None
            and self.acquisition_receipt.manifest_type != "register"
        ):
            raise ValueError("procedure evidence requires a Register acquisition receipt")
        return self


class EPControllingClaimsResolution(BaseModel):
    """Fail-closed result that cannot blur current and historical resolution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    publication_number: str = Field(pattern=r"^[0-9]{7}$")
    resolution_mode: Literal["current", "historical"]
    required_as_of: date
    as_of: date
    status: EPClaimsResolutionStatus
    reason: EPClaimsResolutionReason
    artifacts: tuple[EPSPublicationArtifact, ...] = ()
    selected_document_id: str | None = None
    selected_kind: Literal["B1", "B2", "B3", "B9"] | None = None
    selected_effective_date: date | None = None
    selected_claims_text_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def _validate_resolution(self) -> EPControllingClaimsResolution:
        if (
            self.as_of > self.required_as_of
            and self.reason != EPClaimsResolutionReason.RESOLUTION_AS_OF_MISMATCH
        ):
            raise ValueError("resolution evidence cannot postdate the requested boundary")
        if (
            self.resolution_mode == "historical"
            and self.as_of != self.required_as_of
            and self.reason != EPClaimsResolutionReason.RESOLUTION_AS_OF_MISMATCH
        ):
            raise ValueError("historical resolution requires an exact as-of snapshot")
        if any(
            artifact.record.publication_number != self.publication_number
            for artifact in self.artifacts
        ):
            raise ValueError("retained EPS artifact subject does not match the resolution")
        selected = (
            self.selected_document_id,
            self.selected_kind,
            self.selected_effective_date,
            self.selected_claims_text_sha256,
        )
        if self.status == EPClaimsResolutionStatus.RESOLVED:
            if self.reason != EPClaimsResolutionReason.RESOLVED or any(
                value is None for value in selected
            ):
                raise ValueError("resolved central claims require a complete selected artifact")
            selected_artifacts = [
                artifact
                for artifact in self.artifacts
                if artifact.record.eps_document_id == self.selected_document_id
            ]
            if len(selected_artifacts) != 1:
                raise ValueError("selected EPS document is not retained")
            selected_artifact = selected_artifacts[0]
            if (
                selected_artifact.record.kind != self.selected_kind
                or selected_artifact.record.effective_date != self.selected_effective_date
                or selected_artifact.claims_text_sha256 != self.selected_claims_text_sha256
            ):
                raise ValueError("selected result fields do not bind to the selected artifact")
        elif self.status == EPClaimsResolutionStatus.NO_CENTRAL_CLAIMS:
            if self.reason != EPClaimsResolutionReason.CENTRALLY_REVOKED or any(
                value is not None for value in selected
            ):
                raise ValueError("terminal revocation must expose no selected claim artifact")
        elif self.reason in {
            EPClaimsResolutionReason.RESOLVED,
            EPClaimsResolutionReason.CENTRALLY_REVOKED,
        } or any(value is not None for value in selected):
            raise ValueError("indeterminate central claims cannot expose a selected artifact")
        return self


__all__ = [
    "EPS_ARTIFACT_MAX_BYTES",
    "EPS_PDF_MAX_BYTES",
    "EPS_XML_MAX_BYTES",
    "EP_ACQUISITION_MANIFEST_MAX_BYTES",
    "EP_CHECKPOINT_SCHEMA_EPOCH",
    "EP_CHECKPOINT_SOURCE_STREAM_ID",
    "EPAuthorityAcquisitionManifest",
    "EPAuthorityCoverageEvidence",
    "EPAuthorityManifestRecord",
    "EPCentralProcedureEvidence",
    "EPCentralProcedureState",
    "EPClaimsResolutionReason",
    "EPClaimsResolutionStatus",
    "EPControllingClaimsResolution",
    "EPRegisterAcquisitionManifest",
    "EPRegisterProcedureEvent",
    "EPSMediaArtifact",
    "EPSPublicationArtifact",
    "EPSPublicationRecord",
    "EPSignedAcquisitionReceipt",
    "EPSignedSnapshotHighWaterReceipt",
    "EPSuspensiveAppealState",
    "EPTrustedAcquisitionKey",
    "build_ep_acquisition_envelope_sha256",
    "build_ep_acquisition_signature_payload",
    "build_ep_authority_evidence_binding_sha256",
    "build_ep_procedure_evidence_binding_sha256",
    "build_ep_snapshot_checkpoint_batch_sha256",
    "build_ep_snapshot_checkpoint_envelope_sha256",
    "build_ep_snapshot_high_water_signature_payload",
]
