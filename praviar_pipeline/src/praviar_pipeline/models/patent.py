"""Patent data models — output of Step 2 (search) and used throughout."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from re import fullmatch
from typing import Any, Literal, cast
from urllib.parse import parse_qsl

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from praviar_pipeline.models._base import PatentBase
from praviar_pipeline.models.patent_lineage import (
    AssignmentRecord,
    ForeignPriorityClaim,
    LegalEvent,
    LegalStatus,
    PatentFamily,
    PatentFamilyMember,
    PatentSource,
    PTABProceeding,
    TransactionEvent,
)
from praviar_pipeline.models.patent_term_models import (
    OrangeBookExclusivity,
    OrangeBookInfo,
    PatentTermInfo,
    PTABreakdown,
)
from praviar_pipeline.utils.claim_parser_parsing import split_claims

CLAIM_TEXT_PROVENANCE_SCHEMA_VERSION: Literal["claim-text-provenance-v2"] = (
    "claim-text-provenance-v2"
)
CLAIM_TEXT_COLLECTOR_VERSION = "2026-07-26"
CLAIM_TEXT_FUTURE_SKEW = timedelta(minutes=5)
CLAIM_TEXT_MAX_AGE = timedelta(days=7)
LEGAL_STATUS_PROVENANCE_SCHEMA_VERSION: Literal["legal-status-provenance-v2"] = (
    "legal-status-provenance-v2"
)
LEGAL_STATUS_COLLECTOR_VERSION = "2026-07-26"
LEGAL_STATUS_FUTURE_SKEW = timedelta(minutes=5)
LEGAL_STATUS_MAX_AGE = timedelta(hours=72)

LegalStatusCollectorIdentity = Literal[
    "search.enrichment.epo_ops_legal_status",
    "search.enrichment.epo_register",
]

GenusQueryRole = Literal[
    "murcko_scaffold",
    "canonical_fallback",
    "canonical_refinement_after_scaffold_cap",
]

_TRUSTED_LEGAL_STATUS_COLLECTORS: dict[str, tuple[PatentSource, str, str]] = {
    "search.enrichment.epo_ops_legal_status": (
        PatentSource.EPO_SEARCH,
        LEGAL_STATUS_COLLECTOR_VERSION,
        "https://ops.epo.org/3.2/rest-services/legal/publication/epodoc/",
    ),
    "search.enrichment.epo_register": (
        PatentSource.EPO_SEARCH,
        LEGAL_STATUS_COLLECTOR_VERSION,
        "https://ops.epo.org/3.2/rest-services/register/publication/epodoc/",
    ),
}


def _make_legal_status_attestation_boundary() -> tuple[
    Callable[[LegalStatusProvenance], object],
    Callable[[LegalStatusProvenance, object | None], bool],
]:
    """Create an identity-bound runtime attestation whose type is not exported."""

    class RuntimeLegalStatusAttestation:
        __slots__ = ("cassette_sha256", "provenance_id")

        def __init__(self, provenance: LegalStatusProvenance) -> None:
            self.provenance_id = id(provenance)
            self.cassette_sha256 = provenance.cassette_sha256

    def issue(provenance: LegalStatusProvenance) -> object:
        caller_module = str(sys._getframe(1).f_globals.get("__name__", ""))
        if caller_module != __name__:
            raise PermissionError("legal-status runtime attestation is module-private")
        return RuntimeLegalStatusAttestation(provenance)

    def verifies(provenance: LegalStatusProvenance, attestation: object | None) -> bool:
        return bool(
            isinstance(attestation, RuntimeLegalStatusAttestation)
            and attestation.provenance_id == id(provenance)
            and attestation.cassette_sha256 == provenance.cassette_sha256
        )

    return issue, verifies


_issue_legal_status_attestation, _verifies_legal_status_attestation = (
    _make_legal_status_attestation_boundary()
)
del _make_legal_status_attestation_boundary

_TRUSTED_CLAIM_TEXT_BUILDER_CALLS = frozenset(
    {
        (
            "praviar_pipeline.pipeline.runtime.live_collector_claims",
            "record_claims_text_retrieval",
        ),
        (
            "praviar_pipeline.pipeline.search.normalizers",
            "_patent_hit_from_row",
        ),
    }
)


def _make_claim_text_attestation_boundary() -> tuple[
    Callable[[ClaimTextProvenance], object],
    Callable[[ClaimTextProvenance, object | None], bool],
]:
    """Create an identity-bound runtime attestation for trusted claim collectors."""

    class RuntimeClaimTextAttestation:
        __slots__ = ("cassette_sha256", "provenance_id")

        def __init__(self, provenance: ClaimTextProvenance) -> None:
            self.provenance_id = id(provenance)
            self.cassette_sha256 = provenance.cassette_sha256

    def issue(provenance: ClaimTextProvenance) -> object:
        caller_module = str(sys._getframe(1).f_globals.get("__name__", ""))
        if caller_module != __name__:
            raise PermissionError("claim-text runtime attestation is module-private")
        return RuntimeClaimTextAttestation(provenance)

    def verifies(provenance: ClaimTextProvenance, attestation: object | None) -> bool:
        return bool(
            isinstance(attestation, RuntimeClaimTextAttestation)
            and attestation.provenance_id == id(provenance)
            and attestation.cassette_sha256 == provenance.cassette_sha256
        )

    return issue, verifies


_issue_claim_text_attestation, _verifies_claim_text_attestation = (
    _make_claim_text_attestation_boundary()
)
del _make_claim_text_attestation_boundary


def _checkpoint_semantic_sha256(checkpoint: object) -> str:
    if not hasattr(checkpoint, "model_dump"):
        return ""
    payload = checkpoint.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _checkpoint_patent_hits_sha256(checkpoint: object) -> str:
    payload = getattr(checkpoint, "patent_hits", None)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _make_checkpoint_restore_boundary() -> tuple[
    Callable[..., object],
    Callable[..., bool],
]:
    """Create a loader-issued capability bound to one immutable checkpoint payload."""

    class RuntimeCheckpointRestoreCapability:
        __slots__ = (
            "checkpoint_id",
            "checkpoint_semantic_sha256",
            "checkpoint_sha256",
            "patent_hits_sha256",
            "trusted_claim_text_cassette_sha256",
            "trusted_legal_status_cassette_sha256",
        )

        def __init__(
            self,
            checkpoint: object,
            *,
            checkpoint_sha256: str,
            patent_hits_sha256: str,
            trusted_claim_text_cassette_sha256: frozenset[str],
            trusted_legal_status_cassette_sha256: frozenset[str],
        ) -> None:
            self.checkpoint_id = id(checkpoint)
            self.checkpoint_semantic_sha256 = _checkpoint_semantic_sha256(checkpoint)
            self.checkpoint_sha256 = checkpoint_sha256
            self.patent_hits_sha256 = patent_hits_sha256
            self.trusted_claim_text_cassette_sha256 = trusted_claim_text_cassette_sha256
            self.trusted_legal_status_cassette_sha256 = trusted_legal_status_cassette_sha256

    def issue(
        checkpoint: object,
        *,
        checkpoint_sha256: str,
        patent_hits_sha256: str,
        trusted_claim_text_cassette_sha256: frozenset[str],
        trusted_legal_status_cassette_sha256: frozenset[str],
    ) -> object:
        caller = sys._getframe(1)
        if (
            str(caller.f_globals.get("__name__", "")) != "praviar_pipeline.checkpoint"
            or caller.f_code.co_name != "load_latest_checkpoint"
        ):
            raise PermissionError("checkpoint restore capability is loader-private")
        if fullmatch(r"[0-9a-f]{64}", checkpoint_sha256) is None:
            raise ValueError("checkpoint payload hash is invalid")
        if patent_hits_sha256 != _checkpoint_patent_hits_sha256(checkpoint):
            raise ValueError("checkpoint patent-hit hash is invalid")
        return RuntimeCheckpointRestoreCapability(
            checkpoint,
            checkpoint_sha256=checkpoint_sha256,
            patent_hits_sha256=patent_hits_sha256,
            trusted_claim_text_cassette_sha256=trusted_claim_text_cassette_sha256,
            trusted_legal_status_cassette_sha256=trusted_legal_status_cassette_sha256,
        )

    def verifies(
        checkpoint: object,
        capability: object | None,
        cassette_sha256: str | None = None,
        *,
        claim_text_cassette_sha256: str | None = None,
    ) -> bool:
        return bool(
            isinstance(capability, RuntimeCheckpointRestoreCapability)
            and capability.checkpoint_id == id(checkpoint)
            and capability.checkpoint_semantic_sha256 == _checkpoint_semantic_sha256(checkpoint)
            and capability.patent_hits_sha256 == _checkpoint_patent_hits_sha256(checkpoint)
            and (
                cassette_sha256 is None
                or cassette_sha256 in capability.trusted_legal_status_cassette_sha256
            )
            and (
                claim_text_cassette_sha256 is None
                or claim_text_cassette_sha256 in capability.trusted_claim_text_cassette_sha256
            )
        )

    return issue, verifies


_issue_checkpoint_restore_capability, _verifies_checkpoint_restore_capability = (
    _make_checkpoint_restore_boundary()
)
del _make_checkpoint_restore_boundary

ClaimTextCollectorIdentity = Literal[
    "search.bigquery_result",
    "search.bigquery_translated_result",
    "search.epo_search_result",
    "search.patentsview_result",
    "runtime.bigquery_claims_batch",
    "runtime.patentsview_claims",
    "runtime.epo_ops_claims",
    "step2c.epo_ops_claims",
    "step2c.family_bigquery_claims",
    "step2c.bigquery_claims",
    "analysis.bigquery_claims",
    "analysis.epo_ops_claims",
    "analysis.patentsview_claims",
    "dev.synthetic_fixture",
]

_TRUSTED_CLAIM_TEXT_COLLECTORS: dict[str, PatentSource] = {
    "search.bigquery_result": PatentSource.BIGQUERY,
    "search.epo_search_result": PatentSource.EPO_SEARCH,
    "search.patentsview_result": PatentSource.PATENTSVIEW,
    "runtime.bigquery_claims_batch": PatentSource.BIGQUERY,
    "runtime.patentsview_claims": PatentSource.PATENTSVIEW,
    "runtime.epo_ops_claims": PatentSource.EPO_SEARCH,
    "step2c.epo_ops_claims": PatentSource.EPO_SEARCH,
    "step2c.family_bigquery_claims": PatentSource.BIGQUERY,
    "step2c.bigquery_claims": PatentSource.BIGQUERY,
    "analysis.bigquery_claims": PatentSource.BIGQUERY,
    "analysis.epo_ops_claims": PatentSource.EPO_SEARCH,
    "analysis.patentsview_claims": PatentSource.PATENTSVIEW,
    "dev.synthetic_fixture": PatentSource.SYNTHETIC_FIXTURE,
}

_EXPLICIT_CLAIM_NUMBER_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:claim\s+)?(\d{1,3})\s*[.:]\s+",
    re.IGNORECASE,
)


def _claim_text_locator_base(source: PatentSource, patent_id: str) -> str:
    if source == PatentSource.BIGQUERY:
        return (
            "https://console.cloud.google.com/bigquery?project="
            f"patents-public-data&patent={patent_id}"
        )
    if source == PatentSource.EPO_SEARCH:
        return (
            "https://ops.epo.org/3.2/rest-services/published-data/"
            f"publication/epodoc/{patent_id}/claims"
        )
    if source == PatentSource.PATENTSVIEW:
        return f"https://search.patentsview.org/api/v1/patent/?patent_id={patent_id}"
    if source == PatentSource.SYNTHETIC_FIXTURE:
        return f"praviar-demo://claim-text/{patent_id}"
    raise ValueError("claim-text source has no trusted artifact locator policy")


def artifact_locator_binds_sha256(artifact_locator: str, artifact_sha256: str) -> bool:
    """Return whether a locator has exactly one matching SHA-256 content address."""
    locator = str(artifact_locator or "").strip()
    digest = str(artifact_sha256 or "").strip()
    if not locator or fullmatch(r"[0-9a-f]{64}", digest) is None:
        return False
    _base, separator, fragment = locator.partition("#")
    if not separator or not fragment:
        return False
    try:
        embedded_hashes = [
            value
            for key, value in parse_qsl(
                fragment,
                keep_blank_values=True,
                strict_parsing=True,
            )
            if key == "sha256"
        ]
    except ValueError:
        return False
    return embedded_hashes == [digest]


def _content_addressed_locator(artifact_locator: str, artifact_sha256: str) -> str:
    locator = str(artifact_locator or "").strip()
    if not locator:
        raise ValueError("artifact locator is required")
    base, separator, fragment = locator.partition("#")
    if separator:
        try:
            embedded_hashes = [
                value
                for key, value in parse_qsl(
                    fragment,
                    keep_blank_values=True,
                    strict_parsing=True,
                )
                if key == "sha256"
            ]
        except ValueError as exc:
            raise ValueError("artifact locator fragment is malformed") from exc
        if embedded_hashes:
            if embedded_hashes != [artifact_sha256]:
                raise ValueError("artifact locator SHA-256 mismatch")
            return locator
        return f"{base}#{fragment}&sha256={artifact_sha256}"
    return f"{locator}#sha256={artifact_sha256}"


def _status_from_legal_artifact(
    collector_identity: LegalStatusCollectorIdentity,
    artifact: object,
) -> LegalStatus:
    """Replay the source-specific status derivation over retained collector output."""
    if collector_identity == "search.enrichment.epo_register":
        if not isinstance(artifact, dict):
            return LegalStatus.UNKNOWN
        normalized = str(artifact.get("status") or "").strip().lower()
        return {
            "active": LegalStatus.ACTIVE,
            "in force": LegalStatus.ACTIVE,
            "patent granted": LegalStatus.ACTIVE,
            "pending": LegalStatus.PENDING,
            "application pending": LegalStatus.PENDING,
            "revoked": LegalStatus.REVOKED,
            "patent revoked": LegalStatus.REVOKED,
            "lapsed": LegalStatus.LAPSED,
            "withdrawn": LegalStatus.LAPSED,
            "expired": LegalStatus.EXPIRED,
            "patent expired": LegalStatus.EXPIRED,
        }.get(normalized, LegalStatus.UNKNOWN)

    if not isinstance(artifact, list):
        return LegalStatus.UNKNOWN
    from praviar_pipeline.utils.legal_status_events import (
        derive_legal_status_from_events,
    )

    return derive_legal_status_from_events(artifact)


class ClaimTextProvenance(BaseModel):
    """Content-addressed retrieval cassette for authoritative claim text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["claim-text-provenance-v2"] = CLAIM_TEXT_PROVENANCE_SCHEMA_VERSION
    source: PatentSource
    source_document_id: str = Field(min_length=1)
    retrieved_at: datetime
    artifact_locator: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    collector_identity: ClaimTextCollectorIdentity
    collector_version: str = Field(min_length=1)
    claim_numbers: tuple[int, ...] = ()
    independent_claim_numbers: tuple[int, ...] = ()
    retrieval_complete: bool = False
    cassette_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    _runtime_attestation: object | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _validate_cassette_hash(self) -> ClaimTextProvenance:
        expected_source = _TRUSTED_CLAIM_TEXT_COLLECTORS.get(self.collector_identity)
        if expected_source != self.source:
            raise ValueError("claim-text collector/source attestation mismatch")
        if self.collector_version != CLAIM_TEXT_COLLECTOR_VERSION:
            raise ValueError("claim-text collector version is not trusted")
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("claim-text retrieved_at must be timezone-aware")
        retrieved_at = self.retrieved_at.astimezone(UTC)
        now = datetime.now(UTC)
        if retrieved_at > now + CLAIM_TEXT_FUTURE_SKEW:
            raise ValueError("claim-text provenance timestamp is in the future")
        if retrieved_at < now - CLAIM_TEXT_MAX_AGE:
            raise ValueError("claim-text provenance is stale")
        expected_locator = _claim_text_locator_base(self.source, self.source_document_id)
        if self.artifact_locator.partition("#")[0] != expected_locator:
            raise ValueError("claim-text artifact locator is not allowlisted")
        if not artifact_locator_binds_sha256(self.artifact_locator, self.artifact_sha256):
            raise ValueError("claim-text artifact locator SHA-256 mismatch")
        cassette = {
            "schema_version": self.schema_version,
            "source": self.source.value,
            "source_document_id": self.source_document_id,
            "retrieved_at": self.retrieved_at.isoformat(),
            "artifact_locator": self.artifact_locator,
            "artifact_sha256": self.artifact_sha256,
            "collector_identity": self.collector_identity,
            "collector_version": self.collector_version,
            "claim_numbers": list(self.claim_numbers),
            "independent_claim_numbers": list(self.independent_claim_numbers),
            "retrieval_complete": self.retrieval_complete,
        }
        expected = hashlib.sha256(
            json.dumps(cassette, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if self.cassette_sha256 != expected:
            raise ValueError("claim-text provenance cassette hash mismatch")
        return self

    def supports(self, claims_text: str, patent_id: str) -> bool:
        if not _verifies_claim_text_attestation(self, self._runtime_attestation):
            return False
        try:
            ClaimTextProvenance.model_validate(self.model_dump(mode="python"))
        except (TypeError, ValueError):
            return False
        return bool(
            claims_text
            and self.retrieval_complete
            and self.claim_numbers
            and self.independent_claim_numbers
            and self.source_document_id == patent_id
            and artifact_locator_binds_sha256(self.artifact_locator, self.artifact_sha256)
            and hashlib.sha256(claims_text.encode("utf-8")).hexdigest() == self.artifact_sha256
        )


def build_claim_text_provenance(
    *,
    patent_id: str,
    claims_text: str,
    source: PatentSource,
    artifact_locator: str,
    collector_identity: ClaimTextCollectorIdentity,
    retrieved_at: datetime | None = None,
) -> ClaimTextProvenance:
    """Build a hash-verified provenance cassette for newly retrieved text."""
    timestamp = retrieved_at or datetime.now(UTC)
    artifact_sha256 = hashlib.sha256(claims_text.encode("utf-8")).hexdigest()
    content_bound_locator = _content_addressed_locator(artifact_locator, artifact_sha256)
    parsed_claims = split_claims(claims_text)
    explicit_numbers = tuple(
        int(match.group(1)) for match in _EXPLICIT_CLAIM_NUMBER_PATTERN.finditer(claims_text)
    )
    parsed_numbers = tuple(claim.claim_number for claim in parsed_claims)
    independent_claim_numbers = tuple(
        claim.claim_number for claim in parsed_claims if claim.claim_type == "independent"
    )
    retrieval_complete = bool(
        explicit_numbers
        and explicit_numbers == parsed_numbers
        and len(set(parsed_numbers)) == len(parsed_numbers)
        and tuple(sorted(parsed_numbers)) == parsed_numbers
        and independent_claim_numbers
        and all(claim.raw_text.strip() for claim in parsed_claims)
        and all(
            element.element_text.strip() for claim in parsed_claims for element in claim.elements
        )
    )
    cassette = {
        "schema_version": CLAIM_TEXT_PROVENANCE_SCHEMA_VERSION,
        "source": source.value,
        "source_document_id": patent_id,
        "retrieved_at": timestamp.isoformat(),
        "artifact_locator": content_bound_locator,
        "artifact_sha256": artifact_sha256,
        "collector_identity": collector_identity,
        "collector_version": CLAIM_TEXT_COLLECTOR_VERSION,
        "claim_numbers": list(parsed_numbers),
        "independent_claim_numbers": list(independent_claim_numbers),
        "retrieval_complete": retrieval_complete,
    }
    cassette_sha256 = hashlib.sha256(
        json.dumps(cassette, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    provenance = ClaimTextProvenance(
        schema_version=CLAIM_TEXT_PROVENANCE_SCHEMA_VERSION,
        source=source,
        source_document_id=patent_id,
        retrieved_at=timestamp,
        artifact_locator=content_bound_locator,
        artifact_sha256=artifact_sha256,
        collector_identity=collector_identity,
        collector_version=CLAIM_TEXT_COLLECTOR_VERSION,
        claim_numbers=parsed_numbers,
        independent_claim_numbers=independent_claim_numbers,
        retrieval_complete=retrieval_complete,
        cassette_sha256=cassette_sha256,
    )
    caller = sys._getframe(1)
    caller_identity = (
        str(caller.f_globals.get("__name__", "")),
        caller.f_code.co_name,
    )
    if caller_identity in _TRUSTED_CLAIM_TEXT_BUILDER_CALLS:
        provenance._runtime_attestation = _issue_claim_text_attestation(provenance)
    return provenance


def has_trusted_claim_text_provenance(detail: object) -> bool:
    """Return whether current claim text is bound to a trusted collector cassette."""
    payload = getattr(detail, "claims_text_provenance", None)
    try:
        provenance = ClaimTextProvenance.model_validate(payload)
    except (TypeError, ValueError):
        return False
    claims_text = str(getattr(detail, "claims_text", "") or "")
    patent_id = str(getattr(detail, "patent_id", "") or "")
    claims_text_source = str(getattr(detail, "claims_text_source", "") or "")
    patent_id_upper = patent_id.upper()
    controlling_source = bool(
        patent_id_upper.startswith("US")
        and provenance.source in {PatentSource.BIGQUERY, PatentSource.PATENTSVIEW}
        and provenance.collector_identity != "search.bigquery_translated_result"
    )
    return bool(
        controlling_source
        and claims_text_source == provenance.source.value
        and provenance.supports(claims_text, patent_id)
    )


def trusted_claim_text_provenance(detail: object) -> ClaimTextProvenance | None:
    """Return the trusted current claim-text cassette, if one exists."""
    if not has_trusted_claim_text_provenance(detail):
        return None
    payload = getattr(detail, "claims_text_provenance", None)
    return payload if isinstance(payload, ClaimTextProvenance) else None


def _restore_checkpoint_claim_text_attestation(
    detail: object,
    *,
    checkpoint: object,
    checkpoint_restore_capability: object,
) -> None:
    """Reattach claim-text trust only after authenticated checkpoint loading."""
    caller = sys._getframe(1)
    if (
        str(caller.f_globals.get("__name__", "")) != "praviar_pipeline.checkpoint_restoration"
        or caller.f_code.co_name != "_restore_patent_hits"
    ):
        raise PermissionError("claim-text checkpoint restoration is callsite-private")
    payload = getattr(detail, "claims_text_provenance", None)
    if payload is None:
        return
    provenance = ClaimTextProvenance.model_validate(
        payload.model_dump(mode="python") if hasattr(payload, "model_dump") else payload
    )
    if not _verifies_checkpoint_restore_capability(
        checkpoint,
        checkpoint_restore_capability,
        claim_text_cassette_sha256=provenance.cassette_sha256,
    ):
        return
    claims_text = str(getattr(detail, "claims_text", "") or "")
    patent_id = str(getattr(detail, "patent_id", "") or "")
    claims_text_source = str(getattr(detail, "claims_text_source", "") or "")
    if (
        claims_text_source != provenance.source.value
        or provenance.source_document_id != patent_id
        or hashlib.sha256(claims_text.encode("utf-8")).hexdigest() != provenance.artifact_sha256
    ):
        raise ValueError("checkpoint claim-text provenance subject mismatch")
    provenance._runtime_attestation = _issue_claim_text_attestation(provenance)
    detail.claims_text_provenance = provenance  # type: ignore[attr-defined]
    if not has_trusted_claim_text_provenance(detail):
        raise ValueError("checkpoint claim-text provenance failed trust revalidation")


class LegalStatusProvenance(BaseModel):
    """Trusted-collector attestation for one exact legal-status observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["legal-status-provenance-v2"] = LEGAL_STATUS_PROVENANCE_SCHEMA_VERSION
    source: PatentSource
    source_document_id: str = Field(min_length=1)
    observed_status: LegalStatus
    retrieved_at: datetime
    artifact_locator: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_payload: dict[str, Any] | list[dict[str, Any]]
    collector_identity: LegalStatusCollectorIdentity
    collector_version: str = Field(min_length=1)
    cassette_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    _runtime_attestation: object | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _validate_trusted_attestation(self) -> LegalStatusProvenance:
        policy = _TRUSTED_LEGAL_STATUS_COLLECTORS.get(self.collector_identity)
        if policy is None:
            raise ValueError("legal-status collector is not trusted")
        expected_source, expected_version, locator_prefix = policy
        if self.source != expected_source:
            raise ValueError("legal-status collector/source attestation mismatch")
        if self.collector_version != expected_version:
            raise ValueError("legal-status collector version is not trusted")
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("legal-status retrieved_at must be timezone-aware")
        retrieved_at = self.retrieved_at.astimezone(UTC)
        now = datetime.now(UTC)
        if retrieved_at > now + LEGAL_STATUS_FUTURE_SKEW:
            raise ValueError("legal-status provenance timestamp is in the future")
        if retrieved_at < now - LEGAL_STATUS_MAX_AGE:
            raise ValueError("legal-status provenance is stale")
        expected_locator = f"{locator_prefix}{self.source_document_id}"
        locator_base = self.artifact_locator.partition("#")[0]
        if locator_base != expected_locator:
            raise ValueError("legal-status artifact locator is not allowlisted")
        if not artifact_locator_binds_sha256(self.artifact_locator, self.artifact_sha256):
            raise ValueError("legal-status artifact locator SHA-256 mismatch")
        retained_artifact_sha256 = hashlib.sha256(
            json.dumps(
                self.artifact_payload,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        if retained_artifact_sha256 != self.artifact_sha256:
            raise ValueError("legal-status retained artifact hash mismatch")
        replayed_status = _status_from_legal_artifact(
            self.collector_identity,
            self.artifact_payload,
        )
        if replayed_status != self.observed_status:
            raise ValueError("legal-status retained artifact does not entail observed status")

        cassette = {
            "schema_version": self.schema_version,
            "source": self.source.value,
            "source_document_id": self.source_document_id,
            "observed_status": self.observed_status.value,
            "retrieved_at": self.retrieved_at.isoformat(),
            "artifact_locator": self.artifact_locator,
            "artifact_sha256": self.artifact_sha256,
            "artifact_payload": self.artifact_payload,
            "collector_identity": self.collector_identity,
            "collector_version": self.collector_version,
        }
        expected_cassette_sha256 = hashlib.sha256(
            json.dumps(cassette, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if self.cassette_sha256 != expected_cassette_sha256:
            raise ValueError("legal-status provenance cassette hash mismatch")
        return self

    def supports(self, legal_status: LegalStatus | str, patent_id: str) -> bool:
        """Revalidate the exact status, document, collector, and locator binding."""
        if not _verifies_legal_status_attestation(self, self._runtime_attestation):
            return False
        try:
            status = (
                legal_status if isinstance(legal_status, LegalStatus) else LegalStatus(legal_status)
            )
            LegalStatusProvenance.model_validate(self.model_dump(mode="python"))
        except (TypeError, ValueError):
            return False
        return self.source_document_id == patent_id and self.observed_status == status


def _build_legal_status_provenance(
    *,
    patent_id: str,
    legal_status: LegalStatus,
    artifact: object,
    collector_identity: LegalStatusCollectorIdentity,
    retrieved_at: datetime | None = None,
) -> LegalStatusProvenance:
    """Build a trusted, content-addressed legal-status collector attestation."""
    caller_frame = sys._getframe(1)
    caller_module = str(caller_frame.f_globals.get("__name__", ""))
    expected_caller = {
        "search.enrichment.epo_ops_legal_status": "enrich_legal_status",
        "search.enrichment.epo_register": "enrich_epo_register",
    }[collector_identity]
    if (
        caller_module != "praviar_pipeline.pipeline.search.enrichment"
        or caller_frame.f_code.co_name != expected_caller
    ):
        raise PermissionError("legal-status provenance requires the trusted collector adapter")
    artifact_payload: dict[str, Any] | list[dict[str, Any]]
    if isinstance(artifact, dict):
        artifact_payload = cast("dict[str, Any]", artifact)
    elif isinstance(artifact, list) and all(isinstance(item, dict) for item in artifact):
        artifact_payload = cast("list[dict[str, Any]]", artifact)
    else:
        raise ValueError("legal-status artifact must be an object or list of objects")
    source, collector_version, locator_prefix = _TRUSTED_LEGAL_STATUS_COLLECTORS[collector_identity]
    artifact_bytes = json.dumps(
        artifact_payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    timestamp = retrieved_at or datetime.now(UTC)
    cassette = {
        "schema_version": LEGAL_STATUS_PROVENANCE_SCHEMA_VERSION,
        "source": source.value,
        "source_document_id": patent_id,
        "observed_status": legal_status.value,
        "retrieved_at": timestamp.isoformat(),
        "artifact_locator": f"{locator_prefix}{patent_id}#sha256={artifact_sha256}",
        "artifact_sha256": artifact_sha256,
        "artifact_payload": artifact_payload,
        "collector_identity": collector_identity,
        "collector_version": collector_version,
    }
    cassette_sha256 = hashlib.sha256(
        json.dumps(cassette, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    provenance = LegalStatusProvenance(
        schema_version=LEGAL_STATUS_PROVENANCE_SCHEMA_VERSION,
        source=source,
        source_document_id=patent_id,
        observed_status=legal_status,
        retrieved_at=timestamp,
        artifact_locator=f"{locator_prefix}{patent_id}#sha256={artifact_sha256}",
        artifact_sha256=artifact_sha256,
        artifact_payload=artifact_payload,
        collector_identity=collector_identity,
        collector_version=collector_version,
        cassette_sha256=cassette_sha256,
    )
    provenance._runtime_attestation = _issue_legal_status_attestation(provenance)
    return provenance


def has_trusted_legal_status_provenance(
    detail: object,
    *,
    collector_identity: LegalStatusCollectorIdentity | None = None,
) -> bool:
    """Return whether a patent detail carries a trusted exact-status attestation."""
    payload = getattr(detail, "legal_status_provenance", None)
    try:
        provenance = LegalStatusProvenance.model_validate(payload)
    except (TypeError, ValueError):
        return False
    if collector_identity is not None and provenance.collector_identity != collector_identity:
        return False
    sources = {
        item if isinstance(item, PatentSource) else PatentSource(item)
        for item in (getattr(detail, "sources", None) or [])
    }
    return bool(
        provenance.source in sources
        and provenance.supports(
            getattr(detail, "legal_status", LegalStatus.UNKNOWN),
            str(getattr(detail, "patent_id", "") or ""),
        )
    )


def trusted_legal_status_observations(
    detail: object,
) -> tuple[LegalStatusProvenance, ...]:
    """Return independently attested status observations for one patent."""
    patent_id = str(getattr(detail, "patent_id", "") or "")
    try:
        sources = {
            item if isinstance(item, PatentSource) else PatentSource(item)
            for item in (getattr(detail, "sources", None) or [])
        }
    except ValueError:
        return ()

    candidates = list(getattr(detail, "legal_status_observations", None) or [])
    primary = getattr(detail, "legal_status_provenance", None)
    if primary is not None:
        candidates.append(primary)

    trusted: list[LegalStatusProvenance] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            provenance = LegalStatusProvenance.model_validate(candidate)
        except (TypeError, ValueError):
            continue
        if provenance.cassette_sha256 in seen or provenance.source not in sources:
            continue
        if not provenance.supports(provenance.observed_status, patent_id):
            continue
        seen.add(provenance.cassette_sha256)
        trusted.append(provenance)
    return tuple(trusted)


def trusted_legal_status_conflict(
    detail: object,
) -> tuple[LegalStatus, ...]:
    """Return conflicting authoritative statuses, or an empty tuple."""
    statuses = {
        observation.observed_status
        for observation in trusted_legal_status_observations(detail)
        if observation.observed_status != LegalStatus.UNKNOWN
    }
    if len(statuses) < 2:
        return ()
    return tuple(sorted(statuses, key=lambda status: status.value))


def _restore_checkpoint_legal_status_attestation(
    detail: object,
    *,
    checkpoint: object,
    checkpoint_restore_capability: object,
) -> None:
    """Reattach runtime trust only for an integrity-validated checkpoint restore."""
    caller = sys._getframe(1)
    if (
        str(caller.f_globals.get("__name__", "")) != "praviar_pipeline.checkpoint_restoration"
        or caller.f_code.co_name != "_restore_patent_hits"
    ):
        raise PermissionError("legal-status checkpoint restoration is callsite-private")
    if not _verifies_checkpoint_restore_capability(
        checkpoint,
        checkpoint_restore_capability,
    ):
        raise PermissionError("checkpoint restore capability is invalid")
    sources = {
        item if isinstance(item, PatentSource) else PatentSource(item)
        for item in (getattr(detail, "sources", None) or [])
    }
    patent_id = str(getattr(detail, "patent_id", "") or "")

    def restore_one(payload: object) -> LegalStatusProvenance | None:
        provenance = LegalStatusProvenance.model_validate(
            payload.model_dump(mode="python") if hasattr(payload, "model_dump") else payload
        )
        if not _verifies_checkpoint_restore_capability(
            checkpoint,
            checkpoint_restore_capability,
            provenance.cassette_sha256,
        ):
            return None
        if provenance.source not in sources:
            raise ValueError("checkpoint legal-status provenance source is absent from patent hit")
        if provenance.source_document_id != patent_id:
            raise ValueError("checkpoint legal-status provenance document mismatch")
        provenance._runtime_attestation = _issue_legal_status_attestation(provenance)
        return provenance

    observation_payloads = list(getattr(detail, "legal_status_observations", None) or [])
    restored_observations = [
        restored for item in observation_payloads if (restored := restore_one(item)) is not None
    ]
    detail.legal_status_observations = restored_observations  # type: ignore[attr-defined]

    payload = getattr(detail, "legal_status_provenance", None)
    if payload is not None:
        provenance = restore_one(payload)
        if provenance is not None:
            status = getattr(detail, "legal_status", LegalStatus.UNKNOWN)
            if provenance.observed_status != status:
                raise ValueError("checkpoint legal-status provenance status mismatch")
            detail.legal_status_provenance = provenance  # type: ignore[attr-defined]
            if not has_trusted_legal_status_provenance(detail):
                raise ValueError("checkpoint legal-status provenance failed trust revalidation")

    if len(trusted_legal_status_observations(detail)) < len(restored_observations):
        raise ValueError("checkpoint legal-status observation failed trust revalidation")


class SequencePatentMatch(BaseModel):
    """Content-addressed NCBI patent-protein alignment evidence."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ncbi-patent-sequence-match-v1"] = "ncbi-patent-sequence-match-v1"
    program: Literal["blastp"] = "blastp"
    database: Literal["pat"] = "pat"
    request_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Z0-9-]+$")
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_subunit_index: int = Field(ge=1)
    query_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_length: int = Field(ge=1, le=10000)
    subject_accession: str = Field(min_length=1, max_length=100)
    subject_title: str = Field(default="", max_length=1000)
    identity: float = Field(ge=0.0, le=1.0)
    query_coverage: float = Field(ge=0.0, le=1.0)
    evalue: float = Field(ge=0.0)
    bit_score: float = Field(ge=0.0)
    retrieved_at: datetime
    artifact_locator: str = Field(
        pattern=r"^https://blast\.ncbi\.nlm\.nih\.gov/Blast\.cgi\?",
        max_length=500,
    )


class GenusPatentMatch(BaseModel):
    """Content-addressed developed-structure genus-candidate evidence."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["pubchem-genus-match-v1"] = "pubchem-genus-match-v1"
    search_type: Literal["pubchem_fastsubstructure"] = "pubchem_fastsubstructure"
    query_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_role: GenusQueryRole
    matched_pubchem_cid: int = Field(ge=1)
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieved_at: datetime
    artifact_locator: str = Field(
        pattern=(
            r"^https://pubchem\.ncbi\.nlm\.nih\.gov/rest/pug/compound/"
            r"cid/\d+/xrefs/PatentID/JSON#sha256=[0-9a-f]{64}$"
        ),
        max_length=500,
    )


class PatentHit(PatentBase):
    """A patent found during multi-source search, before full details are fetched.

    External-boundary model. Uses ``extra="forbid"`` (inherited from
    :class:`PatentBase`) so unknown fields from upstream sources surface
    as validation errors. ``patent_id`` and ``jurisdiction`` are
    inherited.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = ""
    abstract: str = ""
    claims_text: str = Field(default="", description="Full claim text if available from source")
    claims_text_source: str = Field(
        default="",
        description="Source used to collect the current claims_text payload",
    )
    claims_text_provenance: ClaimTextProvenance | None = Field(
        default=None,
        description=(
            "Artifact-grade retrieval cassette. Missing or hash-invalid provenance "
            "cannot support a verified claim-text assertion."
        ),
    )

    @field_validator("title", "abstract", "claims_text", "claims_text_source", mode="before")
    @classmethod
    def _coerce_none_to_empty(cls, v: str | None) -> str:
        """Patent sources may return None for text fields. Coerce to empty string
        so downstream steps always get str, never None. The source health record
        tracks which sources returned incomplete data."""
        return v if v is not None else ""

    sources: list[PatentSource] = Field(
        default_factory=list,
        min_length=1,
        description="Which APIs found this patent",
    )
    confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Composite confidence based on source agreement and match quality",
    )
    ranking_composite_score: float | None = Field(default=None, ge=0.0, le=1.0)
    ranking_bm25_score: float | None = Field(default=None, ge=0.0)
    ranking_bm25_normalized_score: float | None = Field(default=None, ge=0.0, le=1.0)
    ranking_embedding_score: float | None = Field(default=None)
    ranking_embedding_normalized_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    ranking_final_blend_score: float | None = Field(default=None, ge=0.0, le=1.0)

    # Metadata
    filing_date: date | None = None
    priority_date: date | None = None
    expiry_date: date | None = None
    assignees: list[str] = Field(default_factory=list)
    inventors: list[str] = Field(default_factory=list)
    cpc_codes: list[str] = Field(default_factory=list)
    legal_status: LegalStatus = LegalStatus.UNKNOWN
    legal_status_provenance: LegalStatusProvenance | None = Field(
        default=None,
        description=(
            "Trusted collector attestation for the exact legal_status value. "
            "Unattested statuses cannot contradict blocking analysis."
        ),
    )
    legal_status_observations: list[LegalStatusProvenance] = Field(
        default_factory=list,
        description=(
            "Independently attested status observations retained for conflict "
            "adjudication. Conflicting authoritative observations force review."
        ),
    )
    primary_legal_status_receipts: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Fresh server-attested primary-authority receipts for term, maintenance, "
            "post-grant, and current-claim reliance gates."
        ),
    )

    # Chemical match details
    match_type: Literal["exact", "similarity", "substructure", "sequence", "text", ""] = Field(
        default="",
        description=(
            "How the compound matched: exact, similarity, substructure, sequence, or text"
        ),
    )
    tanimoto_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Chemical similarity score if from structure search",
    )
    sequence_matches: list[SequencePatentMatch] = Field(
        default_factory=list,
        description=(
            "NCBI GenBank Patent protein alignments. Query sequences are represented "
            "only by SHA-256 and length; raw sequence is not duplicated per hit."
        ),
    )
    genus_matches: list[GenusPatentMatch] = Field(
        default_factory=list,
        description=(
            "PubChem scaffold/substructure matches to developed compounds linked to "
            "this patent. These are genus candidates and do not establish true "
            "Markush-formula coverage."
        ),
    )

    # Patent type
    is_granted: bool = Field(
        default=True,
        description="True for granted patents (B-type), False for applications (A1/A2)",
    )

    # Application metadata
    application_number: str = ""
    examiner: str = ""
    attorney: str = ""
    # ``jurisdiction`` is inherited from PatentBase and populated from
    # the country prefix on patent_id during normalisation.

    # Enrichment data (populated by post-search steps)
    legal_events: list[LegalEvent] = Field(default_factory=list)
    family: PatentFamily | None = None
    family_broadest: bool = Field(
        default=False,
        description="True if this is the broadest-claims member of its patent family",
    )
    family_role: Literal[
        "parent", "continuation", "divisional", "continuation_in_part", "reissue", "unknown", ""
    ] = Field(
        default="",
        description=(
            "Role of this patent within its family lineage. Populated by continuation "
            "expansion when this hit was added via family traversal from another hit."
        ),
    )
    parent_application_id: str = Field(
        default="",
        description=(
            "Patent/application id of the parent hit that caused this one to be added "
            "during continuation expansion. Empty for hits discovered by primary search."
        ),
    )
    patent_term_info: PatentTermInfo | None = None

    # Rich USPTO data (populated by post-search enrichment)
    assignments: list[AssignmentRecord] = Field(default_factory=list)
    foreign_priority: list[ForeignPriorityClaim] = Field(default_factory=list)
    transactions: list[TransactionEvent] = Field(default_factory=list)

    # PTAB post-grant proceedings
    ptab_proceedings: list[PTABProceeding] = Field(
        default_factory=list,
        description="IPR/PGR/CBM proceedings from PTAB API",
    )

    # Orange Book regulatory linkage
    orange_book_listed: bool = Field(
        default=False,
        description="True if patent appears in FDA Orange Book",
    )
    patent_use_code: str = Field(
        default="",
        description="Orange Book U-xxx use code (method-of-treatment, compound, etc.)",
    )
    patent_term_extension_days: int = Field(
        default=0,
        description="Hatch-Waxman PTE days from Orange Book or PTE certificates",
    )
    orange_book_info: OrangeBookInfo | None = Field(
        default=None,
        description="FDA Orange Book listing data if patent covers approved drug",
    )

    # EPO register data
    designated_states: list[str] = Field(
        default_factory=list,
        description="EP designated/validated states",
    )
    ep_register_status: str = Field(
        default="",
        description="Current EP register status when available from EPO OPS register data",
    )
    opposition_events: list[LegalEvent] = Field(
        default_factory=list,
        description="Opposition-related legal events from INPADOC",
    )
    priority_claims: list[ForeignPriorityClaim] = Field(
        default_factory=list,
        description="Priority claims from register data",
    )

    @field_validator("match_type", mode="before")
    @classmethod
    def _coerce_match_type(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip().lower()
            if v not in {
                "exact",
                "similarity",
                "substructure",
                "sequence",
                "text",
                "",
            }:
                return ""
        return v


__all__ = [
    "AssignmentRecord",
    "ClaimTextProvenance",
    "ForeignPriorityClaim",
    "GenusPatentMatch",
    "LegalEvent",
    "LegalStatus",
    "OrangeBookExclusivity",
    "OrangeBookInfo",
    "PTABProceeding",
    "PTABreakdown",
    "PatentFamily",
    "PatentFamilyMember",
    "PatentHit",
    "PatentSource",
    "PatentTermInfo",
    "SequencePatentMatch",
    "TransactionEvent",
    "artifact_locator_binds_sha256",
    "build_claim_text_provenance",
    "has_trusted_claim_text_provenance",
]
