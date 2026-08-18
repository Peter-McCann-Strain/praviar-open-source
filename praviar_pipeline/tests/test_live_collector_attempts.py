from __future__ import annotations

from praviar_pipeline.models.report import (
    EvidenceCollectionDirective,
    SourceHealthEntry,
    SourceStatus,
)
from praviar_pipeline.pipeline.runtime.live_collector_attempts import (
    build_live_collector_attempt,
    covered_patent_ids_if_count_satisfied,
)


def test_build_live_collector_attempt_marks_required_partial_coverage() -> None:
    entry = SourceHealthEntry(
        source="bigquery",
        status=SourceStatus.OK,
        patent_count=1,
        error_message="",
    )

    attempt = build_live_collector_attempt(
        directives=[
            EvidenceCollectionDirective(
                directive_id="claims",
                directive_type="collect_claims_text",
                target_patent_ids=["US1", "EP1"],
                recommended_adapters=["bigquery"],
                required_before_clear=True,
            )
        ],
        source="bigquery",
        entry=entry,
        target_patent_ids=["US1", "EP1"],
        covered_patent_ids=["US1"],
    )

    assert attempt.required_before_clear is True
    assert attempt.missing_patent_ids == ["EP1"]
    assert attempt.summary == "Collector covered some targeted records but left material gaps."


def test_covered_patent_ids_if_count_satisfied_requires_complete_count() -> None:
    partial_entry = SourceHealthEntry(
        source="orange_book",
        status=SourceStatus.OK,
        patent_count=1,
        attempted_count=2,
        covered_count=1,
        error_message="",
    )
    count_only_entry = SourceHealthEntry(
        source="orange_book",
        status=SourceStatus.OK,
        patent_count=2,
        error_message="",
    )
    complete_entry = SourceHealthEntry(
        source="orange_book",
        status=SourceStatus.OK,
        patent_count=2,
        attempted_count=2,
        covered_count=2,
        error_message="",
    )

    assert covered_patent_ids_if_count_satisfied(["US1", "US2"], partial_entry) == []
    assert covered_patent_ids_if_count_satisfied(["US1", "US2"], count_only_entry) == []
    assert covered_patent_ids_if_count_satisfied(["US1", "US2"], complete_entry) == [
        "US1",
        "US2",
    ]
