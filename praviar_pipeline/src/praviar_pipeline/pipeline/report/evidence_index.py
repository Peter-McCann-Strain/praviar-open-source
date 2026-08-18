"""Canonical matter evidence inventory builders for final reports."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from praviar_pipeline.models.report import MatterEvidenceIndex
from praviar_pipeline.pipeline.report.evidence_index_records import (
    build_family_record,
    build_patent_record,
    collect_material_patent_ids,
    unique_strings,
)

if TYPE_CHECKING:
    from praviar_pipeline.models.report import PatentEvidenceRecord


def build_matter_evidence_index(
    *,
    analyses: list,
    doe_assessments: list,
    invalidity_assessments: list,
    analysis_failures: list | None,
    patent_hits: list | None,
    prosecution_dossiers: list | None,
    critic_report,
    source_health,
) -> MatterEvidenceIndex:
    """Build a canonical evidence inventory for all material patents in the matter."""
    analysis_failures = analysis_failures or []
    patent_hits = patent_hits or []

    analysis_by_id = {analysis.patent_id: analysis for analysis in analyses}
    doe_patent_ids = {assessment.patent_id for assessment in doe_assessments}
    invalidity_patent_ids = {assessment.patent_id for assessment in invalidity_assessments}
    failure_by_id = {failure.patent_id: failure for failure in analysis_failures}
    detail_map = {hit.patent_id: hit for hit in patent_hits if getattr(hit, "patent_id", "")}
    dossier_map = {
        (
            dossier.get("patent_id", "")
            if isinstance(dossier, dict)
            else getattr(dossier, "patent_id", "")
        ): dossier
        for dossier in (prosecution_dossiers or [])
        if (
            dossier.get("patent_id", "")
            if isinstance(dossier, dict)
            else getattr(dossier, "patent_id", "")
        )
    }

    critic_findings_by_patent: dict[str, list] = defaultdict(list)
    critic_flagged_patent_ids: list[str] = []
    if critic_report:
        for finding in getattr(critic_report, "findings", []) or []:
            patent_id = getattr(finding, "patent_id", "")
            if not patent_id:
                continue
            critic_findings_by_patent[patent_id].append(finding)
            critic_flagged_patent_ids.append(patent_id)

    material_patent_ids = collect_material_patent_ids(
        analyses,
        analysis_failures,
        patent_hits,
    )

    patent_records = []
    family_groups: dict[str, list[PatentEvidenceRecord]] = defaultdict(list)

    for patent_id in material_patent_ids:
        record = build_patent_record(
            patent_id,
            analysis_by_id=analysis_by_id,
            detail_map=detail_map,
            doe_patent_ids=doe_patent_ids,
            invalidity_patent_ids=invalidity_patent_ids,
            failure_by_id=failure_by_id,
            critic_findings_by_patent=critic_findings_by_patent,
            dossier_map=dossier_map,
        )
        patent_records.append(record)
        if record.family_id:
            family_groups[record.family_id].append(record)

    family_records = []
    for family_id, records in sorted(family_groups.items()):
        family_records.append(build_family_record(family_id, records, detail_map))

    source_names = unique_strings(
        [
            entry.source
            for entry in getattr(source_health, "entries", []) or []
            if getattr(getattr(entry, "status", None), "value", "") != "skipped"
        ]
        + [source_name for record in patent_records for source_name in record.source_names]
    )
    authoritative_source_names = unique_strings(
        [
            source_name
            for record in patent_records
            for source_name in record.authoritative_source_names
        ]
    )
    supporting_source_names = unique_strings(
        [source_name for record in patent_records for source_name in record.supporting_source_names]
    )
    clearance_grade_ready_patent_ids = [
        record.patent_id for record in patent_records if record.clearance_grade_ready
    ]
    incomplete_patent_ids = [
        record.patent_id for record in patent_records if not record.clearance_grade_ready
    ]
    clearance_grade_ready_family_ids = [
        record.family_id for record in family_records if record.clearance_grade_ready
    ]
    incomplete_family_ids = [
        record.family_id for record in family_records if not record.clearance_grade_ready
    ]

    return MatterEvidenceIndex(
        source_names=source_names,
        authoritative_source_names=authoritative_source_names,
        supporting_source_names=supporting_source_names,
        material_patent_count=len(patent_records),
        family_count=len(family_records),
        analysis_failure_patent_ids=[failure.patent_id for failure in analysis_failures],
        critic_flagged_patent_ids=unique_strings(critic_flagged_patent_ids),
        clearance_grade_ready_patent_ids=clearance_grade_ready_patent_ids,
        incomplete_patent_ids=incomplete_patent_ids,
        clearance_grade_ready_family_ids=clearance_grade_ready_family_ids,
        incomplete_family_ids=incomplete_family_ids,
        patent_records=patent_records,
        family_records=family_records,
    )
