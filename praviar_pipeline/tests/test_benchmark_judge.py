"""Tests for the LLM-as-Judge benchmark evaluation module.

Tests each component without requiring API calls:
  - Prompt formatting with mock data
  - Score parsing from LLM response
  - Batch evaluation orchestration
  - Calibration variance measurement
  - Cost tracking
  - Edge cases (empty data, malformed responses, missing fields)
  - Red flag and critical error detection
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure benchmark tooling is importable from its canonical research location
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research" / "tools" / "benchmarks"))

from benchmark_judge import (
    BenchmarkJudge,
    CalibrationResult,
    CaseJudgeResult,
    DimensionScore,
    JudgeScore,
    _compute_cost,
    _extract_json_from_response,
    _find_gt_patent,
    _format_claim_analysis,
    _format_design_around,
    _format_invalidity_assessment,
    parse_judge_response,
)
from benchmark_judge_prompts import (
    JUDGE_DIMENSIONS,
    JUDGE_PROMPTS,
)

# ---------------------------------------------------------------------------
# Fixtures: mock data
# ---------------------------------------------------------------------------


def _make_ground_truth(
    case_id: str = "para4_001",
    compound_name: str = "Fluoxetine",
    smiles: str = "CNCCC(C1=CC=CC=C1)OC2=CC=C(C=C2)C(F)(F)F",
) -> dict[str, Any]:
    """Create a minimal ground truth benchmark case."""
    return {
        "id": case_id,
        "compound": {
            "brand_name": "Prozac",
            "generic_name": compound_name,
            "active_ingredient": "Fluoxetine hydrochloride",
            "smiles": smiles,
            "cas_number": "54910-89-3",
            "pubchem_cid": "3386",
            "therapeutic_area": "Psychiatry",
            "drug_class": "Selective serotonin reuptake inhibitor (SSRI)",
        },
        "patents": [
            {
                "patent_number": "US4314081",
                "assignee": "Eli Lilly and Company",
                "claim_types": ["composition"],
                "key_claims": [1, 5, 7],
                "expiry_date": "2001-02-02",
                "status": "expired",
                "title": "Fluoxetine composition patent",
            },
            {
                "patent_number": "US4626549",
                "assignee": "Eli Lilly and Company",
                "claim_types": ["method"],
                "key_claims": [7],
                "expiry_date": "2003-12-29",
                "status": "invalidated",
                "title": "Method of inhibiting serotonin uptake",
            },
        ],
        "litigation": {
            "case_name": "Eli Lilly & Co. v. Barr Laboratories, Inc.",
            "case_number": "222 F.3d 973 (Fed. Cir. 2000)",
            "court": "Federal Circuit",
            "year": 2000,
            "ruling": "invalidated",
            "claims_upheld": [1, 5],
            "claims_invalidated": [7],
            "invalidity_basis": (
                "Obviousness-type double patenting. The Federal Circuit found the "
                "'549 patent was an obvious variant of the '081 patent."
            ),
        },
        "benchmark": {
            "category": "paragraph_iv",
            "difficulty": "medium",
            "expected_risk_today": "CLEAR",
            "blocking_patents_to_find": ["US4314081", "US4626549"],
            "key_claim_elements": {
                "met": [
                    "Fluoxetine HCl compound is explicitly claimed in '081 patent claim 5",
                    "Method of inhibiting serotonin uptake is claimed in '549 patent claim 7",
                ],
                "not_met": [
                    "Double patenting defense eliminates '549 patent",
                ],
            },
        },
    }


def _make_report_data() -> dict[str, Any]:
    """Create a minimal pipeline report dict."""
    return {
        "risk_summary": {
            "overall_risk": "clear",
            "blocking_patents_count": 0,
            "total_patents_analyzed": 2,
            "key_risks": ["All relevant patents have expired"],
            "executive_summary": (
                "Both Fluoxetine patents (US4314081 and US4626549) have expired. "
                "The '549 patent was invalidated for double patenting in 2000. "
                "No current FTO risk exists for generic fluoxetine."
            ),
        },
        "patent_analyses": [
            {
                "patent_id": "US4314081",
                "title": "Aryloxyphenylpropylamines",
                "assignee": "Eli Lilly",
                "risk_level": "clear",
                "risk_summary": "Patent expired 2001. Compound claim 5 covers fluoxetine HCl directly.",
                "expiry_date": "2001-02-02",
                "claims_analyzed": [
                    {
                        "claim_number": 5,
                        "claim_type": "independent",
                        "overall_status": "met",
                        "overall_confidence": 0.95,
                        "reasoning": "Fluoxetine HCl is explicitly named in claim 5.",
                        "elements": [
                            {
                                "element_number": 1,
                                "element_text": "A compound of the formula fluoxetine hydrochloride",
                                "status": "met",
                                "confidence": 0.95,
                                "reasoning": "Fluoxetine HCl is the exact compound claimed.",
                                "evidence": "Claim 5 explicitly names fluoxetine HCl.",
                            },
                        ],
                    },
                ],
                "design_around_suggestions": [
                    {
                        "element_avoided": 1,
                        "suggestion": "Use fluoxetine free base instead of HCl salt form.",
                        "feasibility": "Chemically feasible but may not avoid Markush coverage in claim 1.",
                    },
                ],
            },
        ],
        "invalidity_assessments": [
            {
                "patent_id": "US4626549",
                "claim_numbers": [7],
                "overall_invalidity_strength": "strong",
                "confidence": 0.85,
                "confidence_band": "HIGH",
                "reasoning": (
                    "The '549 patent was found invalid for obviousness-type double patenting "
                    "by the Federal Circuit."
                ),
                "prior_art": [
                    {
                        "reference_id": "US4314081",
                        "title": "The '081 compound patent",
                        "relevance": "Base patent establishing double patenting reference",
                        "anticipation_score": 0.3,
                        "obviousness_score": 0.9,
                        "reference_type": "patent",
                        "source_database": "",
                    },
                ],
                "written_description_issues": [],
                "ptab": {"has_been_challenged": False, "proceedings": []},
                "claim_charts": [],
                "graham_factors": {
                    "scope_and_content": "Method of serotonin uptake inhibition using fluoxetine",
                    "differences_from_prior_art": "Method claim vs compound claim - obvious variant",
                    "level_of_ordinary_skill": "PhD in pharmacology or medicinal chemistry",
                    "overall_obviousness_assessment": "Highly obvious given the base compound patent",
                },
            },
        ],
    }


def _make_judge_response_json(
    judge_type: str = "claim_analysis",
    overall_score: float = 0.85,
    dimension_score: int = 4,
    red_flags: list[str] | None = None,
    critical_errors: list[str] | None = None,
) -> str:
    """Create a synthetic judge response JSON string."""
    dimensions_keys = JUDGE_DIMENSIONS[judge_type]
    data: dict[str, Any] = {}

    for key in dimensions_keys:
        data[key] = {
            "score": dimension_score,
            "reasoning": f"Test reasoning for {key}.",
        }
        # Special case for grounds_identification
        if key == "grounds_identification":
            data[key]["grounds_found"] = ["obviousness"]
            data[key]["grounds_missed"] = []

    data["red_flags"] = red_flags or []
    data["critical_errors"] = critical_errors or []
    data["overall_score"] = overall_score
    data["summary"] = f"Test summary for {judge_type} evaluation."

    return json.dumps(data)


# ---------------------------------------------------------------------------
# Tests: DimensionScore
# ---------------------------------------------------------------------------


class TestDimensionScore:
    def test_normalized_score_min(self):
        d = DimensionScore(name="test", score=1)
        assert d.normalized == 0.0

    def test_normalized_score_max(self):
        d = DimensionScore(name="test", score=5)
        assert d.normalized == 1.0

    def test_normalized_score_mid(self):
        d = DimensionScore(name="test", score=3)
        assert d.normalized == 0.5

    def test_normalized_score_clamp_below(self):
        d = DimensionScore(name="test", score=0)
        assert d.normalized == 0.0  # max(0, (0-1)/4) = 0.0

    def test_to_dict(self):
        d = DimensionScore(name="accuracy", score=4, reasoning="Good work")
        result = d.to_dict()
        assert result["name"] == "accuracy"
        assert result["score"] == 4
        assert result["normalized"] == 0.75
        assert result["reasoning"] == "Good work"


# ---------------------------------------------------------------------------
# Tests: JudgeScore
# ---------------------------------------------------------------------------


class TestJudgeScore:
    def test_mean_dimension_score_empty(self):
        s = JudgeScore(judge_type="claim_analysis")
        assert s.mean_dimension_score == 0.0

    def test_mean_dimension_score(self):
        s = JudgeScore(
            judge_type="claim_analysis",
            dimensions=[
                DimensionScore(name="a", score=5),  # 1.0
                DimensionScore(name="b", score=3),  # 0.5
                DimensionScore(name="c", score=1),  # 0.0
            ],
        )
        assert s.mean_dimension_score == pytest.approx(0.5)

    def test_to_dict_includes_all_fields(self):
        s = JudgeScore(
            judge_type="invalidity",
            case_id="test_001",
            patent_id="US123",
            overall_score=0.75,
            red_flags=["fabricated patent"],
            critical_errors=["wrong expiry"],
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.003,
            duration_seconds=2.5,
        )
        d = s.to_dict()
        assert d["judge_type"] == "invalidity"
        assert d["case_id"] == "test_001"
        assert d["patent_id"] == "US123"
        assert d["overall_score"] == 0.75
        assert d["red_flags"] == ["fabricated patent"]
        assert d["critical_errors"] == ["wrong expiry"]
        assert d["input_tokens"] == 1000
        assert d["output_tokens"] == 500


# ---------------------------------------------------------------------------
# Tests: CaseJudgeResult
# ---------------------------------------------------------------------------


class TestCaseJudgeResult:
    def test_total_cost(self):
        result = CaseJudgeResult(
            case_id="test",
            claim_scores=[JudgeScore(judge_type="claim_analysis", cost_usd=0.01)],
            invalidity_scores=[JudgeScore(judge_type="invalidity", cost_usd=0.005)],
            legal_soundness=JudgeScore(judge_type="legal_soundness", cost_usd=0.008),
        )
        assert result.total_cost_usd == pytest.approx(0.023)

    def test_total_tokens(self):
        result = CaseJudgeResult(
            case_id="test",
            claim_scores=[
                JudgeScore(judge_type="claim_analysis", input_tokens=500, output_tokens=300),
            ],
            legal_soundness=JudgeScore(
                judge_type="legal_soundness", input_tokens=600, output_tokens=400
            ),
        )
        assert result.total_tokens == 1800

    def test_overall_quality_empty(self):
        result = CaseJudgeResult(case_id="test")
        assert result.overall_quality_score == 0.0

    def test_overall_quality_weighted(self):
        result = CaseJudgeResult(
            case_id="test",
            claim_scores=[JudgeScore(judge_type="claim_analysis", overall_score=0.8)],
            invalidity_scores=[JudgeScore(judge_type="invalidity", overall_score=0.6)],
            design_around_scores=[JudgeScore(judge_type="design_around", overall_score=0.7)],
            legal_soundness=JudgeScore(judge_type="legal_soundness", overall_score=0.9),
        )
        # Weights: claim 0.35, invalidity 0.25, design 0.15, legal 0.25
        expected = (0.35 * 0.8 + 0.25 * 0.6 + 0.15 * 0.7 + 0.25 * 0.9) / (0.35 + 0.25 + 0.15 + 0.25)
        assert result.overall_quality_score == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Tests: CalibrationResult
# ---------------------------------------------------------------------------


class TestCalibrationResult:
    def test_to_dict(self):
        cal = CalibrationResult(
            case_id="test",
            judge_type="legal_soundness",
            num_runs=3,
            scores=[0.8, 0.82, 0.79],
            mean_score=0.803,
            std_dev=0.015,
            variance=0.0002,
            is_stable=True,
        )
        d = cal.to_dict()
        assert d["is_stable"] is True
        assert d["num_runs"] == 3
        assert len(d["scores"]) == 3


# ---------------------------------------------------------------------------
# Tests: JSON extraction
# ---------------------------------------------------------------------------


class TestExtractJson:
    def test_bare_json(self):
        raw = '{"score": 4}'
        assert _extract_json_from_response(raw) == '{"score": 4}'

    def test_code_block(self):
        raw = '```json\n{"score": 4}\n```'
        assert _extract_json_from_response(raw) == '{"score": 4}'

    def test_preamble(self):
        raw = 'Here is my evaluation:\n\n{"score": 4}'
        assert _extract_json_from_response(raw) == '{"score": 4}'

    def test_trailing_text(self):
        raw = '{"score": 4}\n\nI hope this helps!'
        assert _extract_json_from_response(raw) == '{"score": 4}'

    def test_unclosed_code_block(self):
        raw = '```json\n{"score": 4}'
        assert _extract_json_from_response(raw) == '{"score": 4}'

    def test_no_json(self):
        raw = "No JSON here at all"
        result = _extract_json_from_response(raw)
        assert result == "No JSON here at all"


# ---------------------------------------------------------------------------
# Tests: parse_judge_response
# ---------------------------------------------------------------------------


class TestParseJudgeResponse:
    def test_valid_claim_analysis_response(self):
        raw = _make_judge_response_json("claim_analysis", overall_score=0.85, dimension_score=4)
        dims, _flags, _errors, overall, summary = parse_judge_response(raw, "claim_analysis")

        assert len(dims) == 5
        assert all(d.score == 4 for d in dims)
        assert overall == 0.85
        assert "claim_analysis" in summary

    def test_valid_invalidity_response(self):
        raw = _make_judge_response_json("invalidity", overall_score=0.7, dimension_score=3)
        dims, _flags, _errors, overall, _summary = parse_judge_response(raw, "invalidity")

        assert len(dims) == 5
        assert overall == 0.7
        dim_names = {d.name for d in dims}
        assert "grounds_identification" in dim_names
        assert "prior_art_quality" in dim_names

    def test_valid_design_around_response(self):
        raw = _make_judge_response_json("design_around", overall_score=0.6)
        dims, _flags, _errors, _overall, _summary = parse_judge_response(raw, "design_around")

        assert len(dims) == 5
        dim_names = {d.name for d in dims}
        assert "chemical_feasibility" in dim_names
        assert "claim_avoidance" in dim_names

    def test_valid_legal_soundness_response(self):
        raw = _make_judge_response_json("legal_soundness", overall_score=0.9)
        dims, _flags, _errors, _overall, _summary = parse_judge_response(raw, "legal_soundness")

        assert len(dims) == 5
        dim_names = {d.name for d in dims}
        assert "risk_level_accuracy" in dim_names
        assert "actionability" in dim_names

    def test_red_flags_parsed(self):
        raw = _make_judge_response_json(
            "claim_analysis",
            red_flags=["Hallucinated patent US9999999", "Circular reasoning in element 3"],
        )
        _, flags, _, _, _ = parse_judge_response(raw, "claim_analysis")
        assert len(flags) == 2
        assert "Hallucinated patent" in flags[0]

    def test_critical_errors_parsed(self):
        raw = _make_judge_response_json(
            "legal_soundness",
            critical_errors=["Risk level underestimation on active patent"],
        )
        _, _, errors, _, _ = parse_judge_response(raw, "legal_soundness")
        assert len(errors) == 1
        assert "underestimation" in errors[0]

    def test_malformed_json_returns_defaults(self):
        raw = "This is not JSON at all"
        dims, flags, _errors, overall, summary = parse_judge_response(raw, "claim_analysis")
        assert dims == []
        assert flags == []
        assert overall == 0.0
        assert "Failed to parse" in summary

    def test_score_clamping_above_5(self):
        data = {
            "element_identification_accuracy": {"score": 10, "reasoning": "test"},
            "reasoning_quality": {"score": 4, "reasoning": "test"},
            "consistency_with_outcome": {"score": 4, "reasoning": "test"},
            "factual_accuracy": {"score": 4, "reasoning": "test"},
            "confidence_calibration": {"score": 4, "reasoning": "test"},
            "red_flags": [],
            "overall_score": 0.8,
            "summary": "test",
        }
        raw = json.dumps(data)
        dims, _, _, _, _ = parse_judge_response(raw, "claim_analysis")
        assert dims[0].score == 5  # Clamped from 10

    def test_score_clamping_below_1(self):
        data = {
            "element_identification_accuracy": {"score": -1, "reasoning": "test"},
            "reasoning_quality": {"score": 4, "reasoning": "test"},
            "consistency_with_outcome": {"score": 4, "reasoning": "test"},
            "factual_accuracy": {"score": 4, "reasoning": "test"},
            "confidence_calibration": {"score": 4, "reasoning": "test"},
            "red_flags": [],
            "overall_score": 0.8,
            "summary": "test",
        }
        raw = json.dumps(data)
        dims, _, _, _, _ = parse_judge_response(raw, "claim_analysis")
        assert dims[0].score == 1  # Clamped from -1

    def test_overall_score_clamped_to_0_1(self):
        raw = _make_judge_response_json("claim_analysis", overall_score=1.5)
        _, _, _, overall, _ = parse_judge_response(raw, "claim_analysis")
        assert overall == 1.0

    def test_overall_score_negative_clamped(self):
        raw = _make_judge_response_json("claim_analysis", overall_score=-0.5)
        _, _, _, overall, _ = parse_judge_response(raw, "claim_analysis")
        assert overall == 0.0

    def test_missing_dimensions_get_score_1(self):
        """If the LLM omits a dimension, it gets the minimum score."""
        data = {
            "element_identification_accuracy": {"score": 5, "reasoning": "Great"},
            # Missing other dimensions
            "red_flags": [],
            "overall_score": 0.5,
            "summary": "Partial response",
        }
        raw = json.dumps(data)
        dims, _, _, _, _ = parse_judge_response(raw, "claim_analysis")
        assert len(dims) == 5
        assert dims[0].score == 5
        # Missing dimensions default to score 1
        assert dims[1].score == 1


# ---------------------------------------------------------------------------
# Tests: Prompt formatting
# ---------------------------------------------------------------------------


class TestPromptFormatting:
    def test_all_prompt_templates_exist(self):
        assert "claim_analysis" in JUDGE_PROMPTS
        assert "invalidity" in JUDGE_PROMPTS
        assert "design_around" in JUDGE_PROMPTS
        assert "legal_soundness" in JUDGE_PROMPTS

    def test_all_dimension_lists_exist(self):
        for judge_type in JUDGE_PROMPTS:
            assert judge_type in JUDGE_DIMENSIONS
            assert len(JUDGE_DIMENSIONS[judge_type]) == 5

    def test_claim_analysis_prompt_has_rubric(self):
        prompt = JUDGE_PROMPTS["claim_analysis"]
        assert "Element Identification Accuracy" in prompt
        assert "Reasoning Quality" in prompt
        assert "1-5" in prompt
        assert "Red Flags" in prompt
        assert "JSON" in prompt

    def test_invalidity_prompt_has_rubric(self):
        prompt = JUDGE_PROMPTS["invalidity"]
        assert "Invalidity Grounds Identification" in prompt
        assert "Graham" in prompt
        assert "102" in prompt
        assert "103" in prompt

    def test_design_around_prompt_has_rubric(self):
        prompt = JUDGE_PROMPTS["design_around"]
        assert "Chemical Feasibility" in prompt
        assert "Therapeutic Viability" in prompt
        assert "pharmacophore" in prompt

    def test_legal_soundness_prompt_has_rubric(self):
        prompt = JUDGE_PROMPTS["legal_soundness"]
        assert "Risk Level Accuracy" in prompt
        assert "Actionability" in prompt
        assert "Appropriate Caveats" in prompt


class TestFormatClaimAnalysis:
    def test_basic_formatting(self):
        analysis = _make_report_data()["patent_analyses"][0]
        text = _format_claim_analysis(analysis)
        assert "US4314081" in text
        assert "clear" in text
        assert "Element 1" in text
        assert "met" in text

    def test_empty_analysis(self):
        text = _format_claim_analysis({"patent_id": "US000", "claims_analyzed": []})
        assert "US000" in text

    def test_multiple_claims(self):
        analysis = {
            "patent_id": "US123",
            "risk_level": "high",
            "risk_summary": "test",
            "claims_analyzed": [
                {
                    "claim_number": 1,
                    "claim_type": "independent",
                    "overall_status": "met",
                    "overall_confidence": 0.9,
                    "reasoning": "test",
                    "elements": [],
                },
                {
                    "claim_number": 2,
                    "claim_type": "dependent",
                    "overall_status": "not_met",
                    "overall_confidence": 0.7,
                    "reasoning": "test",
                    "elements": [],
                },
            ],
        }
        text = _format_claim_analysis(analysis)
        assert "Claim 1" in text
        assert "Claim 2" in text


class TestFormatInvalidityAssessment:
    def test_basic_formatting(self):
        assessment = _make_report_data()["invalidity_assessments"][0]
        text = _format_invalidity_assessment(assessment)
        assert "US4626549" in text
        assert "strong" in text
        assert "US4314081" in text  # prior art reference

    def test_with_ptab(self):
        assessment = {
            "patent_id": "US999",
            "overall_invalidity_strength": "moderate",
            "confidence": 0.6,
            "confidence_band": "MODERATE",
            "reasoning": "test",
            "prior_art": [],
            "written_description_issues": ["Genus claim too broad"],
            "ptab": {
                "has_been_challenged": True,
                "proceedings": [
                    {
                        "proceeding_number": "IPR2019-00123",
                        "status": "Final Written Decision",
                        "claims_cancelled": [1, 3],
                    },
                ],
            },
            "claim_charts": [],
        }
        text = _format_invalidity_assessment(assessment)
        assert "IPR2019-00123" in text
        assert "Genus claim too broad" in text


class TestFormatDesignAround:
    def test_basic_formatting(self):
        suggestions = _make_report_data()["patent_analyses"][0]["design_around_suggestions"]
        text = _format_design_around(suggestions)
        assert "Suggestion 1" in text
        assert "free base" in text

    def test_empty_suggestions(self):
        text = _format_design_around([])
        assert "No design-around suggestions" in text


# ---------------------------------------------------------------------------
# Tests: Cost computation
# ---------------------------------------------------------------------------


class TestCostComputation:
    def test_haiku_cost(self):
        cost = _compute_cost("claude-haiku-4-5-20251001", 1000, 500)
        expected = (1000 * 1.00 + 500 * 5.00) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_sonnet_cost(self):
        cost = _compute_cost("claude-sonnet-4-6", 1000, 500)
        expected = (1000 * 3.00 + 500 * 15.00) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_unknown_model_defaults_to_haiku(self):
        cost = _compute_cost("unknown-model", 1000, 500)
        expected = (1000 * 1.00 + 500 * 5.00) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_zero_tokens(self):
        cost = _compute_cost("claude-haiku-4-5-20251001", 0, 0)
        assert cost == 0.0


# ---------------------------------------------------------------------------
# Tests: GT patent lookup
# ---------------------------------------------------------------------------


class TestFindGtPatent:
    def test_finds_by_exact_id(self):
        gt = _make_ground_truth()
        patent = _find_gt_patent(gt, "US4314081")
        assert patent.get("assignee") == "Eli Lilly and Company"

    def test_finds_normalized(self):
        gt = _make_ground_truth()
        patent = _find_gt_patent(gt, "us4314081a1")
        assert patent.get("assignee") == "Eli Lilly and Company"

    def test_returns_empty_for_unknown(self):
        gt = _make_ground_truth()
        patent = _find_gt_patent(gt, "US9999999")
        assert patent == {}


# ---------------------------------------------------------------------------
# Tests: BenchmarkJudge with mocked LLM
# ---------------------------------------------------------------------------


def _mock_anthropic_response(text: str, in_tokens: int = 800, out_tokens: int = 400):
    """Create a mock Anthropic API response."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text=text)]
    mock_response.usage = MagicMock(input_tokens=in_tokens, output_tokens=out_tokens)
    return mock_response


class TestBenchmarkJudgeMocked:
    """Test the BenchmarkJudge with mocked Claude API calls."""

    @pytest.fixture
    def mock_judge(self):
        """Create a BenchmarkJudge with a mocked Anthropic client."""
        from unittest.mock import patch as _patch

        with _patch("benchmark_judge._no_paid_api_enabled", return_value=False):
            judge = BenchmarkJudge(model="claude-haiku-4-5-20251001", api_key="test-key")
        return judge

    @pytest.mark.asyncio
    async def test_evaluate_claim_analysis(self, mock_judge):
        response_json = _make_judge_response_json("claim_analysis", overall_score=0.85)
        mock_response = _mock_anthropic_response(response_json)
        mock_judge._client.messages.create = AsyncMock(return_value=mock_response)

        gt = _make_ground_truth()
        report = _make_report_data()

        scores = await mock_judge.evaluate_claim_analysis(report, gt)

        assert len(scores) == 1
        assert scores[0].judge_type == "claim_analysis"
        assert scores[0].overall_score == 0.85
        assert scores[0].patent_id == "US4314081"
        assert len(scores[0].dimensions) == 5
        assert scores[0].cost_usd > 0

    @pytest.mark.asyncio
    async def test_evaluate_invalidity(self, mock_judge):
        response_json = _make_judge_response_json("invalidity", overall_score=0.7)
        mock_response = _mock_anthropic_response(response_json)
        mock_judge._client.messages.create = AsyncMock(return_value=mock_response)

        gt = _make_ground_truth()
        report = _make_report_data()

        scores = await mock_judge.evaluate_invalidity(report, gt)

        assert len(scores) == 1
        assert scores[0].judge_type == "invalidity"
        assert scores[0].overall_score == 0.7
        assert scores[0].patent_id == "US4626549"

    @pytest.mark.asyncio
    async def test_evaluate_design_around(self, mock_judge):
        response_json = _make_judge_response_json("design_around", overall_score=0.65)
        mock_response = _mock_anthropic_response(response_json)
        mock_judge._client.messages.create = AsyncMock(return_value=mock_response)

        gt = _make_ground_truth()
        report = _make_report_data()

        scores = await mock_judge.evaluate_design_around(report, gt)

        assert len(scores) == 1
        assert scores[0].judge_type == "design_around"
        assert scores[0].overall_score == 0.65

    @pytest.mark.asyncio
    async def test_evaluate_design_around_no_suggestions(self, mock_judge):
        """Patents without design-around suggestions should be skipped."""
        gt = _make_ground_truth()
        report = _make_report_data()
        report["patent_analyses"][0]["design_around_suggestions"] = []

        mock_judge._client.messages.create = AsyncMock()  # Should not be called

        scores = await mock_judge.evaluate_design_around(report, gt)
        assert len(scores) == 0
        mock_judge._client.messages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_evaluate_legal_soundness(self, mock_judge):
        response_json = _make_judge_response_json("legal_soundness", overall_score=0.9)
        mock_response = _mock_anthropic_response(response_json)
        mock_judge._client.messages.create = AsyncMock(return_value=mock_response)

        gt = _make_ground_truth()
        report = _make_report_data()

        score = await mock_judge.evaluate_legal_soundness(report, gt)

        assert score.judge_type == "legal_soundness"
        assert score.overall_score == 0.9
        assert score.case_id == "para4_001"

    @pytest.mark.asyncio
    async def test_evaluate_case_calls_all_judges(self, mock_judge):
        """Full case evaluation calls all four judge types."""
        call_count = 0

        async def _mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            # Determine which judge type based on system prompt content
            system = kwargs.get("system", "")
            if "invalidity" in system.lower():
                return _mock_anthropic_response(
                    _make_judge_response_json("invalidity", overall_score=0.7)
                )
            elif "design-around" in system.lower() or "medicinal chemistry" in system.lower():
                return _mock_anthropic_response(
                    _make_judge_response_json("design_around", overall_score=0.65)
                )
            elif "senior patent attorney" in system.lower() or "legal soundness" in system.lower():
                return _mock_anthropic_response(
                    _make_judge_response_json("legal_soundness", overall_score=0.9)
                )
            else:
                return _mock_anthropic_response(
                    _make_judge_response_json("claim_analysis", overall_score=0.85)
                )

        mock_judge._client.messages.create = AsyncMock(side_effect=_mock_create)

        gt = _make_ground_truth()
        report = _make_report_data()

        result = await mock_judge.evaluate_case(report, gt)

        assert result.case_id == "para4_001"
        assert result.compound_name == "Fluoxetine"
        assert len(result.claim_scores) >= 1
        assert len(result.invalidity_scores) >= 1
        assert result.legal_soundness is not None
        assert result.overall_quality_score > 0
        assert result.total_cost_usd > 0
        # At least 4 calls: claim, invalidity, design-around, legal soundness
        assert call_count >= 4

    @pytest.mark.asyncio
    async def test_batch_evaluation(self, mock_judge):
        """Batch evaluation processes multiple cases."""
        response_json = _make_judge_response_json("claim_analysis", overall_score=0.8)
        mock_judge._client.messages.create = AsyncMock(
            return_value=_mock_anthropic_response(response_json)
        )

        gt1 = _make_ground_truth(case_id="case_001")
        gt2 = _make_ground_truth(case_id="case_002")
        report1 = _make_report_data()
        report2 = _make_report_data()

        results = await mock_judge.evaluate_batch([(report1, gt1), (report2, gt2)])

        assert len(results) == 2
        assert results[0].case_id == "case_001"
        assert results[1].case_id == "case_002"

    @pytest.mark.asyncio
    async def test_calibration_3_runs(self, mock_judge):
        """Calibration runs the judge 3 times and measures variance."""
        # Return slightly different scores on each run
        scores_sequence = [0.80, 0.82, 0.81]
        call_idx = 0

        async def _mock_create(**kwargs):
            nonlocal call_idx
            score = scores_sequence[call_idx % len(scores_sequence)]
            call_idx += 1
            return _mock_anthropic_response(
                _make_judge_response_json("legal_soundness", overall_score=score)
            )

        mock_judge._client.messages.create = AsyncMock(side_effect=_mock_create)

        gt = _make_ground_truth()
        report = _make_report_data()

        cal = await mock_judge.calibrate(report, gt, judge_type="legal_soundness", num_runs=3)

        assert cal.num_runs == 3
        assert len(cal.scores) == 3
        assert cal.variance < 0.15
        assert cal.is_stable is True
        assert 0.79 < cal.mean_score < 0.83

    @pytest.mark.asyncio
    async def test_calibration_high_variance(self, mock_judge):
        """High variance should flag as unstable."""
        scores_sequence = [0.3, 0.9, 0.5]
        call_idx = 0

        async def _mock_create(**kwargs):
            nonlocal call_idx
            score = scores_sequence[call_idx % len(scores_sequence)]
            call_idx += 1
            return _mock_anthropic_response(
                _make_judge_response_json("legal_soundness", overall_score=score)
            )

        mock_judge._client.messages.create = AsyncMock(side_effect=_mock_create)

        gt = _make_ground_truth()
        report = _make_report_data()

        cal = await mock_judge.calibrate(report, gt, judge_type="legal_soundness", num_runs=3)

        assert cal.variance >= 0.05  # Definitely not stable
        # With scores [0.3, 0.9, 0.5], variance is ~0.097

    @pytest.mark.asyncio
    async def test_empty_report_no_crash(self, mock_judge):
        """Judge handles empty report data gracefully."""
        response_json = _make_judge_response_json("legal_soundness", overall_score=0.3)
        mock_judge._client.messages.create = AsyncMock(
            return_value=_mock_anthropic_response(response_json)
        )

        gt = _make_ground_truth()
        empty_report: dict[str, Any] = {
            "risk_summary": {},
            "patent_analyses": [],
            "invalidity_assessments": [],
        }

        result = await mock_judge.evaluate_case(empty_report, gt)

        # Should still get a legal soundness evaluation
        assert result.legal_soundness is not None
        # No claim or invalidity or design-around evaluations (no data)
        assert len(result.claim_scores) == 0
        assert len(result.invalidity_scores) == 0
        assert len(result.design_around_scores) == 0

    @pytest.mark.asyncio
    async def test_malformed_llm_response(self, mock_judge):
        """Judge handles garbled LLM output without crashing."""
        mock_judge._client.messages.create = AsyncMock(
            return_value=_mock_anthropic_response("This is not valid JSON at all!!!")
        )

        gt = _make_ground_truth()
        report = _make_report_data()

        score = await mock_judge.evaluate_legal_soundness(report, gt)

        assert score.overall_score == 0.0
        assert "Failed to parse" in score.summary

    @pytest.mark.asyncio
    async def test_cost_tracked_per_call(self, mock_judge):
        """Each judge call tracks its individual cost."""
        response_json = _make_judge_response_json("claim_analysis", overall_score=0.8)
        mock_judge._client.messages.create = AsyncMock(
            return_value=_mock_anthropic_response(response_json, in_tokens=1500, out_tokens=800)
        )

        gt = _make_ground_truth()
        report = _make_report_data()

        scores = await mock_judge.evaluate_claim_analysis(report, gt)

        assert scores[0].input_tokens == 1500
        assert scores[0].output_tokens == 800
        expected_cost = (1500 * 1.00 + 800 * 5.00) / 1_000_000
        assert scores[0].cost_usd == pytest.approx(expected_cost)

    @pytest.mark.asyncio
    async def test_calibrate_claim_analysis(self, mock_judge):
        """Calibration works for claim_analysis type."""

        async def _mock_create(**kwargs):
            return _mock_anthropic_response(
                _make_judge_response_json("claim_analysis", overall_score=0.75)
            )

        mock_judge._client.messages.create = AsyncMock(side_effect=_mock_create)

        gt = _make_ground_truth()
        report = _make_report_data()

        cal = await mock_judge.calibrate(report, gt, judge_type="claim_analysis", num_runs=3)

        assert cal.judge_type == "claim_analysis"
        assert len(cal.scores) == 3

    @pytest.mark.asyncio
    async def test_calibrate_invalidity(self, mock_judge):
        """Calibration works for invalidity type."""

        async def _mock_create(**kwargs):
            return _mock_anthropic_response(
                _make_judge_response_json("invalidity", overall_score=0.65)
            )

        mock_judge._client.messages.create = AsyncMock(side_effect=_mock_create)

        gt = _make_ground_truth()
        report = _make_report_data()

        cal = await mock_judge.calibrate(report, gt, judge_type="invalidity", num_runs=3)

        assert cal.judge_type == "invalidity"
        assert len(cal.scores) == 3

    @pytest.mark.asyncio
    async def test_calibrate_design_around(self, mock_judge):
        """Calibration works for design_around type."""

        async def _mock_create(**kwargs):
            return _mock_anthropic_response(
                _make_judge_response_json("design_around", overall_score=0.55)
            )

        mock_judge._client.messages.create = AsyncMock(side_effect=_mock_create)

        gt = _make_ground_truth()
        report = _make_report_data()

        cal = await mock_judge.calibrate(report, gt, judge_type="design_around", num_runs=3)

        assert cal.judge_type == "design_around"
        assert len(cal.scores) == 3

    @pytest.mark.asyncio
    async def test_calibrate_unknown_type_raises(self, mock_judge):
        gt = _make_ground_truth()
        report = _make_report_data()

        with pytest.raises(ValueError, match="Unknown judge_type"):
            await mock_judge.calibrate(report, gt, judge_type="unknown_type")


# ---------------------------------------------------------------------------
# Tests: Edge cases and prompt template validation
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_prompt_templates_are_formattable(self):
        """All prompt templates can be formatted without KeyError."""
        # Claim analysis
        JUDGE_PROMPTS["claim_analysis"].format(
            compound_name="Test",
            compound_smiles="C",
            patent_id="US123",
            patent_title="Test",
            patent_assignee="Corp",
            litigation_ruling="upheld",
            claims_at_issue="[1, 2]",
            gt_elements_met="- element 1",
            gt_elements_not_met="- element 2",
            pipeline_claim_analysis="test output",
        )

        # Invalidity
        JUDGE_PROMPTS["invalidity"].format(
            patent_id="US123",
            patent_title="Test",
            litigation_ruling="invalidated",
            invalidity_basis="Obviousness",
            claims_challenged="[1]",
            claims_invalidated="[1]",
            claims_upheld="[]",
            pipeline_invalidity_output="test output",
        )

        # Design-around
        JUDGE_PROMPTS["design_around"].format(
            compound_name="Test",
            compound_smiles="C",
            therapeutic_area="Oncology",
            drug_class="kinase inhibitor",
            patent_id="US123",
            claim_limitations="- limitation 1",
            pipeline_design_around="test output",
        )

        # Legal soundness
        JUDGE_PROMPTS["legal_soundness"].format(
            compound_name="Test",
            compound_smiles="C",
            therapeutic_area="Oncology",
            litigation_ruling="upheld",
            invalidity_basis="N/A",
            expected_risk_today="HIGH",
            pipeline_risk_level="high",
            patents_analyzed_count=5,
            blocking_patents_count=2,
            pipeline_report_summary="test",
            pipeline_risk_summary="test",
            pipeline_blocking_patents="US123, US456",
            pipeline_key_risks="- risk 1",
        )

    def test_dimension_keys_match_prompts(self):
        """Each judge type's dimensions appear in its prompt template."""
        for judge_type, dimensions in JUDGE_DIMENSIONS.items():
            prompt = JUDGE_PROMPTS[judge_type]
            for dim in dimensions:
                # Convert snake_case to a word that should appear in the prompt
                # e.g. "element_identification_accuracy" -> "element" should be in prompt
                words = dim.split("_")
                # At least one word from the dimension name should appear
                found = any(word.lower() in prompt.lower() for word in words if len(word) > 3)
                assert found, f"Dimension '{dim}' not reflected in {judge_type} prompt"

    def test_judge_response_with_non_string_red_flags(self):
        """Handle case where red_flags contains non-string values."""
        data = {
            "element_identification_accuracy": {"score": 4, "reasoning": "test"},
            "reasoning_quality": {"score": 4, "reasoning": "test"},
            "consistency_with_outcome": {"score": 4, "reasoning": "test"},
            "factual_accuracy": {"score": 4, "reasoning": "test"},
            "confidence_calibration": {"score": 4, "reasoning": "test"},
            "red_flags": 42,  # Not a list
            "overall_score": 0.8,
            "summary": "test",
        }
        raw = json.dumps(data)
        _, flags, _, _, _ = parse_judge_response(raw, "claim_analysis")
        assert flags == ["42"]

    def test_judge_response_with_null_values(self):
        """Handle null values in dimension scores."""
        data = {
            "element_identification_accuracy": {"score": None, "reasoning": None},
            "reasoning_quality": {"score": 4, "reasoning": "test"},
            "consistency_with_outcome": {"score": 4, "reasoning": "test"},
            "factual_accuracy": {"score": 4, "reasoning": "test"},
            "confidence_calibration": {"score": 4, "reasoning": "test"},
            "red_flags": [],
            "overall_score": None,
            "summary": None,
        }
        raw = json.dumps(data)
        dims, _, _, overall, _summary = parse_judge_response(raw, "claim_analysis")
        assert dims[0].score == 1  # None -> fallback to 1
        assert overall == 0.0  # None -> 0.0
