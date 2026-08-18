"""Direct tests for extracted Step 2b ranking helpers."""

from __future__ import annotations

from datetime import date

import pytest

from praviar_pipeline.pipeline.ranking.scoring import (
    apply_hard_filters,
    compute_composite_score,
    parse_cpc_codes,
    score_recency,
    score_title_keyword,
    use_ranking_reference_date,
)

pytestmark = pytest.mark.usefixtures("mock_settings")


def _make_patent(pub_num: str, *, prioritydate: str = "2020-01-01") -> dict:
    return {
        "publicationnumber": pub_num,
        "prioritydate": prioritydate,
        "filingdate": prioritydate,
    }


def test_parse_cpc_codes_pipe_delimited():
    assert parse_cpc_codes("C12P7/46|C07C57/04") == ["C12P7/46", "C07C57/04"]


def test_apply_hard_filters_keeps_allowed_recent_patent():
    filtered, reasons = apply_hard_filters([_make_patent("US1234567B2")])

    assert [pat["publicationnumber"] for pat in filtered] == ["US1234567B2"]
    assert reasons == {}


def test_score_title_keyword_matches_synonym_direct_module(succinic_acid):
    assert score_title_keyword("Butanedioic acid process", succinic_acid) == 1.0


def test_compute_composite_score_returns_weighted_sum():
    assert compute_composite_score(1.0, 0.0, 0.0, 0.0, 0.0) == pytest.approx(0.30)


def test_governed_reference_date_freezes_filtering_and_recency():
    patent = _make_patent("US1234567B2", prioritydate="2004-01-15")

    with use_ranking_reference_date(date(2026, 1, 15)):
        score = score_recency(date(2025, 1, 15))
        filtered, reasons = apply_hard_filters(
            [patent], include_expired=True, expired_grace_years=1
        )

    assert score == pytest.approx(0.9600273785078713)
    assert filtered == []
    assert reasons == {}
