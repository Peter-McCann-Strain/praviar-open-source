"use client";

import * as React from "react";
import { ClipboardCheck } from "lucide-react";

import { Button, type ButtonProps } from "@/components/ui/button";
import { getReviewLedgerSummary } from "@/components/report/review-ledger-summary";
import type { AnalysisReviewStatusResponse } from "@/hooks/use-analysis-review-status";
import { useReviewerDecisions } from "@/hooks/use-reviewer-decisions";

import { ReviewerDecisionPanel } from "./reviewer-decision-panel";

export interface ReviewerDecisionButtonProps {
  analysisId: string;
  token: string | null;
  /** The report payload; used by the panel to enumerate findings. */
  report: unknown;
  label?: string;
  ariaLabel?: string;
  className?: string;
  variant?: ButtonProps["variant"];
  size?: ButtonProps["size"];
  testId?: string;
  onBeforeOpen?: () => void;
  reviewStatus?: AnalysisReviewStatusResponse;
  reviewStatusLoading?: boolean;
}

/**
 * Entry point for the reviewer accept/reject/edit workflow.
 * Shows a compact summary of current decisions and opens the full panel.
 */
export function ReviewerDecisionButton({
  analysisId,
  token,
  report,
  label,
  ariaLabel,
  className,
  variant = "outline",
  size = "sm",
  testId = "reviewer-decision-button",
  onBeforeOpen,
  reviewStatus,
  reviewStatusLoading,
}: ReviewerDecisionButtonProps) {
  const [open, setOpen] = React.useState(false);
  const { data } = useReviewerDecisions(analysisId, token);
  const counts = data?.counts ?? { accept: 0, reject: 0, edit: 0 };
  const ledgerSummary = getReviewLedgerSummary({
    decisionCounts: counts,
    loading: reviewStatusLoading,
    reviewStatus,
  });

  return (
    <>
      <Button
        type="button"
        variant={variant}
        size={size}
        className={className}
        onClick={() => {
          onBeforeOpen?.();
          setOpen(true);
        }}
        data-testid={testId}
        aria-label={ariaLabel ?? ledgerSummary.ariaLabel}
        title={ledgerSummary.detailLabel ?? undefined}
      >
        <ClipboardCheck className="h-4 w-4" aria-hidden="true" />
        <span>{label ?? ledgerSummary.buttonLabel}</span>
      </Button>
      {open ? (
        <ReviewerDecisionPanel
          open={open}
          onClose={() => setOpen(false)}
          analysisId={analysisId}
          token={token}
          report={report}
          reviewStatus={reviewStatus}
        />
      ) : null}
    </>
  );
}

export default ReviewerDecisionButton;
