"""Claim-text collection helpers for runtime live collectors."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import httpx
import structlog
from tenacity import RetryError

from praviar_pipeline.clients.bigquery import BigQueryClient
from praviar_pipeline.clients.epo_ops import EPOOPSClient
from praviar_pipeline.clients.patentsview import PatentsViewClient
from praviar_pipeline.models.patent import (
    ClaimTextCollectorIdentity,
    PatentSource,
    build_claim_text_provenance,
)
from praviar_pipeline.pipeline.runtime.live_collector_helpers import (
    failed_entry,
    not_configured_error_entry,
    ok_entry,
)
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from praviar_pipeline.models.patent import PatentHit
    from praviar_pipeline.models.report import SourceHealthEntry

logger = structlog.get_logger()


def record_claims_text_retrieval(
    hit: PatentHit,
    text: str,
    *,
    source: PatentSource,
    collector_identity: ClaimTextCollectorIdentity,
    upstream_locator: str,
) -> None:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    locator = f"{upstream_locator}#sha256={digest}"
    hit.claims_text = text
    hit.claims_text_source = source.value
    hit.claims_text_provenance = build_claim_text_provenance(
        patent_id=hit.patent_id,
        claims_text=text,
        source=source,
        artifact_locator=locator,
        collector_identity=collector_identity,
    )


async def collect_claims_from_bigquery_impl(
    patent_hits: list[PatentHit],
) -> tuple[SourceHealthEntry, list[str]]:
    missing_hits = [hit for hit in patent_hits if not (hit.claims_text or "").strip()]
    logger.info(
        "bigquery_claims_start",
        total_hits=len(patent_hits),
        missing_claims=len(missing_hits),
    )
    if not missing_hits:
        return ok_entry("bigquery", len(patent_hits)), []

    try:
        async with BigQueryClient() as client:
            claims_map = await client.get_patent_claims_batch(
                [hit.patent_id for hit in missing_hits]
            )
        enriched_ids: list[str] = []
        for hit in missing_hits:
            text = claims_map.get(hit.patent_id, "")
            if text:
                record_claims_text_retrieval(
                    hit,
                    text,
                    source=PatentSource.BIGQUERY,
                    collector_identity="runtime.bigquery_claims_batch",
                    upstream_locator=(
                        "https://console.cloud.google.com/bigquery?project="
                        f"patents-public-data&patent={hit.patent_id}"
                    ),
                )
                enriched_ids.append(hit.patent_id)
        logger.info(
            "bigquery_claims_done",
            enriched=len(enriched_ids),
            missing=len(missing_hits),
        )
        return ok_entry("bigquery", len(enriched_ids)), enriched_ids
    except Exception as exc:
        return failed_entry("bigquery", exc), []


async def collect_claims_from_patentsview_impl(
    patent_hits: list[PatentHit],
    *,
    max_patents: int | None = None,
) -> tuple[SourceHealthEntry, list[str]]:
    from praviar_pipeline.config import get_settings

    all_missing = [
        hit
        for hit in patent_hits
        if not (hit.claims_text or "").strip() and hit.patent_id.upper().startswith("US")
    ]
    if not all_missing:
        return ok_entry("patentsview", 0), []

    if max_patents is None:
        max_patents = get_settings().search_max_patentsview_claims_patents

    missing_hits = all_missing[:max_patents]
    skipped = len(all_missing) - len(missing_hits)
    logger.info(
        "patentsview_claims_start",
        total_hits=len(patent_hits),
        us_missing_claims=len(all_missing),
        target_count=len(missing_hits),
        skipped_by_cap=skipped,
    )

    try:
        enriched_ids: list[str] = []
        async with PatentsViewClient() as client:
            for idx, hit in enumerate(missing_hits):
                if idx > 0 and idx % 50 == 0:
                    logger.info(
                        "patentsview_claims_progress",
                        processed=idx,
                        total=len(missing_hits),
                        enriched=len(enriched_ids),
                    )
                text = await client.get_patent_claims_text(hit.patent_id)
                if text:
                    record_claims_text_retrieval(
                        hit,
                        text,
                        source=PatentSource.PATENTSVIEW,
                        collector_identity="runtime.patentsview_claims",
                        upstream_locator=(
                            "https://search.patentsview.org/api/v1/patent/"
                            f"?patent_id={hit.patent_id}"
                        ),
                    )
                    enriched_ids.append(hit.patent_id)
        logger.info(
            "patentsview_claims_done",
            enriched=len(enriched_ids),
            total=len(missing_hits),
            skipped_by_cap=skipped,
        )
        return ok_entry("patentsview", len(enriched_ids)), enriched_ids
    except (httpx.ConnectError, httpx.ConnectTimeout, RetryError) as exc:
        logger.warning(
            "patentsview_claims_not_configured",
            error_type=safe_exception_type(exc),
        )
        return not_configured_error_entry("patentsview", exc), []
    except Exception as exc:
        return failed_entry("patentsview", exc), []


async def collect_claims_from_epo_impl(
    patent_hits: list[PatentHit],
    *,
    max_patents: int | None = None,
) -> tuple[SourceHealthEntry, list[str]]:
    from praviar_pipeline.config import get_settings

    all_missing = [
        hit
        for hit in patent_hits
        if not (hit.claims_text or "").strip() and hit.patent_id.upper().startswith("EP")
    ]
    if not all_missing:
        return ok_entry("epo_search", 0), []

    if max_patents is None:
        max_patents = get_settings().search_max_epo_claims_patents

    missing_hits = all_missing[:max_patents]
    skipped = len(all_missing) - len(missing_hits)
    logger.info(
        "epo_claims_start",
        target_count=len(missing_hits),
        total_ep_missing=len(all_missing),
        skipped_by_cap=skipped,
    )

    circuit_breaker_threshold = 10
    try:
        enriched_ids: list[str] = []
        failures = 0
        consecutive_empty = 0
        async with EPOOPSClient() as client:
            for idx, hit in enumerate(missing_hits):
                if idx > 0 and idx % 25 == 0:
                    logger.info(
                        "epo_claims_progress",
                        processed=idx,
                        total=len(missing_hits),
                        enriched=len(enriched_ids),
                    )
                try:
                    text = await client.get_claims_text(hit.patent_id)
                    if text:
                        record_claims_text_retrieval(
                            hit,
                            text,
                            source=PatentSource.EPO_SEARCH,
                            collector_identity="runtime.epo_ops_claims",
                            upstream_locator=(
                                "https://ops.epo.org/3.2/rest-services/published-data/"
                                f"publication/epodoc/{hit.patent_id}/claims"
                            ),
                        )
                        enriched_ids.append(hit.patent_id)
                        consecutive_empty = 0
                    else:
                        consecutive_empty += 1
                        if consecutive_empty >= circuit_breaker_threshold:
                            logger.info(
                                "epo_claims_circuit_open",
                                consecutive_empty=consecutive_empty,
                                processed=idx + 1,
                                remaining=len(missing_hits) - idx - 1,
                            )
                            break
                except (httpx.ConnectError, httpx.ConnectTimeout, RetryError) as exc:
                    logger.warning(
                        "epo_claims_connect_error",
                        error_type=safe_exception_type(exc),
                    )
                    return not_configured_error_entry("epo_search", exc), enriched_ids
                except Exception as exc:
                    failures += 1
                    logger.warning(
                        "epo_claims_patent_failed",
                        error_type=safe_exception_type(exc),
                    )

        logger.info(
            "epo_claims_done",
            enriched=len(enriched_ids),
            total=len(missing_hits),
            skipped_by_cap=skipped,
        )
        return ok_entry("epo_search", len(enriched_ids)), enriched_ids
    except Exception as exc:
        return failed_entry("epo_search", exc), []
