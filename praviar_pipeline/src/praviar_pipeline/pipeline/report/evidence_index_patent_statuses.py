"""Status and gating helpers for patent-level evidence records."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.models.report import RecordComponentStatus, RecordComponentStatusValue
from praviar_pipeline.pipeline.report.evidence_index_shared import unique_strings

if TYPE_CHECKING:
    from praviar_pipeline.models.report import PatentEvidenceRecord


def build_patent_gate_failures(record: PatentEvidenceRecord) -> list[str]:
    failures: list[str] = []
    statuses = {status.component: status.status.value for status in record.component_statuses}
    if statuses.get("claim_level_analysis") == RecordComponentStatusValue.FAILED.value:
        failures.append("analysis_failed")
    if statuses.get("claim_level_analysis") == RecordComponentStatusValue.MISSING.value:
        failures.append("analysis_missing")
    if (
        record.analysis_completed
        and record.claims_analyzed_count == 0
        and statuses.get("claim_level_analysis") != RecordComponentStatusValue.NOT_APPLICABLE.value
    ):
        failures.append("no_claim_level_analysis")
    if statuses.get("claims_text") == RecordComponentStatusValue.MISSING.value:
        failures.append("missing_claims_text")
    if statuses.get("authoritative_records") == RecordComponentStatusValue.MISSING.value:
        failures.append("missing_authoritative_records")
    if statuses.get("family_context") == RecordComponentStatusValue.MISSING.value:
        failures.append("missing_family_context")
    if statuses.get("us_prosecution_context") == RecordComponentStatusValue.MISSING.value:
        failures.append("missing_us_prosecution_context")
    if statuses.get("us_file_wrapper_dossier") == RecordComponentStatusValue.MISSING.value:
        failures.append("missing_us_file_wrapper_dossier")
    if statuses.get("ep_register_context") == RecordComponentStatusValue.MISSING.value:
        failures.append("missing_ep_register_context")
    if any(severity in {"critical", "major"} for severity in record.critic_issue_severities):
        failures.append("critic_major_issue")
    if (
        record.risk_level in {"high", "medium"}
        and statuses.get("doe_assessment") == RecordComponentStatusValue.MISSING.value
    ):
        failures.append("blocking_patent_missing_doe_assessment")
    if (
        record.risk_level in {"high", "medium"}
        and statuses.get("invalidity_assessment") == RecordComponentStatusValue.MISSING.value
    ):
        failures.append("blocking_patent_missing_invalidity_assessment")
    return unique_strings(failures)


def build_patent_component_statuses(
    *,
    patent_id: str,
    jurisdiction: str,
    has_claims_text: bool,
    has_family_context: bool,
    has_authoritative_records: bool,
    has_us_prosecution_context: bool,
    has_us_file_wrapper_dossier: bool,
    has_ep_register_context: bool,
    has_ptab_proceedings: bool,
    has_orange_book_listing: bool,
    analysis_completed: bool,
    analysis_failed: bool,
    claims_analyzed_count: int,
    doe_assessed: bool,
    invalidity_assessed: bool,
) -> list[RecordComponentStatus]:
    """Build the per-patent collection ledger used by evidence and gating."""

    def collected_or_missing(
        *,
        component: str,
        collected: bool,
        source_name: str,
        authority_expected: bool,
        required_before_clear: bool,
        note_collected: str,
        note_missing: str,
    ) -> RecordComponentStatus:
        return RecordComponentStatus(
            component=component,
            status=(
                RecordComponentStatusValue.COLLECTED
                if collected
                else RecordComponentStatusValue.MISSING
            ),
            source_name=source_name,
            authority_expected=authority_expected,
            required_before_clear=required_before_clear,
            note=note_collected if collected else note_missing,
        )

    statuses = [
        collected_or_missing(
            component="claims_text",
            collected=has_claims_text,
            source_name="patentsview",
            authority_expected=True,
            required_before_clear=True,
            note_collected="Claims text is present for this patent.",
            note_missing="Claims text is still missing for this patent.",
        ),
        collected_or_missing(
            component="family_context",
            collected=has_family_context,
            source_name="family_record",
            authority_expected=True,
            required_before_clear=True,
            note_collected="Family context is available for this patent.",
            note_missing="Family context is still missing for this patent.",
        ),
        collected_or_missing(
            component="authoritative_records",
            collected=has_authoritative_records,
            source_name="authoritative_record",
            authority_expected=True,
            required_before_clear=True,
            note_collected="Authoritative record support is available for this patent.",
            note_missing="Authoritative record support is still missing for this patent.",
        ),
        RecordComponentStatus(
            component="claim_level_analysis",
            status=(
                RecordComponentStatusValue.FAILED
                if analysis_failed
                else RecordComponentStatusValue.COLLECTED
                if analysis_completed and claims_analyzed_count > 0
                else RecordComponentStatusValue.MISSING
            ),
            source_name="step4_analyze",
            authority_expected=False,
            required_before_clear=True,
            note=(
                "Claim-level analysis completed."
                if analysis_completed and claims_analyzed_count > 0
                else "Claim-level analysis failed during runtime."
                if analysis_failed
                else "Claim-level analysis has not been completed."
            ),
        ),
        RecordComponentStatus(
            component="doe_assessment",
            status=(
                RecordComponentStatusValue.COLLECTED
                if doe_assessed
                else RecordComponentStatusValue.MISSING
            ),
            source_name="step5_doe",
            authority_expected=False,
            required_before_clear=False,
            note=(
                "Doctrine of equivalents assessment is present."
                if doe_assessed
                else "Doctrine of equivalents assessment is not present."
            ),
        ),
        RecordComponentStatus(
            component="invalidity_assessment",
            status=(
                RecordComponentStatusValue.COLLECTED
                if invalidity_assessed
                else RecordComponentStatusValue.MISSING
            ),
            source_name="step6_invalidity",
            authority_expected=False,
            required_before_clear=False,
            note=(
                "Invalidity assessment is present."
                if invalidity_assessed
                else "Invalidity assessment is not present."
            ),
        ),
        RecordComponentStatus(
            component="ptab_record",
            status=(
                RecordComponentStatusValue.COLLECTED
                if has_ptab_proceedings
                else RecordComponentStatusValue.NOT_APPLICABLE
            ),
            source_name="ptab",
            authority_expected=True,
            required_before_clear=False,
            note=(
                "PTAB record is present for this patent."
                if has_ptab_proceedings
                else "No PTAB record is currently associated with this patent."
            ),
        ),
        RecordComponentStatus(
            component="orange_book_record",
            status=(
                RecordComponentStatusValue.COLLECTED
                if has_orange_book_listing
                else RecordComponentStatusValue.NOT_APPLICABLE
            ),
            source_name="orange_book",
            authority_expected=True,
            required_before_clear=False,
            note=(
                "Orange Book record is present for this patent."
                if has_orange_book_listing
                else "No Orange Book record is currently associated with this patent."
            ),
        ),
    ]

    if jurisdiction == "US":
        statuses.extend(
            [
                collected_or_missing(
                    component="us_prosecution_context",
                    collected=has_us_prosecution_context,
                    source_name="uspto_odp",
                    authority_expected=True,
                    required_before_clear=False,
                    note_collected="U.S. prosecution context is available.",
                    note_missing="U.S. prosecution context is still missing.",
                ),
                collected_or_missing(
                    component="us_file_wrapper_dossier",
                    collected=has_us_file_wrapper_dossier,
                    source_name="uspto_odp",
                    authority_expected=True,
                    required_before_clear=True,
                    note_collected="A dossier-grade U.S. file wrapper is available.",
                    note_missing="A dossier-grade U.S. file wrapper is still missing.",
                ),
            ]
        )
    else:
        statuses.extend(
            [
                RecordComponentStatus(
                    component="us_prosecution_context",
                    status=RecordComponentStatusValue.NOT_APPLICABLE,
                    source_name="uspto_odp",
                    authority_expected=True,
                    required_before_clear=False,
                    note="U.S. prosecution context is not applicable to this patent.",
                ),
                RecordComponentStatus(
                    component="us_file_wrapper_dossier",
                    status=RecordComponentStatusValue.NOT_APPLICABLE,
                    source_name="uspto_odp",
                    authority_expected=True,
                    required_before_clear=True,
                    note="A U.S. file-wrapper dossier is not applicable to this patent.",
                ),
            ]
        )

    if jurisdiction == "EP":
        statuses.append(
            collected_or_missing(
                component="ep_register_context",
                collected=has_ep_register_context,
                source_name="epo_register",
                authority_expected=True,
                required_before_clear=True,
                note_collected="EP register context is available.",
                note_missing="EP register context is still missing.",
            )
        )
    else:
        statuses.append(
            RecordComponentStatus(
                component="ep_register_context",
                status=RecordComponentStatusValue.NOT_APPLICABLE,
                source_name="epo_register",
                authority_expected=True,
                required_before_clear=True,
                note="EP register context is not applicable to this patent.",
            )
        )

    return statuses
