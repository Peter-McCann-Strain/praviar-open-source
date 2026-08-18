"""Fail-closed evidence contracts for current primary-authority legal status.

The contracts deliberately separate collection freshness from the effective
date of a legal event.  They also keep EPO INPADOC/Federated Register evidence
supplementary: national post-grant reliance requires the relevant national
authority, exactly as the EPO Register documentation instructs.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast
from urllib.parse import parse_qsl, urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from collections.abc import Callable

LegalStatusSource = Literal[
    "uspto_odp_application",
    "uspto_odp_ptab",
    "uspto_maintenance_storefront",
    "epo_ops_register",
    "epo_ops_legal",
    "epo_federated_register",
    "ep_national_register",
]
EvidenceScope = Literal[
    "application_prosecution",
    "patent_term",
    "patent_maintenance",
    "post_grant_proceeding",
    "current_claim_set",
    "claim_adjudication",
    "ep_central_proceeding",
    "ep_unitary_effect",
    "ep_national_post_grant",
    "worldwide_legal_events",
]
ParserResult = Literal["conclusive", "inconclusive", "error"]
NormalizedLegalStatusOutcome = Literal[
    "patented",
    "pending",
    "abandoned",
    "paid",
    "grace_period",
    "lapsed",
    "not_yet_due",
    "not_applicable",
    "term_current",
    "term_expired",
    "none_found",
    "terminated",
    "claims_affected",
    "claims_current",
    "claims_upheld",
    "claims_amended",
    "claims_cancelled",
    "mixed",
    "active",
    "inactive",
    "revoked",
    "expired",
    "rejected",
    "unknown",
]

T = TypeVar("T")

_PATENT_ID_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{4,24}$")
_JURISDICTION_RE = re.compile(r"^[A-Z]{2}$")
_HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")
_ATTESTATION_DOMAIN = b"praviar:primary-legal-status-receipt:v2:"
_CANONICAL_ARTIFACT_SCHEMA_VERSION: Literal["primary-legal-status-canonical-artifact-v1"] = (
    "primary-legal-status-canonical-artifact-v1"
)
_OUTCOMES_BY_SCOPE: dict[str, frozenset[str]] = {
    "application_prosecution": frozenset({"patented", "pending", "abandoned", "unknown"}),
    "patent_term": frozenset({"term_current", "term_expired", "unknown"}),
    "patent_maintenance": frozenset(
        {
            "paid",
            "grace_period",
            "lapsed",
            "not_yet_due",
            "not_applicable",
            "unknown",
        }
    ),
    "post_grant_proceeding": frozenset(
        {"none_found", "pending", "terminated", "claims_affected", "unknown"}
    ),
    "current_claim_set": frozenset(
        {
            "claims_current",
            "claims_amended",
            "claims_cancelled",
            "mixed",
            "unknown",
        }
    ),
    "claim_adjudication": frozenset(
        {
            "claims_upheld",
            "claims_amended",
            "claims_cancelled",
            "mixed",
            "unknown",
        }
    ),
    "ep_central_proceeding": frozenset(
        {"active", "pending", "revoked", "lapsed", "expired", "unknown"}
    ),
    "ep_unitary_effect": frozenset({"active", "pending", "rejected", "lapsed", "unknown"}),
    "ep_national_post_grant": frozenset(
        {"active", "inactive", "pending", "revoked", "lapsed", "expired", "unknown"}
    ),
    "worldwide_legal_events": frozenset({"active", "inactive", "pending", "none_found", "unknown"}),
}
_PARSER_BY_SOURCE: dict[str, str] = {
    "uspto_odp_application": "uspto-odp-application-v1",
    "uspto_odp_ptab": "uspto-odp-ptab-v1",
    "uspto_maintenance_storefront": "supervised-uspto-maintenance-v1",
    "epo_ops_register": "epo-ops-register-v1",
    "epo_ops_legal": "epo-ops-legal-v1",
    "epo_federated_register": "supervised-federated-import-v1",
    "ep_national_register": "supervised-national-register-import-v1",
}
_RAW_OUTCOME_BY_SCOPE: dict[str, dict[str, str]] = {
    "application_prosecution": {
        "patented case": "patented",
        "pending": "pending",
        "abandoned": "abandoned",
    },
    "patent_term": {
        "current term": "term_current",
        "expired term": "term_expired",
    },
    "patent_maintenance": {
        "maintenance fee paid": "paid",
        "within maintenance-fee grace period": "grace_period",
        "expired for failure to pay maintenance fee": "lapsed",
        "first maintenance fee not yet due": "not_yet_due",
        "maintenance fees not applicable": "not_applicable",
    },
    "post_grant_proceeding": {
        "no proceeding found": "none_found",
        "proceeding pending": "pending",
        "proceeding terminated without claim change": "terminated",
        "proceeding affected claims": "claims_affected",
    },
    "current_claim_set": {
        "current issued claims verified": "claims_current",
        "issued claims amended": "claims_amended",
        "issued claims cancelled": "claims_cancelled",
        "mixed current claim dispositions": "mixed",
    },
    "claim_adjudication": {
        "claims upheld": "claims_upheld",
        "claims amended": "claims_amended",
        "claims cancelled": "claims_cancelled",
        "mixed claim dispositions": "mixed",
    },
    "ep_central_proceeding": {
        "active": "active",
        "pending": "pending",
        "revoked": "revoked",
        "lapsed": "lapsed",
        "expired": "expired",
    },
    "ep_unitary_effect": {
        "active": "active",
        "pending": "pending",
        "rejected": "rejected",
        "lapsed": "lapsed",
    },
    "ep_national_post_grant": {
        "patent in force": "active",
        "in force": "active",
        "inactive": "inactive",
        "pending": "pending",
        "revoked": "revoked",
        "lapsed": "lapsed",
        "expired": "expired",
    },
    "worldwide_legal_events": {
        "active": "active",
        "inactive": "inactive",
        "pending": "pending",
        "no event found": "none_found",
    },
}


@dataclass(frozen=True)
class _SourceProfile:
    host: str
    path_prefix: str
    authority_level: Literal["primary", "supplementary"]
    collection_modes: frozenset[str]
    scopes: frozenset[str]


_SOURCE_PROFILES: dict[str, _SourceProfile] = {
    "uspto_odp_application": _SourceProfile(
        host="api.uspto.gov",
        path_prefix="/api/v1/patent/applications",
        authority_level="primary",
        collection_modes=frozenset({"api"}),
        scopes=frozenset({"application_prosecution", "patent_term", "current_claim_set"}),
    ),
    "uspto_odp_ptab": _SourceProfile(
        host="api.uspto.gov",
        path_prefix="/api/v1/patent/trials",
        authority_level="primary",
        collection_modes=frozenset({"api"}),
        scopes=frozenset({"post_grant_proceeding", "claim_adjudication"}),
    ),
    "uspto_maintenance_storefront": _SourceProfile(
        host="fees.uspto.gov",
        path_prefix="/MaintenanceFees",
        authority_level="primary",
        collection_modes=frozenset({"supervised_manual"}),
        scopes=frozenset({"patent_maintenance"}),
    ),
    "epo_ops_register": _SourceProfile(
        host="ops.epo.org",
        path_prefix="/3.2/rest-services/register",
        authority_level="primary",
        collection_modes=frozenset({"api"}),
        scopes=frozenset({"ep_central_proceeding", "ep_unitary_effect"}),
    ),
    "epo_ops_legal": _SourceProfile(
        host="ops.epo.org",
        path_prefix="/3.2/rest-services/legal",
        authority_level="supplementary",
        collection_modes=frozenset({"api"}),
        scopes=frozenset({"worldwide_legal_events"}),
    ),
    "epo_federated_register": _SourceProfile(
        host="register.epo.org",
        path_prefix="/",
        authority_level="supplementary",
        collection_modes=frozenset({"supervised_manual"}),
        scopes=frozenset({"ep_national_post_grant"}),
    ),
}


class _CanonicalStatusArtifact(BaseModel):
    """Strict parsed representation for non-native or supervised source imports."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["primary-legal-status-canonical-artifact-v1"] = (
        _CANONICAL_ARTIFACT_SCHEMA_VERSION
    )
    source: LegalStatusSource
    evidence_scope: EvidenceScope
    source_record_identifier: str = Field(min_length=1, max_length=300)
    source_record_patent_number: str = Field(min_length=4, max_length=30)
    application_number: str = Field(default="", max_length=30)
    target_jurisdiction: str = Field(default="", max_length=2)
    raw_status: str = Field(min_length=1, max_length=1000)
    term_end_date: date | None = None
    term_basis_document_ids: list[str] = Field(default_factory=list, max_length=20)
    effective_claim_ids: list[str] = Field(default_factory=list, max_length=1000)
    current_claim_text_sha256: str = ""
    controlling_claim_document_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
    )
    affected_claim_ids: list[str] = Field(default_factory=list, max_length=1000)
    adjudication_document_id: str = Field(default="", max_length=300)


class _USPTOTermArtifact(BaseModel):
    """Exact ODP records required for a conservative statutory term replay."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["uspto-odp-patent-term-artifact-v1"] = (
        "uspto-odp-patent-term-artifact-v1"
    )
    application_record: dict[str, object]
    adjustment_response: dict[str, object]
    continuity_response: dict[str, object]
    documents_response: dict[str, object]
    status_as_of_date: date


class _USPTOPTABArtifact(BaseModel):
    """Exact query-bound ODP PTAB responses, including decision completeness."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["uspto-odp-ptab-artifact-v1"] = "uspto-odp-ptab-artifact-v1"
    proceedings_exchange: dict[str, object]
    decision_exchanges: dict[str, dict[str, object]] = Field(default_factory=dict)


class SupervisedMaintenanceImport(BaseModel):
    """Two-person canonical import of an official Maintenance Fees record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["uspto-maintenance-supervised-import-v1"] = (
        "uspto-maintenance-supervised-import-v1"
    )
    patent_number: str = Field(min_length=4, max_length=30)
    application_number: str = Field(min_length=8, max_length=30)
    source_record_identifier: str = Field(min_length=1, max_length=300)
    raw_status: Literal[
        "Maintenance fee paid",
        "Within maintenance-fee grace period",
        "Expired for failure to pay maintenance fee",
        "First maintenance fee not yet due",
        "Maintenance fees not applicable",
    ]
    storefront_observed_at: datetime
    official_statement_identifier: str = Field(min_length=1, max_length=300)
    official_statement_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    collector_user_id: str = Field(min_length=1, max_length=200)
    supervisor_user_id: str = Field(min_length=1, max_length=200)
    supervisor_role: Literal["attorney", "admin"]
    approved_at: datetime
    official_statement_base64: str = Field(min_length=4)

    @model_validator(mode="after")
    def _validate_supervision(self) -> SupervisedMaintenanceImport:
        if (
            self.storefront_observed_at.tzinfo is None
            or self.storefront_observed_at.utcoffset() is None
            or self.approved_at.tzinfo is None
            or self.approved_at.utcoffset() is None
        ):
            raise ValueError("maintenance import timestamps must be timezone-aware")
        if self.collector_user_id == self.supervisor_user_id:
            raise ValueError("maintenance import requires independent supervision")
        if self.approved_at < self.storefront_observed_at:
            raise ValueError("maintenance approval cannot predate collection")
        if self.approved_at - self.storefront_observed_at > timedelta(hours=4):
            raise ValueError("maintenance approval is too remote from collection")
        try:
            statement = base64.b64decode(
                self.official_statement_base64,
                validate=True,
            )
        except (ValueError, binascii.Error):
            raise ValueError("maintenance statement must be valid retained base64") from None
        if not statement or hashlib.sha256(statement).hexdigest() != (
            self.official_statement_sha256
        ):
            raise ValueError("maintenance statement digest does not match retained bytes")
        _normalise_application_number(self.application_number)
        return self


class PrimaryLegalStatusSetupReadiness(BaseModel):
    """Deployment capability snapshot for the five mandatory US status scopes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ready: bool
    signing_available: bool
    odp_collection_available: bool
    available_scopes: list[EvidenceScope]
    supervised_scopes: list[EvidenceScope]
    blocked_scopes: list[EvidenceScope]
    failure_reasons: list[str]


@dataclass(frozen=True)
class _ArtifactReplay:
    source_record_identifier: str
    source_record_patent_number: str
    application_number: str
    target_jurisdiction: str
    raw_status: str
    normalized_outcome: str
    parser_result: ParserResult
    term_end_date: date | None
    term_basis_document_ids: tuple[str, ...]
    effective_claim_ids: tuple[str, ...]
    current_claim_text_sha256: str
    controlling_claim_document_ids: tuple[str, ...]
    affected_claim_ids: tuple[str, ...]
    adjudication_document_id: str


def _odp_application_identity(
    application_record: dict[str, object],
) -> tuple[str, str, dict[str, object]]:
    metadata_value = application_record.get("applicationMetaData")
    if not isinstance(metadata_value, dict):
        raise ValueError("USPTO application artifact has no applicationMetaData record")
    metadata = {str(key): value for key, value in metadata_value.items()}
    top_level_application = str(application_record.get("applicationNumberText") or "")
    metadata_application = str(metadata.get("applicationNumberText") or "")
    application_number = _normalise_application_number(
        top_level_application or metadata_application
    )
    if (
        top_level_application
        and metadata_application
        and _normalise_application_number(top_level_application)
        != _normalise_application_number(metadata_application)
    ):
        raise ValueError("USPTO application artifact contains conflicting application numbers")
    patent_number = str(metadata.get("patentNumber") or "").strip()
    if not patent_number:
        raise ValueError("USPTO application artifact has no patent number")
    return application_number, patent_number, metadata


def _single_odp_record(
    response: dict[str, object],
    *,
    record_field: str,
    description: str,
) -> dict[str, object]:
    bag = response.get("patentFileWrapperDataBag")
    if isinstance(bag, list):
        if len(bag) != 1 or not isinstance(bag[0], dict):
            raise ValueError(f"{description} must contain exactly one ODP record")
        count = response.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count != 1:
            raise ValueError(f"{description} count does not prove completeness")
        return {str(key): value for key, value in bag[0].items()}
    if record_field in response:
        return response
    raise ValueError(f"{description} has no official record")


def _complete_response_records(
    response: dict[str, object],
    *,
    fields: tuple[str, ...],
    description: str,
) -> list[dict[str, object]]:
    raw_records: object = None
    for field in fields:
        if field in response:
            raw_records = response[field]
            break
    if raw_records is None:
        raw_records = []
    if not isinstance(raw_records, list) or any(not isinstance(item, dict) for item in raw_records):
        raise ValueError(f"{description} records are malformed")
    counts: list[int] = []
    for count_field in ("count", "totalNumFound", "totalHits"):
        if count_field not in response:
            continue
        count_value = response[count_field]
        if isinstance(count_value, bool) or not isinstance(count_value, int):
            raise ValueError(f"{description} completeness count is malformed")
        counts.append(count_value)
    if not counts:
        raise ValueError(f"{description} has no explicit completeness count")
    if any(count != len(raw_records) for count in counts):
        raise ValueError(f"{description} response is incomplete or paginated")
    if any(response.get(field) for field in ("next", "nextPage", "nextPageToken", "hasMore")):
        raise ValueError(f"{description} response declares another page")
    return [
        {str(key): value for key, value in cast("dict[object, object]", item).items()}
        for item in raw_records
    ]


def _continuity_parent_records(
    response: dict[str, object],
    *,
    application_number: str,
) -> list[dict[str, object]]:
    response_application = str(response.get("applicationNumberText") or "")
    if not response_application or (
        _normalise_application_number(response_application) != application_number
    ):
        raise ValueError("USPTO continuity response is for a different application")
    parents = response.get("parentContinuityBag", [])
    children = response.get("childContinuityBag", [])
    if (
        not isinstance(parents, list)
        or any(not isinstance(item, dict) for item in parents)
        or not isinstance(children, list)
        or any(not isinstance(item, dict) for item in children)
    ):
        raise ValueError("USPTO continuity response is malformed")
    return [cast("dict[str, object]", parent) for parent in parents]


def _required_iso_date(value: str, *, missing_message: str, malformed_message: str) -> date:
    if not value:
        raise ValueError(missing_message)
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        raise ValueError(malformed_message) from None


def _continuity_parent_filing_date(parent: dict[str, object]) -> date:
    relationship_code = (
        str(parent.get("claimParentageTypeCode") or parent.get("claimType") or "").strip().upper()
    )
    if relationship_code not in {"CON", "DIV", "CIP", "NST"}:
        raise ValueError("USPTO term replay cannot classify a continuity relationship")
    parent_application = str(
        parent.get("parentApplicationNumberText") or parent.get("parentApplicationNumber") or ""
    ).strip()
    if not parent_application:
        raise ValueError("USPTO continuity parent has no application number")
    parent_filing_value = str(parent.get("parentFilingDate") or parent.get("filingDate") or "")
    return _required_iso_date(
        parent_filing_value,
        missing_message="USPTO continuity parent filing date is missing",
        malformed_message="USPTO continuity parent filing date is malformed",
    )


def _term_effective_filing_date(
    response: dict[str, object],
    *,
    application_number: str,
    metadata: dict[str, object],
) -> date:
    parents = _continuity_parent_records(
        response,
        application_number=application_number,
    )
    filing_value = str(metadata.get("effectiveFilingDate") or metadata.get("filingDate") or "")
    effective_filing = _required_iso_date(
        filing_value,
        missing_message="USPTO application filing date is missing",
        malformed_message="USPTO application filing date is malformed",
    )
    for parent in parents:
        effective_filing = min(effective_filing, _continuity_parent_filing_date(parent))
    return effective_filing


def _require_response_application(
    response: dict[str, object],
    *,
    application_number: str,
    description: str,
) -> None:
    response_application = str(response.get("applicationNumberText") or "")
    if not response_application:
        bag = response.get("patentFileWrapperDataBag")
        if isinstance(bag, list) and len(bag) == 1 and isinstance(bag[0], dict):
            response_application = str(bag[0].get("applicationNumberText") or "")
    if (
        not response_application
        or _normalise_application_number(response_application) != application_number
    ):
        raise ValueError(f"{description} is not bound to the target application")


def _term_adjustment_days(
    response: dict[str, object],
    *,
    application_number: str,
) -> int:
    adjustment = _single_odp_record(
        response,
        record_field="patentTermAdjustmentData",
        description="USPTO adjustment response",
    )
    adjustment_application = _normalise_application_number(
        str(adjustment.get("applicationNumberText") or "")
    )
    if adjustment_application != application_number:
        raise ValueError("USPTO adjustment response is for a different application")
    adjustment_data = adjustment.get("patentTermAdjustmentData")
    if not isinstance(adjustment_data, dict):
        raise ValueError("USPTO adjustment response has no PTA data")
    adjustment_days = adjustment_data.get("adjustmentTotalQuantity")
    if (
        isinstance(adjustment_days, bool)
        or not isinstance(adjustment_days, int)
        or not 0 <= adjustment_days <= 10_000
    ):
        raise ValueError("USPTO adjustment total is not a valid day count")
    return adjustment_days


def _term_extension_days(metadata: dict[str, object]) -> int:
    pte_value = metadata.get(
        "patentTermExtensionDays",
        metadata.get("pteDays"),
    )
    if (
        isinstance(pte_value, bool)
        or not isinstance(pte_value, int)
        or not 0 <= pte_value <= 10_000
    ):
        raise ValueError("USPTO application record does not conclusively state PTE days")
    return pte_value


def _reject_terminal_disclaimer_documents(
    response: dict[str, object],
    *,
    application_number: str,
) -> None:
    _require_response_application(
        response,
        application_number=application_number,
        description="USPTO documents response",
    )
    documents = _complete_response_records(
        response,
        fields=("documentBag", "results"),
        description="USPTO documents response",
    )
    for document in documents:
        code = str(document.get("documentCode") or "").strip().upper()
        description = str(
            document.get("documentDescription") or document.get("documentDescriptionText") or ""
        ).casefold()
        if code == "DIST" or "terminal disclaimer" in description:
            raise ValueError(
                "terminal-disclaimer term needs the linked patent and exact linked expiry"
            )


def _term_artifact_replay(payload: dict[str, object]) -> _ArtifactReplay:
    try:
        artifact = _USPTOTermArtifact.model_validate(payload)
    except ValueError:
        raise ValueError("USPTO term artifact does not match its strict schema") from None
    application_number, patent_number, metadata = _odp_application_identity(
        artifact.application_record
    )
    application_type = (
        str(metadata.get("applicationTypeCode") or metadata.get("applicationTypeCategory") or "")
        .strip()
        .upper()
    )
    if application_type not in {"UTL", "UTILITY"}:
        raise ValueError("conclusive ODP term replay is limited to identified utility applications")

    adjustment_days = _term_adjustment_days(
        artifact.adjustment_response,
        application_number=application_number,
    )
    effective_filing_date = _term_effective_filing_date(
        artifact.continuity_response,
        application_number=application_number,
        metadata=metadata,
    )
    from praviar_pipeline.utils.patent_term_dates import (
        _safe_add_years,
        extract_grant_date,
    )

    if effective_filing_date < date(1995, 6, 8):
        raise ValueError("pre-URAA patent term needs a separate later-of-17-or-20-year analysis")
    if extract_grant_date(patent_number, metadata, artifact.application_record) is None:
        raise ValueError("USPTO term record has no official grant date")

    pte_value = _term_extension_days(metadata)
    _reject_terminal_disclaimer_documents(
        artifact.documents_response,
        application_number=application_number,
    )

    base_end = _safe_add_years(effective_filing_date, 20)
    term_end = base_end + timedelta(days=adjustment_days + pte_value)
    raw_status = "Current term" if term_end >= artifact.status_as_of_date else "Expired term"
    continuity_digest = hashlib.sha256(
        _canonical_artifact_bytes(artifact.continuity_response)
    ).hexdigest()
    basis_ids = (
        f"application:{application_number}",
        f"adjustment:{application_number}",
        f"continuity:{continuity_digest}",
    )
    return _ArtifactReplay(
        source_record_identifier=application_number,
        source_record_patent_number=patent_number,
        application_number=application_number,
        target_jurisdiction="",
        raw_status=raw_status,
        normalized_outcome=_RAW_OUTCOME_BY_SCOPE["patent_term"][raw_status.casefold()],
        parser_result="conclusive",
        term_end_date=term_end,
        term_basis_document_ids=basis_ids,
        effective_claim_ids=(),
        current_claim_text_sha256="",
        controlling_claim_document_ids=(),
        affected_claim_ids=(),
        adjudication_document_id="",
    )


def _record_patent_numbers(record: dict[str, object]) -> set[str]:
    fields = (
        "patentNumber",
        "patentNumberText",
        "respondentPatentNumber",
        "patentOwnerPatentNumber",
    )
    patent_numbers = {
        _publication_subject(str(record[field]), default_jurisdiction="US")
        for field in fields
        if str(record.get(field) or "").strip()
    }
    patent_owner = record.get("patentOwnerData")
    if isinstance(patent_owner, dict):
        patent_numbers.update(
            _publication_subject(str(patent_owner[field]), default_jurisdiction="US")
            for field in fields
            if str(patent_owner.get(field) or "").strip()
        )
    return patent_numbers


def _search_exchange(
    exchange: dict[str, object],
    *,
    expected_query: str,
    description: str,
) -> dict[str, object]:
    if set(exchange) != {"request", "response"}:
        raise ValueError(f"{description} exchange must retain request and response")
    request = exchange.get("request")
    response = exchange.get("response")
    if not isinstance(request, dict) or not isinstance(response, dict):
        raise ValueError(f"{description} exchange is malformed")
    if request.get("q") != expected_query:
        raise ValueError(f"{description} request is not bound to its subject")
    pagination = request.get("pagination")
    if (
        not isinstance(pagination, dict)
        or pagination.get("offset") != 0
        or isinstance(pagination.get("limit"), bool)
        or not isinstance(pagination.get("limit"), int)
        or cast("int", pagination["limit"]) < 1
    ):
        raise ValueError(f"{description} request has no complete first page")
    normalized_response = {str(key): value for key, value in response.items()}
    totals = [
        normalized_response[field]
        for field in ("count", "totalNumFound", "totalHits")
        if field in normalized_response
    ]
    if any(
        isinstance(total, bool)
        or not isinstance(total, int)
        or total > cast("int", pagination["limit"])
        for total in totals
    ):
        raise ValueError(f"{description} request limit does not cover the result set")
    return normalized_response


def _ptab_artifact_replay(payload: dict[str, object]) -> _ArtifactReplay:
    try:
        artifact = _USPTOPTABArtifact.model_validate(payload)
    except ValueError:
        raise ValueError("USPTO PTAB artifact does not match its strict schema") from None
    request_value = artifact.proceedings_exchange.get("request")
    if not isinstance(request_value, dict):
        raise ValueError("USPTO PTAB proceedings request is missing")
    query_value = str(request_value.get("q") or "")
    query_prefix = "patentOwnerData.patentNumber:"
    if not query_value.startswith(query_prefix):
        raise ValueError("USPTO PTAB proceedings request has no patent query")
    query_patent_number = query_value.removeprefix(query_prefix)
    query_subject = _publication_subject(
        query_patent_number,
        default_jurisdiction="US",
    )
    proceedings_response = _search_exchange(
        artifact.proceedings_exchange,
        expected_query=f"{query_prefix}{query_patent_number}",
        description="USPTO PTAB proceedings",
    )
    proceedings = _complete_response_records(
        proceedings_response,
        fields=("patentTrialProceedingDataBag", "results", "hits"),
        description="USPTO PTAB proceedings response",
    )
    pending_statuses = frozenset({"active", "filed", "instituted", "pending"})
    for proceeding in proceedings:
        record_subjects = _record_patent_numbers(proceeding)
        if record_subjects != {query_subject}:
            raise ValueError("PTAB proceeding does not bind exactly to the query patent")
        trial_number = str(proceeding.get("trialNumber") or "").strip()
        if not trial_number:
            raise ValueError("PTAB proceeding has no trial number")
        trial_metadata = proceeding.get("trialMetaData")
        if not isinstance(trial_metadata, dict):
            raise ValueError("PTAB proceeding has no trial metadata")
        status = str(trial_metadata.get("trialStatusCategory") or "").strip()
        if not status:
            raise ValueError("PTAB proceeding has no status")
        if status.casefold() not in pending_statuses:
            raise ValueError(
                "completed PTAB claim effect requires exact controlling decision/certificate text"
            )

    raw_status = "No proceeding found" if not proceedings else "Proceeding pending"
    response_digest = hashlib.sha256(_canonical_artifact_bytes(proceedings_response)).hexdigest()
    return _ArtifactReplay(
        source_record_identifier=f"{query_subject}:{response_digest}",
        source_record_patent_number=query_patent_number,
        application_number="",
        target_jurisdiction="",
        raw_status=raw_status,
        normalized_outcome=_RAW_OUTCOME_BY_SCOPE["post_grant_proceeding"][raw_status.casefold()],
        parser_result="conclusive",
        term_end_date=None,
        term_basis_document_ids=(),
        effective_claim_ids=(),
        current_claim_text_sha256="",
        controlling_claim_document_ids=(),
        affected_claim_ids=(),
        adjudication_document_id="",
    )


def _maintenance_artifact_replay(payload: dict[str, object]) -> _ArtifactReplay:
    try:
        artifact = SupervisedMaintenanceImport.model_validate(payload)
    except ValueError:
        raise ValueError(
            "USPTO maintenance artifact does not match its supervised schema"
        ) from None
    return _ArtifactReplay(
        source_record_identifier=artifact.source_record_identifier,
        source_record_patent_number=artifact.patent_number,
        application_number=_normalise_application_number(artifact.application_number),
        target_jurisdiction="",
        raw_status=artifact.raw_status,
        normalized_outcome=_RAW_OUTCOME_BY_SCOPE["patent_maintenance"][
            artifact.raw_status.casefold()
        ],
        parser_result="conclusive",
        term_end_date=None,
        term_basis_document_ids=(),
        effective_claim_ids=(),
        current_claim_text_sha256="",
        controlling_claim_document_ids=(),
        affected_claim_ids=(),
        adjudication_document_id="",
    )


def _canonical_artifact_bytes(payload: dict[str, object]) -> bytes:
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise ValueError("legal-status artifact is not canonical JSON") from None


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _decode_artifact(artifact: bytes) -> tuple[dict[str, object], bytes]:
    if not artifact:
        raise ValueError("legal-status artifact is empty")
    try:
        decoded = artifact.decode("utf-8")
        payload = json.loads(
            decoded,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ValueError("legal-status artifact must be valid UTF-8 JSON") from None
    if not isinstance(payload, dict):
        raise ValueError("legal-status artifact must be a JSON object")
    canonical_payload = {str(key): value for key, value in payload.items()}
    canonical_bytes = _canonical_artifact_bytes(canonical_payload)
    if len(canonical_bytes) > 100 * 1024 * 1024:
        raise ValueError("legal-status artifact exceeds the retained-artifact limit")
    return canonical_payload, canonical_bytes


def _normalise_application_number(value: str) -> str:
    normalized = re.sub(r"[^0-9]", "", str(value or ""))
    if re.fullmatch(r"\d{8}", normalized) is None:
        raise ValueError("USPTO application number must contain exactly 8 digits")
    return normalized


def _publication_subject(value: str, *, default_jurisdiction: str = "") -> str:
    normalized = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    if default_jurisdiction and not normalized.startswith(default_jurisdiction):
        normalized = f"{default_jurisdiction}{normalized}"
    return re.sub(r"[A-Z]\d?$", "", normalized)


def _replay_artifact_payload(
    *,
    source: LegalStatusSource,
    evidence_scope: EvidenceScope,
    payload: dict[str, object],
) -> _ArtifactReplay:
    """Derive every semantic receipt field from the retained source artifact."""
    schema_version = payload.get("schema_version")
    artifact_contract = (source, evidence_scope, schema_version)
    if artifact_contract == (
        "uspto_odp_application",
        "patent_term",
        "uspto-odp-patent-term-artifact-v1",
    ):
        return _term_artifact_replay(payload)
    if artifact_contract == (
        "uspto_odp_ptab",
        "post_grant_proceeding",
        "uspto-odp-ptab-artifact-v1",
    ):
        return _ptab_artifact_replay(payload)
    if artifact_contract == (
        "uspto_maintenance_storefront",
        "patent_maintenance",
        "uspto-maintenance-supervised-import-v1",
    ):
        return _maintenance_artifact_replay(payload)
    if artifact_contract == (
        "uspto_odp_application",
        "application_prosecution",
        None,
    ):
        application_number, source_record_patent_number, metadata = _odp_application_identity(
            payload
        )
        raw_status = str(metadata.get("applicationStatusDescriptionText") or "").strip()
        if not raw_status:
            raise ValueError("USPTO application artifact has no application status")
        outcome = _RAW_OUTCOME_BY_SCOPE[evidence_scope].get(raw_status.casefold())
        return _ArtifactReplay(
            source_record_identifier=application_number,
            source_record_patent_number=source_record_patent_number,
            application_number=application_number,
            target_jurisdiction="",
            raw_status=raw_status,
            normalized_outcome=outcome or "unknown",
            parser_result="conclusive" if outcome else "inconclusive",
            term_end_date=None,
            term_basis_document_ids=(),
            effective_claim_ids=(),
            current_claim_text_sha256="",
            controlling_claim_document_ids=(),
            affected_claim_ids=(),
            adjudication_document_id="",
        )

    try:
        canonical = _CanonicalStatusArtifact.model_validate(payload)
    except ValueError:
        raise ValueError(
            "legal-status artifact does not match the strict canonical schema"
        ) from None
    if canonical.source != source or canonical.evidence_scope != evidence_scope:
        raise ValueError("legal-status artifact source or scope does not match")
    outcome = _RAW_OUTCOME_BY_SCOPE[evidence_scope].get(canonical.raw_status.strip().casefold())
    return _ArtifactReplay(
        source_record_identifier=canonical.source_record_identifier,
        source_record_patent_number=canonical.source_record_patent_number,
        application_number=canonical.application_number,
        target_jurisdiction=canonical.target_jurisdiction,
        raw_status=canonical.raw_status,
        normalized_outcome=outcome or "unknown",
        parser_result="conclusive" if outcome else "inconclusive",
        term_end_date=canonical.term_end_date,
        term_basis_document_ids=tuple(canonical.term_basis_document_ids),
        effective_claim_ids=tuple(canonical.effective_claim_ids),
        current_claim_text_sha256=canonical.current_claim_text_sha256,
        controlling_claim_document_ids=tuple(canonical.controlling_claim_document_ids),
        affected_claim_ids=tuple(canonical.affected_claim_ids),
        adjudication_document_id=canonical.adjudication_document_id,
    )


class NationalRegisterAuthority(BaseModel):
    """Pinned national-office host definition discovered from an official source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    jurisdiction: str = Field(pattern=r"^[A-Z]{2}$")
    authority_name: str = Field(min_length=2, max_length=200)
    allowed_hosts: list[str] = Field(min_length=1, max_length=8)
    verified_from_url: str = Field(min_length=12, max_length=2000)
    verified_at: datetime

    @model_validator(mode="after")
    def _validate_authority(self) -> NationalRegisterAuthority:
        hosts = [host.strip().lower().rstrip(".") for host in self.allowed_hosts]
        if len(hosts) != len(set(hosts)) or any(not host or "/" in host for host in hosts):
            raise ValueError("national-register hosts must be unique DNS hostnames")
        source = urlparse(self.verified_from_url)
        if source.scheme != "https" or source.hostname not in {
            "www.epo.org",
            "register.epo.org",
        }:
            raise ValueError("national-register authority must be pinned from an EPO source")
        object.__setattr__(self, "allowed_hosts", hosts)
        return self


class PrimaryLegalStatusReceipt(BaseModel):
    """Server-attested receipt for one retained official-source artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["primary-legal-status-receipt-v2"] = "primary-legal-status-receipt-v2"
    patent_id: str = Field(min_length=6, max_length=30)
    source: LegalStatusSource
    evidence_scope: EvidenceScope
    authority_level: Literal["primary", "supplementary"]
    collection_mode: Literal["api", "supervised_manual"]
    source_url: str = Field(min_length=12, max_length=2000)
    target_jurisdiction: str = ""
    collected_at: datetime
    source_record_updated_at: datetime | None = None
    source_record_identifier: str = Field(min_length=1, max_length=300)
    source_record_patent_number: str = Field(min_length=4, max_length=30)
    application_number: str = Field(default="", max_length=30)
    raw_status: str = Field(min_length=1, max_length=1000)
    normalized_outcome: NormalizedLegalStatusOutcome
    parser_result: ParserResult
    term_end_date: date | None = None
    term_basis_document_ids: list[str] = Field(default_factory=list, max_length=20)
    effective_claim_ids: list[str] = Field(default_factory=list, max_length=1000)
    current_claim_text_sha256: str = ""
    controlling_claim_document_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
    )
    affected_claim_ids: list[str] = Field(default_factory=list, max_length=1000)
    adjudication_document_id: str = Field(default="", max_length=300)
    artifact_media_type: str = Field(min_length=3, max_length=200)
    artifact_locator: str = Field(min_length=12, max_length=2200)
    artifact_size_bytes: int = Field(ge=1, le=100 * 1024 * 1024)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_payload: dict[str, object]
    parser_identity: str = Field(min_length=3, max_length=200)
    limitations: list[str] = Field(min_length=1, max_length=20)
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    attestation_key_id: str = Field(min_length=1, max_length=100)
    attestation_hmac_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _validate_contract(self) -> PrimaryLegalStatusReceipt:
        _validate_receipt_identity_and_freshness(self)
        _validate_receipt_source(self)
        replay = _validate_retained_artifact(self)
        _validate_artifact_timestamps(self)
        _validate_replayed_receipt_semantics(self, replay)
        _validate_claim_adjudication_fields(self)
        _validate_parser_contract(self)
        _validate_term_fields(self)
        _validate_current_claim_fields(self)
        if len(self.limitations) != len(set(self.limitations)):
            raise ValueError("limitations must be unique")
        return self


def _validate_receipt_identity_and_freshness(receipt: PrimaryLegalStatusReceipt) -> None:
    patent_id = re.sub(r"[^A-Z0-9]", "", receipt.patent_id.upper())
    if not _PATENT_ID_RE.fullmatch(patent_id):
        raise ValueError("patent_id must be a canonical publication identifier")
    object.__setattr__(receipt, "patent_id", patent_id)
    if receipt.collected_at.tzinfo is None or receipt.collected_at.utcoffset() is None:
        raise ValueError("collected_at must be timezone-aware")
    if receipt.source_record_updated_at is not None and (
        receipt.source_record_updated_at.tzinfo is None
        or receipt.source_record_updated_at.utcoffset() is None
    ):
        raise ValueError("source_record_updated_at must be timezone-aware")
    if receipt.source_record_updated_at is not None and receipt.source_record_updated_at.astimezone(
        UTC
    ) > receipt.collected_at.astimezone(UTC):
        raise ValueError("source record cannot be newer than its collection")


def _validate_national_register_source(receipt: PrimaryLegalStatusReceipt) -> None:
    if not _JURISDICTION_RE.fullmatch(receipt.target_jurisdiction):
        raise ValueError("national-register evidence requires a target jurisdiction")
    if receipt.evidence_scope != "ep_national_post_grant":
        raise ValueError("national-register evidence has national post-grant scope only")
    if receipt.authority_level != "primary":
        raise ValueError("a verified national authority has primary authority level")


def _validate_application_source_binding(
    receipt: PrimaryLegalStatusReceipt,
    *,
    source_path: str,
) -> None:
    application_number = _normalise_application_number(receipt.application_number)
    if receipt.source_record_identifier != application_number:
        raise ValueError("USPTO source record identifier must be the application number")
    path_parts = [part for part in source_path.split("/") if part]
    try:
        application_index = path_parts.index("applications") + 1
        endpoint_application_number = _normalise_application_number(path_parts[application_index])
    except (ValueError, IndexError):
        raise ValueError("USPTO source URL does not bind an application number") from None
    if endpoint_application_number != application_number:
        raise ValueError("USPTO source URL application does not match the source record")
    object.__setattr__(receipt, "application_number", application_number)


def _validate_profile_source(receipt: PrimaryLegalStatusReceipt) -> None:
    profile = _SOURCE_PROFILES[receipt.source]
    if receipt.authority_level != profile.authority_level:
        raise ValueError("authority level does not match the official source profile")
    if receipt.collection_mode not in profile.collection_modes:
        raise ValueError("collection mode does not match the official source profile")
    if receipt.evidence_scope not in profile.scopes:
        raise ValueError("evidence scope exceeds the official source profile")
    parsed = urlparse(receipt.source_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != profile.host
        or not parsed.path.startswith(profile.path_prefix)
    ):
        raise ValueError("source URL does not match the official endpoint contract")
    if receipt.evidence_scope == "patent_term" and not parsed.path.endswith("/adjustment"):
        raise ValueError("patent-term evidence requires the ODP adjustment endpoint")
    if receipt.evidence_scope == "current_claim_set" and not parsed.path.endswith("/documents"):
        raise ValueError("current-claim evidence requires the ODP documents endpoint")
    if receipt.evidence_scope == "post_grant_proceeding" and not parsed.path.endswith(
        "/proceedings/search"
    ):
        raise ValueError("post-grant evidence requires the ODP proceedings search endpoint")
    if receipt.source == "uspto_odp_application":
        _validate_application_source_binding(receipt, source_path=parsed.path)


def _validate_receipt_source(receipt: PrimaryLegalStatusReceipt) -> None:
    if receipt.source == "ep_national_register":
        _validate_national_register_source(receipt)
    else:
        _validate_profile_source(receipt)


def _validate_retained_artifact(receipt: PrimaryLegalStatusReceipt) -> _ArtifactReplay:
    if receipt.artifact_media_type != "application/json":
        raise ValueError("legal-status receipts require a retained canonical JSON artifact")
    canonical_artifact = _canonical_artifact_bytes(receipt.artifact_payload)
    if len(canonical_artifact) != receipt.artifact_size_bytes:
        raise ValueError("legal-status retained artifact size mismatch")
    replayed_artifact_sha256 = hashlib.sha256(canonical_artifact).hexdigest()
    if replayed_artifact_sha256 != receipt.artifact_sha256:
        raise ValueError("legal-status retained artifact digest mismatch")
    locator_base, locator_separator, locator_fragment = receipt.artifact_locator.partition("#")
    if locator_base != receipt.source_url or not locator_separator:
        raise ValueError("legal-status artifact locator does not bind the official source URL")
    try:
        locator_hashes = [
            value
            for key, value in parse_qsl(
                locator_fragment,
                keep_blank_values=True,
                strict_parsing=True,
            )
            if key == "sha256"
        ]
    except ValueError:
        raise ValueError("legal-status artifact locator fragment is malformed") from None
    if locator_hashes != [receipt.artifact_sha256]:
        raise ValueError("legal-status artifact locator does not bind the retained digest")
    return _replay_artifact_payload(
        source=receipt.source,
        evidence_scope=receipt.evidence_scope,
        payload=receipt.artifact_payload,
    )


def _validate_artifact_timestamps(receipt: PrimaryLegalStatusReceipt) -> None:
    artifact_schema = receipt.artifact_payload.get("schema_version")
    if artifact_schema == "uspto-odp-patent-term-artifact-v1":
        term_artifact = _USPTOTermArtifact.model_validate(receipt.artifact_payload)
        if term_artifact.status_as_of_date != receipt.collected_at.astimezone(UTC).date():
            raise ValueError("term status date must equal the receipt collection date")
    if artifact_schema == "uspto-maintenance-supervised-import-v1":
        maintenance_artifact = SupervisedMaintenanceImport.model_validate(receipt.artifact_payload)
        if maintenance_artifact.approved_at.astimezone(UTC) != receipt.collected_at.astimezone(UTC):
            raise ValueError("maintenance approval must equal the receipt collection time")
        if (
            receipt.source_record_updated_at is None
            or maintenance_artifact.storefront_observed_at.astimezone(UTC)
            != receipt.source_record_updated_at.astimezone(UTC)
        ):
            raise ValueError("maintenance source freshness must equal Storefront observation")


def _validate_replayed_receipt_semantics(
    receipt: PrimaryLegalStatusReceipt,
    replay: _ArtifactReplay,
) -> None:
    expected_subject = _publication_subject(
        receipt.patent_id,
        default_jurisdiction=receipt.patent_id[:2],
    )
    replay_subject = _publication_subject(
        replay.source_record_patent_number,
        default_jurisdiction=receipt.patent_id[:2],
    )
    if replay_subject != expected_subject:
        raise ValueError("retained source record does not identify the receipt patent")
    if (
        receipt.source_record_patent_number != replay.source_record_patent_number
        or receipt.source_record_identifier != replay.source_record_identifier
        or receipt.application_number != replay.application_number
        or receipt.target_jurisdiction != replay.target_jurisdiction
        or receipt.raw_status != replay.raw_status
        or receipt.normalized_outcome != replay.normalized_outcome
        or receipt.parser_result != replay.parser_result
        or receipt.term_end_date != replay.term_end_date
        or tuple(receipt.term_basis_document_ids) != replay.term_basis_document_ids
        or tuple(receipt.effective_claim_ids) != replay.effective_claim_ids
        or receipt.current_claim_text_sha256 != replay.current_claim_text_sha256
        or tuple(receipt.controlling_claim_document_ids) != replay.controlling_claim_document_ids
        or tuple(receipt.affected_claim_ids) != replay.affected_claim_ids
        or receipt.adjudication_document_id != replay.adjudication_document_id
    ):
        raise ValueError("receipt semantics do not replay from the retained source artifact")


def _validate_claim_adjudication_fields(receipt: PrimaryLegalStatusReceipt) -> None:
    if receipt.evidence_scope == "claim_adjudication":
        if not receipt.affected_claim_ids or not receipt.adjudication_document_id:
            raise ValueError("claim adjudication requires affected claims and an official decision")
    elif receipt.affected_claim_ids:
        raise ValueError("only claim-adjudication evidence may identify affected claims")


def _validate_parser_contract(receipt: PrimaryLegalStatusReceipt) -> None:
    if receipt.normalized_outcome not in _OUTCOMES_BY_SCOPE[receipt.evidence_scope]:
        raise ValueError("normalized outcome is invalid for the evidence scope")
    if receipt.parser_result == "conclusive" and receipt.normalized_outcome == "unknown":
        raise ValueError("a conclusive parser result cannot have an unknown outcome")
    if receipt.parser_result != "conclusive" and receipt.normalized_outcome != "unknown":
        raise ValueError("an inconclusive or failed parser must have an unknown outcome")
    if receipt.parser_identity != _PARSER_BY_SOURCE[receipt.source]:
        raise ValueError("parser identity is not approved for the official source")
    if receipt.parser_result == "conclusive":
        replayed_outcome = _RAW_OUTCOME_BY_SCOPE[receipt.evidence_scope].get(
            receipt.raw_status.strip().casefold()
        )
        if replayed_outcome != receipt.normalized_outcome:
            raise ValueError("normalized outcome does not match deterministic parser replay")


def _validate_term_fields(receipt: PrimaryLegalStatusReceipt) -> None:
    if receipt.evidence_scope == "patent_term":
        if receipt.term_end_date is None or not receipt.term_basis_document_ids:
            raise ValueError("patent-term evidence requires a term end date and basis documents")
    elif receipt.term_end_date is not None or receipt.term_basis_document_ids:
        raise ValueError("term fields are valid only for patent-term evidence")


def _validate_current_claim_fields(receipt: PrimaryLegalStatusReceipt) -> None:
    if receipt.evidence_scope == "current_claim_set":
        if (
            not receipt.effective_claim_ids
            or not _HEX_64_RE.fullmatch(receipt.current_claim_text_sha256)
            or not receipt.controlling_claim_document_ids
        ):
            raise ValueError(
                "current-claim evidence requires an inventory, text digest, "
                "and controlling documents"
            )
    elif (
        receipt.effective_claim_ids
        or receipt.current_claim_text_sha256
        or receipt.controlling_claim_document_ids
    ):
        raise ValueError("current-claim fields are valid only for current-claim-set evidence")


class PrimaryLegalStatusRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    patent_id: str
    evidence_scope: EvidenceScope
    target_jurisdiction: str = ""
    max_collection_age_hours: int = Field(default=72, ge=24, le=72)


class PrimaryLegalStatusCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    satisfied: bool
    satisfied_requirement_count: int = Field(ge=0)
    required_requirement_count: int = Field(ge=0)
    failure_reasons: list[str]


class PrimaryLegalStatusResolution(BaseModel):
    """Coverage result plus the exact verified winner for each requirement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    coverage: PrimaryLegalStatusCoverage
    selected_receipts: list[PrimaryLegalStatusReceipt]


def _canonical_payload(receipt: PrimaryLegalStatusReceipt) -> bytes:
    payload = receipt.model_dump(
        mode="json",
        exclude={"receipt_sha256", "attestation_hmac_sha256"},
    )
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()


def _normalise_patent_id(value: str) -> str:
    normalised = re.sub(r"[^A-Z0-9]", "", value.upper())
    if not _PATENT_ID_RE.fullmatch(normalised):
        raise ValueError("patent_id must be a canonical publication identifier")
    return normalised


def _validate_collection_times(
    collected_at: datetime,
    source_record_updated_at: datetime | None,
) -> None:
    if collected_at.tzinfo is None or collected_at.utcoffset() is None:
        raise ValueError("collected_at must be timezone-aware")
    if source_record_updated_at is not None and (
        source_record_updated_at.tzinfo is None or source_record_updated_at.utcoffset() is None
    ):
        raise ValueError("source_record_updated_at must be timezone-aware")
    if source_record_updated_at is not None and source_record_updated_at.astimezone(
        UTC
    ) > collected_at.astimezone(UTC):
        raise ValueError("source record cannot be newer than its collection")


def _receipt_authority_level(
    *,
    source: LegalStatusSource,
    source_url: str,
    target_jurisdiction: str,
    national_authority: NationalRegisterAuthority | None,
) -> Literal["primary", "supplementary"]:
    parsed = urlparse(source_url)
    if source != "ep_national_register":
        return _SOURCE_PROFILES[source].authority_level
    if national_authority is None:
        raise ValueError("national-register evidence requires a pinned authority")
    if target_jurisdiction != national_authority.jurisdiction:
        raise ValueError("national-register jurisdiction does not match its authority")
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() not in national_authority.allowed_hosts
    ):
        raise ValueError("national-register URL is not a pinned official authority host")
    return "primary"


def _value_or_default(value: T | None, default: T) -> T:
    return default if value is None else value


def _text_or_default(value: str | None, default: str) -> str:
    return value or default


def _utc_or_none(value: datetime | None) -> datetime | None:
    return value.astimezone(UTC) if value is not None else None


def build_primary_legal_status_receipt(
    *,
    patent_id: str,
    source: LegalStatusSource,
    evidence_scope: EvidenceScope,
    collection_mode: Literal["api", "supervised_manual"],
    source_url: str,
    collected_at: datetime,
    artifact: bytes,
    artifact_media_type: str,
    limitations: list[str],
    attestation_key_id: str,
    attestation_key: bytes,
    source_record_identifier: str | None = None,
    raw_status: str | None = None,
    normalized_outcome: NormalizedLegalStatusOutcome | None = None,
    parser_result: ParserResult | None = None,
    parser_identity: str | None = None,
    application_number: str | None = None,
    source_record_updated_at: datetime | None = None,
    target_jurisdiction: str = "",
    affected_claim_ids: list[str] | None = None,
    adjudication_document_id: str = "",
    term_end_date: date | None = None,
    term_basis_document_ids: list[str] | None = None,
    effective_claim_ids: list[str] | None = None,
    current_claim_text_sha256: str = "",
    controlling_claim_document_ids: list[str] | None = None,
    national_authority: NationalRegisterAuthority | None = None,
) -> PrimaryLegalStatusReceipt:
    """Replay a retained source artifact and issue a content-bound receipt."""
    _validate_collection_times(collected_at, source_record_updated_at)
    authority_level = _receipt_authority_level(
        source=source,
        source_url=source_url,
        target_jurisdiction=target_jurisdiction,
        national_authority=national_authority,
    )
    if not attestation_key_id or len(attestation_key) < 32:
        raise ValueError("legal-status receipt attestation is required")
    artifact_payload, canonical_artifact = _decode_artifact(artifact)
    replay = _replay_artifact_payload(
        source=source,
        evidence_scope=evidence_scope,
        payload=artifact_payload,
    )
    artifact_sha256 = hashlib.sha256(canonical_artifact).hexdigest()
    draft = PrimaryLegalStatusReceipt.model_construct(
        patent_id=_normalise_patent_id(patent_id),
        source=source,
        evidence_scope=evidence_scope,
        authority_level=authority_level,
        collection_mode=collection_mode,
        source_url=source_url,
        target_jurisdiction=_text_or_default(target_jurisdiction, replay.target_jurisdiction),
        collected_at=collected_at.astimezone(UTC),
        source_record_updated_at=_utc_or_none(source_record_updated_at),
        source_record_identifier=_value_or_default(
            source_record_identifier,
            replay.source_record_identifier,
        ),
        source_record_patent_number=replay.source_record_patent_number,
        application_number=_value_or_default(application_number, replay.application_number),
        raw_status=_value_or_default(raw_status, replay.raw_status),
        normalized_outcome=_value_or_default(normalized_outcome, replay.normalized_outcome),
        parser_result=_value_or_default(parser_result, replay.parser_result),
        term_end_date=_value_or_default(term_end_date, replay.term_end_date),
        term_basis_document_ids=_value_or_default(
            term_basis_document_ids,
            list(replay.term_basis_document_ids),
        ),
        effective_claim_ids=_value_or_default(
            effective_claim_ids,
            list(replay.effective_claim_ids),
        ),
        current_claim_text_sha256=_text_or_default(
            current_claim_text_sha256,
            replay.current_claim_text_sha256,
        ),
        controlling_claim_document_ids=_value_or_default(
            controlling_claim_document_ids,
            list(replay.controlling_claim_document_ids),
        ),
        affected_claim_ids=_value_or_default(
            affected_claim_ids,
            list(replay.affected_claim_ids),
        ),
        adjudication_document_id=_text_or_default(
            adjudication_document_id,
            replay.adjudication_document_id,
        ),
        artifact_media_type=artifact_media_type,
        artifact_locator=f"{source_url}#sha256={artifact_sha256}",
        artifact_size_bytes=len(canonical_artifact),
        artifact_sha256=artifact_sha256,
        artifact_payload=artifact_payload,
        parser_identity=_text_or_default(parser_identity, _PARSER_BY_SOURCE[source]),
        limitations=limitations,
        receipt_sha256="0" * 64,
        attestation_key_id=attestation_key_id,
        attestation_hmac_sha256="0" * 64,
    )
    receipt_sha256 = hashlib.sha256(_canonical_payload(draft)).hexdigest()
    signature = hmac.new(
        attestation_key,
        _ATTESTATION_DOMAIN + receipt_sha256.encode(),
        hashlib.sha256,
    ).hexdigest()
    return PrimaryLegalStatusReceipt.model_validate(
        {
            **draft.model_dump(mode="python"),
            "receipt_sha256": receipt_sha256,
            "attestation_hmac_sha256": signature,
        }
    )


def issue_uspto_odp_application_status_receipt(
    *,
    patent_id: str,
    application_data: dict[str, object],
    collected_at: datetime,
    attestation_key_id: str,
    attestation_key: bytes,
) -> PrimaryLegalStatusReceipt:
    """Issue an application-status receipt from an exact ODP collector record."""
    application_number = _normalise_application_number(
        str(application_data.get("applicationNumberText") or "")
    )
    source_url = f"https://api.uspto.gov/api/v1/patent/applications/{application_number}"
    return build_primary_legal_status_receipt(
        patent_id=patent_id,
        source="uspto_odp_application",
        evidence_scope="application_prosecution",
        collection_mode="api",
        source_url=source_url,
        collected_at=collected_at,
        artifact=_canonical_artifact_bytes(application_data),
        artifact_media_type="application/json",
        limitations=["Application status does not itself establish issued-claim enforceability."],
        attestation_key_id=attestation_key_id,
        attestation_key=attestation_key,
    )


def issue_uspto_odp_patent_term_receipt(
    *,
    patent_id: str,
    application_record: dict[str, object],
    adjustment_response: dict[str, object],
    continuity_response: dict[str, object],
    documents_response: dict[str, object],
    collected_at: datetime,
    attestation_key_id: str,
    attestation_key: bytes,
) -> PrimaryLegalStatusReceipt:
    """Issue only when exact ODP records replay a conservative final term.

    The replay rejects pre-URAA terms, non-utility patents, absent PTE fields,
    and any terminal-disclaimer record. Those cases need additional exact
    controlling evidence rather than a guessed expiration date.
    """
    application_number, _patent_number, _metadata = _odp_application_identity(application_record)
    artifact = _USPTOTermArtifact(
        application_record=application_record,
        adjustment_response=adjustment_response,
        continuity_response=continuity_response,
        documents_response=documents_response,
        status_as_of_date=collected_at.astimezone(UTC).date(),
    )
    return build_primary_legal_status_receipt(
        patent_id=patent_id,
        source="uspto_odp_application",
        evidence_scope="patent_term",
        collection_mode="api",
        source_url=(
            f"https://api.uspto.gov/api/v1/patent/applications/{application_number}/adjustment"
        ),
        collected_at=collected_at,
        artifact=_canonical_artifact_bytes(artifact.model_dump(mode="json")),
        artifact_media_type="application/json",
        limitations=[
            "Conclusive only for post-URAA utility records with explicit PTE days "
            "and no terminal-disclaimer document."
        ],
        attestation_key_id=attestation_key_id,
        attestation_key=attestation_key,
    )


def issue_uspto_odp_ptab_status_receipt(
    *,
    patent_id: str,
    proceedings_exchange: dict[str, object],
    decision_exchanges: dict[str, dict[str, object]],
    collected_at: datetime,
    attestation_key_id: str,
    attestation_key: bytes,
) -> PrimaryLegalStatusReceipt:
    """Issue complete negative or exact pending PTAB status receipts."""
    artifact = _USPTOPTABArtifact(
        proceedings_exchange=proceedings_exchange,
        decision_exchanges=decision_exchanges,
    )
    return build_primary_legal_status_receipt(
        patent_id=patent_id,
        source="uspto_odp_ptab",
        evidence_scope="post_grant_proceeding",
        collection_mode="api",
        source_url=("https://api.uspto.gov/api/v1/patent/trials/proceedings/search"),
        collected_at=collected_at,
        artifact=_canonical_artifact_bytes(artifact.model_dump(mode="json")),
        artifact_media_type="application/json",
        limitations=[
            "Complete outcomes are withheld until exact controlling "
            "decision/certificate text is retained."
        ],
        attestation_key_id=attestation_key_id,
        attestation_key=attestation_key,
    )


def issue_supervised_uspto_maintenance_receipt(
    *,
    maintenance_import: SupervisedMaintenanceImport,
    collected_at: datetime,
    attestation_key_id: str,
    attestation_key: bytes,
) -> PrimaryLegalStatusReceipt:
    """Issue a two-person-reviewed canonical Storefront import."""
    if collected_at.astimezone(UTC) != maintenance_import.approved_at.astimezone(UTC):
        raise ValueError("maintenance receipt collection time must equal approval time")
    return build_primary_legal_status_receipt(
        patent_id=maintenance_import.patent_number,
        source="uspto_maintenance_storefront",
        evidence_scope="patent_maintenance",
        collection_mode="supervised_manual",
        source_url="https://fees.uspto.gov/MaintenanceFees",
        collected_at=collected_at,
        source_record_updated_at=maintenance_import.storefront_observed_at,
        artifact=_canonical_artifact_bytes(maintenance_import.model_dump(mode="json")),
        artifact_media_type="application/json",
        limitations=[
            "No reliable public maintenance-status API exists; this receipt requires "
            "independent review of the official Storefront record."
        ],
        attestation_key_id=attestation_key_id,
        attestation_key=attestation_key,
    )


def primary_legal_status_setup_readiness(
    settings: Any,
) -> PrimaryLegalStatusSetupReadiness:
    """Expose collection/signing capability without treating code presence as data."""
    odp_available = bool(str(getattr(settings, "uspto_odp_api_key", "")).strip())
    signing_available = False
    try:
        keyring = settings.checkpoint_integrity_keys
        signing_available = bool(keyring.active_key_id and len(keyring.active_key()) >= 32)
    except (AttributeError, KeyError, TypeError, ValueError):
        signing_available = False

    available: list[EvidenceScope] = []
    if odp_available and signing_available:
        available.append("application_prosecution")
    supervised: list[EvidenceScope] = ["patent_maintenance"] if signing_available else []
    blocked: list[EvidenceScope] = [
        "patent_term",
        "patent_maintenance",
        "post_grant_proceeding",
        "current_claim_set",
    ]
    failures: list[str] = []
    if not odp_available:
        failures.append("USPTO ODP collection credential is unavailable.")
    if not signing_available:
        failures.append("Primary-status receipt signing is unavailable.")
    failures.append(
        "The official ODP application/adjustment contract does not establish "
        "a complete patent-term-extension basis; patent_term remains unavailable."
    )
    failures.append(
        "PTAB complete negative and exact pending outcomes are supported, but "
        "completed claim effects remain unavailable without controlling text."
    )
    failures.append(
        "Maintenance imports have a strict two-person receipt contract but no "
        "authenticated workspace ingestion workflow."
    )
    failures.append(
        "ODP document metadata does not provide exact controlling current-claim "
        "text; current_claim_set remains unavailable."
    )
    return PrimaryLegalStatusSetupReadiness(
        ready=False,
        signing_available=signing_available,
        odp_collection_available=odp_available,
        available_scopes=available,
        supervised_scopes=supervised,
        blocked_scopes=blocked,
        failure_reasons=failures,
    )


def verify_primary_legal_status_receipt(
    receipt: PrimaryLegalStatusReceipt,
    *,
    attestation_keys: dict[str, bytes],
) -> bool:
    if not verify_primary_legal_status_receipt_digest(receipt):
        return False
    key = attestation_keys.get(receipt.attestation_key_id)
    if not key:
        return False
    expected_signature = hmac.new(
        key,
        _ATTESTATION_DOMAIN + receipt.receipt_sha256.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_signature, receipt.attestation_hmac_sha256)


def verify_primary_legal_status_receipt_digest(
    receipt: PrimaryLegalStatusReceipt,
) -> bool:
    """Verify the canonical receipt digest without possessing its HMAC key.

    This is not a standalone authenticity check. It exists for callers that
    have already verified a cryptographic outer envelope containing the exact
    receipt bytes, such as the signed report binding enforced by the API.
    """
    try:
        receipt = PrimaryLegalStatusReceipt.model_validate(receipt.model_dump(mode="python"))
    except (TypeError, ValueError):
        return False
    if not _HEX_64_RE.fullmatch(receipt.receipt_sha256):
        return False
    expected_receipt_sha256 = hashlib.sha256(_canonical_payload(receipt)).hexdigest()
    return hmac.compare_digest(expected_receipt_sha256, receipt.receipt_sha256)


def evaluate_primary_legal_status_coverage(
    *,
    receipts: list[PrimaryLegalStatusReceipt],
    requirements: list[PrimaryLegalStatusRequirement],
    attestation_keys: dict[str, bytes],
    now: datetime,
) -> PrimaryLegalStatusCoverage:
    """Require a fresh, primary, attested receipt for every reliance scope."""
    return resolve_primary_legal_status_receipts(
        receipts=receipts,
        requirements=requirements,
        attestation_keys=attestation_keys,
        now=now,
    ).coverage


def _receipt_evidence_timestamp(
    receipt: PrimaryLegalStatusReceipt,
) -> datetime:
    observed = receipt.source_record_updated_at or receipt.collected_at
    return observed.astimezone(UTC)


def resolve_primary_legal_status_receipts(
    *,
    receipts: list[PrimaryLegalStatusReceipt],
    requirements: list[PrimaryLegalStatusRequirement],
    attestation_keys: dict[str, bytes],
    now: datetime,
) -> PrimaryLegalStatusResolution:
    """Return coverage and only the exact receipts that satisfied it."""
    return _resolve_primary_legal_status_receipts(
        receipts=receipts,
        requirements=requirements,
        now=now,
        receipt_verifier=lambda receipt: verify_primary_legal_status_receipt(
            receipt,
            attestation_keys=attestation_keys,
        ),
    )


def resolve_report_bound_primary_legal_status_receipts(
    *,
    receipts: list[PrimaryLegalStatusReceipt],
    requirements: list[PrimaryLegalStatusRequirement],
    now: datetime,
) -> PrimaryLegalStatusResolution:
    """Resolve receipts already protected by a verified signed report binding.

    The caller must verify the outer report signature and owner binding before
    invoking this function. Receipt digests are still checked so canonical
    payload corruption cannot be hidden inside an otherwise trusted container.
    """
    return _resolve_primary_legal_status_receipts(
        receipts=receipts,
        requirements=requirements,
        now=now,
        receipt_verifier=verify_primary_legal_status_receipt_digest,
    )


def _receipt_matches_requirement(
    receipt: PrimaryLegalStatusReceipt,
    requirement: PrimaryLegalStatusRequirement,
    *,
    patent_id: str,
) -> bool:
    return (
        receipt.patent_id == patent_id
        and receipt.evidence_scope == requirement.evidence_scope
        and receipt.target_jurisdiction == requirement.target_jurisdiction
    )


def _receipt_is_fresh_primary_evidence(
    receipt: PrimaryLegalStatusReceipt,
    requirement: PrimaryLegalStatusRequirement,
    *,
    now: datetime,
    receipt_verifier: Callable[[PrimaryLegalStatusReceipt], bool],
) -> bool:
    return bool(
        receipt.authority_level == "primary"
        and receipt.parser_result == "conclusive"
        and receipt.normalized_outcome != "unknown"
        and receipt_verifier(receipt)
        and 0
        <= (now.astimezone(UTC) - _receipt_evidence_timestamp(receipt)).total_seconds()
        <= requirement.max_collection_age_hours * 3600
    )


def _requirement_label(requirement: PrimaryLegalStatusRequirement) -> str:
    label = str(requirement.evidence_scope)
    if requirement.target_jurisdiction:
        label += f":{requirement.target_jurisdiction}"
    return label


def _latest_consistent_receipt(
    receipts: list[PrimaryLegalStatusReceipt],
    requirement: PrimaryLegalStatusRequirement,
    *,
    patent_id: str,
) -> PrimaryLegalStatusReceipt | str:
    latest_evidence_at = max(_receipt_evidence_timestamp(receipt) for receipt in receipts)
    latest_receipts = [
        receipt
        for receipt in receipts
        if _receipt_evidence_timestamp(receipt) == latest_evidence_at
    ]
    if len({receipt.normalized_outcome for receipt in latest_receipts}) != 1:
        return (
            f"{patent_id} has conflicting primary-authority evidence for "
            f"{_requirement_label(requirement)}"
        )
    return min(latest_receipts, key=lambda receipt: receipt.receipt_sha256)


def _resolve_primary_legal_status_receipts(
    *,
    receipts: list[PrimaryLegalStatusReceipt],
    requirements: list[PrimaryLegalStatusRequirement],
    now: datetime,
    receipt_verifier: Callable[[PrimaryLegalStatusReceipt], bool],
) -> PrimaryLegalStatusResolution:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    failures: list[str] = []
    satisfied = 0
    selected_receipts: list[PrimaryLegalStatusReceipt] = []
    for requirement in requirements:
        patent_id = _normalise_patent_id(requirement.patent_id)
        candidates = [
            receipt
            for receipt in receipts
            if _receipt_matches_requirement(receipt, requirement, patent_id=patent_id)
        ]
        valid = [
            receipt
            for receipt in candidates
            if _receipt_is_fresh_primary_evidence(
                receipt,
                requirement,
                now=now,
                receipt_verifier=receipt_verifier,
            )
        ]
        if valid:
            selection = _latest_consistent_receipt(
                valid,
                requirement,
                patent_id=patent_id,
            )
            if isinstance(selection, str):
                failures.append(selection)
                continue
            selected_receipts.append(selection)
            satisfied += 1
            continue
        failures.append(
            f"{patent_id} lacks fresh primary-authority evidence for "
            f"{_requirement_label(requirement)}"
        )
    return PrimaryLegalStatusResolution(
        coverage=PrimaryLegalStatusCoverage(
            satisfied=not failures,
            satisfied_requirement_count=satisfied,
            required_requirement_count=len(requirements),
            failure_reasons=failures,
        ),
        selected_receipts=selected_receipts,
    )
