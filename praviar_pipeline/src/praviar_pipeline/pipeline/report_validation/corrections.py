"""Deterministic report auto-corrections."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.pipeline.report_validation.common import (
    _ANY_PATENT,
    _ANY_PATENT_RE,
    PATENT_RISK_RE,
    RISK_PATENT_RE,
    extract_patent_risk_pairs,
    find_analysis_by_normalized_patent_id,
    normalize_patent_id,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from praviar_pipeline.models.report_sections import (
        ReportSection,
        ValidationIssue,
        ValidationResult,
    )
    from praviar_pipeline.pipeline.report_data_store import ReportDataStore

logger = structlog.get_logger()

# Wider proximity patterns for CORRECTIONS ONLY (300 chars instead of 100).
# The validator uses 100-char windows for strictness; the corrector uses a wider net
# so long sentences (e.g. parenthetical assignee info) don't escape correction.
# Forward scan: matches any risk word that is immediately followed by "risk"
# (used by the exhaustive canonical correction pass — not the lazy PATENT_RISK_RE).
_RISK_WORD_FORWARD_RE = re.compile(
    r"\b(HIGH|MEDIUM|LOW|CLEAR)\b(?=[\s\-]*risk)",
    re.IGNORECASE,
)

_PATENT_RISK_WIDE_RE = re.compile(
    rf"({_ANY_PATENT})"
    r"[^.]{0,300}?"
    r"\b(HIGH|MEDIUM|LOW|CLEAR)\b"
    r"[\s\-]*risk",
    re.IGNORECASE,
)
_RISK_PATENT_WIDE_RE = re.compile(
    r"\b(HIGH|MEDIUM|LOW|CLEAR)\b"
    r"[\s\-]*risk"
    r"[^.]{0,300}?"
    rf"({_ANY_PATENT})",
    re.IGNORECASE,
)


def _replace_risk_near_patent(
    content: str,
    normalized_patent_id: str,
    old_risk: str,
    new_risk: str,
) -> str:
    """Replace risk level only within regex matches that reference a specific patent.

    Applies both narrow (100-char, matching the validator) and wide (300-char) proximity
    passes, in two orderings:

    1. PATENT_RISK (patent first): safe — patent establishes subject, risk follows.
       Only the matched risk-word group is changed (group-position replacement).

    2. RISK_PATENT (risk first): risky in multi-patent sentences.
       A backward-context check prevents changing a risk word that belongs to an
       earlier patent in the same sentence.  A factory function re-captures the
       current (post-PATENT_RISK) content for each pass so positions are correct.
    """
    _old_upper = old_risk.upper()
    _new_risk = new_risk
    _pid = normalized_patent_id

    def _sub_patent_first(m: re.Match[str]) -> str:
        # Match opens with target patent (group 1); risk word is at end (group 2).
        # Replace only group(2) at its exact byte position — never the entire span.
        if normalize_patent_id(m.group(1)) == _pid and m.group(2).upper() == _old_upper:
            text = m.group(0)
            rel_start = m.start(2) - m.start()
            rel_end = m.end(2) - m.start()
            return text[:rel_start] + _new_risk + text[rel_end:]
        return m.group(0)

    def _make_risk_first_sub(
        scanned_content: str,
    ) -> Callable[[re.Match[str]], str]:
        """Return a substitution function that uses scanned_content for backward lookups."""

        def _sub(m: re.Match[str]) -> str:
            # Match opens with risk word (group 1); target patent is at end (group 2).
            if not (m.group(1).upper() == _old_upper and normalize_patent_id(m.group(2)) == _pid):
                return m.group(0)

            # Guard: if another patent precedes this risk word in the same sentence,
            # that patent "owns" the risk mention — skip to avoid false correction.
            risk_pos = m.start()
            sent_start = scanned_content.rfind(".", 0, risk_pos) + 1
            preceding_in_sentence = scanned_content[sent_start:risk_pos]
            if _ANY_PATENT_RE.search(preceding_in_sentence):
                return m.group(0)

            # Guard: if another patent appears between the risk word and the target
            # patent in the span, the association is ambiguous — skip.
            span_between = m.group(0)[m.end(1) - m.start() : m.start(2) - m.start()]
            if _ANY_PATENT_RE.search(span_between):
                return m.group(0)

            # Safe to correct: replace only the opening risk word (group 1).
            text = m.group(0)
            rel_end = m.end(1) - m.start()
            return _new_risk + text[rel_end:]

        return _sub

    # Narrow PATENT_RISK pass (100-char window — matches the validator's threshold)
    content = PATENT_RISK_RE.sub(_sub_patent_first, content)
    # Narrow RISK_PATENT pass — re-capture updated content for backward lookups
    content = RISK_PATENT_RE.sub(_make_risk_first_sub(content), content)

    # Wide PATENT_RISK pass (300-char window — catches long sentences)
    content = _PATENT_RISK_WIDE_RE.sub(_sub_patent_first, content)
    # Wide RISK_PATENT pass
    content = _RISK_PATENT_WIDE_RE.sub(_make_risk_first_sub(content), content)

    return content


def _apply_risk_level_correction(
    section: ReportSection,
    issue: ValidationIssue,
) -> int:
    if not issue.expected or not issue.actual:
        return 0
    if issue.patent_id:
        updated = _replace_risk_near_patent(
            section.content,
            issue.patent_id,
            issue.actual,
            issue.expected,
        )
    else:
        updated = re.sub(
            re.escape(f"{issue.actual} risk"),
            f"{issue.expected} risk",
            section.content,
            flags=re.IGNORECASE,
        )
    if updated == section.content:
        return 0
    section.content = updated
    return 1


def _apply_cross_section_risk_correction(
    section: ReportSection,
    issue: ValidationIssue,
    data_store: ReportDataStore | None,
) -> int:
    if not issue.patent_id or not data_store:
        return 0
    analysis = find_analysis_by_normalized_patent_id(data_store, issue.patent_id)
    if not analysis:
        return 0
    canonical_risk = analysis.risk_level.value.upper()
    corrections = 0
    for raw_patent_id, stated_risk in extract_patent_risk_pairs(section.content):
        if normalize_patent_id(raw_patent_id) != issue.patent_id:
            continue
        if stated_risk == canonical_risk:
            continue
        updated = _replace_risk_near_patent(
            section.content,
            issue.patent_id,
            stated_risk,
            canonical_risk,
        )
        if updated != section.content:
            section.content = updated
            corrections += 1
    return corrections


def _fact_replacement_candidates(validator_name: str, actual: str) -> list[str]:
    candidates = [actual]
    if validator_name == "date_match":
        candidates.append(actual.replace("-", "/"))
    return candidates


def _apply_fact_correction(
    section: ReportSection,
    issue: ValidationIssue,
    *,
    validator_name: str,
) -> int:
    if not issue.expected or not issue.actual:
        return 0
    if validator_name == "assignee_match" and re.match(
        r"^(HIGH|MEDIUM|LOW|CLEAR)\b",
        issue.actual,
        re.IGNORECASE,
    ):
        return 0
    for candidate in _fact_replacement_candidates(validator_name, issue.actual):
        if candidate in section.content:
            section.content = section.content.replace(candidate, issue.expected)
            return 1
    return 0


def _apply_issue_correction(
    section: ReportSection,
    validation_result: ValidationResult,
    issue: ValidationIssue,
    data_store: ReportDataStore | None,
) -> int:
    if validation_result.validator_name == "risk_level_match":
        return _apply_risk_level_correction(section, issue)
    if validation_result.validator_name == "cross_section_risk_consistency":
        return _apply_cross_section_risk_correction(section, issue, data_store)
    if validation_result.validator_name in {"date_match", "assignee_match"}:
        return _apply_fact_correction(
            section,
            issue,
            validator_name=validation_result.validator_name,
        )
    return 0


def _apply_exhaustive_corrections(
    sections: list[ReportSection],
    data_store: ReportDataStore | None,
) -> int:
    if not data_store:
        return 0
    corrections = 0
    for _ in range(5):
        pass_corrections = _exhaustive_canonical_correction(sections, data_store)
        corrections += pass_corrections
        if pass_corrections == 0:
            break
    return corrections


def apply_corrections(
    sections: list[ReportSection],
    validation_results: list[ValidationResult],
    data_store: ReportDataStore | None = None,
) -> list[ReportSection]:
    """Apply deterministic corrections for issues where the fix is unambiguous."""
    corrections_applied = 0

    for validation_result in validation_results:
        for issue in validation_result.issues:
            if not issue.section_id:
                continue

            for section in sections:
                if section.section_id != issue.section_id:
                    continue
                corrections_applied += _apply_issue_correction(
                    section,
                    validation_result,
                    issue,
                    data_store,
                )

    corrections_applied += _apply_exhaustive_corrections(sections, data_store)

    if corrections_applied:
        logger.info("report_auto_corrections_applied", count=corrections_applied)

    return sections


_Replacement = tuple[int, int, str]


def _append_replacement(
    replacements: list[_Replacement],
    *,
    start: int,
    end: int,
    canonical_risk: str,
) -> None:
    if any(
        existing_start <= start < existing_end for existing_start, existing_end, _ in replacements
    ):
        return
    replacements.append((start, end, canonical_risk))


def _forward_scan_end(
    content: str,
    patent_match: re.Match[str],
    normalized_patent_id: str,
) -> int:
    scan_start = patent_match.end()
    scan_end = min(len(content), scan_start + 400)
    next_dot = content.find(".", scan_start, scan_end)
    if next_dot >= 0:
        scan_end = next_dot + 1
    window = content[scan_start:scan_end]
    for next_patent_match in _ANY_PATENT_RE.finditer(window):
        if normalize_patent_id(next_patent_match.group(0)) != normalized_patent_id:
            return scan_start + next_patent_match.start()
    return scan_end


def _collect_forward_replacements(
    content: str,
    patent_match: re.Match[str],
    *,
    normalized_patent_id: str,
    canonical_risk: str,
    replacements: list[_Replacement],
) -> None:
    scan_start = patent_match.end()
    scan_end = _forward_scan_end(content, patent_match, normalized_patent_id)
    window = content[scan_start:scan_end]
    for risk_match in _RISK_WORD_FORWARD_RE.finditer(window):
        if risk_match.group(1).upper() == canonical_risk:
            continue
        _append_replacement(
            replacements,
            start=scan_start + risk_match.start(1),
            end=scan_start + risk_match.end(1),
            canonical_risk=canonical_risk,
        )


def _backward_scan_start(
    content: str,
    patent_match: re.Match[str],
    normalized_patent_id: str,
) -> int | None:
    back_end = patent_match.start()
    previous_dot = content.rfind(".", 0, back_end)
    back_start = previous_dot + 1 if previous_dot >= 0 else 0
    back_window = content[back_start:back_end]
    has_other_patent = any(
        normalize_patent_id(match.group(0)) != normalized_patent_id
        for match in _ANY_PATENT_RE.finditer(back_window)
    )
    return None if has_other_patent else back_start


def _collect_backward_replacements(
    content: str,
    patent_match: re.Match[str],
    *,
    normalized_patent_id: str,
    canonical_risk: str,
    replacements: list[_Replacement],
) -> None:
    back_end = patent_match.start()
    back_start = _backward_scan_start(content, patent_match, normalized_patent_id)
    if back_start is None:
        return
    back_window = content[back_start:back_end]
    for risk_match in _RISK_WORD_FORWARD_RE.finditer(back_window):
        if risk_match.group(1).upper() == canonical_risk:
            continue
        _append_replacement(
            replacements,
            start=back_start + risk_match.start(1),
            end=back_start + risk_match.end(1),
            canonical_risk=canonical_risk,
        )


def _canonical_risk_for_patent_match(
    patent_match: re.Match[str],
    data_store: ReportDataStore,
) -> tuple[str, str] | None:
    normalized_patent_id = normalize_patent_id(patent_match.group(0))
    analysis = find_analysis_by_normalized_patent_id(data_store, normalized_patent_id)
    if not analysis:
        return None
    return normalized_patent_id, analysis.risk_level.value.upper()


def _apply_replacements(content: str, replacements: list[_Replacement]) -> str:
    for start, end, replacement in sorted(replacements, key=lambda item: -item[0]):
        content = content[:start] + replacement + content[end:]
    return content


def _correct_section_canonical_risks(
    section: ReportSection,
    data_store: ReportDataStore,
) -> int:
    content = section.content
    replacements: list[_Replacement] = []
    for patent_match in _ANY_PATENT_RE.finditer(content):
        canonical_risk = _canonical_risk_for_patent_match(patent_match, data_store)
        if canonical_risk is None:
            continue
        normalized_patent_id, risk = canonical_risk
        _collect_forward_replacements(
            content,
            patent_match,
            normalized_patent_id=normalized_patent_id,
            canonical_risk=risk,
            replacements=replacements,
        )
        _collect_backward_replacements(
            content,
            patent_match,
            normalized_patent_id=normalized_patent_id,
            canonical_risk=risk,
            replacements=replacements,
        )
    if not replacements:
        return 0
    section.content = _apply_replacements(content, replacements)
    return len(replacements)


def _exhaustive_canonical_correction(
    sections: list[ReportSection],
    data_store: ReportDataStore,
) -> int:
    """Scan every patent ID occurrence in both directions and correct non-canonical risk words.

    Forward scan: catches "patent_ID ... RISK risk" patterns.
    Backward scan: catches "RISK risk ... patent_ID" patterns when no other patent
    appears between the sentence boundary and the target patent ID (safe attribution).

    Works as a position-safe, right-to-left batch replacer to avoid shifting issues.
    """
    return sum(_correct_section_canonical_risks(section, data_store) for section in sections)
