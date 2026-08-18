"""Exact-media client and fail-closed central-claims resolver for EPO EPS.

Official contract implemented here:

* base URL: ``https://data.epo.org/publication-server/rest/v1.2``
* raw XML: ``/patents/{epsDocumentId}/document.xml``
* PDF/A: ``/patents/{epsDocumentId}/document.pdf``

The client does not probe guessed kind codes.  Callers must supply the complete
official publication manifest for the EP publication number and retained
central-procedure evidence.  Resolution is by explicit effective date and
correction linkage, never by lexicographic or numeric kind-code ordering.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from typing import TYPE_CHECKING, Literal, Protocol

import httpx
import structlog
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from defusedxml import ElementTree
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from praviar_pipeline.clients.base import AsyncClientMixin
from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.models.epo_publication import (
    EPS_PDF_MAX_BYTES,
    EPS_XML_MAX_BYTES,
    EPAuthorityAcquisitionManifest,
    EPCentralProcedureEvidence,
    EPCentralProcedureState,
    EPClaimsResolutionReason,
    EPClaimsResolutionStatus,
    EPControllingClaimsResolution,
    EPRegisterAcquisitionManifest,
    EPSignedAcquisitionReceipt,
    EPSignedSnapshotHighWaterReceipt,
    EPSMediaArtifact,
    EPSPublicationArtifact,
    EPSPublicationRecord,
    EPSuspensiveAppealState,
    EPTrustedAcquisitionKey,
    build_ep_acquisition_envelope_sha256,
    build_ep_acquisition_signature_payload,
    build_ep_snapshot_checkpoint_batch_sha256,
    build_ep_snapshot_checkpoint_envelope_sha256,
    build_ep_snapshot_high_water_signature_payload,
)
from praviar_pipeline.utils.http_bodies import read_bounded_response_body

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, Sequence
    from xml.etree.ElementTree import Element

logger = structlog.get_logger()

BASE_URL = "https://data.epo.org/publication-server/rest/v1.2"
EPS_AGGREGATE_MAX_BYTES = 256 * 1024 * 1024
EPS_MAX_CLAIMS_PER_DOCUMENT = 1_000
EPS_MAX_PUBLICATION_RECORDS = 64
EPS_XML_REPLICATION_RELIABLE_FROM = date(2006, 1, 1)
_XML_CONTENT_TYPES = frozenset({"application/xml", "text/xml"})
_PDF_CONTENT_TYPES = frozenset({"application/pdf"})
_RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})
_CORRECTION_CODE = re.compile(r"\bW(?P<sequence>[1-9][0-9]*)(?P<kind>B[123])\b")
_JSON_MAX_DEPTH = 24
_JSON_MAX_NODES = 50_000
_JSON_MAX_CONTAINER_ITEMS = 10_000
_JSON_MAX_STRING_CHARS = 1_000_000
_JSON_MAX_KEY_CHARS = 256


class EPOPublicationResolutionConfig(BaseModel):
    """Strict current-resolution policy; trust keys are injected separately."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_evidence_age_days: int = Field(default=7, ge=0, le=31)
    max_future_clock_skew_seconds: int = Field(default=60, ge=0, le=300)
    require_high_water_receipts: Literal[True] = True


class EPAcquisitionEvidenceBundle(BaseModel):
    """Collector/store interchange contract with no synthetic evidence defaults."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    records: tuple[EPSPublicationRecord, ...]
    procedure: EPCentralProcedureEvidence
    authority_high_water: EPSignedSnapshotHighWaterReceipt
    register_high_water: EPSignedSnapshotHighWaterReceipt


class EPAcquisitionEvidenceCollector(Protocol):
    async def collect(
        self,
        publication_number: str,
        required_as_of: date,
    ) -> EPAcquisitionEvidenceBundle: ...


class EPAcquisitionEvidenceStore(Protocol):
    async def load_latest(
        self,
        publication_number: str,
        required_as_of: date,
    ) -> EPAcquisitionEvidenceBundle | None: ...

    async def persist(self, evidence: EPAcquisitionEvidenceBundle) -> None: ...


class EPCheckpointAdvance(BaseModel):
    """Verified checkpoint candidate submitted to atomic durable persistence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    checkpoint: EPSignedSnapshotHighWaterReceipt
    checkpoint_envelope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_snapshot_sequence: int = Field(ge=1)

    @model_validator(mode="after")
    def _validate_advance(self) -> EPCheckpointAdvance:
        if (
            build_ep_snapshot_checkpoint_envelope_sha256(self.checkpoint)
            != self.checkpoint_envelope_sha256
        ):
            raise ValueError("checkpoint advance digest does not match signed envelope")
        if self.source_snapshot_sequence < self.checkpoint.minimum_snapshot_sequence:
            raise ValueError("checkpoint floor exceeds its source snapshot")
        return self


class EPCheckpointBatchResult(BaseModel):
    """Persistence attestation for one atomic authority/Register checkpoint batch."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["advanced", "idempotent", "rejected"]
    persisted_checkpoint_envelope_sha256: tuple[str, ...] = Field(max_length=2)
    persisted_checkpoint_batch_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def _validate_result(self) -> EPCheckpointBatchResult:
        if self.status == "rejected" and (
            self.persisted_checkpoint_envelope_sha256
            or self.persisted_checkpoint_batch_sha256 is not None
        ):
            raise ValueError("rejected checkpoint batch cannot attest persisted candidates")
        if self.status != "rejected" and (
            len(self.persisted_checkpoint_envelope_sha256) != 2
            or self.persisted_checkpoint_batch_sha256 is None
        ):
            raise ValueError("accepted checkpoint batch must attest both candidates")
        return self


class EPAtomicCheckpointStore(Protocol):
    """Trusted persistence boundary.

    Implementations must atomically compare and advance the complete batch,
    keyed by ``(source stream/schema epoch, manifest_type, subject)``; the
    required-as-of date is persisted state, never part of the monotonic key. Generation one
    requires an empty prior digest.  Later generations require exactly the
    currently persisted generation plus one and its exact envelope digest.
    Its source snapshot sequence must also be strictly greater than the
    persisted sequence, and required-as-of must not move backwards. Exact
    complete-batch repeats are idempotent; any older, forked, mixed
    idempotent/advance, partial, or skipped generation must be rejected without
    modifying either key. Both candidates must carry the same verified joint
    checkpoint-batch digest.
    """

    async def load_trusted_checkpoint_keys(
        self,
    ) -> Mapping[str, EPTrustedAcquisitionKey]:
        """Return checkpoint-only public keys owned by persistence/KMS."""
        ...

    async def compare_and_advance_atomic(
        self,
        advances: tuple[EPCheckpointAdvance, EPCheckpointAdvance],
    ) -> EPCheckpointBatchResult: ...


class _RetryableEPSRequestError(Exception):
    def __init__(self, detail: str, *, status_code: int | None = None) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def _reject_duplicate_json_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _validate_json_lexical_depth(raw_bytes: bytes) -> None:
    depth = 0
    in_string = False
    escaped = False
    for value in raw_bytes:
        if in_string:
            if escaped:
                escaped = False
            elif value == 0x5C:
                escaped = True
            elif value == 0x22:
                in_string = False
            continue
        if value == 0x22:
            in_string = True
        elif value in {0x5B, 0x7B}:
            depth += 1
            if depth > _JSON_MAX_DEPTH:
                raise ValueError("manifest JSON nesting exceeds the resource limit")
        elif value in {0x5D, 0x7D}:
            depth -= 1
            if depth < 0:
                raise ValueError("manifest JSON delimiters are unbalanced")
    if in_string or depth != 0:
        raise ValueError("manifest JSON delimiters are incomplete")


def _validate_json_value_limits(root: dict[str, object]) -> None:
    pending: list[tuple[object, int]] = [(root, 1)]
    nodes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if nodes > _JSON_MAX_NODES or depth > _JSON_MAX_DEPTH:
            raise ValueError("manifest JSON structure exceeds the resource limit")
        if isinstance(value, dict):
            if len(value) > _JSON_MAX_CONTAINER_ITEMS:
                raise ValueError("manifest JSON object exceeds the item limit")
            for key, nested in value.items():
                if len(key) > _JSON_MAX_KEY_CHARS:
                    raise ValueError("manifest JSON key exceeds the length limit")
                pending.append((nested, depth + 1))
        elif isinstance(value, list):
            if len(value) > _JSON_MAX_CONTAINER_ITEMS:
                raise ValueError("manifest JSON array exceeds the item limit")
            pending.extend((nested, depth + 1) for nested in value)
        elif isinstance(value, str) and len(value) > _JSON_MAX_STRING_CHARS:
            raise ValueError("manifest JSON string exceeds the length limit")


def _parse_canonical_json_object(raw_bytes: bytes) -> dict[str, object]:
    _validate_json_lexical_depth(raw_bytes)
    try:
        parsed = json.loads(
            raw_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON value: {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("manifest is not strict UTF-8 JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("manifest root must be a JSON object")
    _validate_json_value_limits(parsed)
    canonical = json.dumps(
        parsed,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if canonical != raw_bytes:
        raise ValueError("manifest bytes are not canonical JSON")
    return parsed


def _trusted_key_for_signature(
    *,
    trusted_keys: Mapping[str, EPTrustedAcquisitionKey],
    signing_key_id: str,
    purpose: Literal[
        "authority_acquisition",
        "register_acquisition",
        "authority_checkpoint",
        "register_checkpoint",
    ],
    key_revocation_epoch: int,
    signed_at: datetime,
) -> EPTrustedAcquisitionKey | None:
    trusted_key = trusted_keys.get(signing_key_id)
    if (
        trusted_key is None
        or trusted_key.key_id != signing_key_id
        or trusted_key.purpose != purpose
        or trusted_key.status != "active"
        or trusted_key.revocation_epoch != key_revocation_epoch
        or signed_at < trusted_key.not_before
        or signed_at > trusted_key.not_after
    ):
        return None
    return trusted_key


def _verify_and_parse_receipt(
    receipt: EPSignedAcquisitionReceipt,
    trusted_public_keys: Mapping[str, EPTrustedAcquisitionKey],
    *,
    manifest_type: Literal["authority", "register"],
) -> tuple[EPAuthorityAcquisitionManifest | EPRegisterAcquisitionManifest | None, bool]:
    if receipt.manifest_type != manifest_type:
        return None, False
    purpose: Literal["authority_acquisition", "register_acquisition"] = (
        "authority_acquisition" if manifest_type == "authority" else "register_acquisition"
    )
    trusted_key = _trusted_key_for_signature(
        trusted_keys=trusted_public_keys,
        signing_key_id=receipt.signing_key_id,
        purpose=purpose,
        key_revocation_epoch=receipt.key_revocation_epoch,
        signed_at=receipt.signed_at,
    )
    if trusted_key is None:
        return None, False
    try:
        signature_payload = build_ep_acquisition_signature_payload(
            manifest_type=manifest_type,
            manifest_schema_version=receipt.manifest_schema_version,
            signing_key_id=receipt.signing_key_id,
            key_revocation_epoch=receipt.key_revocation_epoch,
            signed_at=receipt.signed_at,
            manifest_bytes=receipt.manifest_bytes,
        )
        Ed25519PublicKey.from_public_bytes(trusted_key.public_key).verify(
            receipt.signature,
            signature_payload,
        )
    except (InvalidSignature, ValueError):
        return None, False
    try:
        parsed = _parse_canonical_json_object(receipt.manifest_bytes)
    except ValueError:
        return None, False
    if parsed.get("schema_version") != receipt.manifest_schema_version:
        return None, False
    try:
        if manifest_type == "authority":
            return EPAuthorityAcquisitionManifest.model_validate(parsed), True
        return EPRegisterAcquisitionManifest.model_validate(parsed), True
    except ValidationError:
        return None, True


def _verify_high_water_receipt(
    receipt: EPSignedSnapshotHighWaterReceipt,
    trusted_keys: Mapping[str, EPTrustedAcquisitionKey],
    *,
    manifest_type: Literal["authority", "register"],
    subject: str,
    required_as_of: date,
    source_acquisition_envelope_sha256: str,
    snapshot_sequence: int,
    acquisition_signed_at: datetime,
) -> bool:
    if (
        receipt.manifest_type != manifest_type
        or receipt.subject != subject
        or receipt.required_as_of != required_as_of
        or receipt.source_acquisition_envelope_sha256 != source_acquisition_envelope_sha256
        or snapshot_sequence < receipt.minimum_snapshot_sequence
        or receipt.signed_at < acquisition_signed_at
    ):
        return False
    purpose: Literal["authority_checkpoint", "register_checkpoint"] = (
        "authority_checkpoint" if manifest_type == "authority" else "register_checkpoint"
    )
    trusted_key = _trusted_key_for_signature(
        trusted_keys=trusted_keys,
        signing_key_id=receipt.signing_key_id,
        purpose=purpose,
        key_revocation_epoch=receipt.key_revocation_epoch,
        signed_at=receipt.signed_at,
    )
    if trusted_key is None:
        return False
    payload = build_ep_snapshot_high_water_signature_payload(
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
        prior_checkpoint_envelope_sha256=(receipt.prior_checkpoint_envelope_sha256),
        minimum_snapshot_sequence=receipt.minimum_snapshot_sequence,
        source_acquisition_envelope_sha256=(receipt.source_acquisition_envelope_sha256),
        signing_key_id=receipt.signing_key_id,
        key_revocation_epoch=receipt.key_revocation_epoch,
        signed_at=receipt.signed_at,
    )
    try:
        Ed25519PublicKey.from_public_bytes(trusted_key.public_key).verify(
            receipt.signature,
            payload,
        )
    except (InvalidSignature, ValueError):
        return False
    return True


def _local_name(element: Element) -> str:
    return str(element.tag).rsplit("}", 1)[-1]


def _normalize_xml_text(element: Element) -> str:
    return " ".join("".join(element.itertext()).split())


def _parse_xml_date(value: str) -> date:
    if re.fullmatch(r"[0-9]{8}", value) is None:
        raise SourceUnavailableError(
            "epo_publication_server",
            "EPS XML publication date is missing or malformed",
        )
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        raise SourceUnavailableError(
            "epo_publication_server",
            "EPS XML publication date is invalid",
        ) from None


def _extract_b9_correction(root: Element) -> tuple[int, str]:
    """Read one explicit WnB1/B2/B3 correction link from correction metadata."""
    matches: set[tuple[int, str]] = set()
    for element in root.iter():
        local = _local_name(element).lower()
        metadata_element = "correction" in local or local.startswith("b015")
        candidates: list[str] = []
        if metadata_element:
            candidates.extend(str(value) for value in element.attrib.values())
            candidates.append(_normalize_xml_text(element))
        for key, value in element.attrib.items():
            if "correction" in str(key).lower():
                candidates.append(str(value))
        for candidate in candidates:
            for match in _CORRECTION_CODE.finditer(candidate.upper()):
                matches.add((int(match.group("sequence")), match.group("kind")))
    if len(matches) != 1:
        raise SourceUnavailableError(
            "epo_publication_server",
            "B9 XML does not contain one unambiguous correction target",
        )
    return next(iter(matches))


def _extract_proceedings_language_claims(
    root: Element,
    proceedings_language: str,
) -> tuple[str, tuple[int, ...]]:
    claims_containers = [
        element
        for element in root.iter()
        if _local_name(element).lower() == "claims"
        and str(element.attrib.get("lang", "")).strip().lower() == proceedings_language
    ]
    if len(claims_containers) != 1:
        raise SourceUnavailableError(
            "epo_publication_server",
            "EPS XML does not contain one complete language-of-proceedings claims section",
        )

    claims: list[tuple[int, str]] = []
    for element in claims_containers[0].iter():
        if _local_name(element).lower() != "claim":
            continue
        if len(claims) >= EPS_MAX_CLAIMS_PER_DOCUMENT:
            raise SourceUnavailableError(
                "epo_publication_server",
                "EPS XML claim count exceeds the resource limit",
            )
        raw_number = str(
            element.attrib.get("num")
            or element.attrib.get("number")
            or element.attrib.get("id")
            or ""
        ).strip()
        match = re.search(r"([0-9]+)$", raw_number)
        if match is None:
            raise SourceUnavailableError(
                "epo_publication_server",
                "EPS XML claim number is missing or malformed",
            )
        number = int(match.group(1))
        text = _normalize_xml_text(element)
        text = re.sub(
            rf"^\s*(?:claim\s+)?0*{number}\s*[.:]\s*",
            "",
            text,
            count=1,
            flags=re.IGNORECASE,
        ).strip()
        if not text:
            raise SourceUnavailableError(
                "epo_publication_server",
                "EPS XML contains an empty claim",
            )
        claims.append((number, text))

    numbers = tuple(number for number, _text in claims)
    if not numbers or numbers != tuple(range(1, len(numbers) + 1)):
        raise SourceUnavailableError(
            "epo_publication_server",
            "EPS XML claim set is truncated, duplicated, or non-contiguous",
        )
    claims_text = "\n\n".join(f"{number}. {text}" for number, text in claims)
    return claims_text, numbers


def _parse_and_validate_xml(
    record: EPSPublicationRecord,
    raw_xml: bytes,
) -> tuple[
    str,
    str,
    str,
    Literal["en", "de", "fr"],
    str,
    tuple[int, ...],
]:
    try:
        root = ElementTree.fromstring(raw_xml)
    except Exception as exc:
        raise SourceUnavailableError(
            "epo_publication_server",
            "EPS XML is truncated, unsafe, or malformed",
        ) from exc
    if _local_name(root).lower() != "ep-patent-document":
        raise SourceUnavailableError(
            "epo_publication_server",
            "EPS XML root is not an EP patent document",
        )

    xml_document_id = str(root.attrib.get("id", "")).strip()
    xml_file_name = str(root.attrib.get("file", "")).strip()
    xml_number = str(root.attrib.get("doc-number", "")).strip().zfill(7)
    xml_kind = str(root.attrib.get("kind", "")).strip().upper()
    xml_root_language = str(root.attrib.get("lang", "")).strip().lower()
    xml_publication_date = _parse_xml_date(str(root.attrib.get("date-publ", "")).strip())

    if not xml_document_id or not xml_file_name:
        raise SourceUnavailableError(
            "epo_publication_server",
            "EPS XML document identifiers are incomplete",
        )
    if xml_number != record.publication_number:
        raise SourceUnavailableError(
            "epo_publication_server",
            "EPS XML publication number does not match manifest",
        )
    if xml_kind != record.kind:
        raise SourceUnavailableError(
            "epo_publication_server",
            "EPS XML kind code does not match manifest",
        )
    if xml_publication_date != record.publication_date:
        raise SourceUnavailableError(
            "epo_publication_server",
            "EPS XML publication date does not match manifest",
        )
    if xml_publication_date < EPS_XML_REPLICATION_RELIABLE_FROM:
        raise SourceUnavailableError(
            "epo_publication_server",
            "pre-2006 EPS XML cannot establish exact controlling claims",
        )
    if not xml_file_name.upper().endswith(f"{record.kind}.XML"):
        raise SourceUnavailableError(
            "epo_publication_server",
            "EPS XML file identifier does not match kind code",
        )

    if record.kind == "B9":
        sequence, corrected_kind = _extract_b9_correction(root)
        target = str(record.correction_of_document_id or "")
        if sequence != record.correction_sequence or not target.endswith(corrected_kind):
            raise SourceUnavailableError(
                "epo_publication_server",
                "B9 XML correction linkage does not match manifest",
            )

    if xml_root_language not in {"en", "de", "fr"}:
        raise SourceUnavailableError(
            "epo_publication_server",
            "EPS XML root language is missing or invalid",
        )
    procedure_languages = {
        _normalize_xml_text(element).lower()
        for element in root.iter()
        if _local_name(element).upper() == "B251EP" and _normalize_xml_text(element)
    }
    if len(procedure_languages) != 1:
        raise SourceUnavailableError(
            "epo_publication_server",
            "EPS XML procedure language is missing or ambiguous",
        )
    raw_proceedings_language = next(iter(procedure_languages))
    if raw_proceedings_language == "en":
        proceedings_language: Literal["en", "de", "fr"] = "en"
    elif raw_proceedings_language == "de":
        proceedings_language = "de"
    elif raw_proceedings_language == "fr":
        proceedings_language = "fr"
    else:
        raise SourceUnavailableError(
            "epo_publication_server",
            "EPS XML procedure language is invalid",
        )
    claims_text, claim_numbers = _extract_proceedings_language_claims(
        root,
        proceedings_language,
    )
    return (
        xml_document_id,
        xml_file_name,
        xml_root_language,
        proceedings_language,
        claims_text,
        claim_numbers,
    )


def _validate_pdf(raw_pdf: bytes) -> None:
    if not raw_pdf.startswith(b"%PDF-"):
        raise SourceUnavailableError(
            "epo_publication_server",
            "EPS PDF media header is invalid",
        )
    if not raw_pdf.rstrip().endswith(b"%%EOF"):
        raise SourceUnavailableError(
            "epo_publication_server",
            "EPS PDF media is truncated or missing its EOF marker",
        )


def _indeterminate(
    publication_number: str,
    as_of: date,
    reason: EPClaimsResolutionReason,
    artifacts: Sequence[EPSPublicationArtifact] = (),
    *,
    resolution_mode: Literal["current", "historical"],
    required_as_of: date,
) -> EPControllingClaimsResolution:
    return EPControllingClaimsResolution(
        publication_number=publication_number,
        resolution_mode=resolution_mode,
        required_as_of=required_as_of,
        as_of=as_of,
        status=EPClaimsResolutionStatus.INDETERMINATE,
        reason=reason,
        artifacts=tuple(artifacts),
    )


def _procedure_gate(
    publication_number: str,
    procedure: EPCentralProcedureEvidence,
    artifacts: Sequence[EPSPublicationArtifact] = (),
    *,
    resolution_mode: Literal["current", "historical"],
    required_as_of: date,
) -> EPControllingClaimsResolution | None:
    if not procedure.register_complete:
        return _indeterminate(
            publication_number,
            procedure.as_of,
            EPClaimsResolutionReason.PROCEDURE_EVIDENCE_MISSING,
            artifacts,
            resolution_mode=resolution_mode,
            required_as_of=required_as_of,
        )
    if procedure.suspensive_appeal_state == EPSuspensiveAppealState.UNRESOLVED:
        return _indeterminate(
            publication_number,
            procedure.as_of,
            EPClaimsResolutionReason.SUSPENSIVE_APPEAL_UNRESOLVED,
            artifacts,
            resolution_mode=resolution_mode,
            required_as_of=required_as_of,
        )
    if procedure.central_state == EPCentralProcedureState.CENTRALLY_REVOKED:
        return EPControllingClaimsResolution(
            publication_number=publication_number,
            resolution_mode=resolution_mode,
            required_as_of=required_as_of,
            as_of=procedure.as_of,
            status=EPClaimsResolutionStatus.NO_CENTRAL_CLAIMS,
            reason=EPClaimsResolutionReason.CENTRALLY_REVOKED,
            artifacts=tuple(artifacts),
        )
    if procedure.central_state == EPCentralProcedureState.UNKNOWN:
        return _indeterminate(
            publication_number,
            procedure.as_of,
            EPClaimsResolutionReason.CENTRAL_PROCEEDING_UNKNOWN,
            artifacts,
            resolution_mode=resolution_mode,
            required_as_of=required_as_of,
        )
    if procedure.central_state != EPCentralProcedureState.CLEAR:
        return _indeterminate(
            publication_number,
            procedure.as_of,
            EPClaimsResolutionReason.CENTRAL_PROCEEDING_PENDING,
            artifacts,
            resolution_mode=resolution_mode,
            required_as_of=required_as_of,
        )
    return None


def _semantic_evidence_reason(
    publication_number: str,
    records: Sequence[EPSPublicationRecord],
    procedure: EPCentralProcedureEvidence,
    trusted_public_keys: Mapping[str, EPTrustedAcquisitionKey],
) -> EPClaimsResolutionReason | None:
    coverage = procedure.authority_coverage
    if coverage is None:
        return EPClaimsResolutionReason.AUTHORITY_MANIFEST_INCOMPLETE
    authority_manifest, authority_signature_valid = _verify_and_parse_receipt(
        coverage.acquisition_receipt,
        trusted_public_keys,
        manifest_type="authority",
    )
    if not authority_signature_valid:
        return EPClaimsResolutionReason.AUTHORITY_EVIDENCE_UNTRUSTED
    if not isinstance(authority_manifest, EPAuthorityAcquisitionManifest):
        return EPClaimsResolutionReason.AUTHORITY_CONTENT_MISMATCH
    if (
        authority_manifest.publication_number != publication_number
        or authority_manifest.source_bundle_sha256 != coverage.retained_authority_sha256
        or authority_manifest.snapshot_coverage_from != coverage.coverage_from
        or authority_manifest.derived_coverage_through != coverage.coverage_through
        or authority_manifest.authority_snapshot_locator != coverage.source_locator
        or len(authority_manifest.records) != coverage.record_count
    ):
        return EPClaimsResolutionReason.AUTHORITY_CONTENT_MISMATCH
    expected_method = (
        "eps_weekly_publication_lists"
        if authority_manifest.weekly_acquisitions
        else "ep_authority_file"
    )
    if coverage.coverage_method != expected_method:
        return EPClaimsResolutionReason.AUTHORITY_CONTENT_MISMATCH

    supplied_records = sorted(
        (
            record.publication_number,
            record.eps_document_id,
            record.kind,
            record.publication_date,
            record.authority_exception_code,
            record.correction_of_document_id,
            record.correction_sequence,
        )
        for record in records
    )
    derived_records = sorted(
        (
            record.publication_number,
            record.eps_document_id,
            record.kind,
            record.publication_date,
            record.authority_exception_code,
            record.correction_of_document_id,
            record.correction_sequence,
        )
        for record in authority_manifest.records
    )
    if supplied_records != derived_records:
        return EPClaimsResolutionReason.AUTHORITY_CONTENT_MISMATCH

    if not procedure.register_complete:
        return None
    if procedure.acquisition_receipt is None:
        return EPClaimsResolutionReason.PROCEDURE_EVIDENCE_UNTRUSTED
    register_manifest, register_signature_valid = _verify_and_parse_receipt(
        procedure.acquisition_receipt,
        trusted_public_keys,
        manifest_type="register",
    )
    if not register_signature_valid:
        return EPClaimsResolutionReason.PROCEDURE_EVIDENCE_UNTRUSTED
    if not isinstance(register_manifest, EPRegisterAcquisitionManifest):
        return EPClaimsResolutionReason.PROCEDURE_CONTENT_MISMATCH
    if (
        register_manifest.source_document_id != procedure.source_document_id
        or register_manifest.source_locator != procedure.source_locator
        or register_manifest.as_of != procedure.as_of
        or register_manifest.source_artifact_sha256 != procedure.retained_register_sha256
        or register_manifest.derived_state != procedure.central_state
        or register_manifest.derived_suspensive_appeal_state != procedure.suspensive_appeal_state
    ):
        return EPClaimsResolutionReason.PROCEDURE_CONTENT_MISMATCH
    supplied_effective_dates = {record.eps_document_id: record.effective_date for record in records}
    if (
        any(value is None for value in supplied_effective_dates.values())
        or register_manifest.derived_effective_dates != supplied_effective_dates
    ):
        return EPClaimsResolutionReason.PROCEDURE_CONTENT_MISMATCH
    return None


def _publication_preflight_reason(
    publication_number: str,
    records: Sequence[EPSPublicationRecord],
    procedure: EPCentralProcedureEvidence,
    trusted_public_keys: Mapping[str, EPTrustedAcquisitionKey],
) -> EPClaimsResolutionReason | None:
    if procedure.source_document_id != f"EP{publication_number}":
        return EPClaimsResolutionReason.PROCEDURE_SUBJECT_MISMATCH
    if not records:
        return EPClaimsResolutionReason.PUBLICATION_SET_EMPTY
    if len(records) > EPS_MAX_PUBLICATION_RECORDS:
        return EPClaimsResolutionReason.RESOURCE_LIMIT_EXCEEDED
    if any(record.publication_number != publication_number for record in records):
        return EPClaimsResolutionReason.CONFLICTING_PUBLICATION
    semantic_reason = _semantic_evidence_reason(
        publication_number,
        records,
        procedure,
        trusted_public_keys,
    )
    if semantic_reason is not None:
        return semantic_reason
    coverage = procedure.authority_coverage
    if coverage is None:
        return EPClaimsResolutionReason.AUTHORITY_MANIFEST_INCOMPLETE
    if (
        coverage.publication_number != publication_number
        or coverage.record_count != len(records)
        or coverage.coverage_through < procedure.as_of
        or coverage.coverage_from > min(record.publication_date for record in records)
    ):
        return EPClaimsResolutionReason.AUTHORITY_MANIFEST_INCOMPLETE
    authority_dates = {record.authority_as_of for record in records}
    if authority_dates != {coverage.coverage_through}:
        return EPClaimsResolutionReason.AUTHORITY_MANIFEST_INCOMPLETE
    if any(record.authority_exception_code for record in records):
        return EPClaimsResolutionReason.AUTHORITY_EXCEPTION_PRESENT

    document_ids = [record.eps_document_id for record in records]
    if len(document_ids) != len(set(document_ids)):
        return EPClaimsResolutionReason.DUPLICATE_PUBLICATION
    identities = [
        (record.kind, record.publication_date, record.effective_date) for record in records
    ]
    if len(identities) != len(set(identities)):
        return EPClaimsResolutionReason.CONFLICTING_PUBLICATION

    bases = [record for record in records if record.kind in {"B1", "B2", "B3"}]
    if sum(record.kind == "B1" for record in bases) != 1:
        return EPClaimsResolutionReason.BASE_GRANT_MISSING
    if any(record.effective_date is None for record in records):
        return EPClaimsResolutionReason.EFFECTIVE_DATE_MISSING
    if any(
        record.publication_date > procedure.as_of
        or (record.effective_date is not None and record.effective_date > procedure.as_of)
        for record in records
    ):
        return EPClaimsResolutionReason.CONFLICTING_PUBLICATION

    base_ids = {record.eps_document_id for record in bases}
    corrections: dict[str, list[EPSPublicationRecord]] = defaultdict(list)
    for record in records:
        if record.kind != "B9":
            continue
        target = str(record.correction_of_document_id or "")
        if target not in base_ids:
            return EPClaimsResolutionReason.CORRECTION_TARGET_MISSING
        corrections[target].append(record)
    for target_records in corrections.values():
        target_id = str(target_records[0].correction_of_document_id or "")
        target_record = next(record for record in bases if record.eps_document_id == target_id)
        sequences = sorted(int(record.correction_sequence or 0) for record in target_records)
        if sequences != list(range(1, len(sequences) + 1)):
            return EPClaimsResolutionReason.CORRECTION_CHAIN_INCOMPLETE
        ordered = sorted(target_records, key=lambda item: int(item.correction_sequence or 0))
        first = ordered[0]
        if (
            first.publication_date <= target_record.publication_date
            or first.effective_date is None
            or target_record.effective_date is None
            or first.effective_date < target_record.effective_date
        ):
            return EPClaimsResolutionReason.CORRECTION_CHAIN_INCOMPLETE
        if any(
            later.publication_date <= earlier.publication_date
            or later.effective_date is None
            or earlier.effective_date is None
            or later.effective_date < earlier.effective_date
            for earlier, later in pairwise(ordered)
        ):
            return EPClaimsResolutionReason.CORRECTION_CHAIN_INCOMPLETE
    return None


def _resolve_ep_central_claims(
    publication_number: str,
    artifacts: Sequence[EPSPublicationArtifact],
    procedure: EPCentralProcedureEvidence,
    *,
    trusted_acquisition_public_keys: Mapping[str, EPTrustedAcquisitionKey],
    resolution_mode: Literal["current", "historical"],
    required_as_of: date,
) -> EPControllingClaimsResolution:
    records = [artifact.record for artifact in artifacts]
    reason = _publication_preflight_reason(
        publication_number,
        records,
        procedure,
        trusted_acquisition_public_keys,
    )
    if reason is not None:
        return _indeterminate(
            publication_number,
            procedure.as_of,
            reason,
            artifacts,
            resolution_mode=resolution_mode,
            required_as_of=required_as_of,
        )
    aggregate_bytes = sum(
        len(artifact.xml.raw_bytes) + len(artifact.pdf.raw_bytes) for artifact in artifacts
    )
    if aggregate_bytes > EPS_AGGREGATE_MAX_BYTES:
        return _indeterminate(
            publication_number,
            procedure.as_of,
            EPClaimsResolutionReason.RESOURCE_LIMIT_EXCEEDED,
            artifacts,
            resolution_mode=resolution_mode,
            required_as_of=required_as_of,
        )
    procedure_result = _procedure_gate(
        publication_number,
        procedure,
        artifacts,
        resolution_mode=resolution_mode,
        required_as_of=required_as_of,
    )
    if procedure_result is not None:
        return procedure_result

    artifact_by_id = {artifact.record.eps_document_id: artifact for artifact in artifacts}
    bases = [artifact for artifact in artifacts if artifact.record.kind in {"B1", "B2", "B3"}]
    latest_effective = max(
        record.effective_date
        for record in (artifact.record for artifact in bases)
        if record.effective_date is not None
    )
    current_bases = [
        artifact for artifact in bases if artifact.record.effective_date == latest_effective
    ]
    if len(current_bases) != 1:
        return _indeterminate(
            publication_number,
            procedure.as_of,
            EPClaimsResolutionReason.CONFLICTING_PUBLICATION,
            artifacts,
            resolution_mode=resolution_mode,
            required_as_of=required_as_of,
        )
    selected = current_bases[0]

    correction_records = sorted(
        (
            artifact.record
            for artifact in artifacts
            if artifact.record.kind == "B9"
            and artifact.record.correction_of_document_id == selected.record.eps_document_id
        ),
        key=lambda record: int(record.correction_sequence or 0),
    )
    if correction_records:
        selected = artifact_by_id[correction_records[-1].eps_document_id]

    return EPControllingClaimsResolution(
        publication_number=publication_number,
        resolution_mode=resolution_mode,
        required_as_of=required_as_of,
        as_of=procedure.as_of,
        status=EPClaimsResolutionStatus.RESOLVED,
        reason=EPClaimsResolutionReason.RESOLVED,
        artifacts=tuple(artifacts),
        selected_document_id=selected.record.eps_document_id,
        selected_kind=selected.record.kind,
        selected_effective_date=selected.record.effective_date,
        selected_claims_text_sha256=selected.claims_text_sha256,
    )


def resolve_ep_historical_central_claims(
    publication_number: str,
    artifacts: Sequence[EPSPublicationArtifact],
    procedure: EPCentralProcedureEvidence,
    *,
    historical_as_of: date,
    trusted_acquisition_public_keys: Mapping[str, EPTrustedAcquisitionKey] | None = None,
) -> EPControllingClaimsResolution:
    """Resolve an explicitly historical snapshot; never label it current."""
    if procedure.as_of != historical_as_of:
        return _indeterminate(
            publication_number,
            procedure.as_of,
            EPClaimsResolutionReason.RESOLUTION_AS_OF_MISMATCH,
            artifacts,
            resolution_mode="historical",
            required_as_of=historical_as_of,
        )
    return _resolve_ep_central_claims(
        publication_number,
        artifacts,
        procedure,
        trusted_acquisition_public_keys=trusted_acquisition_public_keys or {},
        resolution_mode="historical",
        required_as_of=historical_as_of,
    )


def _prepare_current_checkpoint_advances(
    publication_number: str,
    procedure: EPCentralProcedureEvidence,
    trusted_keys: Mapping[str, EPTrustedAcquisitionKey],
    *,
    authority_high_water: EPSignedSnapshotHighWaterReceipt | None,
    register_high_water: EPSignedSnapshotHighWaterReceipt | None,
    required_as_of: date,
    evaluated_at: datetime,
    policy: EPOPublicationResolutionConfig,
) -> tuple[
    EPClaimsResolutionReason | None,
    tuple[EPCheckpointAdvance, EPCheckpointAdvance] | None,
]:
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        return EPClaimsResolutionReason.RESOLUTION_AS_OF_MISMATCH, None
    if required_as_of != evaluated_at.astimezone(UTC).date():
        return EPClaimsResolutionReason.RESOLUTION_AS_OF_MISMATCH, None
    if procedure.as_of > required_as_of:
        return EPClaimsResolutionReason.RESOLUTION_AS_OF_MISMATCH, None
    if required_as_of - procedure.as_of > timedelta(days=policy.max_evidence_age_days):
        return EPClaimsResolutionReason.CURRENT_EVIDENCE_STALE, None
    if authority_high_water is None or register_high_water is None:
        return EPClaimsResolutionReason.HIGH_WATER_EVIDENCE_MISSING, None
    coverage = procedure.authority_coverage
    if coverage is None or procedure.acquisition_receipt is None:
        return EPClaimsResolutionReason.HIGH_WATER_EVIDENCE_MISSING, None
    authority_manifest, _ = _verify_and_parse_receipt(
        coverage.acquisition_receipt,
        trusted_keys,
        manifest_type="authority",
    )
    register_manifest, _ = _verify_and_parse_receipt(
        procedure.acquisition_receipt,
        trusted_keys,
        manifest_type="register",
    )
    if not isinstance(authority_manifest, EPAuthorityAcquisitionManifest) or not isinstance(
        register_manifest, EPRegisterAcquisitionManifest
    ):
        return EPClaimsResolutionReason.EVIDENCE_ROLLBACK_DETECTED, None
    signing_key_ids = {
        coverage.acquisition_receipt.signing_key_id,
        procedure.acquisition_receipt.signing_key_id,
        authority_high_water.signing_key_id,
        register_high_water.signing_key_id,
    }
    if len(signing_key_ids) != 4:
        return EPClaimsResolutionReason.EVIDENCE_ROLLBACK_DETECTED, None
    skew = timedelta(seconds=policy.max_future_clock_skew_seconds)
    oldest_allowed = evaluated_at - timedelta(days=policy.max_evidence_age_days)
    freshness_timestamps = (
        coverage.retrieved_at,
        procedure.retrieved_at,
        authority_manifest.acquired_at,
        register_manifest.acquired_at,
        coverage.acquisition_receipt.signed_at,
        procedure.acquisition_receipt.signed_at,
        authority_high_water.signed_at,
        register_high_water.signed_at,
    )
    if any(
        timestamp > evaluated_at + skew or timestamp < oldest_allowed
        for timestamp in freshness_timestamps
    ):
        return EPClaimsResolutionReason.CURRENT_EVIDENCE_STALE, None
    authority_envelope_sha256 = build_ep_acquisition_envelope_sha256(coverage.acquisition_receipt)
    register_envelope_sha256 = build_ep_acquisition_envelope_sha256(procedure.acquisition_receipt)
    if (
        authority_high_water.source_stream_id != register_high_water.source_stream_id
        or authority_high_water.schema_epoch != register_high_water.schema_epoch
    ):
        return EPClaimsResolutionReason.EVIDENCE_ROLLBACK_DETECTED, None
    expected_batch_sha256 = build_ep_snapshot_checkpoint_batch_sha256(
        source_stream_id=authority_high_water.source_stream_id,
        schema_epoch=authority_high_water.schema_epoch,
        authority_subject=publication_number,
        register_subject=procedure.source_document_id,
        required_as_of=required_as_of,
        authority_checkpoint_generation=authority_high_water.checkpoint_generation,
        register_checkpoint_generation=register_high_water.checkpoint_generation,
        authority_prior_checkpoint_envelope_sha256=(
            authority_high_water.prior_checkpoint_envelope_sha256
        ),
        register_prior_checkpoint_envelope_sha256=(
            register_high_water.prior_checkpoint_envelope_sha256
        ),
        authority_minimum_snapshot_sequence=authority_high_water.minimum_snapshot_sequence,
        register_minimum_snapshot_sequence=register_high_water.minimum_snapshot_sequence,
        authority_source_acquisition_envelope_sha256=authority_envelope_sha256,
        register_source_acquisition_envelope_sha256=register_envelope_sha256,
    )
    if (
        authority_high_water.checkpoint_batch_sha256 != expected_batch_sha256
        or register_high_water.checkpoint_batch_sha256 != expected_batch_sha256
        or authority_high_water.counterpart_source_acquisition_envelope_sha256
        != register_envelope_sha256
        or register_high_water.counterpart_source_acquisition_envelope_sha256
        != authority_envelope_sha256
    ):
        return EPClaimsResolutionReason.EVIDENCE_ROLLBACK_DETECTED, None
    if not _verify_high_water_receipt(
        authority_high_water,
        trusted_keys,
        manifest_type="authority",
        subject=publication_number,
        required_as_of=required_as_of,
        source_acquisition_envelope_sha256=authority_envelope_sha256,
        snapshot_sequence=authority_manifest.snapshot_sequence,
        acquisition_signed_at=max(
            coverage.acquisition_receipt.signed_at,
            authority_manifest.acquired_at,
        ),
    ):
        return EPClaimsResolutionReason.EVIDENCE_ROLLBACK_DETECTED, None
    if not _verify_high_water_receipt(
        register_high_water,
        trusted_keys,
        manifest_type="register",
        subject=procedure.source_document_id,
        required_as_of=required_as_of,
        source_acquisition_envelope_sha256=register_envelope_sha256,
        snapshot_sequence=register_manifest.snapshot_sequence,
        acquisition_signed_at=max(
            procedure.acquisition_receipt.signed_at,
            register_manifest.acquired_at,
        ),
    ):
        return EPClaimsResolutionReason.EVIDENCE_ROLLBACK_DETECTED, None
    advances = (
        EPCheckpointAdvance(
            checkpoint=authority_high_water,
            checkpoint_envelope_sha256=(
                build_ep_snapshot_checkpoint_envelope_sha256(authority_high_water)
            ),
            source_snapshot_sequence=authority_manifest.snapshot_sequence,
        ),
        EPCheckpointAdvance(
            checkpoint=register_high_water,
            checkpoint_envelope_sha256=(
                build_ep_snapshot_checkpoint_envelope_sha256(register_high_water)
            ),
            source_snapshot_sequence=register_manifest.snapshot_sequence,
        ),
    )
    return None, advances


async def _compare_and_advance_current_checkpoints(
    store: EPAtomicCheckpointStore,
    advances: tuple[EPCheckpointAdvance, EPCheckpointAdvance] | None,
) -> EPClaimsResolutionReason | None:
    if advances is None:
        return EPClaimsResolutionReason.EVIDENCE_ROLLBACK_DETECTED
    try:
        result = await store.compare_and_advance_atomic(advances)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.error("epo_checkpoint_compare_and_advance_failed")
        return EPClaimsResolutionReason.CHECKPOINT_STORE_UNAVAILABLE
    expected_digests = tuple(advance.checkpoint_envelope_sha256 for advance in advances)
    expected_batch_sha256 = advances[0].checkpoint.checkpoint_batch_sha256
    if (
        result.status == "rejected"
        or result.persisted_checkpoint_envelope_sha256 != expected_digests
        or result.persisted_checkpoint_batch_sha256 != expected_batch_sha256
    ):
        return EPClaimsResolutionReason.EVIDENCE_ROLLBACK_DETECTED
    return None


async def _validate_and_advance_current_checkpoints(
    store: EPAtomicCheckpointStore | None,
    acquisition_keys: Mapping[str, EPTrustedAcquisitionKey],
    publication_number: str,
    procedure: EPCentralProcedureEvidence,
    *,
    authority_high_water: EPSignedSnapshotHighWaterReceipt | None,
    register_high_water: EPSignedSnapshotHighWaterReceipt | None,
    required_as_of: date,
    evaluated_at: datetime,
    policy: EPOPublicationResolutionConfig,
) -> EPClaimsResolutionReason | None:
    if store is None:
        return EPClaimsResolutionReason.CHECKPOINT_STORE_UNAVAILABLE
    if any(
        key.purpose not in {"authority_acquisition", "register_acquisition"}
        for key in acquisition_keys.values()
    ):
        return EPClaimsResolutionReason.AUTHORITY_EVIDENCE_UNTRUSTED
    try:
        checkpoint_keys = dict(await store.load_trusted_checkpoint_keys())
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.error("epo_checkpoint_trust_load_failed")
        return EPClaimsResolutionReason.CHECKPOINT_STORE_UNAVAILABLE
    if (
        not checkpoint_keys
        or set(checkpoint_keys).intersection(acquisition_keys)
        or any(
            key_id != key.key_id
            or key.purpose not in {"authority_checkpoint", "register_checkpoint"}
            for key_id, key in checkpoint_keys.items()
        )
        or len({key.public_key for key in (*acquisition_keys.values(), *checkpoint_keys.values())})
        != len(acquisition_keys) + len(checkpoint_keys)
    ):
        return EPClaimsResolutionReason.EVIDENCE_ROLLBACK_DETECTED
    reason, advances = _prepare_current_checkpoint_advances(
        publication_number,
        procedure,
        {**acquisition_keys, **checkpoint_keys},
        authority_high_water=authority_high_water,
        register_high_water=register_high_water,
        required_as_of=required_as_of,
        evaluated_at=evaluated_at,
        policy=policy,
    )
    if reason is not None:
        return reason
    return await _compare_and_advance_current_checkpoints(store, advances)


async def resolve_ep_current_central_claims(
    publication_number: str,
    artifacts: Sequence[EPSPublicationArtifact],
    procedure: EPCentralProcedureEvidence,
    *,
    required_as_of: date,
    evaluated_at: datetime,
    authority_high_water: EPSignedSnapshotHighWaterReceipt | None,
    register_high_water: EPSignedSnapshotHighWaterReceipt | None,
    checkpoint_store: EPAtomicCheckpointStore | None,
    policy: EPOPublicationResolutionConfig | None = None,
    trusted_acquisition_public_keys: Mapping[str, EPTrustedAcquisitionKey] | None = None,
) -> EPControllingClaimsResolution:
    """Resolve current claims only with fresh, monotonic signed evidence."""
    trust = trusted_acquisition_public_keys or {}
    current_policy = policy or EPOPublicationResolutionConfig()
    records = [artifact.record for artifact in artifacts]
    reason = _publication_preflight_reason(
        publication_number,
        records,
        procedure,
        trust,
    )
    if reason is None:
        reason = await _validate_and_advance_current_checkpoints(
            checkpoint_store,
            trust,
            publication_number,
            procedure,
            authority_high_water=authority_high_water,
            register_high_water=register_high_water,
            required_as_of=required_as_of,
            evaluated_at=evaluated_at,
            policy=current_policy,
        )
    if reason is not None:
        return _indeterminate(
            publication_number,
            procedure.as_of,
            reason,
            artifacts,
            resolution_mode="current",
            required_as_of=required_as_of,
        )
    return _resolve_ep_central_claims(
        publication_number,
        artifacts,
        procedure,
        trusted_acquisition_public_keys=trust,
        resolution_mode="current",
        required_as_of=required_as_of,
    )


class EPOPublicationServerClient(AsyncClientMixin):
    """Anonymous EPS REST v1.2 client with bounded exact-media retrieval."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        retry_delays: tuple[float, ...] = (0.5, 1.5),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        trusted_acquisition_public_keys: Mapping[str, EPTrustedAcquisitionKey] | None = None,
        resolution_config: EPOPublicationResolutionConfig | None = None,
        checkpoint_store: EPAtomicCheckpointStore | None = None,
    ) -> None:
        canonical_base_url = httpx.URL(f"{BASE_URL}/")
        if client is not None and client.base_url != canonical_base_url:
            raise ValueError("injected EPS HTTP client base_url must equal the canonical EPO URL")
        if client is not None and getattr(client, "follow_redirects", False) is not False:
            raise ValueError("injected EPS HTTP client must disable redirect following")
        self._external_client = client is not None
        self._client = client or httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=httpx.Timeout(30.0, connect=10.0, read=30.0, write=10.0, pool=10.0),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
            follow_redirects=False,
            headers={"User-Agent": "Praviar-EPS-Claims/1.0"},
        )
        self._retry_delays = retry_delays
        self._sleep = sleep
        self._resolution_config = resolution_config or EPOPublicationResolutionConfig()
        self._checkpoint_store = checkpoint_store
        self._trusted_acquisition_public_keys = dict(trusted_acquisition_public_keys or {})
        if any(
            key_id != trusted_key.key_id
            or trusted_key.purpose not in {"authority_acquisition", "register_acquisition"}
            for key_id, trusted_key in self._trusted_acquisition_public_keys.items()
        ) or len({key.public_key for key in self._trusted_acquisition_public_keys.values()}) != len(
            self._trusted_acquisition_public_keys
        ):
            raise ValueError("trusted acquisition keyring is malformed or purpose-confused")

    async def close(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    async def _get_media_once(
        self,
        record: EPSPublicationRecord,
        media_format: Literal["xml", "pdf"],
        *,
        aggregate_budget_bytes: int,
    ) -> tuple[bytes, str]:
        expected_types = _XML_CONTENT_TYPES if media_format == "xml" else _PDF_CONTENT_TYPES
        media_limit = EPS_XML_MAX_BYTES if media_format == "xml" else EPS_PDF_MAX_BYTES
        max_bytes = min(media_limit, aggregate_budget_bytes)
        if max_bytes < 1:
            raise SourceUnavailableError(
                "epo_publication_server",
                "EPS publication media exceed the aggregate resource limit",
            )
        path = f"/patents/{record.eps_document_id}/document.{media_format}"
        try:
            async with self._client.stream(
                "GET",
                path,
                headers={
                    "Accept": next(iter(expected_types)),
                    "Accept-Encoding": "identity",
                },
            ) as response:
                if response.status_code in _RETRYABLE_STATUS_CODES:
                    raise _RetryableEPSRequestError(
                        "EPS REST request returned a transient status",
                        status_code=response.status_code,
                    )
                if response.status_code != 200:
                    raise SourceUnavailableError(
                        "epo_publication_server",
                        "EPS REST media response must have status 200",
                        status_code=response.status_code,
                    )
                encoding = response.headers.get("Content-Encoding", "identity").strip().lower()
                if encoding not in {"", "identity"}:
                    raise SourceUnavailableError(
                        "epo_publication_server",
                        "EPS media was not delivered with identity encoding",
                    )
                content_type = response.headers.get("Content-Type", "").partition(";")[0].lower()
                if content_type not in expected_types:
                    raise SourceUnavailableError(
                        "epo_publication_server",
                        "EPS media content type does not match the requested format",
                    )
                raw_bytes = await read_bounded_response_body(
                    response,
                    max_bytes=max_bytes,
                    source="epo_publication_server",
                    detail=(
                        "EPS publication media exceed the aggregate resource limit"
                        if aggregate_budget_bytes < media_limit
                        else (f"EPS {media_format.upper()} exceeds the retained-media limit")
                    ),
                )
        except asyncio.CancelledError:
            raise
        except _RetryableEPSRequestError:
            raise
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise _RetryableEPSRequestError("EPS REST transport failed") from exc
        return raw_bytes, content_type

    async def _get_media(
        self,
        record: EPSPublicationRecord,
        media_format: Literal["xml", "pdf"],
        *,
        aggregate_budget_bytes: int,
    ) -> EPSMediaArtifact:
        last_failure: _RetryableEPSRequestError | None = None
        for attempt in range(len(self._retry_delays) + 1):
            try:
                raw_bytes, content_type = await self._get_media_once(
                    record,
                    media_format,
                    aggregate_budget_bytes=aggregate_budget_bytes,
                )
                retrieved_at = datetime.now(UTC)
                return EPSMediaArtifact(
                    media_format=media_format,
                    source_url=(
                        f"{BASE_URL}/patents/{record.eps_document_id}/document.{media_format}"
                    ),
                    content_type=content_type,
                    retrieved_at=retrieved_at,
                    raw_bytes=raw_bytes,
                    sha256=hashlib.sha256(raw_bytes).hexdigest(),
                )
            except _RetryableEPSRequestError as exc:
                last_failure = exc
                if attempt == len(self._retry_delays):
                    break
                await self._sleep(self._retry_delays[attempt])
        assert last_failure is not None
        raise SourceUnavailableError(
            "epo_publication_server",
            "EPS REST request failed after explicit retries",
            status_code=last_failure.status_code,
        ) from None

    async def fetch_publication(
        self,
        record: EPSPublicationRecord,
        *,
        aggregate_budget_bytes: int = EPS_AGGREGATE_MAX_BYTES,
    ) -> EPSPublicationArtifact:
        """Fetch and bind exact XML and PDF bytes for one manifest-listed document."""
        if record.authority_exception_code:
            raise SourceUnavailableError(
                "epo_publication_server",
                "authority-file exception prevents exact publication retrieval",
            )
        xml = await self._get_media(
            record,
            "xml",
            aggregate_budget_bytes=aggregate_budget_bytes,
        )
        (
            xml_document_id,
            xml_file_name,
            xml_root_language,
            proceedings_language,
            claims_text,
            claim_numbers,
        ) = _parse_and_validate_xml(record, xml.raw_bytes)
        pdf = await self._get_media(
            record,
            "pdf",
            aggregate_budget_bytes=aggregate_budget_bytes - len(xml.raw_bytes),
        )
        _validate_pdf(pdf.raw_bytes)
        return EPSPublicationArtifact(
            record=record,
            xml=xml,
            pdf=pdf,
            xml_document_id=xml_document_id,
            xml_file_name=xml_file_name,
            xml_root_language=xml_root_language,
            proceedings_language=proceedings_language,
            claims_text=claims_text,
            claim_numbers=claim_numbers,
            claims_text_sha256=hashlib.sha256(claims_text.encode("utf-8")).hexdigest(),
        )

    async def _fetch_artifacts(
        self,
        records: Sequence[EPSPublicationRecord],
    ) -> tuple[EPSPublicationArtifact, ...]:
        artifacts: list[EPSPublicationArtifact] = []
        aggregate_bytes = 0
        for record in records:
            artifact = await self.fetch_publication(
                record,
                aggregate_budget_bytes=EPS_AGGREGATE_MAX_BYTES - aggregate_bytes,
            )
            aggregate_bytes += len(artifact.xml.raw_bytes) + len(artifact.pdf.raw_bytes)
            if aggregate_bytes > EPS_AGGREGATE_MAX_BYTES:
                raise SourceUnavailableError(
                    "epo_publication_server",
                    "EPS publication media exceed the aggregate resource limit",
                )
            artifacts.append(artifact)
        return tuple(artifacts)

    async def resolve_historical_central_claims(
        self,
        publication_number: str,
        records: Sequence[EPSPublicationRecord],
        procedure: EPCentralProcedureEvidence,
        *,
        historical_as_of: date,
    ) -> EPControllingClaimsResolution:
        """Resolve an explicitly named historical snapshot."""
        if procedure.as_of != historical_as_of:
            return _indeterminate(
                publication_number,
                procedure.as_of,
                EPClaimsResolutionReason.RESOLUTION_AS_OF_MISMATCH,
                resolution_mode="historical",
                required_as_of=historical_as_of,
            )
        preflight = _publication_preflight_reason(
            publication_number,
            records,
            procedure,
            self._trusted_acquisition_public_keys,
        )
        if preflight is not None:
            return _indeterminate(
                publication_number,
                procedure.as_of,
                preflight,
                resolution_mode="historical",
                required_as_of=historical_as_of,
            )
        procedure_result = _procedure_gate(
            publication_number,
            procedure,
            resolution_mode="historical",
            required_as_of=historical_as_of,
        )
        if procedure_result is not None:
            return procedure_result
        artifacts = await self._fetch_artifacts(records)
        return resolve_ep_historical_central_claims(
            publication_number,
            artifacts,
            procedure,
            historical_as_of=historical_as_of,
            trusted_acquisition_public_keys=self._trusted_acquisition_public_keys,
        )

    async def resolve_current_central_claims(
        self,
        publication_number: str,
        records: Sequence[EPSPublicationRecord],
        procedure: EPCentralProcedureEvidence,
        *,
        authority_high_water: EPSignedSnapshotHighWaterReceipt | None = None,
        register_high_water: EPSignedSnapshotHighWaterReceipt | None = None,
        required_as_of: date | None = None,
    ) -> EPControllingClaimsResolution:
        """Resolve current claims only with fresh, persisted high-water receipts."""
        evaluated_at = datetime.now(UTC)
        current_boundary = required_as_of or evaluated_at.date()
        preflight = _publication_preflight_reason(
            publication_number,
            records,
            procedure,
            self._trusted_acquisition_public_keys,
        )
        if preflight is None:
            preflight = await _validate_and_advance_current_checkpoints(
                self._checkpoint_store,
                self._trusted_acquisition_public_keys,
                publication_number,
                procedure,
                authority_high_water=authority_high_water,
                register_high_water=register_high_water,
                required_as_of=current_boundary,
                evaluated_at=evaluated_at,
                policy=self._resolution_config,
            )
        if preflight is not None:
            return _indeterminate(
                publication_number,
                procedure.as_of,
                preflight,
                resolution_mode="current",
                required_as_of=current_boundary,
            )
        procedure_result = _procedure_gate(
            publication_number,
            procedure,
            resolution_mode="current",
            required_as_of=current_boundary,
        )
        if procedure_result is not None:
            return procedure_result
        artifacts = await self._fetch_artifacts(records)
        return _resolve_ep_central_claims(
            publication_number,
            artifacts,
            procedure,
            trusted_acquisition_public_keys=self._trusted_acquisition_public_keys,
            resolution_mode="current",
            required_as_of=current_boundary,
        )


__all__ = [
    "BASE_URL",
    "EPS_PDF_MAX_BYTES",
    "EPS_XML_MAX_BYTES",
    "EPAcquisitionEvidenceBundle",
    "EPAcquisitionEvidenceCollector",
    "EPAcquisitionEvidenceStore",
    "EPAtomicCheckpointStore",
    "EPCheckpointAdvance",
    "EPCheckpointBatchResult",
    "EPOPublicationResolutionConfig",
    "EPOPublicationServerClient",
    "resolve_ep_current_central_claims",
    "resolve_ep_historical_central_claims",
]
