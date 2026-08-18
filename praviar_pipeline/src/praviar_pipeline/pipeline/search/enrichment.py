"""Enrichment helpers for the Step 2 patent search pipeline.

Consolidates what was previously spread across five modules:
  record_builders.py, epo_enrichment.py, us_enrichment.py,
  regulatory_enrichment.py, post_enrichment.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

import httpx
import structlog
from pydantic import ValidationError

from praviar_pipeline.clients.epo_ops import EPOOPSClient
from praviar_pipeline.clients.uspto_odp import USPTOODPClient
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import (
    AuthenticationError,
    ConfigurationError,
    SourceUnavailableError,
)
from praviar_pipeline.models.patent import (
    AssignmentRecord,
    ForeignPriorityClaim,
    LegalEvent,
    LegalStatus,
    PatentFamily,
    PatentFamilyMember,
    PatentSource,
    PTABProceeding,
    _build_legal_status_provenance,
)
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from praviar_pipeline.models.patent import PatentHit

logger = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class EnrichmentOutcome:
    """Coverage-aware outcome for a deterministic enrichment source."""

    attempted_count: int
    covered_count: int
    evidence_count: int

    def __post_init__(self) -> None:
        if min(self.attempted_count, self.covered_count, self.evidence_count) < 0:
            raise ValueError("Enrichment outcome counts must be non-negative")
        if self.covered_count > self.attempted_count:
            raise ValueError("Enrichment coverage cannot exceed attempted targets")


def _evidence_count(value: int | EnrichmentOutcome) -> int:
    return value.evidence_count if isinstance(value, EnrichmentOutcome) else value


# ---------------------------------------------------------------------------
# record_builders -- shared payload builders
# ---------------------------------------------------------------------------


def parse_optional_iso_date(value: object) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def build_legal_event(event: Mapping[str, object]) -> LegalEvent:
    return LegalEvent(
        event_date=parse_optional_iso_date(event.get("event_date", "")),
        event_code=str(event.get("event_code", "")),
        event_description=str(event.get("event_description", "")),
        country=str(event.get("country", "")),
    )


def build_patent_family(family_data: Mapping[str, Any]) -> PatentFamily:
    members = family_data.get("members", [])
    return PatentFamily(
        family_id=str(family_data.get("family_id", "")),
        members=[PatentFamilyMember(**member) for member in members if isinstance(member, dict)],
    )


def build_priority_claim(priority: Mapping[str, object]) -> ForeignPriorityClaim:
    return ForeignPriorityClaim(
        country=str(priority.get("country", "")),
        application_number=str(priority.get("doc_number", "")),
        priority_date=parse_optional_iso_date(priority.get("date", "")),
    )


def dump_legal_events(hit: PatentHit) -> list[dict] | None:
    if not hit.legal_events:
        return None
    return [event.model_dump() for event in hit.legal_events]


def build_assignment_record(assignment: Mapping[str, object]) -> AssignmentRecord:
    return AssignmentRecord(
        conveyance=str(assignment.get("conveyanceText", "")),
        recorded_date=parse_optional_iso_date(assignment.get("assignmentRecordedDate", "")),
        reel_frame=str(assignment.get("reelAndFrameNumber", "")),
    )


def build_ptab_proceeding(proceeding: Mapping[str, object]) -> PTABProceeding:
    return PTABProceeding(
        proceeding_number=str(
            proceeding.get("trialNumber", proceeding.get("proceedingNumber", ""))
        ),
        proceeding_type=str(proceeding.get("trialType", proceeding.get("type", ""))),
        filing_date=parse_optional_iso_date(
            proceeding.get("filingDate", proceeding.get("accordedFilingDate", ""))
        ),
        institution_date=parse_optional_iso_date(proceeding.get("institutionDecisionDate", "")),
        status=str(proceeding.get("status", proceeding.get("dispositionStatus", ""))),
        petitioner=str(proceeding.get("petitionerPartyName", "")),
    )


def _replace_primary_status_receipt(hit: PatentHit, receipt) -> None:
    hit.primary_legal_status_receipts = [
        retained
        for retained in hit.primary_legal_status_receipts
        if not (
            retained.get("source") == receipt.source
            and retained.get("evidence_scope") == receipt.evidence_scope
        )
    ]
    hit.primary_legal_status_receipts.append(receipt.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# epo_enrichment -- EPO-backed enrichment helpers
# ---------------------------------------------------------------------------


def _event_key(event) -> tuple[object, str, str, str]:
    return (
        getattr(event, "event_date", None),
        str(getattr(event, "event_code", "") or ""),
        str(getattr(event, "event_description", "") or ""),
        str(getattr(event, "country", "") or ""),
    )


def _append_unique_legal_event(target: list, event) -> None:
    existing_keys = {_event_key(existing) for existing in target}
    event_key = _event_key(event)
    if event_key not in existing_keys:
        target.append(event)


def _retain_legal_status_observation(hit: PatentHit, provenance) -> None:
    cassette_sha256 = provenance.cassette_sha256
    if any(
        observation.cassette_sha256 == cassette_sha256
        for observation in hit.legal_status_observations
    ):
        return
    hit.legal_status_observations.append(provenance)


def _register_status_to_legal_status(status: str):
    normalized = str(status or "").strip().lower()
    if not normalized:
        return None
    if "pending" in normalized:
        return "pending"
    if "revok" in normalized:
        return "revoked"
    if "lapse" in normalized or "withdraw" in normalized:
        return "lapsed"
    if "grant" in normalized or "active" in normalized or "in force" in normalized:
        return "active"
    if "expir" in normalized:
        return "expired"
    return None


async def enrich_legal_status(
    hits: list[PatentHit],
    *,
    max_patents: int | None = None,
    derive_legal_status: Callable[[list[dict]], LegalStatus],
    client_factory=None,
) -> int:
    settings = get_settings()
    if max_patents is None:
        max_patents = settings.search_max_legal_status_patents
    if not settings.ops_consumer_key or not settings.ops_consumer_secret:
        raise ConfigurationError(
            "EPO OPS credentials not configured",
            source="epo_legal_status",
            step="search_enrichment",
        )

    target = hits[:max_patents]
    logger.info("enrich_legal_status_start", target_count=len(target), total_hits=len(hits))
    enriched = 0
    failures = 0
    auth_failure_type: str | None = None
    factory = client_factory or EPOOPSClient
    async with factory() as client:
        for idx, hit in enumerate(target):
            if idx > 0 and idx % 25 == 0:
                logger.info(
                    "enrich_legal_status_progress",
                    processed=idx,
                    total=len(target),
                    enriched=enriched,
                )
            try:
                events = await client.get_legal_status(hit.patent_id)
                if events:
                    hit.legal_events = [build_legal_event(evt) for evt in events]
                    hit.legal_status = derive_legal_status(events)
                    provenance = _build_legal_status_provenance(
                        patent_id=hit.patent_id,
                        legal_status=hit.legal_status,
                        artifact=events,
                        collector_identity="search.enrichment.epo_ops_legal_status",
                    )
                    hit.legal_status_provenance = provenance
                    _retain_legal_status_observation(hit, provenance)
                    if PatentSource.EPO_SEARCH not in hit.sources:
                        hit.sources.append(PatentSource.EPO_SEARCH)
                    for evt in events:
                        desc = evt.get("event_description", "").lower()
                        if "opposition" in desc or "oppos" in desc:
                            hit.opposition_events.append(build_legal_event(evt))
                    enriched += 1
            except AuthenticationError as exc:
                auth_failure_type = safe_exception_type(exc)
                logger.error(
                    "legal_status_auth_failed",
                    processed=idx,
                    total=len(target),
                    error_type=auth_failure_type,
                )
                break
            except (httpx.HTTPError, ValidationError, KeyError, ValueError) as exc:
                failures += 1
                logger.warning(
                    "legal_status_enrichment_failed",
                    error_type=safe_exception_type(exc),
                )
                continue

    if auth_failure_type is not None:
        raise AuthenticationError(
            "EPO legal-status authentication failed",
            source="epo_legal_status",
        ) from None
    if failures:
        logger.error(
            "legal_status_enrichment_failures",
            count=failures,
            total=len(target),
        )
        raise SourceUnavailableError(
            "epo_legal_status",
            "legal-status coverage failed",
        ) from None
    logger.info("legal_status_enrichment_done", enriched=enriched, total=len(target))
    return enriched


async def expand_families(
    hits: list[PatentHit],
    *,
    max_patents: int | None = None,
    client_factory=None,
) -> EnrichmentOutcome:
    settings = get_settings()
    if max_patents is None:
        max_patents = settings.search_max_family_patents
    if not settings.ops_consumer_key or not settings.ops_consumer_secret:
        raise ConfigurationError(
            "EPO OPS credentials not configured",
            source="family_record",
            step="search_enrichment",
        )

    target = hits[:max_patents]
    logger.info("expand_families_start", target_count=len(target), total_hits=len(hits))
    expanded = 0
    failures = 0
    auth_failure_type: str | None = None
    factory = client_factory or EPOOPSClient
    async with factory() as client:
        for idx, hit in enumerate(target):
            if idx > 0 and idx % 25 == 0:
                logger.info(
                    "expand_families_progress",
                    processed=idx,
                    total=len(target),
                    expanded=expanded,
                )
            try:
                family_data = await client.get_family(hit.patent_id)
                if family_data and family_data.get("members"):
                    hit.family = build_patent_family(family_data)
                    expanded += 1
            except AuthenticationError as exc:
                auth_failure_type = safe_exception_type(exc)
                logger.error(
                    "family_expansion_auth_failed",
                    processed=idx,
                    total=len(target),
                    error_type=auth_failure_type,
                )
                break
            except (httpx.HTTPError, ValidationError, KeyError, ValueError) as exc:
                failures += 1
                logger.warning(
                    "family_expansion_failed",
                    error_type=safe_exception_type(exc),
                )
                continue

    if auth_failure_type is not None:
        raise AuthenticationError(
            "EPO family authentication failed",
            source="family_record",
        ) from None
    if failures:
        logger.error(
            "family_expansion_failures",
            count=failures,
            total=len(target),
        )
        raise SourceUnavailableError(
            "family_record",
            "family expansion coverage failed",
        ) from None
    logger.info("family_expansion_done", expanded=expanded, total=len(target))
    return EnrichmentOutcome(
        attempted_count=len(target),
        covered_count=len(target),
        evidence_count=expanded,
    )


async def enrich_epo_register(
    hits: list[PatentHit],
    *,
    max_patents: int = 50,
    client_factory=None,
) -> EnrichmentOutcome:
    settings = get_settings()
    if not settings.ops_consumer_key or not settings.ops_consumer_secret:
        raise ConfigurationError(
            "EPO OPS credentials not configured",
            source="epo_register",
            step="search_enrichment",
        )

    target = [h for h in hits[:max_patents] if h.patent_id.startswith("EP")]
    logger.info("enrich_epo_register_start", target_count=len(target), total_hits=len(hits))
    enriched = 0
    auth_failure_type: str | None = None
    failures = 0
    factory = client_factory or EPOOPSClient
    async with factory() as client:
        for idx, hit in enumerate(target):
            if idx > 0 and idx % 10 == 0:
                logger.info(
                    "enrich_epo_register_progress",
                    processed=idx,
                    total=len(target),
                    enriched=enriched,
                )
            try:
                register_data = await client.get_register(hit.patent_id)
                if not register_data:
                    continue

                hit.designated_states = register_data.get("designated_states", [])
                hit.ep_register_status = str(register_data.get("status", "") or "")

                for register_event in register_data.get("legal_events", []):
                    _append_unique_legal_event(hit.legal_events, build_legal_event(register_event))

                for opposition in register_data.get("opposition_events", []):
                    _append_unique_legal_event(hit.opposition_events, build_legal_event(opposition))

                register_status = _register_status_to_legal_status(hit.ep_register_status)
                if register_status:
                    observed_status = LegalStatus(register_status)
                    register_provenance = _build_legal_status_provenance(
                        patent_id=hit.patent_id,
                        legal_status=observed_status,
                        artifact=register_data,
                        collector_identity="search.enrichment.epo_register",
                    )
                    _retain_legal_status_observation(hit, register_provenance)
                    if PatentSource.EPO_SEARCH not in hit.sources:
                        hit.sources.append(PatentSource.EPO_SEARCH)
                    observed_statuses = {
                        observation.observed_status
                        for observation in hit.legal_status_observations
                        if observation.observed_status != LegalStatus.UNKNOWN
                    }
                    if len(observed_statuses) > 1:
                        hit.legal_status = LegalStatus.UNKNOWN
                        hit.legal_status_provenance = None
                    else:
                        hit.legal_status = observed_status
                        hit.legal_status_provenance = register_provenance

                biblio = await client.get_biblio(hit.patent_id)
                for priority in biblio.get("priority_claims", []):
                    hit.priority_claims.append(build_priority_claim(priority))

                enriched += 1
            except AuthenticationError as exc:
                auth_failure_type = safe_exception_type(exc)
                logger.error(
                    "epo_register_auth_failed",
                    error_type=auth_failure_type,
                )
                break
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                failures += 1
                logger.warning(
                    "epo_register_enrichment_failed",
                    error_type=safe_exception_type(exc),
                )

    if auth_failure_type is not None:
        raise AuthenticationError(
            "EPO register authentication failed",
            source="epo_register",
        ) from None
    if failures:
        raise SourceUnavailableError(
            "epo_register",
            "EPO register coverage failed",
        ) from None

    logger.info("epo_register_enrichment_done", enriched=enriched, total=len(target))
    return EnrichmentOutcome(
        attempted_count=len(target),
        covered_count=len(target),
        evidence_count=enriched,
    )


# ---------------------------------------------------------------------------
# us_enrichment -- US-specific enrichment helpers
# ---------------------------------------------------------------------------


async def enrich_patent_term(
    hits: list[PatentHit],
    *,
    max_patents: int | None = None,
) -> int:
    from praviar_pipeline.utils.patent_term import calculate_patent_term

    settings = get_settings()
    if max_patents is None:
        max_patents = settings.search_max_patent_term_calc

    if not settings.uspto_odp_api_key:
        raise ConfigurationError(
            "USPTO ODP API key not configured",
            source="uspto_odp",
            step="search_enrichment",
        )

    us_granted = [h for h in hits[:max_patents] if h.patent_id.startswith("US") and h.is_granted]
    logger.info("enrich_patent_term_start", target_count=len(us_granted), total_hits=len(hits))
    calculated = 0
    failures = 0
    for hit in us_granted:
        try:
            legal_events_dicts = dump_legal_events(hit)
            term_info = await calculate_patent_term(
                hit.patent_id,
                legal_events=legal_events_dicts,
            )
            hit.patent_term_info = term_info
            if term_info.adjusted_expiry and term_info.calculation_confidence > 0.5:
                hit.expiry_date = term_info.adjusted_expiry
            calculated += 1
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            failures += 1
            logger.warning(
                "patent_term_calc_failed",
                error_type=safe_exception_type(exc),
            )

    if failures:
        raise SourceUnavailableError(
            "uspto_odp",
            "patent-term coverage failed",
        ) from None

    logger.info("patent_term_enrichment_done", calculated=calculated, total=len(us_granted))
    return calculated


async def enrich_application_data(
    hits: list[PatentHit],
    *,
    max_patents: int | None = None,
    client_factory=USPTOODPClient,
) -> int:
    settings = get_settings()
    if max_patents is None:
        max_patents = settings.search_max_patent_term_calc

    if not settings.uspto_odp_api_key:
        raise ConfigurationError(
            "USPTO ODP API key not configured",
            source="uspto_odp",
            step="search_enrichment",
        )

    us_granted = [h for h in hits[:max_patents] if h.patent_id.startswith("US") and h.is_granted]
    logger.info("enrich_application_data_start", target_count=len(us_granted), total_hits=len(hits))
    enriched = 0
    source_failure_type: str | None = None
    failures = 0
    async with client_factory() as client:
        for idx, hit in enumerate(us_granted):
            if idx > 0 and idx % 25 == 0:
                logger.info(
                    "enrich_application_data_progress",
                    processed=idx,
                    total=len(us_granted),
                    enriched=enriched,
                )
            try:
                application_data = await client.get_application_data(hit.patent_id)
                if not application_data:
                    continue
                metadata = application_data.get("applicationMetaData", {})

                from praviar_pipeline.clients.primary_legal_status import (
                    issue_uspto_odp_application_status_receipt,
                    issue_uspto_odp_patent_term_receipt,
                )

                integrity_keys = settings.checkpoint_integrity_keys
                collected_at = datetime.now(UTC)
                application_status_receipt = issue_uspto_odp_application_status_receipt(
                    patent_id=hit.patent_id,
                    application_data=application_data,
                    collected_at=collected_at,
                    attestation_key_id=integrity_keys.active_key_id,
                    attestation_key=integrity_keys.active_key(),
                )
                _replace_primary_status_receipt(
                    hit,
                    application_status_receipt,
                )

                adjustment_fetch = getattr(type(client), "get_adjustment", None)
                continuity_fetch = getattr(
                    type(client),
                    "get_continuity_artifact",
                    None,
                )
                documents_fetch = getattr(
                    type(client),
                    "get_file_wrapper_documents_artifact",
                    None,
                )
                if (
                    callable(adjustment_fetch)
                    and callable(continuity_fetch)
                    and callable(documents_fetch)
                ):
                    adjustment_response = await adjustment_fetch(
                        client,
                        hit.patent_id,
                    )
                    continuity_response = await continuity_fetch(
                        client,
                        hit.patent_id,
                    )
                    documents_response = await documents_fetch(
                        client,
                        hit.patent_id,
                    )
                    try:
                        term_receipt = issue_uspto_odp_patent_term_receipt(
                            patent_id=hit.patent_id,
                            application_record=application_data,
                            adjustment_response=adjustment_response,
                            continuity_response=continuity_response,
                            documents_response=documents_response,
                            collected_at=collected_at,
                            attestation_key_id=integrity_keys.active_key_id,
                            attestation_key=integrity_keys.active_key(),
                        )
                    except ValueError as exc:
                        logger.info(
                            "primary_patent_term_receipt_withheld",
                            reason_type=safe_exception_type(exc),
                        )
                    else:
                        _replace_primary_status_receipt(hit, term_receipt)

                hit.application_number = application_data.get("applicationNumberText", "")
                hit.examiner = metadata.get("examinerNameText", "")
                attorney_data = application_data.get("recordAttorney", {})
                if isinstance(attorney_data, dict):
                    hit.attorney = attorney_data.get("registrationNumber", "")

                if not hit.inventors:
                    for inventor in metadata.get("inventorBag", []):
                        name = inventor.get("inventorNameText", "")
                        if name and name != hit.patent_id:
                            hit.inventors.append(name)

                for assignment in application_data.get("assignmentBag", []):
                    hit.assignments.append(build_assignment_record(assignment))

                if not hit.assignees and hit.assignments:
                    latest_assignment = hit.assignments[0]
                    if latest_assignment.assignee:
                        hit.assignees = [latest_assignment.assignee]

                enriched += 1
            except httpx.ConnectError as exc:
                # The entire source is unreachable — fail closed so the caller
                # can surface this as a source-level outage rather than silently
                # skipping enrichment for all remaining patents.
                source_failure_type = safe_exception_type(exc)
                break
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                failures += 1
                logger.warning(
                    "app_data_enrichment_failed",
                    error_type=safe_exception_type(exc),
                )

    if source_failure_type is not None:
        logger.warning(
            "app_data_source_failed",
            error_type=source_failure_type,
        )
        raise SourceUnavailableError(
            "uspto_odp",
            "application data lookup failed",
        ) from None
    if failures:
        raise SourceUnavailableError(
            "uspto_odp",
            "application data coverage failed",
        ) from None

    logger.info("application_data_enrichment_done", enriched=enriched, total=len(us_granted))
    return enriched


async def enrich_ptab_proceedings(
    hits: list[PatentHit],
    *,
    max_patents: int = 50,
    client_factory=None,
) -> EnrichmentOutcome:
    from praviar_pipeline.clients.primary_legal_status import (
        issue_uspto_odp_ptab_status_receipt,
    )
    from praviar_pipeline.clients.ptab import PTABClient

    settings = get_settings()
    if not settings.uspto_odp_api_key:
        raise ConfigurationError(
            "USPTO ODP API key not configured",
            source="ptab",
            step="search_enrichment",
        )

    us_granted = [h for h in hits[:max_patents] if h.patent_id.startswith("US") and h.is_granted]
    logger.info("enrich_ptab_proceedings_start", target_count=len(us_granted), total_hits=len(hits))
    enriched = 0
    failure_type: str | None = None
    factory = client_factory or PTABClient
    try:
        async with factory() as client:
            for idx, hit in enumerate(us_granted):
                if idx > 0 and idx % 10 == 0:
                    logger.info(
                        "enrich_ptab_proceedings_progress",
                        processed=idx,
                        total=len(us_granted),
                        enriched=enriched,
                    )
                try:
                    proceedings_exchange: dict[str, object] | None = None
                    artifact_fetch = getattr(
                        type(client),
                        "get_proceedings_artifact",
                        None,
                    )
                    if callable(artifact_fetch):
                        proceedings_exchange = await artifact_fetch(
                            client,
                            hit.patent_id,
                        )
                        response = proceedings_exchange.get("response", {})
                        if not isinstance(response, dict):
                            raise ValueError("PTAB proceedings response is malformed")
                        proceedings = response.get(
                            "patentTrialProceedingDataBag",
                            response.get("results", response.get("hits", [])),
                        )
                        if not isinstance(proceedings, list):
                            raise ValueError("PTAB proceedings records are malformed")
                    else:
                        proceedings = await client.get_proceedings(hit.patent_id)

                    for proceeding in proceedings:
                        if not isinstance(proceeding, dict):
                            raise ValueError("PTAB proceeding is malformed")
                        hit.ptab_proceedings.append(build_ptab_proceeding(proceeding))

                    if proceedings_exchange is not None:
                        decision_exchanges: dict[str, dict[str, object]] = {}
                        decision_fetch = getattr(
                            type(client),
                            "get_decisions_artifact",
                            None,
                        )
                        if callable(decision_fetch):
                            for proceeding in proceedings:
                                trial_number = str(
                                    proceeding.get("trialNumber")
                                    or proceeding.get("proceedingNumber")
                                    or ""
                                ).strip()
                                if trial_number:
                                    decision_exchanges[trial_number] = await decision_fetch(
                                        client, trial_number
                                    )
                        receipt = issue_uspto_odp_ptab_status_receipt(
                            patent_id=hit.patent_id,
                            proceedings_exchange=proceedings_exchange,
                            decision_exchanges=decision_exchanges,
                            collected_at=datetime.now(UTC),
                            attestation_key_id=(settings.checkpoint_integrity_keys.active_key_id),
                            attestation_key=(settings.checkpoint_integrity_keys.active_key()),
                        )
                        _replace_primary_status_receipt(hit, receipt)

                    if proceedings:
                        enriched += 1
                except AuthenticationError as exc:
                    logger.warning(
                        "ptab_enrichment_auth_failed",
                        error_type=safe_exception_type(exc),
                    )
                    failure_type = safe_exception_type(exc)
                    break
                except (SourceUnavailableError, httpx.HTTPError, KeyError, ValueError) as exc:
                    logger.warning(
                        "ptab_enrichment_patent_failed",
                        error_type=safe_exception_type(exc),
                    )
                    failure_type = safe_exception_type(exc)
                    break
    except (ConfigurationError, AuthenticationError) as exc:
        logger.warning(
            "ptab_enrichment_skipped",
            error_type=safe_exception_type(exc),
        )
        failure_type = safe_exception_type(exc)

    if failure_type is not None:
        raise SourceUnavailableError(
            "ptab",
            "PTAB enrichment coverage failed",
        ) from None

    logger.info("ptab_enrichment_done", enriched=enriched)
    return EnrichmentOutcome(
        attempted_count=len(us_granted),
        covered_count=len(us_granted),
        evidence_count=enriched,
    )


# ---------------------------------------------------------------------------
# regulatory_enrichment -- Orange Book enrichment
# ---------------------------------------------------------------------------


async def enrich_orange_book(hits: list) -> EnrichmentOutcome:
    from praviar_pipeline.clients.orange_book import _extract_patent_number, load_orange_book
    from praviar_pipeline.models.patent import (
        OrangeBookExclusivity,
        OrangeBookInfo,
    )

    try:
        orange_book_index = await load_orange_book()
    except Exception as exc:
        logger.warning(
            "orange_book_load_failed",
            error_type=safe_exception_type(exc),
        )
        raise SourceUnavailableError(
            "orange_book",
            "Orange Book index load failed",
        ) from None

    settings = get_settings()
    pte_data: dict[str, dict] = {}
    if settings.pte_certificates_csv_path:
        try:
            from praviar_pipeline.utils.patent_expiry import _get_pte_certificates_cache

            pte_data = _get_pte_certificates_cache(settings.pte_certificates_csv_path)
        except Exception as exc:
            logger.warning(
                "pte_certificates_load_failed",
                error_type=safe_exception_type(exc),
            )
            raise SourceUnavailableError(
                "pte_certificates",
                "PTE certificate load failed",
            ) from None

    enriched = 0
    for hit in hits:
        if not hit.patent_id.startswith("US"):
            continue

        entries = orange_book_index.lookup(hit.patent_id)
        if not entries:
            if pte_data:
                normalized_number = _extract_patent_number(hit.patent_id)
                pte_entry = pte_data.get(normalized_number)
                if pte_entry and pte_entry.get("extension_days", 0) > 0:
                    hit.patent_term_extension_days = pte_entry["extension_days"]
            continue

        nda_numbers = list({entry.nda_number for entry in entries if entry.nda_number})
        product_names = list({entry.product_name for entry in entries if entry.product_name})
        active_ingredients = list(
            {entry.active_ingredient for entry in entries if entry.active_ingredient}
        )
        dosage_forms_routes = sorted(
            {entry.dosage_form_route for entry in entries if entry.dosage_form_route}
        )
        use_codes = list({entry.patent_use_code for entry in entries if entry.patent_use_code})
        exclusivity_pairs = sorted(
            {
                (record.code, record.expiration_date)
                for entry in entries
                for record in entry.exclusivities
            }
        )

        hit.orange_book_info = OrangeBookInfo(
            is_listed=True,
            nda_numbers=nda_numbers,
            product_names=product_names,
            active_ingredients=active_ingredients,
            dosage_forms_routes=dosage_forms_routes,
            reference_listed_drug=any(entry.reference_listed_drug for entry in entries),
            reference_standard=any(entry.reference_standard for entry in entries),
            drug_substance_patent=any(entry.drug_substance_patent for entry in entries),
            drug_product_patent=any(entry.drug_product_patent for entry in entries),
            patent_use_codes=use_codes,
            exclusivities=[
                OrangeBookExclusivity(code=code, expiration_date=expiration_date)
                for code, expiration_date in exclusivity_pairs
            ],
            pediatric_exclusivity=any(entry.pediatric_exclusivity for entry in entries),
            delist_requested=any(entry.delist_requested for entry in entries),
        )

        hit.orange_book_listed = True
        if use_codes:
            hit.patent_use_code = use_codes[0]

        if pte_data:
            normalized_number = _extract_patent_number(hit.patent_id)
            pte_entry = pte_data.get(normalized_number)
            if pte_entry and pte_entry.get("extension_days", 0) > 0:
                hit.patent_term_extension_days = pte_entry["extension_days"]

        if hit.patent_term_info and hit.patent_term_info.pte_days > 0:
            hit.patent_term_extension_days = max(
                hit.patent_term_extension_days, hit.patent_term_info.pte_days
            )

        ob_boost = 0.1
        if any(entry.drug_substance_patent for entry in entries):
            ob_boost = 0.15
        hit.confidence_score = min(1.0, hit.confidence_score + ob_boost)

        enriched += 1

    logger.info(
        "orange_book_enrichment_done",
        enriched=enriched,
        total_ob_patents=orange_book_index.patent_count,
    )
    attempted = sum(1 for hit in hits if hit.patent_id.startswith("US"))
    return EnrichmentOutcome(
        attempted_count=attempted,
        covered_count=attempted,
        evidence_count=enriched,
    )


# ---------------------------------------------------------------------------
# post_enrichment -- post-search enrichment orchestration
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SearchEnrichmentCounts:
    legal: int
    families: int
    patent_term: int
    application_data: int
    epo_register: int
    ptab: int
    orange_book: int
    continuations: int = 0


async def enrich_hits(
    hits: list[PatentHit],
    *,
    enrich_legal_status: Callable[[list[PatentHit]], Awaitable[int]],
    expand_families: Callable[[list[PatentHit]], Awaitable[EnrichmentOutcome]],
    enrich_patent_term: Callable[[list[PatentHit]], Awaitable[int]],
    enrich_application_data: Callable[[list[PatentHit]], Awaitable[int]],
    enrich_epo_register: Callable[[list[PatentHit]], Awaitable[EnrichmentOutcome]],
    enrich_ptab_proceedings: Callable[[list[PatentHit]], Awaitable[EnrichmentOutcome]],
    enrich_orange_book: Callable[[list[PatentHit]], Awaitable[EnrichmentOutcome]],
    expand_continuations: Callable[[list[PatentHit]], Awaitable[int]] | None = None,
) -> SearchEnrichmentCounts:
    """Run the deterministic post-search enrichment steps in order."""
    import time

    total = len(hits)
    logger.info("step2_post_enrichment_start", hit_count=total)

    def _phase(name: str) -> float:
        logger.info("step2_enrichment_phase_start", phase=name, hit_count=total)
        return time.perf_counter()

    def _done(name: str, t0: float, count: int) -> None:
        elapsed = round(time.perf_counter() - t0, 2)
        logger.info(
            "step2_enrichment_phase_done",
            phase=name,
            enriched=count,
            hit_count=total,
            elapsed_s=elapsed,
        )

    t0 = _phase("legal_status")
    legal_count = await enrich_legal_status(hits)
    _done("legal_status", t0, legal_count)

    t0 = _phase("family_expansion")
    family_count = _evidence_count(await expand_families(hits))
    _done("family_expansion", t0, family_count)

    t0 = _phase("patent_term")
    patent_term_count = await enrich_patent_term(hits)
    _done("patent_term", t0, patent_term_count)

    t0 = _phase("application_data")
    app_data_count = await enrich_application_data(hits)
    _done("application_data", t0, app_data_count)

    t0 = _phase("epo_register")
    epo_register_count = _evidence_count(await enrich_epo_register(hits))
    _done("epo_register", t0, epo_register_count)

    t0 = _phase("ptab_proceedings")
    ptab_count = _evidence_count(await enrich_ptab_proceedings(hits))
    _done("ptab_proceedings", t0, ptab_count)

    t0 = _phase("orange_book")
    orange_book_count = _evidence_count(await enrich_orange_book(hits))
    _done("orange_book", t0, orange_book_count)

    continuation_count = 0
    if expand_continuations is not None:
        t0 = _phase("continuations")
        continuation_count = await expand_continuations(hits)
        _done("continuations", t0, continuation_count)

    logger.info(
        "step2_post_enrichment_done",
        hit_count=total,
        legal=legal_count,
        families=family_count,
        patent_term=patent_term_count,
        epo_register=epo_register_count,
        ptab=ptab_count,
        orange_book=orange_book_count,
        continuations=continuation_count,
    )
    return SearchEnrichmentCounts(
        legal=legal_count,
        families=family_count,
        patent_term=patent_term_count,
        application_data=app_data_count,
        epo_register=epo_register_count,
        ptab=ptab_count,
        orange_book=orange_book_count,
        continuations=continuation_count,
    )


async def run_step2_post_enrichment(
    hits: list[PatentHit],
    *,
    enrich_legal_status,
    expand_families,
    enrich_patent_term,
    enrich_application_data,
    enrich_epo_register,
    enrich_ptab_proceedings,
    enrich_orange_book,
    expand_continuations=None,
) -> SearchEnrichmentCounts:
    """Run Step 2 post-enrichment using the pipeline's stable wrapper callables."""
    return await enrich_hits(
        hits,
        enrich_legal_status=enrich_legal_status,
        expand_families=expand_families,
        enrich_patent_term=enrich_patent_term,
        enrich_application_data=enrich_application_data,
        enrich_epo_register=enrich_epo_register,
        enrich_ptab_proceedings=enrich_ptab_proceedings,
        enrich_orange_book=enrich_orange_book,
        expand_continuations=expand_continuations,
    )
