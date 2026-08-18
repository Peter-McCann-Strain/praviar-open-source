"use client";

import { ExportDialog } from "@/components/collaboration/export-dialog";
import { FeedbackModal } from "@/components/collaboration/feedback-modal";
import { ShareDialog } from "@/components/collaboration/share-dialog";
import { ReportMonitorPlanDialog } from "@/components/report-page/report-monitor-plan-dialog";
import type { AnalysisReviewStatusResponse } from "@/hooks/use-analysis-review-status";
import type { ReportWorkspaceSummaryResponse } from "@/hooks/use-report-workspace-summary";
import type { ReviewerDecisionListResponse } from "@/hooks/use-reviewer-decisions";
import type { FTOReport } from "@praviar/shared-types";
import type { ClaimedUseReceiptLedgerState } from "@/components/report/claimed-use-receipt-ledger";

interface ReportPageDialogsProps {
  reportId: string;
  report: FTOReport;
  exportOpen: boolean;
  shareOpen: boolean;
  feedbackOpen: boolean;
  monitorOpen: boolean;
  shareActive?: boolean;
  shareLastViewedAt?: string | null;
  shareRecipientBound?: boolean;
  shareViewCount?: number | null;
  reviewStatus?: AnalysisReviewStatusResponse;
  reviewStatusLoading?: boolean;
  reviewerDecisions?: ReviewerDecisionListResponse | null;
  reviewerDecisionsLoading?: boolean;
  workspaceSummary?: ReportWorkspaceSummaryResponse;
  workspaceSummaryLoading?: boolean;
  currentUserRole?: string | null;
  currentUserRoleState?: "ready" | "loading" | "unavailable";
  claimedUseReceiptState?: ClaimedUseReceiptLedgerState;
  onExportClose: () => void;
  onExportRoleRetry?: () => void;
  onShareStateRefresh?: () => void;
  onShareClose: () => void;
  onFeedbackChange: (open: boolean) => void;
  onMonitorChange: (open: boolean) => void;
}

export function ReportPageDialogs({
  reportId,
  report,
  exportOpen,
  shareOpen,
  feedbackOpen,
  monitorOpen,
  shareActive,
  shareLastViewedAt,
  shareRecipientBound,
  shareViewCount,
  reviewStatus,
  reviewStatusLoading,
  reviewerDecisions,
  reviewerDecisionsLoading,
  workspaceSummary,
  workspaceSummaryLoading,
  currentUserRole,
  currentUserRoleState,
  claimedUseReceiptState,
  onExportClose,
  onExportRoleRetry,
  onShareStateRefresh,
  onShareClose,
  onFeedbackChange,
  onMonitorChange,
}: ReportPageDialogsProps) {
  return (
    <>
      <ExportDialog
        reportId={reportId}
        report={report}
        open={exportOpen}
        reviewStatus={reviewStatus}
        reviewStatusLoading={reviewStatusLoading}
        reviewerDecisions={reviewerDecisions}
        reviewerDecisionsLoading={reviewerDecisionsLoading}
        shareActive={shareActive}
        shareLastViewedAt={shareLastViewedAt}
        shareRecipientBound={shareRecipientBound}
        shareViewCount={shareViewCount}
        workspaceSummary={workspaceSummary}
        workspaceSummaryLoading={workspaceSummaryLoading}
        currentUserRole={currentUserRole}
        currentUserRoleState={currentUserRoleState}
        claimedUseReceiptState={claimedUseReceiptState}
        onRefreshCurrentUserRole={onExportRoleRetry}
        onClose={onExportClose}
      />
      <ShareDialog
        reportId={reportId}
        report={report}
        open={shareOpen}
        onClose={onShareClose}
        onShareStateRefresh={onShareStateRefresh}
      />
      <FeedbackModal
        analysisId={reportId}
        patentId=""
        currentRisk={report.risk_summary?.overall_risk ?? ""}
        open={feedbackOpen}
        onOpenChange={onFeedbackChange}
      />
      <ReportMonitorPlanDialog
        analysisId={reportId}
        report={report}
        open={monitorOpen}
        workspaceSummary={workspaceSummary}
        onOpenChange={onMonitorChange}
      />
    </>
  );
}
