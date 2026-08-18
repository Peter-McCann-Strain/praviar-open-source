"""Deterministic validation-flow helpers for unified report pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from praviar_pipeline.models.report_sections import ValidationResult


def _collect_validation_issue_descriptions(
    validation_results: list[ValidationResult],
) -> list[str]:
    issues: list[str] = []
    for validation_result in validation_results:
        for issue in validation_result.issues:
            issues.append(issue.description)
    return issues


def _group_validation_issues_by_section(
    validation_results: list[ValidationResult],
) -> dict[str, list[str]]:
    # Only include ERROR-severity issues when deciding which sections to retry.
    # WARNING issues (assignee_match, ptab_format, word_count_bounds, patent_id_exists)
    # are recorded in corrections and logs but don't justify a full section regeneration.
    section_issues: dict[str, list[str]] = {}
    for validation_result in validation_results:
        for issue in validation_result.issues:
            if issue.severity != "error":
                continue
            section_id = issue.section_id or "general"
            section_issues.setdefault(section_id, []).append(issue.description)
    return section_issues


def _sections_needing_retry(section_issues: dict[str, list[str]]) -> set[str]:
    return {section_id for section_id in section_issues if section_id != "general"}


def _build_retry_context(
    context: str,
    issues_for_section: list[str],
    retry_attempt: int,
) -> str:
    feedback = "\n".join(f"- {issue}" for issue in issues_for_section)
    return (
        f"{context}\n\n"
        f"CRITICAL — your previous section had these validation "
        f"failures and was REJECTED:\n{feedback}\n\n"
        f"You MUST fix ALL issues. This is attempt "
        f"{retry_attempt + 2}. "
        f"Do NOT question whether patent IDs exist — they are "
        f"verified real patents from authoritative databases."
    )
