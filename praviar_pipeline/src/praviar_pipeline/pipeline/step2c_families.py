"""Step 2.5: Patent family expansion and broadest-claims selection.

Groups patents by family, fetches claims for family members, and selects
the member with the broadest independent claims for downstream analysis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.clients.bigquery import BigQueryClient
from praviar_pipeline.models.patent import PatentSource
from praviar_pipeline.pipeline.runtime.live_collector_claims import (
    record_claims_text_retrieval,
)
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from praviar_pipeline.models.patent import PatentHit

logger = structlog.get_logger()


def _estimate_claim_breadth(claims_text: str) -> float:
    """Heuristic score for how broad an independent claim is.

    Higher score = broader claim. Factors:
    - Fewer elements (shorter claims tend to be broader)
    - More functional language ("comprising", "consisting of")
    - Fewer specific limitations
    """
    if not claims_text:
        return 0.0

    # Extract first independent claim (claim 1)
    lines = claims_text.split("\n")
    claim_1_lines = []
    in_claim_1 = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("1.") or stripped.startswith("1 ."):
            in_claim_1 = True
        elif in_claim_1 and (stripped and stripped[0].isdigit() and "." in stripped[:4]):
            break
        if in_claim_1:
            claim_1_lines.append(stripped)

    claim_1_text = " ".join(claim_1_lines).lower()
    if not claim_1_text:
        claim_1_text = claims_text.lower()

    score = 0.0

    # Broader claims tend to be shorter (fewer limitations)
    word_count = len(claim_1_text.split())
    if word_count < 50:
        score += 3.0
    elif word_count < 100:
        score += 2.0
    elif word_count < 200:
        score += 1.0

    # "comprising" is open-ended (broader) vs "consisting of" (closed)
    if "comprising" in claim_1_text:
        score += 2.0
    if "consisting essentially of" in claim_1_text:
        score += 1.0
    if "consisting of" in claim_1_text and "consisting essentially" not in claim_1_text:
        score -= 1.0  # Narrower

    # Count semicolons as element separators — fewer = broader
    semicolons = claim_1_text.count(";")
    if semicolons < 3:
        score += 1.0

    # Functional language = broader
    functional_terms = ["capable of", "adapted to", "configured to", "operable to"]
    for term in functional_terms:
        if term in claim_1_text:
            score += 0.5

    return max(score, 0.0)


async def _enrich_biblio_from_epo_ops(patents: list[PatentHit]) -> int:
    """Fetch title and abstract from EPO OPS for INPADOC stubs missing both.

    INPADOC stubs from family expansion arrive with only a patent_id — no title,
    abstract, or claims. Without title/abstract, triage is blind. EPO OPS DOCDB
    bibliographic source can enrich records returned by that configured
    endpoint. It is attempted when BigQuery leaves the fields unavailable,
    without implying exhaustive office or jurisdiction coverage.

    Returns the number of patents enriched with at least a title.
    """
    stubs = [p for p in patents if not p.title and not p.abstract]
    if not stubs:
        return 0

    from praviar_pipeline.clients.epo_ops import EPOOPSClient

    logger.info("epo_ops_biblio_enrichment_start", stubs=len(stubs), total=len(patents))
    enriched = 0

    async with EPOOPSClient() as epo_client:
        for p in stubs:
            try:
                biblio = await epo_client.get_biblio(p.patent_id)
                if biblio.get("title"):
                    p.title = biblio["title"]
                    if biblio.get("abstract"):
                        p.abstract = biblio["abstract"]
                    enriched += 1
            except Exception as exc:
                logger.debug(
                    "epo_ops_biblio_fetch_failed",
                    error_type=safe_exception_type(exc),
                )

    if enriched:
        logger.info("epo_ops_biblio_enrichment_done", enriched=enriched, total=len(stubs))
    else:
        logger.warning(
            "epo_ops_biblio_enrichment_empty",
            stubs=len(stubs),
        )
    return enriched


def _epo_ops_can_supply_claims(patent_id: str) -> bool:
    """Return True for jurisdictions where EPO OPS reliably returns claims text.

    EP and WO are fully indexed in the DOCDB collection with English claims.
    US patents are in DOCDB but EPO OPS does not return their full English
    claims text; those come from USPTO ODP or BigQuery instead.
    """
    return patent_id.upper().startswith(("EP", "WO"))


async def _enrich_claims_from_epo_ops(patents: list[PatentHit]) -> int:
    """Fetch English claims text from EPO OPS for EP/WO patents missing it.

    Falls back to EPO OPS after BigQuery is unavailable (quota/billing).
    Only processes EP and WO patents — other jurisdictions (US, CN, JP, KR)
    are skipped to avoid consuming EPO OPS rate-limit slots for patents
    where the endpoint reliably returns empty results.
    Per-patent exception handling means one failure never blocks others.

    Returns the number of patents enriched.
    """
    missing = [p for p in patents if not p.claims_text and _epo_ops_can_supply_claims(p.patent_id)]
    if not missing:
        return 0

    from praviar_pipeline.clients.epo_ops import EPOOPSClient

    logger.info("epo_ops_claims_enrichment_start", count=len(missing))
    enriched = 0
    consecutive_empty = 0
    circuit_breaker_threshold = 10

    async with EPOOPSClient() as epo_client:
        for p in missing:
            try:
                text = await epo_client.get_claims_text(p.patent_id)
                if text:
                    record_claims_text_retrieval(
                        p,
                        text,
                        source=PatentSource.EPO_SEARCH,
                        collector_identity="step2c.epo_ops_claims",
                        upstream_locator=(
                            "https://ops.epo.org/3.2/rest-services/published-data/"
                            f"publication/epodoc/{p.patent_id}/claims"
                        ),
                    )
                    enriched += 1
                    consecutive_empty = 0
                else:
                    consecutive_empty += 1
                    if consecutive_empty >= circuit_breaker_threshold:
                        logger.info(
                            "epo_ops_claims_circuit_open",
                            consecutive_empty=consecutive_empty,
                        )
                        break
            except Exception as exc:
                logger.debug(
                    "epo_ops_claims_fetch_failed",
                    error_type=safe_exception_type(exc),
                )

    if enriched:
        logger.info("epo_ops_claims_enrichment_done", enriched=enriched, total=len(missing))
    else:
        logger.debug("epo_ops_claims_enrichment_empty", count=len(missing))
    return enriched


async def expand_and_select_families(
    hits: list[PatentHit],
) -> list[PatentHit]:
    """Group patents by family and select broadest-claims member.

    For each patent family with multiple members in the hit list:
    1. Fetch claims text for all members (if missing)
    2. Score each member's independent claims for breadth
    3. Mark the broadest member with family_broadest=True
    4. Deduplicate: keep only the broadest member per family

    Patents without family info are passed through unchanged.

    Returns:
        Deduplicated list with broadest family member preferred.
    """
    if not hits:
        return []

    # Group by family ID
    family_groups: dict[str, list[PatentHit]] = {}
    no_family: list[PatentHit] = []

    for hit in hits:
        family_id = None
        if hit.family and hit.family.family_id:
            family_id = hit.family.family_id

        if family_id:
            family_groups.setdefault(family_id, []).append(hit)
        else:
            no_family.append(hit)

    if not family_groups:
        logger.debug("family_expansion_skip", total_hits=len(hits))
        return hits

    # Fetch missing claims for family members
    missing_claims_ids = []
    for members in family_groups.values():
        for m in members:
            if not m.claims_text:
                missing_claims_ids.append(m.patent_id)

    if missing_claims_ids:
        try:
            async with BigQueryClient() as bq:
                claims_map = await bq.get_patent_claims_batch(missing_claims_ids)
                enriched = 0
                for members in family_groups.values():
                    for m in members:
                        if not m.claims_text and m.patent_id in claims_map:
                            record_claims_text_retrieval(
                                m,
                                claims_map[m.patent_id],
                                source=PatentSource.BIGQUERY,
                                collector_identity="step2c.family_bigquery_claims",
                                upstream_locator=(
                                    "https://console.cloud.google.com/bigquery?project="
                                    f"patents-public-data&patent={m.patent_id}"
                                ),
                            )
                            enriched += 1
                logger.info(
                    "family_claims_enriched", enriched=enriched, total=len(missing_claims_ids)
                )
        except Exception as exc:
            logger.warning(
                "family_claims_enrichment_failed",
                error_type=safe_exception_type(exc),
            )

    # Select broadest member per family
    result: list[PatentHit] = list(no_family)
    families_deduplicated = 0

    for _family_id, members in family_groups.items():
        if len(members) == 1:
            result.append(members[0])
            continue

        # Score each member
        scored = []
        for m in members:
            breadth = _estimate_claim_breadth(m.claims_text)
            scored.append((breadth, m))

        # Sort by breadth (highest first), then by confidence_score as tiebreaker
        scored.sort(key=lambda x: (x[0], x[1].confidence_score), reverse=True)

        # Mark broadest and keep it
        broadest = scored[0][1]
        broadest.family_broadest = True
        result.append(broadest)
        families_deduplicated += len(members) - 1

        logger.debug(
            "family_broadest_selected",
            members=len(members),
            breadth_score=scored[0][0],
        )

    logger.info(
        "family_expansion_complete",
        input_hits=len(hits),
        output_hits=len(result),
        families_processed=len(family_groups),
        deduplicated=families_deduplicated,
    )

    return result


async def enrich_claims_text(patents: list[PatentHit]) -> int:
    """Batch-fetch claims text for patents that don't have it.

    Tries BigQuery first (one batch query); falls back to EPO OPS DOCDB when
    BigQuery is unavailable (quota exhausted, billing disabled). Called after
    family expansion and before triage so that triage decisions are based on
    actual claim language, not just abstracts.

    Returns the number of patents enriched.
    """
    missing = [p for p in patents if not p.claims_text]
    if not missing:
        logger.info("claims_enrichment_skipped", total=len(patents))
        return 0

    logger.info(
        "claims_enrichment_start",
        missing=len(missing),
        total=len(patents),
        pct_missing=round(len(missing) / len(patents) * 100, 1),
    )

    enriched = 0
    try:
        async with BigQueryClient() as bq:
            claims_map = await bq.get_patent_claims_batch([p.patent_id for p in missing])
        for p in missing:
            text = claims_map.get(p.patent_id, "")
            if text:
                record_claims_text_retrieval(
                    p,
                    text,
                    source=PatentSource.BIGQUERY,
                    collector_identity="step2c.bigquery_claims",
                    upstream_locator=(
                        "https://console.cloud.google.com/bigquery?project="
                        f"patents-public-data&patent={p.patent_id}"
                    ),
                )
                enriched += 1
    except Exception as exc:
        logger.warning(
            "claims_enrichment_bigquery_failed",
            error_type=safe_exception_type(exc),
            missing=len(missing),
        )

    # EPO OPS fallback for patents still missing claims text
    still_missing = len([p for p in missing if not p.claims_text])
    if still_missing:
        enriched += await _enrich_claims_from_epo_ops(patents)

    logger.info(
        "claims_enrichment_complete",
        enriched=enriched,
        still_missing=len([p for p in missing if not p.claims_text]),
        total=len(patents),
    )
    return enriched


async def enrich_biblio_from_epo_ops(patents: list[PatentHit]) -> int:
    """Public entry point: enrich title/abstract for INPADOC stubs via EPO OPS.

    Called from the search loop enrichment pipeline after family expansion so
    that triage can use real title/abstract instead of empty strings.

    Returns the number of patents enriched with at least a title.
    """
    return await _enrich_biblio_from_epo_ops(patents)
