"""Tests for Step 2b: Patent Ranking Funnel — scoring, filtering, and BM25 ranking."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

# All tests in this module need mock_settings to avoid anthropic_api_key
# validation when get_settings() is called inside ranking functions.
pytestmark = pytest.mark.usefixtures("mock_settings")

# ── Test Data Helpers ──────────────────────────────────────────────────


def _make_patent(
    pub_num: str = "US1234567B2",
    title: str = "Test patent",
    abstract: str = "",
    classification: str = "",
    cids: str = "811",
    prioritydate: str = "2020-01-01",
    grantdate: str = "2022-01-01",
    assignees: str = "Test Corp",
    **kwargs,
) -> dict:
    """Create a mock SDQ patent dict."""
    pat = {
        "publicationnumber": pub_num,
        "title": title,
        "abstract": abstract,
        "classification": classification,
        "cids": cids,
        "prioritydate": prioritydate,
        "grantdate": grantdate,
        "assignees": assignees,
    }
    pat.update(kwargs)
    return pat


# ── Hard Filter Tests ──────────────────────────────────────────────────


class TestHardFilters:
    def test_filters_non_allowed_jurisdiction_patents(self):
        from praviar_pipeline.pipeline.step2b_rank import _apply_hard_filters

        patents = [
            _make_patent("US1234567B2"),
            _make_patent("EP1234567B1"),
            _make_patent("WO2020123456A1"),
            _make_patent("US7777777B1"),
            _make_patent("CN1234567B"),
            _make_patent("BR1234567A1"),  # Brazil — not in allowed list
            _make_patent("ZA1234567B"),  # South Africa — not in allowed list
        ]
        result, _reasons = _apply_hard_filters(patents)
        pub_nums = [p["publicationnumber"] for p in result]
        # BR and ZA are NOT in allowed jurisdictions
        assert "BR1234567A1" not in pub_nums
        assert "ZA1234567B" not in pub_nums
        # US, WO, EP, CN are allowed by default
        assert "US1234567B2" in pub_nums
        assert "EP1234567B1" in pub_nums
        assert "CN1234567B" in pub_nums
        assert "WO2020123456A1" in pub_nums
        assert "US7777777B1" in pub_nums

    def test_applications_pass_through(self):
        """A1/A2 kind codes (published applications) should now pass through."""
        from praviar_pipeline.pipeline.step2b_rank import _apply_hard_filters

        patents = [
            _make_patent("US1234567A1"),  # Application — now passes
            _make_patent("US1234567A2"),  # Application — now passes
            _make_patent("US1234567B2"),  # Granted — passes
            _make_patent("US1234567B1"),  # Granted — passes
        ]
        result, _reasons = _apply_hard_filters(patents)
        pub_nums = [p["publicationnumber"] for p in result]
        assert "US1234567A1" in pub_nums
        assert "US1234567A2" in pub_nums
        assert "US1234567B2" in pub_nums
        assert "US1234567B1" in pub_nums

    def test_keeps_recent_expired_patents(self):
        from praviar_pipeline.pipeline.step2b_rank import _apply_hard_filters

        patents = [
            # Filed 2005 → expired ~2025, within 5-year grace period
            _make_patent("US1111111B2", prioritydate="2005-01-01"),
            # Filed 1990 → expired ~2010, outside grace period
            _make_patent("US2222222B2", prioritydate="1990-01-01"),
        ]
        result, _reasons = _apply_hard_filters(patents, include_expired=True, expired_grace_years=5)
        pub_nums = [p["publicationnumber"] for p in result]
        assert "US1111111B2" in pub_nums
        assert "US2222222B2" not in pub_nums

    def test_exclude_expired_entirely(self):
        from praviar_pipeline.pipeline.step2b_rank import _apply_hard_filters

        patents = [
            _make_patent("US1111111B2", prioritydate="2000-01-01"),  # Expired
            _make_patent("US2222222B2", prioritydate="2020-01-01"),  # Active
        ]
        result, _reasons = _apply_hard_filters(patents, include_expired=False)
        pub_nums = [p["publicationnumber"] for p in result]
        assert "US1111111B2" not in pub_nums
        assert "US2222222B2" in pub_nums

    def test_no_kind_code_passes_through(self):
        """Patents without a kind code (bare numbers) should pass through."""
        from praviar_pipeline.pipeline.step2b_rank import _apply_hard_filters

        patents = [_make_patent("US1234567")]
        result, _reasons = _apply_hard_filters(patents)
        assert len(result) == 1

    def test_handles_dashed_patent_numbers(self):
        """SDQ returns dashed patent numbers like US-6954300-B2."""
        from praviar_pipeline.pipeline.step2b_rank import _apply_hard_filters

        patents = [
            _make_patent("US-6954300-B2"),  # Granted — should pass
            _make_patent("US-2020012345-A1"),  # Application — now passes (A kind codes allowed)
        ]
        result, _reasons = _apply_hard_filters(patents)
        pub_nums = [p["publicationnumber"] for p in result]
        assert "US-6954300-B2" in pub_nums
        assert "US-2020012345-A1" in pub_nums

    def test_keeps_reissue_patents(self):
        """E kind codes (reissue patents) are granted and should pass."""
        from praviar_pipeline.pipeline.step2b_rank import _apply_hard_filters

        patents = [
            _make_patent("US-RE49000-E"),
            _make_patent("US1234567E"),
        ]
        result, _reasons = _apply_hard_filters(patents)
        assert len(result) == 2


# ── Scoring Signal Tests ──────────────────────────────────────────────


class TestCPCScoring:
    def test_high_relevance_biosynthesis(self):
        from praviar_pipeline.pipeline.step2b_rank import _score_cpc_relevance

        assert _score_cpc_relevance(["C12P7/46"]) == 1.0
        assert _score_cpc_relevance(["C12N15/52"]) == 1.0
        assert _score_cpc_relevance(["C07C57/04"]) == 1.0
        assert _score_cpc_relevance(["C07D309/00"]) == 1.0

    def test_medium_relevance_chemistry(self):
        from praviar_pipeline.pipeline.step2b_rank import _score_cpc_relevance

        assert _score_cpc_relevance(["C08F20/00"]) == 0.5
        assert _score_cpc_relevance(["C09D5/00"]) == 0.5

    def test_pharma_high_relevance(self):
        from praviar_pipeline.pipeline.step2b_rank import _score_cpc_relevance

        assert _score_cpc_relevance(["A61K31/00"]) == 1.0  # Pharma compositions
        assert _score_cpc_relevance(["A61P35/00"]) == 1.0  # Therapeutic activity

    def test_no_relevance(self):
        from praviar_pipeline.pipeline.step2b_rank import _score_cpc_relevance

        assert _score_cpc_relevance(["H01L21/00"]) == 0.0  # Semiconductors
        assert _score_cpc_relevance(["G06F3/00"]) == 0.0  # Computing

    def test_empty_codes(self):
        from praviar_pipeline.pipeline.step2b_rank import _score_cpc_relevance

        assert _score_cpc_relevance([]) == 0.0

    def test_highest_relevance_wins(self):
        from praviar_pipeline.pipeline.step2b_rank import _score_cpc_relevance

        # If both high and low relevance codes present, high wins
        assert _score_cpc_relevance(["A61K31/00", "C12P7/46"]) == 1.0


class TestCompoundCountScoring:
    def test_few_compounds_high_score(self):
        from praviar_pipeline.pipeline.step2b_rank import _score_compound_count

        assert _score_compound_count(1) == 1.0
        assert _score_compound_count(5) == 1.0

    def test_moderate_compounds(self):
        from praviar_pipeline.pipeline.step2b_rank import _score_compound_count

        assert _score_compound_count(10) == 0.7
        assert _score_compound_count(20) == 0.7

    def test_many_compounds_low_score(self):
        from praviar_pipeline.pipeline.step2b_rank import _score_compound_count

        assert _score_compound_count(50) == 0.3
        assert _score_compound_count(100) == 0.3

    def test_database_patent_zero_score(self):
        from praviar_pipeline.pipeline.step2b_rank import _score_compound_count

        assert _score_compound_count(500) == 0.0
        assert _score_compound_count(10000) == 0.0


class TestRecencyScoring:
    def test_recent_patent_high_score(self):
        from praviar_pipeline.pipeline.step2b_rank import _score_recency

        recent = date(date.today().year - 1, 1, 1)
        score = _score_recency(recent)
        assert score > 0.9

    def test_old_patent_low_score(self):
        from praviar_pipeline.pipeline.step2b_rank import _score_recency

        old = date(date.today().year - 24, 1, 1)
        score = _score_recency(old)
        assert score < 0.1

    def test_very_old_patent_zero(self):
        from praviar_pipeline.pipeline.step2b_rank import _score_recency

        ancient = date(1990, 1, 1)
        assert _score_recency(ancient) == 0.0

    def test_unknown_date_penalized(self):
        from praviar_pipeline.pipeline.step2b_rank import _score_recency

        assert _score_recency(None) == 0.0


class TestTitleKeywordScoring:
    def test_compound_name_in_title(self, succinic_acid):
        from praviar_pipeline.pipeline.step2b_rank import _score_title_keyword

        assert _score_title_keyword("Methods for producing succinic acid", succinic_acid) == 1.0

    def test_synonym_in_title(self, succinic_acid):
        from praviar_pipeline.pipeline.step2b_rank import _score_title_keyword

        assert _score_title_keyword("Butanedioic acid production method", succinic_acid) == 1.0

    def test_cas_in_title(self, succinic_acid):
        from praviar_pipeline.pipeline.step2b_rank import _score_title_keyword

        assert _score_title_keyword("Compound 110-15-6 applications", succinic_acid) == 1.0

    def test_unrelated_title(self, succinic_acid):
        from praviar_pipeline.pipeline.step2b_rank import _score_title_keyword

        assert _score_title_keyword("Thermoplastic polymer processing", succinic_acid) == 0.0

    def test_empty_title(self, succinic_acid):
        from praviar_pipeline.pipeline.step2b_rank import _score_title_keyword

        assert _score_title_keyword("", succinic_acid) == 0.0

    def test_short_synonym_ignored(self, succinic_acid):
        """Synonyms shorter than 4 chars should be skipped to avoid false matches."""
        from praviar_pipeline.pipeline.step2b_rank import _score_title_keyword

        # "SA" would match many titles if not length-filtered
        succinic_acid_short = succinic_acid.model_copy(update={"synonyms": ["SA"]})
        assert _score_title_keyword("SA-based polymers", succinic_acid_short) == 0.0


class TestMultiSourceScoring:
    def test_found_in_other_source(self):
        from praviar_pipeline.pipeline.step2b_rank import _score_multi_source
        from praviar_pipeline.utils.patent_ids import normalize_patent_id

        # multi_source_ids contains already-normalized IDs (produced by
        # normalize_patent_id in normalizers.py).  The bare number and B2
        # both normalize to the same B-tier key.
        multi_source_ids = {normalize_patent_id("US7851188B2")}
        assert _score_multi_source("US7851188B2", multi_source_ids) == 1.0

    def test_not_in_other_source(self):
        from praviar_pipeline.pipeline.step2b_rank import _score_multi_source

        multi_source_ids = {"US9999999B"}  # normalized form of a different patent
        assert _score_multi_source("US7851188B2", multi_source_ids) == 0.0


# ── Composite Score Tests ─────────────────────────────────────────────


class TestCompositeScore:
    def test_all_max_scores(self):
        from praviar_pipeline.pipeline.step2b_rank import _compute_composite_score

        score = _compute_composite_score(1.0, 1.0, 1.0, 1.0, 1.0)
        assert score == pytest.approx(1.0)

    def test_all_zero_scores(self):
        from praviar_pipeline.pipeline.step2b_rank import _compute_composite_score

        score = _compute_composite_score(0.0, 0.0, 0.0, 0.0, 0.0)
        assert score == pytest.approx(0.0)

    def test_weights_sum_to_one(self):
        from praviar_pipeline.pipeline.step2b_rank import _compute_composite_score

        # Weights: 0.30 + 0.20 + 0.15 + 0.15 + 0.20 = 1.0
        score = _compute_composite_score(1.0, 1.0, 1.0, 1.0, 1.0)
        assert score == pytest.approx(1.0)

    def test_cpc_has_highest_weight(self):
        from praviar_pipeline.pipeline.step2b_rank import _compute_composite_score

        # Only CPC score = 1.0, rest = 0.0
        cpc_only = _compute_composite_score(1.0, 0.0, 0.0, 0.0, 0.0)
        # Only compound count = 1.0
        cc_only = _compute_composite_score(0.0, 1.0, 0.0, 0.0, 0.0)
        assert cpc_only > cc_only  # CPC weight (0.30) > compound count weight (0.20)


# ── Utility Function Tests ────────────────────────────────────────────


class TestParseFunctions:
    def test_parse_date_iso(self):
        from praviar_pipeline.pipeline.step2b_rank import _parse_date

        assert _parse_date("2020-03-15") == date(2020, 3, 15)

    def test_parse_date_compact(self):
        from praviar_pipeline.pipeline.step2b_rank import _parse_date

        assert _parse_date("20200315") == date(2020, 3, 15)

    def test_parse_date_us_format(self):
        from praviar_pipeline.pipeline.step2b_rank import _parse_date

        assert _parse_date("03/15/2020") == date(2020, 3, 15)

    def test_parse_date_none(self):
        from praviar_pipeline.pipeline.step2b_rank import _parse_date

        assert _parse_date(None) is None
        assert _parse_date("") is None

    def test_parse_date_invalid(self):
        from praviar_pipeline.pipeline.step2b_rank import _parse_date

        assert _parse_date("not-a-date") is None

    def test_parse_cpc_codes_semicolon(self):
        from praviar_pipeline.pipeline.step2b_rank import _parse_cpc_codes

        codes = _parse_cpc_codes("C12P7/46; C07C57/04")
        assert codes == ["C12P7/46", "C07C57/04"]

    def test_parse_cpc_codes_pipe(self):
        """SDQ uses pipe-delimited classification codes."""
        from praviar_pipeline.pipeline.step2b_rank import _parse_cpc_codes

        codes = _parse_cpc_codes("B32B17/10|C09K9/02|G02F1/155")
        assert codes == ["B32B17/10", "C09K9/02", "G02F1/155"]

    def test_parse_cpc_codes_list(self):
        from praviar_pipeline.pipeline.step2b_rank import _parse_cpc_codes

        codes = _parse_cpc_codes(["C12P7/46", "C07C57/04"])
        assert codes == ["C12P7/46", "C07C57/04"]

    def test_parse_cpc_codes_empty(self):
        from praviar_pipeline.pipeline.step2b_rank import _parse_cpc_codes

        assert _parse_cpc_codes(None) == []
        assert _parse_cpc_codes("") == []

    def test_count_cids_string_comma(self):
        from praviar_pipeline.pipeline.step2b_rank import _count_cids

        assert _count_cids("811,2969,5460307") == 3

    def test_count_cids_string_pipe(self):
        """SDQ uses pipe-delimited CID strings."""
        from praviar_pipeline.pipeline.step2b_rank import _count_cids

        assert _count_cids("174|222|811|962|1030") == 5

    def test_count_cids_list(self):
        from praviar_pipeline.pipeline.step2b_rank import _count_cids

        assert _count_cids([811, 2969]) == 2

    def test_count_cids_empty(self):
        from praviar_pipeline.pipeline.step2b_rank import _count_cids

        assert _count_cids(None) == 0
        assert _count_cids("") == 0

    def test_extract_kind_code(self):
        from praviar_pipeline.pipeline.ranking.scoring import extract_kind_code

        assert extract_kind_code("US7851188B2") == "B2"
        assert extract_kind_code("US7851188A1") == "A1"
        assert extract_kind_code("US1234567") == ""


# ── Integration: rank_patents ──────────────────────────────────────────


class TestRankPatents:
    def test_returns_capped_results(self, succinic_acid, mock_settings):
        """rank_patents should return at most max_results patents."""
        from praviar_pipeline.pipeline.step2b_rank import rank_patents

        patents = [
            _make_patent(
                f"US{1000000 + i}B2",
                title=f"Patent about succinic acid #{i}",
                classification="C12P7/46",
                cids="811",
            )
            for i in range(50)
        ]

        with patch("praviar_pipeline.pipeline.step2b_rank._bm25_rerank") as mock_bm25:
            # BM25 returns all candidates with uniform scores
            mock_bm25.return_value = [(p, 1.0) for p in patents]
            result = rank_patents(patents, succinic_acid, max_results=10)

        assert len(result) <= 10

    def test_empty_input(self, succinic_acid, mock_settings):
        """Empty input should return empty output."""
        from praviar_pipeline.pipeline.step2b_rank import rank_patents

        result = rank_patents([], succinic_acid)
        assert result == []

    def test_all_filtered_out(self, succinic_acid, mock_settings):
        """If hard filters remove everything, return empty."""
        from praviar_pipeline.pipeline.step2b_rank import rank_patents

        patents = [
            _make_patent("BR1234567B1"),  # Non-allowed jurisdiction (Brazil)
            _make_patent("ZA1234567B"),  # Non-allowed jurisdiction (South Africa)
        ]
        result = rank_patents(patents, succinic_acid)
        assert result == []

    def test_relevant_patents_rank_higher(self, succinic_acid, mock_settings):
        """Patents with biosynthesis CPC codes and compound name in title should rank higher."""
        from praviar_pipeline.pipeline.step2b_rank import rank_patents

        relevant = _make_patent(
            "US1111111B2",
            title="Production of succinic acid by fermentation",
            classification="C12P7/46",
            cids="811",
            prioritydate="2020-01-01",
        )
        noise = _make_patent(
            "US2222222B2",
            title="General polymer catalyst screening",
            classification="B01J21/00",
            cids=",".join(str(i) for i in range(500)),  # 500 compounds → database patent
            prioritydate="2005-01-01",
        )

        with patch("praviar_pipeline.pipeline.step2b_rank._bm25_rerank") as mock_bm25:
            # BM25 gives a slight edge to the relevant patent
            mock_bm25.return_value = [(relevant, 2.0), (noise, 0.5)]
            result = rank_patents([relevant, noise], succinic_acid, max_results=10)

        assert len(result) == 2
        assert result[0]["publicationnumber"] == "US1111111B2"

    def test_multi_source_bonus(self, succinic_acid, mock_settings):
        """Patents found by multiple sources should get a ranking boost."""
        from praviar_pipeline.pipeline.step2b_rank import rank_patents

        # Both patents have same CPC, compound count, recency — differ only in multi-source
        multi_source_pat = _make_patent(
            "US3333333B2",
            title="Organic acid production",
            classification="C07C57/04",
            cids="811",
            prioritydate="2019-01-01",
        )
        single_source_pat = _make_patent(
            "US4444444B2",
            title="Organic acid production",
            classification="C07C57/04",
            cids="811",
            prioritydate="2019-01-01",
        )

        multi_source_ids = {"US3333333"}  # Only this one has multi-source signal

        with patch("praviar_pipeline.pipeline.step2b_rank._bm25_rerank") as mock_bm25:
            mock_bm25.return_value = [
                (multi_source_pat, 1.0),
                (single_source_pat, 1.0),
            ]
            result = rank_patents(
                [multi_source_pat, single_source_pat],
                succinic_acid,
                multi_source_ids=multi_source_ids,
                max_results=10,
            )

        # Multi-source patent should rank first (due to 0.20 weight bonus)
        assert result[0]["publicationnumber"] == "US3333333B2"

    def test_bm25_failure_propagates(self, succinic_acid, mock_settings):
        """If BM25 fails, the error should propagate (no silent fallback)."""
        from praviar_pipeline.pipeline.step2b_rank import rank_patents

        patents = [
            _make_patent("US5555555B2", title="Succinic acid", classification="C12P7/46"),
        ]

        with (
            patch(
                "praviar_pipeline.pipeline.step2b_rank._bm25_rerank",
                side_effect=RuntimeError("BM25 broken"),
            ),
            pytest.raises(RuntimeError, match="BM25 broken"),
        ):
            rank_patents(patents, succinic_acid, max_results=10)

    def test_no_input_mutation(self, succinic_acid, mock_settings):
        """Ranking should not mutate input dicts."""
        from praviar_pipeline.pipeline.step2b_rank import rank_patents

        patents = [
            _make_patent("US6666666B2", title="Test", classification="C12P7/46"),
        ]
        original_keys = set(patents[0].keys())

        with patch("praviar_pipeline.pipeline.step2b_rank._bm25_rerank") as mock_bm25:
            mock_bm25.return_value = [(patents[0], 1.0)]
            result = rank_patents(patents, succinic_acid, max_results=10)

        assert len(result) == 1
        # Verify input dicts are not mutated with internal scoring keys
        assert set(patents[0].keys()) == original_keys


# ── End-to-End Ranking with Realistic Data ─────────────────────────────


class TestRankingEndToEnd:
    def test_realistic_patent_ordering(self, succinic_acid, mock_settings):
        """Simulate 20 patents with varying relevance and verify top-5 ordering."""
        from praviar_pipeline.pipeline.step2b_rank import rank_patents

        patents = [
            # Highly relevant: biosynthesis CPC, few compounds, recent, name in title
            _make_patent(
                "US0000001B2",
                title="Fermentation method for succinic acid production",
                abstract="A process using E. coli to produce succinic acid",
                classification="C12P7/46; C07C57/04",
                cids="811,2969",
                prioritydate="2022-01-01",
            ),
            # Relevant: organic chemistry, name in title
            _make_patent(
                "US0000002B2",
                title="Purification of succinic acid from fermentation broth",
                abstract="Crystallization method for bio-based succinic acid",
                classification="C07C51/43",
                cids="811",
                prioritydate="2021-06-01",
            ),
            # Moderate: chemistry CPC, but many compounds (screening patent)
            _make_patent(
                "US0000003B2",
                title="Catalytic screening of dicarboxylic acids",
                abstract="High-throughput screening of organic acid catalysts",
                classification="C07C57/00",
                cids=",".join(str(i) for i in range(200)),
                prioritydate="2018-01-01",
            ),
            # Noise: unrelated CPC, many compounds, old
            _make_patent(
                "US0000004B2",
                title="Semiconductor fabrication process",
                abstract="Chemical vapor deposition of thin films",
                classification="H01L21/00",
                cids=",".join(str(i) for i in range(1000)),
                prioritydate="2000-01-01",
            ),
            # Noise: pharmaceutical, many compounds
            _make_patent(
                "US0000005B2",
                title="Drug formulation with excipients",
                abstract="Tablet coating composition",
                classification="A61K9/20",
                cids=",".join(str(i) for i in range(300)),
                prioritydate="2015-01-01",
            ),
        ]

        with patch("praviar_pipeline.pipeline.step2b_rank._bm25_rerank") as mock_bm25:
            # Simulate BM25 giving higher scores to patents mentioning succinic acid
            mock_bm25.return_value = [
                (patents[0], 5.0),  # Strong text match
                (patents[1], 4.0),  # Good text match
                (patents[2], 1.0),  # Weak match (dicarboxylic acids)
                (patents[3], 0.1),  # Irrelevant
                (patents[4], 0.2),  # Irrelevant
            ]
            result = rank_patents(patents, succinic_acid, max_results=5)

        # The top 2 should be the biosynthesis/purification patents
        top_ids = [p["publicationnumber"] for p in result[:2]]
        assert "US0000001B2" in top_ids
        assert "US0000002B2" in top_ids

        # Semiconductor patent should be ranked last
        assert result[-1]["publicationnumber"] in ("US0000004B2", "US0000005B2")
