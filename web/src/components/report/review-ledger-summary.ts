import type {
  AnalysisReviewDecisionCounts,
  AnalysisReviewStatusResponse,
} from "@/hooks/use-analysis-review-status";

export interface ReviewLedgerSummaryInput {
  decisionCounts?: AnalysisReviewDecisionCounts | null;
  loading?: boolean;
  reviewStatus?: AnalysisReviewStatusResponse | null;
  uncertaintyCount?: number;
}

export interface ReviewLedgerSummary {
  ariaLabel: string;
  buttonLabel: string;
  compactCoverageLabel: string | null;
  coverageLabel: string | null;
  decisionMixLabel: string | null;
  detailLabel: string | null;
}

export function getReviewLedgerSummary({
  decisionCounts,
  loading,
  reviewStatus,
  uncertaintyCount = 0,
}: ReviewLedgerSummaryInput): ReviewLedgerSummary {
  const counts = reviewStatus?.decision_counts ?? decisionCounts ?? null;
  const coverageLabel = reviewStatus
    ? `${reviewStatus.findings_reviewed.toLocaleString()} / ${reviewStatus.findings_total.toLocaleString()} findings reviewed`
    : null;
  const compactCoverageLabel = reviewStatus
    ? `${reviewStatus.findings_reviewed.toLocaleString()}/${reviewStatus.findings_total.toLocaleString()}`
    : null;
  const decisionMixLabel = counts ? formatDecisionMix(counts) : null;
  const usefulDecisionMix =
    decisionMixLabel && decisionMixLabel !== "No reviewer decisions recorded"
      ? decisionMixLabel
      : null;
  const detailParts = [coverageLabel, usefulDecisionMix].filter(
    (part): part is string => Boolean(part),
  );
  const detailLabel = detailParts.length > 0 ? detailParts.join("; ") : null;
  const buttonLabel =
    compactCoverageLabel != null
      ? `Ledger · ${compactCoverageLabel}`
      : usefulDecisionMix != null
        ? `Review findings · ${usefulDecisionMix}`
        : loading
          ? "Review status loading"
          : "Review findings";
  const fallbackDetail =
    uncertaintyCount > 0
      ? `${uncertaintyCount.toLocaleString()} uncertainty ${
          uncertaintyCount === 1 ? "item" : "items"
        } tracked`
      : "No reviewer decisions recorded";
  const ariaLabel = detailLabel
    ? `Review findings. ${detailLabel}.`
    : `Review findings. ${fallbackDetail}.`;

  return {
    ariaLabel,
    buttonLabel,
    compactCoverageLabel,
    coverageLabel,
    decisionMixLabel,
    detailLabel,
  };
}

export function formatDecisionMix(
  counts: AnalysisReviewDecisionCounts,
): string {
  const parts = [
    counts.accept > 0 ? `${counts.accept.toLocaleString()} accepted` : null,
    counts.edit > 0 ? `${counts.edit.toLocaleString()} edited` : null,
    counts.reject > 0 ? `${counts.reject.toLocaleString()} rejected` : null,
  ].filter((part): part is string => Boolean(part));

  return parts.length > 0
    ? parts.join(" / ")
    : "No reviewer decisions recorded";
}
