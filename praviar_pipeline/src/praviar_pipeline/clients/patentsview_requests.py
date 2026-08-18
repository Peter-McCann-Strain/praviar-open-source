"""USPTO ODP request body builders.

Replaces PatentsView GET-params request builders with POST body builders
for the api.uspto.gov/api/v1/patent/applications/search endpoint.
"""

from __future__ import annotations

from praviar_pipeline.clients.patentsview_queries import _strip_patent_id

# These constants are kept for backward compatibility with existing callers
# that reference them by name; the ODP endpoint does not use field selection.
DEFAULT_PATENT_FIELDS: list[str] = []
DEFAULT_CPC_FIELDS: list[str] = []
DEFAULT_ASSIGNEE_FIELDS: list[str] = []
DEFAULT_PATENT_DETAIL_FIELDS: list[str] = []
DEFAULT_CLAIMS_FIELDS: list[str] = []
DEFAULT_COMPOUND_KEYWORD_FIELDS: list[str] = []


def build_search_request_body(
    query: str,
    fields: list[str] | None = None,
    *,
    limit: int = 100,
    offset: int = 0,
    sort: list[dict] | None = None,
) -> dict:
    """Build the POST body for the USPTO ODP applications search endpoint.

    The ODP API uses nested pagination and does not support field selection;
    the ``fields`` and ``sort`` parameters are accepted for API compatibility
    but are not forwarded.
    """
    del fields, sort
    return {
        "q": query,
        "pagination": {"limit": min(limit, 500), "offset": offset},
    }


def build_search_request_params(
    query: str,
    fields: list[str] | None = None,
    *,
    size: int = 100,
    sort: list[dict] | None = None,
) -> dict:
    """Alias for build_search_request_body using the old PatentsView signature."""
    return build_search_request_body(query, fields, limit=size, sort=sort)


def build_claims_request_params(patent_id: str) -> dict:
    """Build request body to look up a single patent by number."""
    num = _strip_patent_id(patent_id)
    return build_search_request_body(
        f"applicationMetaData.patentNumber:{num}",
        limit=1,
    )
