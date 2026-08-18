"use client";

import { Star } from "lucide-react";
import type { FTOReport } from "@praviar/shared-types";
import { Badge } from "@/components/ui/badge";
import { RiskBadge } from "@/components/shared/risk-badge";
import { ReviewStatusBadge } from "@/components/report/review-status-badge";
import { getPatentReviewTier, type ReviewStatus } from "@/lib/review-rules";
import { useReviewStore } from "@/stores/review-store";
import type { ReviewerDecisionListResponse } from "@/hooks/use-reviewer-decisions";
import {
  getPatentNarrativePreview,
  isBroadestSearchFunnelHit,
} from "./patents-tab-row-utils";

export function PatentRiskTableRow({
  report,
  analysis,
  analysisId,
  serverDecisions,
  onPatentSelect,
}: {
  report: FTOReport;
  analysis: FTOReport["patent_analyses"][number];
  analysisId?: string;
  /**
   * Reviewer decisions for the parent analysis, resolved once by
   * PatentRiskOverview and shared across rows. Threaded in (rather than each
   * row calling useReviewerDecisions/useAuthToken) so a large patent table does
   * not mount one auth-token poller + query subscription per row.
   */
  serverDecisions?: ReviewerDecisionListResponse;
  onPatentSelect: (patentId: string) => void;
}) {
  const reviewStore = useReviewStore();
  // Server reviewer decisions are the source of truth. The local Zustand store
  // is a client-only convenience that can diverge from what other reviewers
  // persisted, so prefer the server status when a decision exists for this
  // patent and fall back to the local store only when the server has none.
  const isBroadest = isBroadestSearchFunnelHit(report, analysis.patent_id);
  const narrativePreview = getPatentNarrativePreview(
    report,
    analysis.patent_id,
  );

  const serverDecision = serverDecisions?.items.find(
    (d) => d.finding_type === "patent" && d.finding_ref === analysis.patent_id,
  );
  const localStatus = reviewStore.getReview(
    analysisId ?? "",
    analysis.patent_id,
  )?.status;
  // Preserve the exact persisted reviewer decision. Collapsing accept/edit/reject
  // into generic reviewed/approved labels hides legally meaningful context.
  const reviewStatus: ReviewStatus = serverDecision
    ? serverDecision.decision === "accept"
      ? "accepted"
      : serverDecision.decision === "edit"
        ? "edited"
        : "rejected"
    : (localStatus ?? "ai_draft");

  return (
    <tr
      key={analysis.patent_id}
      className="block p-4 hover:bg-[var(--surface-muted)] focus-within:bg-[var(--surface-muted)] md:table-row md:p-0"
    >
      <td className="block pb-3 md:table-cell md:px-4 md:py-3">
        <button
          type="button"
          aria-label={`Open patent details for ${analysis.patent_id}`}
          data-print-content
          className="block min-h-11 w-full max-w-full rounded-sm text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
          onClick={() => onPatentSelect(analysis.patent_id)}
        >
          <span className="flex flex-wrap items-center gap-1.5 text-sm font-mono text-[var(--text-primary)]">
            {analysis.patent_id}
            {isBroadest ? (
              <Badge
                variant="secondary"
                className="gap-0.5 px-1.5 py-0 text-xs"
              >
                <Star aria-hidden="true" className="h-2.5 w-2.5" />
                Broadest
              </Badge>
            ) : null}
          </span>
          {narrativePreview ? (
            <span className="mt-1 block max-w-[34rem] text-xs text-[var(--text-tertiary)] md:max-w-[300px] md:truncate">
              {narrativePreview}
            </span>
          ) : null}
        </button>
      </td>
      <td className="flex items-center justify-between gap-3 py-2 md:table-cell md:px-4 md:py-3">
        <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
          Risk level
        </span>
        <RiskBadge risk={analysis.risk_level} size="sm" />
      </td>
      <td className="flex items-center justify-between gap-3 py-2 md:table-cell md:px-4 md:py-3">
        <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
          Review status
        </span>
        <ReviewStatusBadge
          status={reviewStatus}
          tier={getPatentReviewTier({
            risk_level: analysis.risk_level,
            claims_analyzed: (analysis.claims_analyzed ?? []).map((claim) => ({
              confidence: claim.overall_confidence,
            })),
          })}
        />
      </td>
      <td className="flex items-start justify-between gap-3 py-2 text-sm text-[var(--text-secondary)] md:table-cell md:px-4 md:py-3">
        <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
          Owner
        </span>
        <span className="break-words text-right md:text-left">
          {analysis.assignee}
        </span>
      </td>
      <td className="flex items-start justify-between gap-3 py-2 text-sm text-[var(--text-secondary)] md:table-cell md:px-4 md:py-3">
        <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
          Expiration
        </span>
        <span>{analysis.expiry_date ?? "\u2014"}</span>
      </td>
    </tr>
  );
}
