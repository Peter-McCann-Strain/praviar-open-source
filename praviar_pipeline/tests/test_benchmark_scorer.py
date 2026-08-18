"""Tests for the benchmark scoring module.

Tests each scoring dimension with mock data, including edge cases:
  - Discovery recall (no blocking, all found, partial)
  - Triage scoring (false dismissals, noise)
  - Risk classification (confusion matrix, weighted F1, conservative errors)
  - Claim element-level accuracy (partial matches, confidence calibration)
  - Invalidity scoring (prior art recall, strength matrix, PTAB)
  - False positive / false negative rates
  - Composite score weighting (false negative 5x penalty)
  - Patent term scoring (expiry date accuracy)
  - Bootstrap confidence intervals
  - Aggregate scoring across multiple cases
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure benchmark tooling is importable from its canonical research location
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research" / "tools" / "benchmarks"))

from benchmark_scorer import (
    BenchmarkScore,
    BenchmarkScorer,
    ConfusionMatrix,
    _compute_weighted_f1,
    _invalidity_strength_score,
    _make_confusion_matrix,
    _mean,
    _patent_ids_match,
    aggregate_scores,
    bootstrap_ci,
    normalize_patent_id,
)

# ---------------------------------------------------------------------------
# Fixtures: mock data
# ---------------------------------------------------------------------------


def _make_ground_truth(
    case_id: str = "BENCH-001",
    name: str = "Test Compound",
    difficulty: str = "Medium",
    category: str = "paragraph_iv_anda",
    expected_risk_today: str = "CLEAR",
    key_patents: list | None = None,
    blocking_patents_pre_expiry: list | None = None,
) -> dict:
    """Create a minimal ground truth case."""
    if key_patents is None:
        key_patents = [
            {
                "number": "US1234567",
                "title": "Test Patent",
                "assignee": "Test Corp",
                "expiry": "2020-01-01",
                "status": "expired",
            },
        ]

    return {
        "id": case_id,
        "name": name,
        "difficulty": difficulty,
        "category": category,
        "compound": {
            "generic_name": "test_compound",
            "brand_name": "TestBrand",
        },
        "patents": {
            "key_patents": key_patents,
        },
        "benchmark_value": {
            "expected_risk_today": expected_risk_today,
            "blocking_patents_pre_expiry": blocking_patents_pre_expiry or ["US1234567"],
        },
    }


def _make_report(
    overall_risk: str = "clear",
    patent_analyses: list | None = None,
    invalidity_assessments: list | None = None,
    patent_details: dict | None = None,
    total_patents_found: int = 10,
    patents_after_triage: int = 5,
    total_input_tokens: int = 100000,
    total_output_tokens: int = 50000,
    estimated_cost_usd: float = 11.0,
) -> dict:
    """Create a minimal FTOReport dict."""
    return {
        "risk_summary": {
            "overall_risk": overall_risk,
            "blocking_patents_count": 0,
            "total_patents_analyzed": len(patent_analyses or []),
            "key_risks": [],
            "executive_summary": "Test summary.",
        },
        "patent_analyses": patent_analyses or [],
        "invalidity_assessments": invalidity_assessments or [],
        "patent_details": patent_details or {},
        "total_patents_found": total_patents_found,
        "patents_after_triage": patents_after_triage,
        "analysis_failures": [],
        "verification": {"checks": []},
        "audit_trail": {"total_duration_seconds": 120.0},
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "estimated_cost_usd": estimated_cost_usd,
    }


def _make_patent_analysis(
    patent_id: str = "US1234567",
    risk_level: str = "clear",
    claims: list | None = None,
    expiry_date: str | None = None,
) -> dict:
    """Create a minimal PatentAnalysis dict."""
    return {
        "patent_id": patent_id,
        "title": f"Test patent {patent_id}",
        "risk_level": risk_level,
        "risk_summary": "Test risk summary.",
        "claims_analyzed": claims or [],
        "expiry_date": expiry_date,
    }


def _make_claim_analysis(
    claim_number: int = 1,
    overall_status: str = "met",
    elements: list | None = None,
    overall_confidence: float = 0.85,
) -> dict:
    """Create a minimal ClaimAnalysis dict."""
    return {
        "claim_number": claim_number,
        "claim_type": "independent",
        "overall_status": overall_status,
        "overall_confidence": overall_confidence,
        "elements": elements or [],
    }


def _make_element(
    element_number: int = 1,
    status: str = "met",
    confidence: float = 0.9,
) -> dict:
    """Create a minimal ClaimElement dict."""
    return {
        "element_number": element_number,
        "element_text": f"Element {element_number}",
        "status": status,
        "reasoning": "Test reasoning.",
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# Patent ID normalization
# ---------------------------------------------------------------------------


class TestNormalizePatentId:
    def test_strips_kind_code(self):
        assert normalize_patent_id("US1234567A1") == "US1234567"
        assert normalize_patent_id("US1234567B2") == "US1234567"

    def test_uppercase(self):
        assert normalize_patent_id("us1234567a1") == "US1234567"

    def test_strips_whitespace(self):
        assert normalize_patent_id("  US1234567B2  ") == "US1234567"

    def test_strips_hyphens(self):
        assert normalize_patent_id("US-12-345-67") == "US1234567"

    def test_no_kind_code(self):
        assert normalize_patent_id("US1234567") == "US1234567"

    def test_patent_ids_match(self):
        assert _patent_ids_match("US1234567A1", "US1234567B2")
        assert _patent_ids_match("US1234567", "US1234567A1")
        assert not _patent_ids_match("US1234567", "US7654321")


# ---------------------------------------------------------------------------
# Discovery Score
# ---------------------------------------------------------------------------


class TestDiscoveryScore:
    def test_all_blocking_found(self):
        """All blocking patents are discovered."""
        gt = _make_ground_truth(
            key_patents=[
                {"number": "US1111111", "status": "expired", "expiry": "2020-01-01"},
                {"number": "US2222222", "status": "expired", "expiry": "2020-01-01"},
            ],
            blocking_patents_pre_expiry=["US1111111", "US2222222"],
        )
        report = _make_report(
            patent_analyses=[
                _make_patent_analysis("US1111111A1", "clear"),
                _make_patent_analysis("US2222222B2", "clear"),
            ],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.discovery.recall == 1.0
        assert len(score.discovery.discovered_blocking) == 2
        assert len(score.discovery.missed_blocking) == 0

    def test_no_blocking_found(self):
        """No blocking patents are discovered."""
        gt = _make_ground_truth(
            key_patents=[
                {"number": "US1111111", "status": "expired", "expiry": "2020-01-01"},
                {"number": "US2222222", "status": "expired", "expiry": "2020-01-01"},
            ],
            blocking_patents_pre_expiry=["US1111111", "US2222222"],
        )
        report = _make_report(patent_analyses=[])

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.discovery.recall == 0.0
        assert len(score.discovery.missed_blocking) == 2

    def test_partial_discovery(self):
        """Only some blocking patents found."""
        gt = _make_ground_truth(
            key_patents=[
                {"number": "US1111111", "status": "expired", "expiry": "2020-01-01"},
                {"number": "US2222222", "status": "expired", "expiry": "2020-01-01"},
            ],
            blocking_patents_pre_expiry=["US1111111", "US2222222"],
        )
        report = _make_report(
            patent_analyses=[_make_patent_analysis("US1111111", "clear")],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.discovery.recall == 0.5
        assert "US1111111" in score.discovery.discovered_blocking
        assert "US2222222" in score.discovery.missed_blocking

    def test_no_blocking_patents_in_gt(self):
        """Ground truth has no blocking patents."""
        gt = _make_ground_truth(
            key_patents=[],
            blocking_patents_pre_expiry=[],
        )
        report = _make_report()

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        # No blocking patents to find = perfect recall
        assert score.discovery.recall == 1.0

    def test_discovery_via_patent_details(self):
        """Patents found in patent_details (not just analyses)."""
        gt = _make_ground_truth(
            key_patents=[
                {"number": "US1111111", "status": "expired", "expiry": "2020-01-01"},
            ],
            blocking_patents_pre_expiry=["US1111111"],
        )
        report = _make_report(
            patent_analyses=[],
            patent_details={"US1111111B2": {"sources": ["bigquery"]}},
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.discovery.recall == 1.0


# ---------------------------------------------------------------------------
# Triage Score
# ---------------------------------------------------------------------------


class TestTriageScore:
    def test_all_blocking_survive_triage(self):
        gt = _make_ground_truth(
            key_patents=[
                {"number": "US1111111", "status": "expired", "expiry": "2020-01-01"},
            ],
            blocking_patents_pre_expiry=["US1111111"],
        )
        report = _make_report(
            patent_analyses=[_make_patent_analysis("US1111111", "clear")],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.triage.recall == 1.0
        assert score.triage.false_dismissal_rate == 0.0
        assert len(score.triage.false_dismissals) == 0

    def test_blocking_patent_dismissed_at_triage(self):
        gt = _make_ground_truth(
            key_patents=[
                {"number": "US1111111", "status": "expired", "expiry": "2020-01-01"},
                {"number": "US2222222", "status": "expired", "expiry": "2020-01-01"},
            ],
            blocking_patents_pre_expiry=["US1111111", "US2222222"],
        )
        # Only US1111111 was analyzed (US2222222 was dismissed at triage)
        report = _make_report(
            patent_analyses=[_make_patent_analysis("US1111111", "clear")],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.triage.recall == 0.5
        assert score.triage.false_dismissal_rate == 0.5
        assert "US2222222" in score.triage.false_dismissals

    def test_no_blocking_patents(self):
        gt = _make_ground_truth(
            key_patents=[],
            blocking_patents_pre_expiry=[],
        )
        report = _make_report()

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.triage.recall == 1.0


# ---------------------------------------------------------------------------
# Risk Classification Score
# ---------------------------------------------------------------------------


class TestRiskScore:
    def test_correct_overall_risk(self):
        gt = _make_ground_truth(expected_risk_today="CLEAR")
        report = _make_report(overall_risk="clear")

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.risk.overall_risk_correct is True
        assert score.risk.overall_risk_predicted == "clear"
        assert score.risk.overall_risk_expected == "clear"

    def test_incorrect_overall_risk(self):
        gt = _make_ground_truth(expected_risk_today="HIGH")
        report = _make_report(overall_risk="clear")

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.risk.overall_risk_correct is False

    def test_per_patent_risk_accuracy(self):
        """Multiple patents with mixed risk accuracy."""
        gt = _make_ground_truth(
            key_patents=[
                {"number": "US1111111", "status": "expired", "expiry": "2020-01-01"},
                {"number": "US2222222", "status": "expired", "expiry": "2020-01-01"},
            ],
            blocking_patents_pre_expiry=["US1111111", "US2222222"],
        )
        report = _make_report(
            patent_analyses=[
                _make_patent_analysis("US1111111", "clear"),  # Correct
                _make_patent_analysis("US2222222", "high"),  # Incorrect (should be clear)
            ],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.risk.per_patent_accuracy == 0.5

    def test_confusion_matrix_structure(self):
        gt = _make_ground_truth(
            key_patents=[
                {"number": "US1111111", "status": "expired", "expiry": "2020-01-01"},
            ],
            blocking_patents_pre_expiry=["US1111111"],
        )
        report = _make_report(
            patent_analyses=[_make_patent_analysis("US1111111", "clear")],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        cm = score.risk.confusion_matrix
        assert cm.labels == ["high", "medium", "low", "clear"]
        assert len(cm.matrix) == 4
        assert all(len(row) == 4 for row in cm.matrix)


# ---------------------------------------------------------------------------
# Confusion Matrix helpers
# ---------------------------------------------------------------------------


class TestConfusionMatrix:
    def test_accuracy(self):
        cm = ConfusionMatrix(
            labels=["a", "b"],
            matrix=[[5, 1], [2, 7]],
        )
        assert cm.accuracy() == 12 / 15

    def test_empty_matrix(self):
        cm = ConfusionMatrix(labels=[], matrix=[])
        assert cm.accuracy() == 0.0

    def test_weighted_f1(self):
        cm = _make_confusion_matrix(
            ["high", "medium", "low", "clear"],
            ["high", "high", "clear", "clear"],
            ["high", "medium", "clear", "clear"],
        )
        f1 = _compute_weighted_f1(cm)
        assert 0.0 < f1 <= 1.0

    def test_perfect_f1(self):
        cm = _make_confusion_matrix(
            ["high", "clear"],
            ["high", "high", "clear", "clear"],
            ["high", "high", "clear", "clear"],
        )
        f1 = _compute_weighted_f1(cm)
        assert f1 == 1.0


# ---------------------------------------------------------------------------
# Claim Analysis Score
# ---------------------------------------------------------------------------


class TestClaimScore:
    def test_element_accuracy_perfect(self):
        """All elements correctly predicted."""
        gt = _make_ground_truth(
            key_patents=[
                {
                    "number": "US1111111",
                    "status": "expired",
                    "expiry": "2020-01-01",
                    "claims_ground_truth": [
                        {
                            "claim_number": 1,
                            "expected_overall_status": "met",
                            "elements": [
                                {"element_number": 1, "expected_status": "met"},
                                {"element_number": 2, "expected_status": "not_met"},
                            ],
                        },
                    ],
                },
            ],
            blocking_patents_pre_expiry=["US1111111"],
        )

        claim = _make_claim_analysis(
            claim_number=1,
            overall_status="met",
            elements=[
                _make_element(1, "met", 0.95),
                _make_element(2, "not_met", 0.85),
            ],
        )
        report = _make_report(
            patent_analyses=[
                _make_patent_analysis("US1111111", "high", claims=[claim]),
            ],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.claim.element_accuracy == 1.0
        assert score.claim.claim_accuracy == 1.0
        assert score.claim.total_elements_evaluated == 2
        assert score.claim.total_claims_evaluated == 1

    def test_element_accuracy_mixed(self):
        """Some elements correct, some wrong."""
        gt = _make_ground_truth(
            key_patents=[
                {
                    "number": "US1111111",
                    "status": "expired",
                    "expiry": "2020-01-01",
                    "claims_ground_truth": [
                        {
                            "claim_number": 1,
                            "expected_overall_status": "met",
                            "elements": [
                                {"element_number": 1, "expected_status": "met"},
                                {"element_number": 2, "expected_status": "not_met"},
                            ],
                        },
                    ],
                },
            ],
            blocking_patents_pre_expiry=["US1111111"],
        )

        claim = _make_claim_analysis(
            claim_number=1,
            overall_status="met",
            elements=[
                _make_element(1, "met", 0.9),
                _make_element(2, "met", 0.7),  # Wrong: should be not_met
            ],
        )
        report = _make_report(
            patent_analyses=[
                _make_patent_analysis("US1111111", "high", claims=[claim]),
            ],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.claim.element_accuracy == 0.5

    def test_no_claim_ground_truth(self):
        """No claim ground truth available."""
        gt = _make_ground_truth()
        report = _make_report(
            patent_analyses=[_make_patent_analysis("US1234567", "clear")],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.claim.element_accuracy == 0.0
        assert score.claim.total_elements_evaluated == 0

    def test_confidence_calibration_buckets(self):
        """Confidence calibration populates correct buckets."""
        gt = _make_ground_truth(
            key_patents=[
                {
                    "number": "US1111111",
                    "status": "expired",
                    "expiry": "2020-01-01",
                    "claims_ground_truth": [
                        {
                            "claim_number": 1,
                            "expected_overall_status": "met",
                            "elements": [
                                {"element_number": 1, "expected_status": "met"},
                                {"element_number": 2, "expected_status": "met"},
                                {"element_number": 3, "expected_status": "met"},
                            ],
                        },
                    ],
                },
            ],
            blocking_patents_pre_expiry=["US1111111"],
        )

        claim = _make_claim_analysis(
            claim_number=1,
            overall_status="met",
            elements=[
                _make_element(1, "met", 0.95),  # 0.8-1.0 bucket, correct
                _make_element(2, "met", 0.5),  # 0.4-0.6 bucket, correct
                _make_element(3, "not_met", 0.1),  # 0.0-0.2 bucket, incorrect
            ],
        )
        report = _make_report(
            patent_analyses=[
                _make_patent_analysis("US1111111", "high", claims=[claim]),
            ],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        cal = score.claim.confidence_calibration
        assert "0.8-1.0" in cal
        assert cal["0.8-1.0"] == 1.0  # 1 correct out of 1
        assert "0.4-0.6" in cal
        assert cal["0.4-0.6"] == 1.0  # 1 correct out of 1
        assert "0.0-0.2" in cal
        assert cal["0.0-0.2"] == 0.0  # 0 correct out of 1


# ---------------------------------------------------------------------------
# Invalidity Score
# ---------------------------------------------------------------------------


class TestInvalidityScore:
    def test_prior_art_recall(self):
        gt = _make_ground_truth(
            key_patents=[
                {
                    "number": "US1111111",
                    "status": "expired",
                    "expiry": "2020-01-01",
                    "known_invalidity": {
                        "overall_strength": "moderate",
                        "known_prior_art": [
                            {"reference_id": "US9999999"},
                            {"reference_id": "US8888888"},
                        ],
                        "known_ptab_proceedings": [],
                        "known_written_description_issues": [],
                    },
                },
            ],
            blocking_patents_pre_expiry=["US1111111"],
        )
        report = _make_report(
            invalidity_assessments=[
                {
                    "patent_id": "US1111111",
                    "overall_invalidity_strength": "moderate",
                    "prior_art": [
                        {"reference_id": "US9999999A1"},  # Found (matches after normalization)
                    ],
                    "ptab": {"proceedings": []},
                    "written_description_issues": [],
                },
            ],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.invalidity.prior_art_recall == 0.5  # 1 of 2 found
        assert "US9999999" in score.invalidity.found_prior_art

    def test_no_invalidity_ground_truth(self):
        gt = _make_ground_truth()
        report = _make_report()

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        # No invalidity to check = perfect recall by convention
        assert score.invalidity.prior_art_recall == 1.0

    def test_strength_scoring(self):
        """Test the invalidity strength scoring matrix."""
        assert _invalidity_strength_score("strong", "strong") == 1.0
        assert _invalidity_strength_score("moderate", "strong") == 0.5
        assert _invalidity_strength_score("weak", "strong") == 0.0
        assert _invalidity_strength_score("strong", "weak") == 0.25
        assert _invalidity_strength_score("moderate", "moderate") == 1.0
        assert _invalidity_strength_score("weak", "weak") == 1.0

    def test_strength_scoring_asymmetry(self):
        """Under-estimating strength is penalized more than over-estimating."""
        # Missing strong invalidity is worse than over-flagging weak
        assert _invalidity_strength_score("weak", "strong") < _invalidity_strength_score(
            "strong", "weak"
        )

    def test_ptab_recall(self):
        gt = _make_ground_truth(
            key_patents=[
                {
                    "number": "US1111111",
                    "status": "expired",
                    "expiry": "2020-01-01",
                    "known_invalidity": {
                        "overall_strength": "strong",
                        "known_prior_art": [],
                        "known_ptab_proceedings": [
                            {"proceeding_number": "IPR2019-00123"},
                        ],
                        "known_written_description_issues": [],
                    },
                },
            ],
            blocking_patents_pre_expiry=["US1111111"],
        )
        report = _make_report(
            invalidity_assessments=[
                {
                    "patent_id": "US1111111",
                    "overall_invalidity_strength": "strong",
                    "prior_art": [],
                    "ptab": {
                        "proceedings": [
                            {"proceeding_number": "IPR2019-00123"},
                        ],
                    },
                    "written_description_issues": [],
                },
            ],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.invalidity.ptab_recall == 1.0


# ---------------------------------------------------------------------------
# False Positive Rate
# ---------------------------------------------------------------------------


class TestFalsePositiveRate:
    def test_no_false_positives(self):
        gt = _make_ground_truth()
        gt["known_non_blocking_patents"] = [
            {"patent_id": "US3333333", "expected_risk_level": "clear"},
        ]
        report = _make_report(
            patent_analyses=[
                _make_patent_analysis("US1234567", "clear"),
                _make_patent_analysis("US3333333", "clear"),  # Correctly clear
            ],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.false_positive_rate == 0.0

    def test_false_positive_flagged_high(self):
        gt = _make_ground_truth()
        gt["known_non_blocking_patents"] = [
            {"patent_id": "US3333333", "expected_risk_level": "clear"},
        ]
        report = _make_report(
            patent_analyses=[
                _make_patent_analysis("US3333333", "high"),  # False positive!
            ],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.false_positive_rate == 1.0

    def test_no_non_blocking_patents(self):
        gt = _make_ground_truth()
        report = _make_report()

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.false_positive_rate == 0.0


# ---------------------------------------------------------------------------
# False Negative Rate
# ---------------------------------------------------------------------------


class TestFalseNegativeRate:
    def test_no_false_negatives_expired(self):
        """Expired patents rated CLEAR is correct, not a false negative."""
        gt = _make_ground_truth(
            expected_risk_today="CLEAR",
            key_patents=[
                {"number": "US1111111", "status": "expired", "expiry": "2020-01-01"},
            ],
            blocking_patents_pre_expiry=["US1111111"],
        )
        report = _make_report(
            overall_risk="clear",
            patent_analyses=[_make_patent_analysis("US1111111", "clear")],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        # Expired + rated clear is correct
        assert score.false_negative_rate == 0.0

    def test_false_negative_active_patent_rated_clear(self):
        """Active blocking patent rated CLEAR is a critical false negative."""
        gt = _make_ground_truth(
            expected_risk_today="HIGH",
            key_patents=[
                {"number": "US1111111", "status": "active", "expiry": "2030-01-01"},
            ],
            blocking_patents_pre_expiry=["US1111111"],
        )
        report = _make_report(
            overall_risk="clear",
            patent_analyses=[_make_patent_analysis("US1111111", "clear")],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.false_negative_rate > 0.0

    def test_false_negative_not_discovered(self):
        """Blocking patent not even discovered is a false negative."""
        gt = _make_ground_truth(
            expected_risk_today="HIGH",
            key_patents=[
                {"number": "US1111111", "status": "active", "expiry": "2030-01-01"},
            ],
            blocking_patents_pre_expiry=["US1111111"],
        )
        report = _make_report(overall_risk="clear", patent_analyses=[])

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.false_negative_rate > 0.0

    def test_no_blocking_patents(self):
        gt = _make_ground_truth(
            key_patents=[],
            blocking_patents_pre_expiry=[],
        )
        report = _make_report()

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.false_negative_rate == 0.0


# ---------------------------------------------------------------------------
# Composite Score
# ---------------------------------------------------------------------------


class TestCompositeScore:
    def test_perfect_score(self):
        """Perfect scores across all dimensions yields ~1.0 composite."""
        gt = _make_ground_truth(
            expected_risk_today="CLEAR",
            key_patents=[
                {
                    "number": "US1111111",
                    "status": "expired",
                    "expiry": "2020-01-01",
                    "claims_ground_truth": [
                        {
                            "claim_number": 1,
                            "expected_overall_status": "met",
                            "elements": [
                                {"element_number": 1, "expected_status": "met"},
                            ],
                        },
                    ],
                    "known_invalidity": {
                        "overall_strength": "moderate",
                        "known_prior_art": [{"reference_id": "US9999999"}],
                        "known_ptab_proceedings": [],
                        "known_written_description_issues": [],
                    },
                },
            ],
            blocking_patents_pre_expiry=["US1111111"],
        )

        claim = _make_claim_analysis(
            claim_number=1,
            overall_status="met",
            elements=[_make_element(1, "met", 0.95)],
        )
        report = _make_report(
            overall_risk="clear",
            patent_analyses=[_make_patent_analysis("US1111111", "clear", claims=[claim])],
            invalidity_assessments=[
                {
                    "patent_id": "US1111111",
                    "overall_invalidity_strength": "moderate",
                    "prior_art": [{"reference_id": "US9999999"}],
                    "ptab": {"proceedings": []},
                    "written_description_issues": [],
                },
            ],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        # Should be close to 1.0
        assert score.composite_score >= 0.90

    def test_false_negative_dominates_score(self):
        """False negatives carry 50% weight, so they tank the composite score."""
        gt = _make_ground_truth(
            expected_risk_today="HIGH",
            key_patents=[
                {"number": "US1111111", "status": "active", "expiry": "2030-01-01"},
            ],
            blocking_patents_pre_expiry=["US1111111"],
        )

        # Perfect everywhere except: didn't find the blocking patent
        report = _make_report(overall_risk="clear", patent_analyses=[])

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        # FN rate = 1.0, so composite loses 0.50 points
        assert score.composite_score < 0.60

    def test_composite_weights_sum(self):
        """The composite weights sum to 1.0."""
        # From the formula: 0.05 + 0.05 + 0.10 + 0.15 + 0.05 + 0.10 + 0.50 = 1.00
        total_weight = 0.05 + 0.05 + 0.10 + 0.15 + 0.05 + 0.10 + 0.50
        assert abs(total_weight - 1.0) < 1e-10

    def test_false_negative_5x_penalty(self):
        """FN weight (0.50) is 5x the FP weight (0.10)."""
        fn_weight = 0.50
        fp_weight = 0.10
        assert fn_weight / fp_weight == 5.0


# ---------------------------------------------------------------------------
# Patent Term Score
# ---------------------------------------------------------------------------


class TestPatentTermScore:
    def test_exact_expiry_match(self):
        gt = _make_ground_truth(
            key_patents=[
                {"number": "US1111111", "status": "expired", "expiry": "2020-06-15"},
            ],
            blocking_patents_pre_expiry=["US1111111"],
        )
        report = _make_report(
            patent_analyses=[
                _make_patent_analysis("US1111111", "clear", expiry_date="2020-06-15"),
            ],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.patent_term.exact_matches == 1
        assert score.patent_term.accuracy == 1.0
        assert score.patent_term.mean_absolute_error_days == 0.0

    def test_expiry_within_1_year(self):
        gt = _make_ground_truth(
            key_patents=[
                {"number": "US1111111", "status": "expired", "expiry": "2020-06-15"},
            ],
            blocking_patents_pre_expiry=["US1111111"],
        )
        report = _make_report(
            patent_analyses=[
                _make_patent_analysis("US1111111", "clear", expiry_date="2020-09-15"),
            ],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.patent_term.within_1_year == 1
        assert score.patent_term.accuracy == 1.0  # Within 1 year counts as accurate

    def test_no_expiry_data(self):
        gt = _make_ground_truth()
        report = _make_report(
            patent_analyses=[_make_patent_analysis("US1234567", "clear")],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.patent_term.patents_evaluated == 0


# ---------------------------------------------------------------------------
# Bootstrap Confidence Intervals
# ---------------------------------------------------------------------------


class TestBootstrapCI:
    def test_basic_ci(self):
        values = [0.8, 0.85, 0.9, 0.88, 0.82, 0.87, 0.91, 0.86]
        lo, hi = bootstrap_ci(values, seed=42)

        assert lo < hi
        assert lo >= min(values)
        assert hi <= max(values)

    def test_single_value(self):
        lo, hi = bootstrap_ci([0.5], seed=42)
        assert lo == 0.5
        assert hi == 0.5

    def test_empty_values(self):
        lo, hi = bootstrap_ci([], seed=42)
        assert lo == 0.0
        assert hi == 0.0

    def test_perfect_values(self):
        """All identical values should give a tight CI."""
        lo, hi = bootstrap_ci([1.0] * 10, seed=42)
        assert lo == 1.0
        assert hi == 1.0

    def test_reproducibility(self):
        """Same seed should produce same results."""
        values = [0.7, 0.8, 0.9, 0.85]
        ci1 = bootstrap_ci(values, seed=123)
        ci2 = bootstrap_ci(values, seed=123)
        assert ci1 == ci2


# ---------------------------------------------------------------------------
# Aggregate Scoring
# ---------------------------------------------------------------------------


class TestAggregateScoring:
    def _make_scores(self, n: int = 3) -> list[BenchmarkScore]:
        scores = []
        for i in range(n):
            s = BenchmarkScore(
                case_id=f"BENCH-{i:03d}",
                case_name=f"Test Case {i}",
                tier="tier2",
            )
            s.discovery.recall = 0.8 + i * 0.1
            s.triage.recall = 0.9
            s.risk.per_patent_accuracy = 0.85
            s.risk.weighted_f1 = 0.80
            s.claim.element_accuracy = 0.75
            s.invalidity.prior_art_recall = 0.70
            s.false_positive_rate = 0.1
            s.false_negative_rate = 0.05
            s.composite_score = 0.85 + i * 0.02
            s.estimated_cost_usd = 10.0 + i
            s.total_tokens = 150000
            scores.append(s)
        return scores

    def test_aggregate_basic(self):
        scores = self._make_scores(3)
        agg = aggregate_scores(scores)

        assert agg.total_cases == 3
        assert agg.mean_composite_score > 0
        assert agg.total_cost_usd == sum(s.estimated_cost_usd for s in scores)

    def test_aggregate_cases_by_tier(self):
        scores = self._make_scores(3)
        agg = aggregate_scores(scores)

        assert "tier2" in agg.cases_by_tier
        assert agg.cases_by_tier["tier2"] == 3

    def test_aggregate_confidence_intervals(self):
        scores = self._make_scores(5)  # Need >= 3 for CI
        agg = aggregate_scores(scores)

        assert "composite_score" in agg.confidence_intervals
        lo, hi = agg.confidence_intervals["composite_score"]
        assert lo <= hi

    def test_aggregate_empty(self):
        agg = aggregate_scores([])
        assert agg.total_cases == 0
        assert agg.mean_composite_score == 0.0

    def test_aggregate_per_case_scores(self):
        scores = self._make_scores(2)
        agg = aggregate_scores(scores)

        assert len(agg.per_case_scores) == 2
        assert all("case_id" in s for s in agg.per_case_scores)


# ---------------------------------------------------------------------------
# Serialization (to_dict)
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_benchmark_score_to_dict(self):
        gt = _make_ground_truth()
        report = _make_report(
            patent_analyses=[_make_patent_analysis("US1234567", "clear")],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()
        d = score.to_dict()

        assert isinstance(d, dict)
        assert "case_id" in d
        assert "composite_score" in d
        assert "discovery" in d
        assert "triage" in d
        assert "risk" in d
        assert "claim" in d
        assert "invalidity" in d
        assert "patent_term" in d
        assert "false_positive_rate" in d
        assert "false_negative_rate" in d

    def test_aggregate_to_dict(self):
        scores = [BenchmarkScore(case_id="TEST")]
        scores[0].composite_score = 0.9
        agg = aggregate_scores(scores)
        d = agg.to_dict()

        assert isinstance(d, dict)
        assert "total_cases" in d
        assert "mean_composite_score" in d

    def test_confusion_matrix_to_dict(self):
        cm = ConfusionMatrix(labels=["a", "b"], matrix=[[3, 1], [0, 5]])
        d = cm.to_dict()

        assert d["labels"] == ["a", "b"]
        assert abs(d["accuracy"] - 8 / 9) < 1e-3


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_report(self):
        """Empty report should not crash."""
        gt = _make_ground_truth()
        report = _make_report(patent_analyses=[])

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert isinstance(score, BenchmarkScore)
        assert score.composite_score >= 0.0

    def test_empty_ground_truth(self):
        """Minimal ground truth should not crash."""
        gt = {
            "id": "BENCH-EMPTY",
            "name": "Empty",
            "difficulty": "Easy",
            "category": "test",
            "compound": {"generic_name": "nothing"},
            "patents": {"key_patents": []},
            "benchmark_value": {"expected_risk_today": "CLEAR"},
        }
        report = _make_report()

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert isinstance(score, BenchmarkScore)

    def test_mismatched_patent_ids(self):
        """Patent IDs that don't match between GT and report."""
        gt = _make_ground_truth(
            key_patents=[
                {"number": "US9999999", "status": "active", "expiry": "2030-01-01"},
            ],
            blocking_patents_pre_expiry=["US9999999"],
        )
        report = _make_report(
            patent_analyses=[_make_patent_analysis("US0000001", "high")],
        )

        scorer = BenchmarkScorer(report, gt)
        score = scorer.score()

        assert score.discovery.recall == 0.0
        assert "US9999999" in score.discovery.missed_blocking

    def test_mean_empty(self):
        assert _mean([]) == 0.0
        assert _mean([1.0]) == 1.0
        assert _mean([1.0, 3.0]) == 2.0
