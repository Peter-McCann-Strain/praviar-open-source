from __future__ import annotations

from praviar_pipeline.models.patent import PatentHit, PatentSource
from praviar_pipeline.pipeline.runtime.live_collector_claims import (
    record_claims_text_retrieval,
)


def trusted_claim_text_fields(
    patent_id: str,
    claims_text: str,
    *,
    source: PatentSource | None = None,
) -> dict:
    if source is None:
        source = (
            PatentSource.PATENTSVIEW
            if patent_id.upper().startswith("US")
            else PatentSource.EPO_SEARCH
        )
    if not claims_text.lstrip().startswith(("1.", "Claim 1", "claim 1")):
        claims_text = f"1. {claims_text.strip()}"
    collector_by_source = {
        PatentSource.BIGQUERY: "runtime.bigquery_claims_batch",
        PatentSource.EPO_SEARCH: "runtime.epo_ops_claims",
        PatentSource.PATENTSVIEW: "runtime.patentsview_claims",
    }
    locator_by_source = {
        PatentSource.BIGQUERY: (
            "https://console.cloud.google.com/bigquery?project="
            f"patents-public-data&patent={patent_id}"
        ),
        PatentSource.EPO_SEARCH: (
            "https://ops.epo.org/3.2/rest-services/published-data/"
            f"publication/epodoc/{patent_id}/claims"
        ),
        PatentSource.PATENTSVIEW: (
            f"https://search.patentsview.org/api/v1/patent/?patent_id={patent_id}"
        ),
    }
    hit = PatentHit(patent_id=patent_id, sources=[source])
    record_claims_text_retrieval(
        hit,
        claims_text,
        source=source,
        collector_identity=collector_by_source[source],
        upstream_locator=locator_by_source[source],
    )
    return {
        "claims_text": hit.claims_text,
        "claims_text_source": hit.claims_text_source,
        "claims_text_provenance": hit.claims_text_provenance,
    }
