"""Shared helpers for matter evidence index construction."""

from __future__ import annotations


def unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result


def collect_material_patent_ids(
    analyses: list,
    analysis_failures: list,
    patent_hits: list | None = None,
) -> list[str]:
    material_patent_ids: list[str] = []
    seen_patent_ids: set[str] = set()
    for analysis in analyses:
        if analysis.patent_id in seen_patent_ids:
            continue
        material_patent_ids.append(analysis.patent_id)
        seen_patent_ids.add(analysis.patent_id)
    for failure in analysis_failures:
        if failure.patent_id in seen_patent_ids:
            continue
        material_patent_ids.append(failure.patent_id)
        seen_patent_ids.add(failure.patent_id)
    for patent_hit in patent_hits or []:
        patent_id = getattr(patent_hit, "patent_id", "")
        if not patent_id or patent_id in seen_patent_ids:
            continue
        material_patent_ids.append(patent_id)
        seen_patent_ids.add(patent_id)
    return material_patent_ids
