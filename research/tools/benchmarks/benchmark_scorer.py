"""Benchmark scoring module for Praviar Pipeline FTO pipeline validation.

Takes a pipeline FTOReport + ground truth benchmark case and computes
all scoring dimensions defined in the validation plan:

  1. Discovery Score (recall, precision@K)
  2. Triage Score (recall, precision, false dismissal rate)
  3. Risk Classification Score (accuracy, F1, confusion matrix)
  4. Claim Analysis Score (element-level, claim-level, confidence calibration)
  5. Invalidity Score (prior art recall, strength accuracy, PTAB recall)
  6. False Positive Rate
  7. False Negative Rate
  8. Composite Score (weighted, false negatives 5x penalty)
  9. Patent Term Score (expiry date accuracy)

Usage:
    from benchmark_scorer import BenchmarkScorer
    scorer = BenchmarkScorer(report, ground_truth)
    score = scorer.score()
"""

from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

# Single source of truth for patent-ID normalization lives in scoring_core.
# We support both import styles used across the repo:
#   * Package import: ``from research.tools.benchmarks import scoring_core``
#     (used when the repo root is on sys.path, e.g. ``pytest research/tests``).
#   * Direct path import: ``import scoring_core`` (used by praviar_pipeline tests
#     that insert ``research/tools/benchmarks/`` onto sys.path).
try:
    from research.tools.benchmarks import scoring_core
except ImportError:  # pragma: no cover - exercised by praviar_pipeline test path
    import scoring_core  # type: ignore[no-redef]

# Re-exported below as ``normalize_patent_id`` so existing call sites keep
# working without churn. Aliasing here makes the import statically used and
# keeps ruff from flagging it as F401.
normalize_patent_id = scoring_core.normalize_patent_id


# ---------------------------------------------------------------------------
# Pydantic-free data classes — these files live in research tooling, not the package
# ---------------------------------------------------------------------------


@dataclass
class ConfusionMatrix:
    """Generic NxN confusion matrix with labeled axes."""

    labels: list[str]
    matrix: list[list[int]]

    def total(self) -> int:
        return sum(sum(row) for row in self.matrix)

    def accuracy(self) -> float:
        t = self.total()
        if t == 0:
            return 0.0
        return sum(self.matrix[i][i] for i in range(len(self.labels))) / t

    def to_dict(self) -> dict[str, Any]:
        return {
            "labels": self.labels,
            "matrix": self.matrix,
            "accuracy": round(self.accuracy(), 4),
            "total": self.total(),
        }


@dataclass
class DiscoveryScore:
    """Patent discovery scoring (Steps 1-2)."""

    recall: float = 0.0
    precision_at_k: dict[int, float] = field(default_factory=dict)
    discovered_blocking: list[str] = field(default_factory=list)
    missed_blocking: list[str] = field(default_factory=list)
    source_attribution: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recall": round(self.recall, 4),
            "precision_at_k": {k: round(v, 4) for k, v in self.precision_at_k.items()},
            "discovered_blocking": self.discovered_blocking,
            "missed_blocking": self.missed_blocking,
            "source_attribution": self.source_attribution,
        }


@dataclass
class TriageScore:
    """Patent triage scoring (Step 3)."""

    recall: float = 0.0
    precision: float = 0.0
    false_dismissals: list[str] = field(default_factory=list)
    false_dismissal_rate: float = 0.0
    noise_ratio: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "recall": round(self.recall, 4),
            "precision": round(self.precision, 4),
            "false_dismissals": self.false_dismissals,
            "false_dismissal_rate": round(self.false_dismissal_rate, 4),
            "noise_ratio": round(self.noise_ratio, 4),
        }


@dataclass
class RiskScore:
    """Risk classification scoring (Steps 4 and 8)."""

    per_patent_accuracy: float = 0.0
    overall_risk_correct: bool = False
    overall_risk_predicted: str = ""
    overall_risk_expected: str = ""
    confusion_matrix: ConfusionMatrix = field(
        default_factory=lambda: ConfusionMatrix(labels=[], matrix=[])
    )
    conservative_error_rate: float = 0.0
    weighted_f1: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "per_patent_accuracy": round(self.per_patent_accuracy, 4),
            "overall_risk_correct": self.overall_risk_correct,
            "overall_risk_predicted": self.overall_risk_predicted,
            "overall_risk_expected": self.overall_risk_expected,
            "confusion_matrix": self.confusion_matrix.to_dict(),
            "conservative_error_rate": round(self.conservative_error_rate, 4),
            "weighted_f1": round(self.weighted_f1, 4),
        }


@dataclass
class ClaimScore:
    """Claim-level and element-level analysis scoring (Step 4)."""

    element_accuracy: float = 0.0
    element_confusion_matrix: ConfusionMatrix = field(
        default_factory=lambda: ConfusionMatrix(labels=[], matrix=[])
    )
    claim_accuracy: float = 0.0
    confidence_calibration: dict[str, float] = field(default_factory=dict)
    total_elements_evaluated: int = 0
    total_claims_evaluated: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "element_accuracy": round(self.element_accuracy, 4),
            "element_confusion_matrix": self.element_confusion_matrix.to_dict(),
            "claim_accuracy": round(self.claim_accuracy, 4),
            "confidence_calibration": {
                k: round(v, 4) for k, v in self.confidence_calibration.items()
            },
            "total_elements_evaluated": self.total_elements_evaluated,
            "total_claims_evaluated": self.total_claims_evaluated,
        }


@dataclass
class InvalidityScore:
    """Invalidity analysis scoring (Step 6)."""

    prior_art_recall: float = 0.0
    strength_score: float = 0.0
    ptab_recall: float = 0.0
    written_description_detected: bool = False
    found_prior_art: list[str] = field(default_factory=list)
    missed_prior_art: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prior_art_recall": round(self.prior_art_recall, 4),
            "strength_score": round(self.strength_score, 4),
            "ptab_recall": round(self.ptab_recall, 4),
            "written_description_detected": self.written_description_detected,
            "found_prior_art": self.found_prior_art,
            "missed_prior_art": self.missed_prior_art,
        }


@dataclass
class PatentTermScore:
    """Patent term / expiry date scoring."""

    patents_evaluated: int = 0
    exact_matches: int = 0
    within_1_year: int = 0
    within_3_years: int = 0
    accuracy: float = 0.0
    mean_absolute_error_days: float = 0.0
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "patents_evaluated": self.patents_evaluated,
            "exact_matches": self.exact_matches,
            "within_1_year": self.within_1_year,
            "within_3_years": self.within_3_years,
            "accuracy": round(self.accuracy, 4),
            "mean_absolute_error_days": round(self.mean_absolute_error_days, 1),
            "details": self.details,
        }


@dataclass
class BenchmarkScore:
    """Complete benchmark score for a single case."""

    case_id: str = ""
    case_name: str = ""
    tier: str = ""
    category: str = ""

    discovery: DiscoveryScore = field(default_factory=DiscoveryScore)
    triage: TriageScore = field(default_factory=TriageScore)
    risk: RiskScore = field(default_factory=RiskScore)
    claim: ClaimScore = field(default_factory=ClaimScore)
    invalidity: InvalidityScore = field(default_factory=InvalidityScore)
    patent_term: PatentTermScore = field(default_factory=PatentTermScore)

    false_positive_rate: float = 0.0
    false_negative_rate: float = 0.0
    composite_score: float = 0.0

    # Diagnostics
    pipeline_duration_seconds: float = 0.0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    verification_checks_passed: int = 0
    verification_checks_failed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "case_name": self.case_name,
            "tier": self.tier,
            "category": self.category,
            "discovery": self.discovery.to_dict(),
            "triage": self.triage.to_dict(),
            "risk": self.risk.to_dict(),
            "claim": self.claim.to_dict(),
            "invalidity": self.invalidity.to_dict(),
            "patent_term": self.patent_term.to_dict(),
            "false_positive_rate": round(self.false_positive_rate, 4),
            "false_negative_rate": round(self.false_negative_rate, 4),
            "composite_score": round(self.composite_score, 4),
            "pipeline_duration_seconds": round(self.pipeline_duration_seconds, 2),
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 4),
            "verification_checks_passed": self.verification_checks_passed,
            "verification_checks_failed": self.verification_checks_failed,
        }


@dataclass
class AggregateScore:
    """Aggregate statistics across all benchmark cases."""

    total_cases: int = 0
    cases_by_tier: dict[str, int] = field(default_factory=dict)

    mean_discovery_recall: float = 0.0
    mean_triage_recall: float = 0.0
    mean_risk_accuracy: float = 0.0
    mean_element_accuracy: float = 0.0
    mean_invalidity_recall: float = 0.0
    mean_false_positive_rate: float = 0.0
    mean_false_negative_rate: float = 0.0
    mean_composite_score: float = 0.0

    overall_risk_confusion_matrix: ConfusionMatrix = field(
        default_factory=lambda: ConfusionMatrix(labels=[], matrix=[])
    )

    total_blocking_patents: int = 0
    total_discovered_blocking: int = 0
    total_missed_blocking: int = 0
    total_false_dismissals: int = 0

    confidence_intervals: dict[str, tuple[float, float]] = field(default_factory=dict)

    total_cost_usd: float = 0.0
    total_tokens: int = 0
    total_duration_seconds: float = 0.0

    per_case_scores: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cases": self.total_cases,
            "cases_by_tier": self.cases_by_tier,
            "mean_discovery_recall": round(self.mean_discovery_recall, 4),
            "mean_triage_recall": round(self.mean_triage_recall, 4),
            "mean_risk_accuracy": round(self.mean_risk_accuracy, 4),
            "mean_element_accuracy": round(self.mean_element_accuracy, 4),
            "mean_invalidity_recall": round(self.mean_invalidity_recall, 4),
            "mean_false_positive_rate": round(self.mean_false_positive_rate, 4),
            "mean_false_negative_rate": round(self.mean_false_negative_rate, 4),
            "mean_composite_score": round(self.mean_composite_score, 4),
            "overall_risk_confusion_matrix": self.overall_risk_confusion_matrix.to_dict(),
            "total_blocking_patents": self.total_blocking_patents,
            "total_discovered_blocking": self.total_discovered_blocking,
            "total_missed_blocking": self.total_missed_blocking,
            "total_false_dismissals": self.total_false_dismissals,
            "confidence_intervals": {
                k: (round(lo, 4), round(hi, 4))
                for k, (lo, hi) in self.confidence_intervals.items()
            },
            "total_cost_usd": round(self.total_cost_usd, 4),
            "total_tokens": self.total_tokens,
            "total_duration_seconds": round(self.total_duration_seconds, 2),
            "per_case_scores": self.per_case_scores,
        }


# ---------------------------------------------------------------------------
# Patent ID normalization
# ---------------------------------------------------------------------------
# ``normalize_patent_id`` is imported from scoring_core at the top of this
# module. Keeping a single implementation prevents drift between research
# tooling consumers (benchmark_scorer, enrich_ground_truth, report_scorer).


def _patent_ids_match(a: str, b: str) -> bool:
    """Check if two patent IDs refer to the same patent."""
    return normalize_patent_id(a) == normalize_patent_id(b)


def _find_patent_in_list(target_id: str, id_list: list[str]) -> bool:
    """Check if a patent ID (normalized) appears in a list of patent IDs."""
    target = normalize_patent_id(target_id)
    return any(normalize_patent_id(pid) == target for pid in id_list)


# ---------------------------------------------------------------------------
# Risk level helpers
# ---------------------------------------------------------------------------

_RISK_ORDER = {"high": 3, "medium": 2, "low": 1, "clear": 0}
_RISK_LABELS = ["high", "medium", "low", "clear"]


def _risk_ordinal(level: str) -> int:
    return _RISK_ORDER.get(level.lower().strip(), -1)


def _make_confusion_matrix(
    labels: list[str], predictions: list[str], actuals: list[str]
) -> ConfusionMatrix:
    """Build a confusion matrix from parallel lists of predictions and actuals."""
    n = len(labels)
    idx = {label: i for i, label in enumerate(labels)}
    matrix = [[0] * n for _ in range(n)]
    for pred, actual in zip(predictions, actuals):
        p = idx.get(pred.lower().strip(), -1)
        a = idx.get(actual.lower().strip(), -1)
        if p >= 0 and a >= 0:
            matrix[a][p] += 1  # rows = actual, cols = predicted
    return ConfusionMatrix(labels=labels, matrix=matrix)


def _compute_weighted_f1(cm: ConfusionMatrix) -> float:
    """Compute macro-averaged F1, weighted by class prevalence."""
    n = len(cm.labels)
    if n == 0 or cm.total() == 0:
        return 0.0

    f1_scores = []
    supports = []
    for i in range(n):
        tp = cm.matrix[i][i]
        fp = sum(cm.matrix[j][i] for j in range(n)) - tp
        fn = sum(cm.matrix[i][j] for j in range(n)) - tp
        support = sum(cm.matrix[i])

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        f1_scores.append(f1)
        supports.append(support)

    total_support = sum(supports)
    if total_support == 0:
        return 0.0
    return sum(f1 * s for f1, s in zip(f1_scores, supports)) / total_support


# ---------------------------------------------------------------------------
# Invalidity strength scoring
# ---------------------------------------------------------------------------

_STRENGTH_SCORE_MATRIX = {
    ("strong", "strong"): 1.0,
    ("moderate", "strong"): 0.5,
    ("weak", "strong"): 0.0,
    ("strong", "moderate"): 0.75,
    ("moderate", "moderate"): 1.0,
    ("weak", "moderate"): 0.5,
    ("strong", "weak"): 0.25,
    ("moderate", "weak"): 0.75,
    ("weak", "weak"): 1.0,
}


def _invalidity_strength_score(predicted: str, expected: str) -> float:
    """Score invalidity strength prediction against expected value.

    Scoring is asymmetric: under-estimating strength (missing strong invalidity)
    is penalized more than over-estimating (flagging weak as strong).
    """
    key = (predicted.lower().strip(), expected.lower().strip())
    return _STRENGTH_SCORE_MATRIX.get(key, 0.0)


# ---------------------------------------------------------------------------
# Bootstrap confidence intervals
# ---------------------------------------------------------------------------


def bootstrap_ci(
    values: list[float],
    stat_fn=None,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """Compute bootstrap confidence interval for a statistic.

    Args:
        values: Sample values.
        stat_fn: Statistic function (default: mean).
        n_bootstrap: Number of bootstrap samples.
        confidence: Confidence level (default: 0.95 = 95% CI).
        seed: Random seed for reproducibility.

    Returns:
        (lower_bound, upper_bound) tuple.
    """
    if not values:
        return (0.0, 0.0)

    if stat_fn is None:

        def _default_mean(v: list[float]) -> float:
            return sum(v) / len(v) if v else 0.0

        stat_fn = _default_mean

    rng = random.Random(seed)
    n = len(values)
    bootstraps = []
    for _ in range(n_bootstrap):
        sample = [rng.choice(values) for _ in range(n)]
        bootstraps.append(stat_fn(sample))

    bootstraps.sort()
    alpha = 1.0 - confidence
    lo_idx = max(0, int(math.floor(alpha / 2 * n_bootstrap)))
    hi_idx = min(n_bootstrap - 1, int(math.ceil((1 - alpha / 2) * n_bootstrap)))
    return (bootstraps[lo_idx], bootstraps[hi_idx])


# ---------------------------------------------------------------------------
# Main scorer
# ---------------------------------------------------------------------------


class BenchmarkScorer:
    """Scores a single pipeline run against ground truth.

    Args:
        report_data: Deserialized FTOReport dict (from report.model_dump(mode="json")).
        ground_truth: A single benchmark case dict from the benchmark JSON.
    """

    def __init__(
        self, report_data: dict[str, Any], ground_truth: dict[str, Any]
    ) -> None:
        self.report = report_data
        self.gt = ground_truth

    # -- Public API ----------------------------------------------------------

    def score(self) -> BenchmarkScore:
        """Compute all scoring dimensions and return a BenchmarkScore."""
        result = BenchmarkScore(
            case_id=self.gt.get("id", ""),
            case_name=self.gt.get("name", ""),
            tier=self._infer_tier(),
            category=self.gt.get("category", ""),
        )

        result.discovery = self._score_discovery()
        result.triage = self._score_triage()
        result.risk = self._score_risk()
        result.claim = self._score_claims()
        result.invalidity = self._score_invalidity()
        result.patent_term = self._score_patent_term()

        result.false_positive_rate = self._score_false_positive_rate()
        result.false_negative_rate = self._score_false_negative_rate()

        result.composite_score = self._compute_composite(result)

        # Diagnostics
        result.pipeline_duration_seconds = self.report.get("audit_trail", {}).get(
            "total_duration_seconds", 0.0
        )
        result.total_tokens = self.report.get(
            "total_input_tokens", 0
        ) + self.report.get("total_output_tokens", 0)
        result.estimated_cost_usd = self.report.get("estimated_cost_usd", 0.0)

        verification = self.report.get("verification", {})
        checks = verification.get("checks", [])
        result.verification_checks_passed = sum(1 for c in checks if c.get("passed"))
        result.verification_checks_failed = sum(
            1 for c in checks if not c.get("passed")
        )

        return result

    # -- Discovery -----------------------------------------------------------

    def _score_discovery(self) -> DiscoveryScore:
        """Score patent discovery: did we find the known blocking patents?"""
        blocking = self._get_blocking_patents()
        must_discover = [p for p in blocking if p.get("must_discover", True)]

        # Collect all patent IDs from pipeline output
        discovered_ids = self._get_all_discovered_patent_ids()

        discovered = []
        missed = []
        for patent in must_discover:
            pid = patent.get("number", patent.get("patent_id", ""))
            if _find_patent_in_list(pid, discovered_ids):
                discovered.append(pid)
            else:
                missed.append(pid)

        recall = len(discovered) / len(must_discover) if must_discover else 1.0

        # Precision@K: of the top K patents, how many are blocking?
        ranked_ids = self._get_ranked_patent_ids()
        blocking_ids = [p.get("number", p.get("patent_id", "")) for p in blocking]
        precision_at_k: dict[int, float] = {}
        for k in [20, 50, 100]:
            top_k = ranked_ids[:k]
            if top_k:
                found_in_k = sum(
                    1 for bid in blocking_ids if _find_patent_in_list(bid, top_k)
                )
                precision_at_k[k] = (
                    found_in_k / len(blocking_ids) if blocking_ids else 1.0
                )
            else:
                precision_at_k[k] = 0.0

        # Source attribution
        source_attr: dict[str, list[str]] = {}
        for pid in discovered:
            sources = self._get_sources_for_patent(pid)
            source_attr[pid] = sources

        return DiscoveryScore(
            recall=recall,
            precision_at_k=precision_at_k,
            discovered_blocking=discovered,
            missed_blocking=missed,
            source_attribution=source_attr,
        )

    # -- Triage --------------------------------------------------------------

    def _score_triage(self) -> TriageScore:
        """Score triage: were blocking patents kept and noise removed?"""
        blocking = self._get_blocking_patents()
        blocking_ids = [p.get("number", p.get("patent_id", "")) for p in blocking]

        # Get patents that survived triage (those that were analyzed)
        analyzed_ids = [
            a.get("patent_id", "") for a in self.report.get("patent_analyses", [])
        ]

        # Triage recall: blocking patents that survived triage
        if not blocking_ids:
            return TriageScore(recall=1.0, precision=1.0)

        surviving_blocking = [
            bid for bid in blocking_ids if _find_patent_in_list(bid, analyzed_ids)
        ]
        dismissed = [
            bid for bid in blocking_ids if not _find_patent_in_list(bid, analyzed_ids)
        ]

        recall = len(surviving_blocking) / len(blocking_ids)
        false_dismissal_rate = len(dismissed) / len(blocking_ids)

        # Triage precision: of analyzed patents, how many are blocking?
        precision = 0.0
        if analyzed_ids:
            blocking_in_analyzed = sum(
                1 for bid in blocking_ids if _find_patent_in_list(bid, analyzed_ids)
            )
            precision = blocking_in_analyzed / len(analyzed_ids)

        # Noise ratio: known irrelevant patents that survived triage
        irrelevant = self.gt.get("benchmark_value", {}).get(
            "known_irrelevant_patents", []
        )
        noise_count = 0
        for irr in irrelevant:
            irr_id = irr.get("patent_id", irr.get("number", ""))
            if _find_patent_in_list(irr_id, analyzed_ids):
                noise_count += 1
        noise_ratio = noise_count / len(analyzed_ids) if analyzed_ids else 0.0

        return TriageScore(
            recall=recall,
            precision=precision,
            false_dismissals=dismissed,
            false_dismissal_rate=false_dismissal_rate,
            noise_ratio=noise_ratio,
        )

    # -- Risk ----------------------------------------------------------------

    def _score_risk(self) -> RiskScore:
        """Score risk classification at per-patent and overall levels."""
        bv = self.gt.get("benchmark_value", {})
        expected_overall = bv.get("expected_risk_today", "").lower()
        predicted_overall = (
            self.report.get("risk_summary", {}).get("overall_risk", "").lower()
        )

        overall_correct = expected_overall == predicted_overall

        # Per-patent risk scoring
        blocking = self._get_blocking_patents()
        non_blocking = self._get_non_blocking_patents()
        predictions: list[str] = []
        actuals: list[str] = []
        conservative_errors = 0
        total_patents_scored = 0

        for patent in blocking:
            pid = patent.get("number", patent.get("patent_id", ""))
            expected_risk = patent.get(
                "expected_risk_level", bv.get("expected_risk_today", "")
            ).lower()
            predicted_risk = self._get_patent_risk_level(pid)
            if predicted_risk is not None:
                predictions.append(predicted_risk)
                actuals.append(expected_risk)
                total_patents_scored += 1
                if _risk_ordinal(predicted_risk) < _risk_ordinal(expected_risk):
                    conservative_errors += 1

        for patent in non_blocking:
            pid = patent.get("number", patent.get("patent_id", ""))
            expected_risk = patent.get("expected_risk_level", "clear").lower()
            predicted_risk = self._get_patent_risk_level(pid)
            if predicted_risk is not None:
                predictions.append(predicted_risk)
                actuals.append(expected_risk)
                total_patents_scored += 1
                if _risk_ordinal(predicted_risk) < _risk_ordinal(expected_risk):
                    conservative_errors += 1

        cm = _make_confusion_matrix(_RISK_LABELS, predictions, actuals)
        accuracy = cm.accuracy()
        f1 = _compute_weighted_f1(cm)
        conservative_rate = (
            conservative_errors / total_patents_scored if total_patents_scored else 0.0
        )

        return RiskScore(
            per_patent_accuracy=accuracy,
            overall_risk_correct=overall_correct,
            overall_risk_predicted=predicted_overall,
            overall_risk_expected=expected_overall,
            confusion_matrix=cm,
            conservative_error_rate=conservative_rate,
            weighted_f1=f1,
        )

    # -- Claims --------------------------------------------------------------

    def _score_claims(self) -> ClaimScore:
        """Score element-level and claim-level analysis accuracy."""
        blocking = self._get_blocking_patents()

        element_preds: list[str] = []
        element_actuals: list[str] = []
        claim_preds: list[str] = []
        claim_actuals: list[str] = []
        confidence_buckets: dict[str, list[bool]] = {
            "0.0-0.2": [],
            "0.2-0.4": [],
            "0.4-0.6": [],
            "0.6-0.8": [],
            "0.8-1.0": [],
        }

        for patent in blocking:
            pid = patent.get("number", patent.get("patent_id", ""))
            claims_gt = patent.get("claims_ground_truth", [])
            if not claims_gt:
                continue

            analysis = self._find_patent_analysis(pid)
            if not analysis:
                continue

            for cgt in claims_gt:
                claim_num = cgt.get("claim_number")
                expected_overall = cgt.get("expected_overall_status", "").lower()
                predicted_claim = self._find_claim_analysis(analysis, claim_num)

                if predicted_claim and expected_overall:
                    pred_overall = predicted_claim.get("overall_status", "").lower()
                    claim_preds.append(pred_overall)
                    claim_actuals.append(expected_overall)

                    # Element-level
                    for elem_gt in cgt.get("elements", []):
                        elem_num = elem_gt.get("element_number")
                        expected_elem = elem_gt.get("expected_status", "").lower()
                        predicted_elem = self._find_element(predicted_claim, elem_num)

                        if predicted_elem and expected_elem:
                            pred_status = predicted_elem.get("status", "").lower()
                            element_preds.append(pred_status)
                            element_actuals.append(expected_elem)

                            # Confidence calibration
                            conf = predicted_elem.get("confidence", 0.0)
                            correct = pred_status == expected_elem
                            bucket = self._confidence_bucket(conf)
                            confidence_buckets[bucket].append(correct)

        element_labels = ["met", "not_met", "partially_met", "unclear"]
        elem_cm = _make_confusion_matrix(element_labels, element_preds, element_actuals)
        elem_accuracy = elem_cm.accuracy()
        claim_accuracy = 0.0
        if claim_preds:
            correct_claims = sum(
                1 for p, a in zip(claim_preds, claim_actuals) if p == a
            )
            claim_accuracy = correct_claims / len(claim_preds)

        # Calibration: actual accuracy per confidence bucket
        calibration = {}
        for bucket, correct_list in confidence_buckets.items():
            if correct_list:
                calibration[bucket] = sum(correct_list) / len(correct_list)

        return ClaimScore(
            element_accuracy=elem_accuracy,
            element_confusion_matrix=elem_cm,
            claim_accuracy=claim_accuracy,
            confidence_calibration=calibration,
            total_elements_evaluated=len(element_preds),
            total_claims_evaluated=len(claim_preds),
        )

    # -- Invalidity ----------------------------------------------------------

    def _score_invalidity(self) -> InvalidityScore:
        """Score invalidity analysis: prior art recall, strength, PTAB."""
        blocking = self._get_blocking_patents()
        pipeline_inv = self.report.get("invalidity_assessments", [])

        all_found_prior_art: list[str] = []
        all_missed_prior_art: list[str] = []
        strength_scores: list[float] = []
        ptab_expected: list[str] = []
        ptab_found: list[str] = []
        wd_expected = False
        wd_found = False

        for patent in blocking:
            pid = patent.get("number", patent.get("patent_id", ""))
            known_inv = patent.get("known_invalidity", {})
            if not known_inv:
                continue

            # Find pipeline invalidity assessment for this patent
            inv_assessment = None
            for inv in pipeline_inv:
                if _patent_ids_match(inv.get("patent_id", ""), pid):
                    inv_assessment = inv
                    break

            # Prior art recall
            known_pa = known_inv.get("known_prior_art", [])
            for pa_ref in known_pa:
                ref_id = pa_ref.get("reference_id", "")
                if inv_assessment and self._find_prior_art_ref(inv_assessment, ref_id):
                    all_found_prior_art.append(ref_id)
                else:
                    all_missed_prior_art.append(ref_id)

            # Strength scoring
            expected_strength = known_inv.get("overall_strength", "")
            if expected_strength and inv_assessment:
                predicted_strength = inv_assessment.get(
                    "overall_invalidity_strength", ""
                )
                if predicted_strength:
                    strength_scores.append(
                        _invalidity_strength_score(
                            predicted_strength, expected_strength
                        )
                    )

            # PTAB recall
            known_ptab = known_inv.get("known_ptab_proceedings", [])
            for ptab in known_ptab:
                ptab_num = ptab.get("proceeding_number", "")
                ptab_expected.append(ptab_num)
                if inv_assessment and self._find_ptab_proceeding(
                    inv_assessment, ptab_num
                ):
                    ptab_found.append(ptab_num)

            # Written description
            known_wd = known_inv.get("known_written_description_issues", [])
            if known_wd:
                wd_expected = True
                if inv_assessment and inv_assessment.get("written_description_issues"):
                    wd_found = True

        total_pa = len(all_found_prior_art) + len(all_missed_prior_art)
        pa_recall = len(all_found_prior_art) / total_pa if total_pa else 1.0

        avg_strength = (
            sum(strength_scores) / len(strength_scores) if strength_scores else 0.0
        )
        ptab_recall = len(ptab_found) / len(ptab_expected) if ptab_expected else 1.0

        return InvalidityScore(
            prior_art_recall=pa_recall,
            strength_score=avg_strength,
            ptab_recall=ptab_recall,
            written_description_detected=wd_found if wd_expected else True,
            found_prior_art=all_found_prior_art,
            missed_prior_art=all_missed_prior_art,
        )

    # -- Patent Term ---------------------------------------------------------

    def _score_patent_term(self) -> PatentTermScore:
        """Score patent term / expiry date accuracy."""
        blocking = self._get_blocking_patents()
        non_blocking = self._get_non_blocking_patents()
        all_patents = blocking + non_blocking

        details: list[dict[str, Any]] = []
        absolute_errors_days: list[int] = []
        exact = within_1y = within_3y = evaluated = 0

        for patent in all_patents:
            pid = patent.get("number", patent.get("patent_id", ""))
            expected_expiry_str = patent.get("expiry", patent.get("expiry_date", ""))
            if not expected_expiry_str:
                continue

            # Parse expected expiry (may be partial like "2013-01" or full "2010-12-28")
            expected_date = self._parse_date(expected_expiry_str)
            if not expected_date:
                continue

            # Find predicted expiry from pipeline
            predicted_date = self._get_patent_expiry(pid)
            if not predicted_date:
                continue

            evaluated += 1
            delta_days = abs((predicted_date - expected_date).days)
            absolute_errors_days.append(delta_days)

            if delta_days == 0:
                exact += 1
            if delta_days <= 365:
                within_1y += 1
            if delta_days <= 1095:
                within_3y += 1

            details.append(
                {
                    "patent_id": pid,
                    "expected_expiry": str(expected_date),
                    "predicted_expiry": str(predicted_date),
                    "delta_days": delta_days,
                }
            )

        accuracy = within_1y / evaluated if evaluated else 0.0
        mae = (
            sum(absolute_errors_days) / len(absolute_errors_days)
            if absolute_errors_days
            else 0.0
        )

        return PatentTermScore(
            patents_evaluated=evaluated,
            exact_matches=exact,
            within_1_year=within_1y,
            within_3_years=within_3y,
            accuracy=accuracy,
            mean_absolute_error_days=mae,
            details=details,
        )

    # -- False Positive Rate -------------------------------------------------

    def _score_false_positive_rate(self) -> float:
        """Compute false positive rate: non-blocking patents flagged as HIGH/MEDIUM."""
        non_blocking = self._get_non_blocking_patents()
        if not non_blocking:
            return 0.0

        flagged = 0
        evaluated = 0
        for patent in non_blocking:
            pid = patent.get("number", patent.get("patent_id", ""))
            predicted_risk = self._get_patent_risk_level(pid)
            if predicted_risk is not None:
                evaluated += 1
                if predicted_risk in ("high", "medium"):
                    flagged += 1

        return flagged / evaluated if evaluated else 0.0

    # -- False Negative Rate -------------------------------------------------

    def _score_false_negative_rate(self) -> float:
        """Compute false negative rate: blocking patents missed or rated LOW/CLEAR.

        A "miss" is any of:
          1. Blocking patent never discovered (Steps 1-2)
          2. Discovered but dismissed at triage (Step 3)
          3. Analyzed but rated LOW or CLEAR despite being blocking
        """
        blocking = self._get_blocking_patents()
        if not blocking:
            return 0.0

        discovered_ids = self._get_all_discovered_patent_ids()
        analyzed_ids = [
            a.get("patent_id", "") for a in self.report.get("patent_analyses", [])
        ]

        missed = 0
        for patent in blocking:
            pid = patent.get("number", patent.get("patent_id", ""))
            blocking_status = patent.get("blocking_status", "currently_blocking")
            expected_risk = patent.get("expected_risk_level", "").lower()

            # For formerly blocking patents where expected risk is now CLEAR,
            # the pipeline should find them and rate them CLEAR (not miss them)
            if blocking_status == "formerly_blocking" and expected_risk == "clear":
                continue

            # Check if discovered
            if not _find_patent_in_list(pid, discovered_ids):
                missed += 1
                continue

            # Check if survived triage (was analyzed)
            if not _find_patent_in_list(pid, analyzed_ids):
                missed += 1
                continue

            # Check if risk is adequate
            predicted_risk = self._get_patent_risk_level(pid)
            if predicted_risk and predicted_risk in ("low", "clear"):
                # Only count as FN if the expected risk is HIGH or MEDIUM
                if expected_risk in ("high", "medium"):
                    missed += 1

        # Denominator: only currently blocking patents
        currently_blocking = [
            p
            for p in blocking
            if p.get("blocking_status", "currently_blocking") != "formerly_blocking"
            or p.get("expected_risk_level", "").lower() not in ("clear", "low")
        ]

        return missed / len(currently_blocking) if currently_blocking else 0.0

    # -- Composite -----------------------------------------------------------

    def _compute_composite(self, score: BenchmarkScore) -> float:
        """Compute the weighted composite score.

        Weights from the validation plan:
          0.05 * discovery_recall
          0.05 * triage_recall
          0.10 * risk_classification_f1
          0.15 * element_accuracy
          0.05 * invalidity_recall
          0.10 * (1 - false_positive_rate)
          0.50 * (1 - false_negative_rate)   # 5x weight on avoiding misses
        """
        return (
            0.05 * score.discovery.recall
            + 0.05 * score.triage.recall
            + 0.10 * score.risk.weighted_f1
            + 0.15 * score.claim.element_accuracy
            + 0.05 * score.invalidity.prior_art_recall
            + 0.10 * (1.0 - score.false_positive_rate)
            + 0.50 * (1.0 - score.false_negative_rate)
        )

    # -- Data extraction helpers ---------------------------------------------

    def _infer_tier(self) -> str:
        """Infer the benchmark tier from the difficulty field."""
        difficulty = self.gt.get("difficulty", "").lower()
        mapping = {
            "easy": "tier1",
            "medium": "tier2",
            "hard": "tier3",
            "expert": "tier4",
        }
        return mapping.get(difficulty, "unknown")

    def _get_blocking_patents(self) -> list[dict[str, Any]]:
        """Get known blocking patents from ground truth.

        Supports both validation plan format (benchmark_value.blocking_patents_pre_expiry)
        and the pharma_litigation_benchmarks format (patents.key_patents).
        """
        bv = self.gt.get("benchmark_value", {})

        # Try validation plan format first
        known_blocking = self.gt.get("known_blocking_patents", [])
        if known_blocking:
            return known_blocking

        # Fall back to pharma_litigation format: key_patents are the blocking ones
        patents = self.gt.get("patents", {})
        key_patents = patents.get("key_patents", [])
        # Enrich with blocking_patents_pre_expiry info
        blocking_ids = bv.get("blocking_patents_pre_expiry", [])

        result = []
        for kp in key_patents:
            pid = kp.get("number", "")
            # Determine if this patent was blocking pre-expiry
            is_known_blocking = (
                any(
                    normalize_patent_id(pid) == normalize_patent_id(bid)
                    for bid in blocking_ids
                )
                if blocking_ids
                else True
            )  # If no explicit list, assume all key patents are blocking

            if is_known_blocking:
                # Map status to blocking_status
                status = kp.get("status", "unknown")
                blocking_status = (
                    "formerly_blocking" if status == "expired" else "currently_blocking"
                )
                expected_risk = (
                    "clear"
                    if status == "expired"
                    else bv.get("expected_risk_today", "high").lower()
                )

                result.append(
                    {
                        **kp,
                        "patent_id": pid,
                        "blocking_status": blocking_status,
                        "expected_risk_level": expected_risk,
                        "must_discover": True,
                    }
                )

        return result

    def _get_non_blocking_patents(self) -> list[dict[str, Any]]:
        """Get known non-blocking patents from ground truth."""
        return self.gt.get("known_non_blocking_patents", [])

    def _get_all_discovered_patent_ids(self) -> list[str]:
        """Get all patent IDs the pipeline discovered (from patent_analyses + patent_details)."""
        ids: list[str] = []

        # From patent_analyses (Step 4)
        for a in self.report.get("patent_analyses", []):
            pid = a.get("patent_id", "")
            if pid:
                ids.append(pid)

        # From patent_details (raw PatentHit data)
        for pid in self.report.get("patent_details", {}).keys():
            if pid and pid not in ids:
                ids.append(pid)

        # From analysis_failures (patents that were attempted)
        for f in self.report.get("analysis_failures", []):
            pid = f.get("patent_id", "")
            if pid and pid not in ids:
                ids.append(pid)

        return ids

    def _get_ranked_patent_ids(self) -> list[str]:
        """Get patent IDs in confidence-ranked order."""
        analyses = self.report.get("patent_analyses", [])
        # Sort by whatever confidence metric is available
        sorted_analyses = sorted(
            analyses,
            key=lambda a: max(
                (
                    c.get("overall_confidence", 0.0)
                    for c in a.get("claims_analyzed", [])
                ),
                default=0.0,
            ),
            reverse=True,
        )
        return [a.get("patent_id", "") for a in sorted_analyses]

    def _get_sources_for_patent(self, patent_id: str) -> list[str]:
        """Get the source attribution for a discovered patent."""
        details = self.report.get("patent_details", {})
        for pid, detail in details.items():
            if _patent_ids_match(pid, patent_id):
                return detail.get("sources", [])
        return []

    def _get_patent_risk_level(self, patent_id: str) -> str | None:
        """Find the predicted risk level for a patent by ID."""
        for a in self.report.get("patent_analyses", []):
            if _patent_ids_match(a.get("patent_id", ""), patent_id):
                return a.get("risk_level", "").lower()
        return None

    def _find_patent_analysis(self, patent_id: str) -> dict[str, Any] | None:
        """Find the full patent analysis dict for a given patent ID."""
        for a in self.report.get("patent_analyses", []):
            if _patent_ids_match(a.get("patent_id", ""), patent_id):
                return a
        return None

    def _find_claim_analysis(
        self, analysis: dict[str, Any], claim_number: int
    ) -> dict[str, Any] | None:
        """Find a specific claim analysis within a patent analysis."""
        for c in analysis.get("claims_analyzed", []):
            if c.get("claim_number") == claim_number:
                return c
        return None

    def _find_element(
        self, claim: dict[str, Any], element_number: int
    ) -> dict[str, Any] | None:
        """Find a specific element within a claim analysis."""
        for e in claim.get("elements", []):
            if e.get("element_number") == element_number:
                return e
        return None

    def _find_prior_art_ref(self, inv_assessment: dict[str, Any], ref_id: str) -> bool:
        """Check if a prior art reference was found in an invalidity assessment."""
        for pa in inv_assessment.get("prior_art", []):
            if _patent_ids_match(pa.get("reference_id", ""), ref_id):
                return True
        return False

    def _find_ptab_proceeding(
        self, inv_assessment: dict[str, Any], proceeding_number: str
    ) -> bool:
        """Check if a PTAB proceeding was found."""
        ptab = inv_assessment.get("ptab", {})
        for proc in ptab.get("proceedings", []):
            if proc.get("proceeding_number", "").strip() == proceeding_number.strip():
                return True
        return False

    def _get_patent_expiry(self, patent_id: str) -> Any:
        """Get the predicted expiry date for a patent."""
        for a in self.report.get("patent_analyses", []):
            if _patent_ids_match(a.get("patent_id", ""), patent_id):
                expiry = a.get("expiry_date")
                if expiry:
                    return self._parse_date(str(expiry))
        return None

    @staticmethod
    def _confidence_bucket(confidence: float) -> str:
        """Map a confidence value to a calibration bucket."""
        if confidence < 0.2:
            return "0.0-0.2"
        elif confidence < 0.4:
            return "0.2-0.4"
        elif confidence < 0.6:
            return "0.4-0.6"
        elif confidence < 0.8:
            return "0.6-0.8"
        else:
            return "0.8-1.0"

    @staticmethod
    def _parse_date(date_str: str) -> Any:
        """Parse a date string in various formats."""
        from datetime import datetime

        date_str = date_str.strip()
        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.date()
            except ValueError:
                continue
        return None


# ---------------------------------------------------------------------------
# Aggregate scoring
# ---------------------------------------------------------------------------


def aggregate_scores(scores: list[BenchmarkScore]) -> AggregateScore:
    """Compute aggregate statistics across multiple benchmark cases.

    Includes bootstrap confidence intervals for key metrics.
    """
    if not scores:
        return AggregateScore()

    agg = AggregateScore(total_cases=len(scores))

    # Cases by tier
    tier_counts: Counter[str] = Counter()
    for s in scores:
        tier_counts[s.tier] += 1
    agg.cases_by_tier = dict(tier_counts)

    # Mean scores
    agg.mean_discovery_recall = _mean([s.discovery.recall for s in scores])
    agg.mean_triage_recall = _mean([s.triage.recall for s in scores])
    agg.mean_risk_accuracy = _mean([s.risk.per_patent_accuracy for s in scores])
    agg.mean_element_accuracy = _mean([s.claim.element_accuracy for s in scores])
    agg.mean_invalidity_recall = _mean([s.invalidity.prior_art_recall for s in scores])
    agg.mean_false_positive_rate = _mean([s.false_positive_rate for s in scores])
    agg.mean_false_negative_rate = _mean([s.false_negative_rate for s in scores])
    agg.mean_composite_score = _mean([s.composite_score for s in scores])

    # Overall risk confusion matrix (aggregate across all cases)
    all_preds = [
        s.risk.overall_risk_predicted for s in scores if s.risk.overall_risk_predicted
    ]
    all_actuals = [
        s.risk.overall_risk_expected for s in scores if s.risk.overall_risk_expected
    ]
    agg.overall_risk_confusion_matrix = _make_confusion_matrix(
        _RISK_LABELS, all_preds, all_actuals
    )

    # Totals
    agg.total_blocking_patents = sum(
        len(s.discovery.discovered_blocking) + len(s.discovery.missed_blocking)
        for s in scores
    )
    agg.total_discovered_blocking = sum(
        len(s.discovery.discovered_blocking) for s in scores
    )
    agg.total_missed_blocking = sum(len(s.discovery.missed_blocking) for s in scores)
    agg.total_false_dismissals = sum(len(s.triage.false_dismissals) for s in scores)

    agg.total_cost_usd = sum(s.estimated_cost_usd for s in scores)
    agg.total_tokens = sum(s.total_tokens for s in scores)
    agg.total_duration_seconds = sum(s.pipeline_duration_seconds for s in scores)

    # Bootstrap confidence intervals
    ci_metrics = {
        "composite_score": [s.composite_score for s in scores],
        "discovery_recall": [s.discovery.recall for s in scores],
        "triage_recall": [s.triage.recall for s in scores],
        "false_negative_rate": [s.false_negative_rate for s in scores],
        "false_positive_rate": [s.false_positive_rate for s in scores],
        "element_accuracy": [s.claim.element_accuracy for s in scores],
    }
    for metric_name, values in ci_metrics.items():
        if len(values) >= 3:  # Need at least 3 samples for meaningful CI
            agg.confidence_intervals[metric_name] = bootstrap_ci(values)

    # Per-case scores for the report
    agg.per_case_scores = [s.to_dict() for s in scores]

    return agg


def _mean(values: list[float]) -> float:
    """Compute mean, returning 0.0 for empty lists."""
    return sum(values) / len(values) if values else 0.0
