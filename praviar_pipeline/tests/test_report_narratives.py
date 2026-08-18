from __future__ import annotations

from praviar_pipeline.pipeline.report.narratives import _extract_per_patent_narratives


def test_extract_per_patent_narratives_splits_key_patent_blocks() -> None:
    content = (
        "### US1234567B2\nFirst narrative paragraph.\n### US7654321B1\nSecond narrative paragraph."
    )

    narratives = _extract_per_patent_narratives(content)

    assert narratives == {
        "US1234567B2": "### US1234567B2\nFirst narrative paragraph.",
        "US7654321B1": "### US7654321B1\nSecond narrative paragraph.",
    }
