"""Compound library service helpers."""

from __future__ import annotations

import uuid
from collections import Counter
from typing import cast

import structlog
from praviar_pipeline.models.report_source_spans import ClaimSourceSpanMap
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from api.db.models import Analysis, AnalysisStatus, Compound, OrganizationCompound
from api.errors import APIError
from api.schemas.compounds import CompoundResponse
from api.services.report_access import (
    validate_claim_source_span_map,
    validate_report_publishability,
)

logger = structlog.get_logger()

MAX_COMPOUND_SEARCH_LENGTH = 200
LIKE_ESCAPE_CHARACTER = "\\"


def org_compound_query(org_id: uuid.UUID):
    """Select globally deduplicated identity with organization-local usage metadata."""
    return (
        select(
            Compound,
            OrganizationCompound.display_name,
            OrganizationCompound.first_analyzed_at,
            OrganizationCompound.analysis_count,
        )
        .options(
            load_only(
                Compound.id,
                Compound.canonical_smiles,
                Compound.inchi_key,
                Compound.molecular_formula,
                Compound.molecular_weight,
                Compound.functional_groups,
                Compound.pubchem_cid,
            )
        )
        .join(
            OrganizationCompound,
            OrganizationCompound.compound_id == Compound.id,
        )
        .where(OrganizationCompound.org_id == org_id)
    )


def _compound_response_from_row(row) -> CompoundResponse:  # noqa: ANN001
    compound, display_name, first_analyzed_at, analysis_count = row
    return CompoundResponse(
        id=compound.id,
        canonical_smiles=compound.canonical_smiles,
        inchi_key=compound.inchi_key,
        name=display_name,
        molecular_formula=compound.molecular_formula,
        molecular_weight=compound.molecular_weight,
        functional_groups=compound.functional_groups,
        pubchem_cid=compound.pubchem_cid,
        first_analyzed_at=first_analyzed_at,
        analysis_count=analysis_count,
    )


def escape_like_pattern(value: str) -> str:
    """Escape SQL LIKE wildcards while preserving literal chemistry input."""
    return (
        value.replace(LIKE_ESCAPE_CHARACTER, LIKE_ESCAPE_CHARACTER * 2)
        .replace("%", f"{LIKE_ESCAPE_CHARACTER}%")
        .replace("_", f"{LIKE_ESCAPE_CHARACTER}_")
    )


async def list_compounds_for_org(
    db: AsyncSession,
    org_id: uuid.UUID,
    *,
    search: str | None,
    page: int,
    per_page: int,
) -> dict:
    """List compounds analyzed by the given org."""
    query = org_compound_query(org_id)

    if search:
        search_pattern = f"%{escape_like_pattern(search)}%"
        query = query.where(
            OrganizationCompound.display_name.ilike(
                search_pattern,
                escape=LIKE_ESCAPE_CHARACTER,
            )
            | Compound.canonical_smiles.ilike(
                search_pattern,
                escape=LIKE_ESCAPE_CHARACTER,
            )
            | Compound.inchi_key.ilike(
                search_pattern,
                escape=LIKE_ESCAPE_CHARACTER,
            )
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    paged_query = (
        query.order_by(
            OrganizationCompound.first_analyzed_at.desc(),
            Compound.id.asc(),
        )
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = (await db.execute(paged_query)).all()
    items = [_compound_response_from_row(row) for row in rows]

    return {"items": items, "total": total, "page": page, "per_page": per_page}


async def get_compound_for_org(
    db,
    org_id: uuid.UUID,
    compound_id: uuid.UUID,
) -> CompoundResponse:
    """Load a single org-scoped compound or raise 404."""
    query = org_compound_query(org_id).where(Compound.id == compound_id)
    row = (await db.execute(query)).one_or_none()
    if not row:
        logger.warning("compound_not_found", compound_id=str(compound_id), org_id=str(org_id))
        raise APIError(404, "Not Found", "Compound not found")
    return _compound_response_from_row(row)


def _extract_provenanced_patent_ids(
    report_data: object,
    *,
    analysis_id: object,
    org_id: object,
) -> set[str] | None:
    """Extract patent IDs only when the report's patent list is provenance-covered."""
    if not isinstance(report_data, dict) or not report_data:
        return None
    try:
        validate_report_publishability(
            report_data,
            analysis_id=str(analysis_id),
            org_id=str(org_id),
        )
        validate_claim_source_span_map(report_data.get("claim_source_span_map"))
        source_map = ClaimSourceSpanMap.model_validate(report_data["claim_source_span_map"])
    except (KeyError, ValueError):
        return None

    patent_analyses = report_data.get("patent_analyses")
    if not isinstance(patent_analyses, list):
        return None

    patents = set()
    for patent_analysis in patent_analyses:
        if isinstance(patent_analysis, dict) and patent_analysis.get("patent_id"):
            patents.add(patent_analysis["patent_id"])
    supported_patent_ids = {
        entry.patent_id
        for entry in source_map.entries
        if entry.patent_id
        and entry.customer_visible
        and entry.support_status == "supported"
        and entry.source_span_ids
    }
    if not patents.issubset(supported_patent_ids):
        return None
    return patents


async def _load_latest_report_patents_by_compound(
    db,
    org_id: uuid.UUID,
    compounds: list[CompoundResponse],
) -> dict[uuid.UUID, set[str]]:
    """Fetch the newest publishable completed report for each compound identity."""
    if not compounds:
        return {}

    smiles_values = sorted({compound.canonical_smiles for compound in compounds})
    inchi_keys = sorted({compound.inchi_key for compound in compounds if compound.inchi_key})
    report_inchi_key = Analysis.report_data[("compound", "inchi_key")].astext
    identity_filters = [Analysis.compound_smiles.in_(smiles_values)]
    if inchi_keys:
        identity_filters.append(report_inchi_key.in_(inchi_keys))

    candidate_query = (
        select(
            Analysis.id.label("analysis_id"),
            Analysis.compound_smiles,
            Analysis.report_data,
        )
        .where(
            Analysis.org_id == org_id,
            or_(*identity_filters),
            Analysis.status == AnalysisStatus.COMPLETED,
            Analysis.report_data.isnot(None),
            func.jsonb_typeof(Analysis.report_data) == "object",
            Analysis.report_data != {},
        )
        .order_by(
            Analysis.completed_at.desc(),
            Analysis.id.desc(),
        )
    )
    analysis_rows = (await db.execute(candidate_query)).all()

    compound_id_by_inchi = {
        compound.inchi_key: compound.id for compound in compounds if compound.inchi_key
    }
    compound_ids_by_smiles: dict[str, list[uuid.UUID]] = {}
    for compound in compounds:
        compound_ids_by_smiles.setdefault(compound.canonical_smiles, []).append(compound.id)

    patents_by_compound_id: dict[uuid.UUID, set[str]] = {}
    for analysis_id, compound_smiles, report_data in analysis_rows:
        report_compound = report_data.get("compound") if isinstance(report_data, dict) else None
        report_inchi = (
            str(report_compound.get("inchi_key", "")).strip()
            if isinstance(report_compound, dict)
            else ""
        )
        if report_inchi:
            compound_id = compound_id_by_inchi.get(report_inchi)
            if compound_id is None:
                continue
        else:
            matching_ids = compound_ids_by_smiles.get(compound_smiles, [])
            if not compound_smiles or len(matching_ids) != 1:
                continue
            compound_id = matching_ids[0]

        if compound_id in patents_by_compound_id:
            continue
        patent_ids = _extract_provenanced_patent_ids(
            report_data,
            analysis_id=analysis_id,
            org_id=org_id,
        )
        if patent_ids is None:
            logger.warning(
                "compound_compare_report_failed_provenance",
            )
            continue
        patents_by_compound_id[compound_id] = patent_ids
    return patents_by_compound_id


async def compare_compounds_for_org(
    db,
    org_id: uuid.UUID,
    ids: list[uuid.UUID],
) -> dict:
    """Compare 2-4 org-scoped compounds and compute overlapping patents."""
    query = org_compound_query(org_id).where(Compound.id.in_(ids))
    rows = (await db.execute(query)).all()
    compounds = [_compound_response_from_row(row) for row in rows]
    if len(compounds) != len(ids):
        raise APIError(404, "Not Found", "One or more compounds not found")

    compounds_by_id = {compound.id: compound for compound in compounds}
    ordered_compounds = [compounds_by_id[compound_id] for compound_id in ids]
    latest_patents_by_compound_id = await _load_latest_report_patents_by_compound(
        db,
        org_id,
        ordered_compounds,
    )

    all_patents = Counter(
        patent_id
        for compound in ordered_compounds
        for patent_id in latest_patents_by_compound_id.get(compound.id, set())
    )
    overlapping: list[dict[str, str | int]] = []
    for patent_id, compound_count in all_patents.items():
        if compound_count >= 2:
            overlapping.append({"patent_id": patent_id, "compound_count": compound_count})
    overlapping.sort(
        key=lambda item: (
            -cast(int, item["compound_count"]),
            cast(str, item["patent_id"]),
        )
    )

    return {"compounds": ordered_compounds, "overlapping_patents": overlapping}
