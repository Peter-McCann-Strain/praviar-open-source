"""Family-level evidence record builders."""

from __future__ import annotations

from praviar_pipeline.models.report import (
    FamilyEvidenceRecord,
    PatentEvidenceRecord,
    RecordComponentStatus,
    RecordComponentStatusValue,
)
from praviar_pipeline.pipeline.report.evidence_index_shared import unique_strings
from praviar_pipeline.utils.patent_family import pending_family_member_ids


def build_family_gate_failures(
    *,
    family_id: str,
    jurisdictions: list[str],
    broadest_patent_id: str,
    incomplete_patent_ids: list[str],
) -> list[str]:
    failures: list[str] = []
    if not family_id:
        failures.append("missing_family_id")
    if not jurisdictions:
        failures.append("missing_family_jurisdictions")
    if not broadest_patent_id:
        failures.append("missing_broadest_material_patent")
    if incomplete_patent_ids:
        failures.append("incomplete_material_patent_records")
    return failures


def _family_component_status(
    *,
    component: str,
    source_name: str,
    statuses: list[str],
    authority_expected: bool = True,
    required_before_clear: bool = False,
    collected_note: str,
    missing_note: str,
) -> RecordComponentStatus:
    unique_statuses = set(statuses)
    if not unique_statuses:
        status = RecordComponentStatusValue.MISSING
        note = missing_note
    elif unique_statuses <= {RecordComponentStatusValue.NOT_APPLICABLE.value}:
        status = RecordComponentStatusValue.NOT_APPLICABLE
        note = f"{component.replace('_', ' ')} is not applicable across this family."
    elif RecordComponentStatusValue.MISSING.value in unique_statuses:
        status = RecordComponentStatusValue.MISSING
        note = missing_note
    elif RecordComponentStatusValue.FAILED.value in unique_statuses:
        status = RecordComponentStatusValue.FAILED
        note = missing_note
    else:
        status = RecordComponentStatusValue.COLLECTED
        note = collected_note
    return RecordComponentStatus(
        component=component,
        status=status,
        source_name=source_name,
        authority_expected=authority_expected,
        required_before_clear=required_before_clear,
        note=note,
    )


def build_family_record(
    family_id: str,
    records: list[PatentEvidenceRecord],
    detail_map: dict[str, object],
) -> FamilyEvidenceRecord:
    detail = next(
        (
            detail_map.get(record.patent_id)
            for record in records
            if detail_map.get(record.patent_id)
        ),
        None,
    )
    family = getattr(detail, "family", None) if detail else None
    members = list(getattr(family, "members", []) or []) if family else []
    pending_member_count = max(
        len(pending_family_member_ids(members)),
        int(any("pending_family" in record.future_risk_signals for record in records)),
    )
    clearance_grade_ready_patent_ids = [
        record.patent_id for record in records if record.clearance_grade_ready
    ]
    incomplete_patent_ids = [
        record.patent_id for record in records if not record.clearance_grade_ready
    ]
    jurisdictions = unique_strings(
        [
            jurisdiction
            for record in records
            for jurisdiction in (
                record.family_jurisdictions
                or ([record.jurisdiction] if record.jurisdiction else [])
            )
        ]
    )
    broadest_patent_id = next(
        (record.patent_id for record in records if record.family_broadest),
        records[0].patent_id,
    )
    authoritative_record_categories = unique_strings(
        [category for record in records for category in record.authoritative_record_categories]
    )
    by_component: dict[str, list[str]] = {}
    for record in records:
        for component_status in record.component_statuses:
            by_component.setdefault(component_status.component, []).append(
                component_status.status.value
            )
    return FamilyEvidenceRecord(
        family_id=family_id,
        material_patent_ids=[record.patent_id for record in records],
        jurisdictions=jurisdictions,
        broadest_patent_id=broadest_patent_id,
        member_count=len(members) if members else len(records),
        pending_member_count=pending_member_count,
        blocking_patent_ids=[
            record.patent_id for record in records if record.risk_level in {"high", "medium"}
        ],
        orange_book_listed_patent_ids=[
            record.patent_id for record in records if record.has_orange_book_listing
        ],
        authoritative_record_categories=authoritative_record_categories,
        component_statuses=[
            _family_component_status(
                component="family_context",
                source_name="family_record",
                statuses=by_component.get("family_context", []),
                required_before_clear=True,
                collected_note="Family context is collected across the material family.",
                missing_note="Family context is incomplete across the material family.",
            ),
            _family_component_status(
                component="claims_text",
                source_name="patentsview",
                statuses=by_component.get("claims_text", []),
                required_before_clear=True,
                collected_note="Claims text is collected across the material family.",
                missing_note="Claims text is incomplete across the material family.",
            ),
            _family_component_status(
                component="claim_level_analysis",
                source_name="step4_analyze",
                statuses=by_component.get("claim_level_analysis", []),
                authority_expected=False,
                required_before_clear=True,
                collected_note="Claim-level analysis is complete across the material family.",
                missing_note="Claim-level analysis remains incomplete across the material family.",
            ),
            _family_component_status(
                component="authoritative_records",
                source_name="family_record",
                statuses=by_component.get("authoritative_records", []),
                required_before_clear=True,
                collected_note="Authoritative record coverage exists across the material family.",
                missing_note=(
                    "Authoritative record coverage remains incomplete across the material family."
                ),
            ),
        ],
        clearance_grade_ready=len(incomplete_patent_ids) == 0,
        gate_failures=build_family_gate_failures(
            family_id=family_id,
            jurisdictions=jurisdictions,
            broadest_patent_id=broadest_patent_id,
            incomplete_patent_ids=incomplete_patent_ids,
        ),
        clearance_grade_ready_patent_ids=clearance_grade_ready_patent_ids,
        incomplete_patent_ids=incomplete_patent_ids,
    )
