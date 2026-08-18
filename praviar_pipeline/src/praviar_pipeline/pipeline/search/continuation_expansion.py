"""Continuation/divisional/reissue expansion for Step 2 patent search.

After primary search + ranking produces a hit list, this module traverses each
hit's family to pick up continuations, divisionals, continuations-in-part, and
reissues that share the same specification. Continuation claims can be BROADER
than parent claims, so missing them is a correctness bug with real FTO
consequences (SG-122).

Design:
- For US hits, prefer USPTO ODP continuity data (explicit continuity type).
- Fall back to EPO OPS family endpoint for non-US jurisdictions.
- De-dupe against existing hits by normalized patent id; merge family_role
  metadata onto an existing hit if the continuation was already found by a
  different search method.
- Cap traversal depth at ``MAX_DEPTH`` levels (default 2) to avoid chasing
  continuations-of-continuations-of-continuations.
- Fail-closed: if a required lineage source is not configured or cannot be
  queried, raise so Step 2 cannot silently omit continuation risk.
"""

from __future__ import annotations

import httpx
import structlog

from praviar_pipeline.clients.epo_ops import EPOOPSClient
from praviar_pipeline.clients.uspto_odp import USPTOODPClient
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import (
    AuthenticationError,
    ConfigurationError,
    SourceUnavailableError,
)
from praviar_pipeline.models.patent import PatentHit, PatentSource
from praviar_pipeline.utils.patent_ids import normalize_patent_id
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

logger = structlog.get_logger()

MAX_DEPTH = 2

# Map USPTO ODP continuityType values / descriptions to PatentHit.family_role literals.
_ODP_TYPE_TO_ROLE = {
    "continuation": "continuation",
    "con": "continuation",
    "continuation-in-part": "continuation_in_part",
    "continuation in part": "continuation_in_part",
    "cip": "continuation_in_part",
    "divisional": "divisional",
    "div": "divisional",
    "reissue": "reissue",
    "substitute": "continuation",
}


def _classify_odp_continuity(entry: dict) -> str:
    """Return a family_role literal from a USPTO ODP continuity bag entry."""
    raw = (
        entry.get("claimParentageTypeLabel")
        or entry.get("claimParentageType")
        or entry.get("continuityType")
        or ""
    )
    key = str(raw).strip().lower()
    if not key:
        return "unknown"
    if key in _ODP_TYPE_TO_ROLE:
        return _ODP_TYPE_TO_ROLE[key]
    # Substring fallbacks for free-text descriptions.
    if "continuation in part" in key or "cip" in key:
        return "continuation_in_part"
    if "continuation" in key:
        return "continuation"
    if "divisional" in key:
        return "divisional"
    if "reissue" in key:
        return "reissue"
    return "unknown"


def _child_patent_id_from_odp_entry(entry: dict) -> str:
    """Extract the child publication/patent number from an ODP continuity entry."""
    pid = (
        entry.get("childPatentNumber")
        or entry.get("childPublicationNumber")
        or entry.get("childApplicationNumberText")
        or ""
    )
    return str(pid).strip()


def _family_member_to_patent_id(member: dict) -> str:
    """Format a DOCDB family member dict as a patent id string."""
    country = str(member.get("country", "") or "").strip()
    doc_number = str(member.get("doc_number", "") or "").strip()
    kind = str(member.get("kind", "") or "").strip()
    if not country or not doc_number:
        return ""
    return f"{country}{doc_number}{kind}"


def _merge_role_onto_existing(
    hit: PatentHit,
    *,
    role: str,
    parent_id: str,
) -> None:
    """If an existing hit lacks family_role metadata, populate it."""
    if role and not hit.family_role:
        hit.family_role = role  # type: ignore[assignment]
    if parent_id and not hit.parent_application_id:
        hit.parent_application_id = parent_id


def _make_continuation_hit(
    *,
    patent_id: str,
    role: str,
    parent_id: str,
    source: PatentSource,
) -> PatentHit:
    """Build a new PatentHit for a family member discovered during expansion.

    Uses a very low confidence score — the continuation is discovered by
    traversal, not by a structure/text match. Ranking signal is left to
    subsequent enrichment + triage.
    """
    return PatentHit(
        patent_id=patent_id,
        sources=[source],
        confidence_score=0.1,
        family_role=role,  # type: ignore[arg-type]
        parent_application_id=parent_id,
    )


async def _enter_source_client(client_ctx, source: str):
    failure_kind: str | None = None
    try:
        return await client_ctx.__aenter__()
    except AuthenticationError:
        failure_kind = "authentication"
    except ConfigurationError:
        failure_kind = "configuration"
    except (SourceUnavailableError, httpx.HTTPError):
        failure_kind = "source"

    if failure_kind == "authentication":
        raise AuthenticationError(
            "lineage source authentication failed",
            source=source,
        ) from None
    if failure_kind == "configuration":
        raise ConfigurationError(
            "lineage source configuration failed",
            source=source,
            step="continuation_expansion",
        ) from None
    raise SourceUnavailableError(source, "lineage source connection failed") from None


async def _expand_from_odp(
    client: USPTOODPClient,
    hit: PatentHit,
    seen: dict[str, PatentHit],
    new_hits: list[PatentHit],
) -> int:
    """Use USPTO ODP continuity data to add US continuations for ``hit``.

    Returns the number of new hits added for this parent.
    """
    added = 0
    failure_kind: str | None = None
    failure_type: str | None = None
    try:
        entries = await client.get_continuity_data(hit.patent_id)
    except SourceUnavailableError as exc:
        failure_kind = "source"
        failure_type = safe_exception_type(exc)
    except AuthenticationError as exc:
        failure_kind = "authentication"
        failure_type = safe_exception_type(exc)
    except httpx.HTTPError as exc:
        failure_kind = "source"
        failure_type = safe_exception_type(exc)
    except (KeyError, ValueError) as exc:
        failure_kind = "source"
        failure_type = safe_exception_type(exc)

    if failure_type is not None:
        logger.error(
            "continuation_expansion_odp_failed",
            error_type=failure_type,
        )
        if failure_kind == "authentication":
            raise AuthenticationError(
                "continuation source authentication failed",
                source="uspto_odp",
            ) from None
        raise SourceUnavailableError(
            "uspto_odp",
            "continuation lookup failed",
        ) from None

    for entry in entries:
        role = _classify_odp_continuity(entry)
        if role not in {"continuation", "divisional", "continuation_in_part", "reissue"}:
            continue
        child_id = _child_patent_id_from_odp_entry(entry)
        if not child_id:
            continue
        norm = normalize_patent_id(child_id)
        if not norm:
            continue
        if norm in seen:
            _merge_role_onto_existing(seen[norm], role=role, parent_id=hit.patent_id)
            continue
        new_hit = _make_continuation_hit(
            patent_id=child_id,
            role=role,
            parent_id=hit.patent_id,
            source=PatentSource.INPADOC,  # ODP has no enum; treat as lineage discovery
        )
        seen[norm] = new_hit
        new_hits.append(new_hit)
        added += 1
    return added


async def _expand_from_epo_family(
    client: EPOOPSClient,
    hit: PatentHit,
    seen: dict[str, PatentHit],
    new_hits: list[PatentHit],
) -> int:
    """Use EPO OPS family endpoint to add non-US family members as unknown role."""
    added = 0
    failure_kind: str | None = None
    failure_type: str | None = None
    try:
        family_data = await client.get_family(hit.patent_id)
    except SourceUnavailableError as exc:
        failure_kind = "source"
        failure_type = safe_exception_type(exc)
    except AuthenticationError as exc:
        failure_kind = "authentication"
        failure_type = safe_exception_type(exc)
    except httpx.HTTPError as exc:
        failure_kind = "source"
        failure_type = safe_exception_type(exc)
    except (KeyError, ValueError) as exc:
        failure_kind = "source"
        failure_type = safe_exception_type(exc)

    if failure_type is not None:
        logger.error(
            "continuation_expansion_epo_failed",
            error_type=failure_type,
        )
        if failure_kind == "authentication":
            raise AuthenticationError(
                "family source authentication failed",
                source="epo_ops",
            ) from None
        raise SourceUnavailableError("epo_ops", "family lookup failed") from None

    if not family_data:
        return 0
    if not isinstance(family_data, dict):
        raise SourceUnavailableError("epo_ops", "Malformed family response")
    for member in family_data.get("members", []):
        if not isinstance(member, dict):
            continue
        pid = _family_member_to_patent_id(member)
        if not pid:
            continue
        norm = normalize_patent_id(pid)
        if not norm or norm == normalize_patent_id(hit.patent_id):
            continue
        if norm in seen:
            # Only fill role if nothing else has claimed it; EPO family doesn't
            # distinguish continuation vs. foreign equivalent, so use "unknown".
            _merge_role_onto_existing(seen[norm], role="unknown", parent_id=hit.patent_id)
            continue
        new_hit = _make_continuation_hit(
            patent_id=pid,
            role="unknown",
            parent_id=hit.patent_id,
            source=PatentSource.INPADOC,
        )
        seen[norm] = new_hit
        new_hits.append(new_hit)
        added += 1
    return added


async def expand_continuations(
    hits: list[PatentHit],
    *,
    max_patents: int | None = None,
    max_depth: int = MAX_DEPTH,
    odp_client_factory=USPTOODPClient,
    epo_client_factory=EPOOPSClient,
) -> int:
    """Expand ``hits`` in-place with continuations, divisionals, and reissues.

    Returns the total number of new hits appended to ``hits``. Existing hits
    that were already present but match a continuation relationship have their
    ``family_role`` / ``parent_application_id`` filled in (no duplication).

    The function is fail-closed: missing credentials, auth, transport, and
    source unavailability errors are propagated so continuation coverage cannot
    be silently omitted.
    """
    if not hits:
        return 0

    settings = get_settings()
    if max_patents is None:
        max_patents = settings.search_max_family_patents

    odp_available = bool(settings.uspto_odp_api_key)
    epo_available = bool(settings.ops_consumer_key and settings.ops_consumer_secret)

    missing_sources = []
    if not odp_available:
        missing_sources.append("uspto_odp")
    if not epo_available:
        missing_sources.append("epo_ops")
    if missing_sources:
        raise ConfigurationError(
            "Continuation expansion requires configured USPTO ODP and EPO OPS credentials; "
            f"missing: {', '.join(missing_sources)}",
            source="continuation_expansion",
            step="search",
        )

    seen: dict[str, PatentHit] = {}
    for hit in hits:
        norm = normalize_patent_id(hit.patent_id)
        if norm:
            seen[norm] = hit

    total_added = 0

    # Frontier for BFS. Level 0 = the original hits.
    frontier = list(hits[:max_patents])

    odp_client_ctx = odp_client_factory() if odp_available else None
    epo_client_ctx = epo_client_factory() if epo_available else None

    odp_entered = False
    epo_entered = False
    try:
        odp_client = (
            await _enter_source_client(odp_client_ctx, "uspto_odp")
            if odp_client_ctx is not None
            else None
        )
        odp_entered = odp_client_ctx is not None
        epo_client = (
            await _enter_source_client(epo_client_ctx, "epo_ops")
            if epo_client_ctx is not None
            else None
        )
        epo_entered = epo_client_ctx is not None

        for depth in range(max_depth):
            next_frontier: list[PatentHit] = []
            for parent_hit in frontier:
                newly_added_for_parent: list[PatentHit] = []

                odp_added = 0
                if odp_client is not None and parent_hit.patent_id.upper().startswith("US"):
                    odp_added = await _expand_from_odp(
                        odp_client, parent_hit, seen, newly_added_for_parent
                    )

                epo_added = 0
                if epo_client is not None:
                    epo_added = await _expand_from_epo_family(
                        epo_client, parent_hit, seen, newly_added_for_parent
                    )

                added_here = odp_added + epo_added
                if added_here:
                    logger.info(
                        "continuation_expansion",
                        found=added_here,
                        added=added_here,
                        depth=depth,
                    )
                hits.extend(newly_added_for_parent)
                next_frontier.extend(newly_added_for_parent)
                total_added += added_here

            if not next_frontier:
                break
            frontier = next_frontier
    finally:
        if odp_client_ctx is not None and odp_entered:
            await odp_client_ctx.__aexit__(None, None, None)
        if epo_client_ctx is not None and epo_entered:
            await epo_client_ctx.__aexit__(None, None, None)

    logger.info("continuation_expansion_done", added=total_added)
    return total_added


__all__ = ["MAX_DEPTH", "expand_continuations"]
