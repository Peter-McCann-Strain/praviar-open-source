"use client";

import { AlertTriangle, CheckCircle, XCircle, Clock } from "lucide-react";
import { IdentityReviewCheckpoint } from "@/components/pipeline/identity-review-checkpoint";
import { ReportReviewCheckpoint } from "@/components/pipeline/report-review-checkpoint";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface CheckpointGateProps {
  type:
    | "identity_review"
    | "search_review"
    | "triage_review"
    | "analysis_review"
    | "report_review";
  data: Record<string, unknown>;
  onApprove: () => void;
  onReject: () => void;
  onModify?: (modifications: Record<string, unknown>) => void;
  isSubmitting?: boolean;
  errorMessage?: string;
}

const CHECKPOINT_CONFIG = {
  identity_review: {
    title: "Review Resolved Identity",
    description:
      "Verify the exact resolved identity before any patent search begins.",
    icon: AlertTriangle,
  },
  search_review: {
    title: "Review Search Results",
    description:
      "Review the patent search results before proceeding to triage.",
    icon: Clock,
  },
  triage_review: {
    title: "Review Triage Results",
    description: "Review which patents were selected for claim analysis.",
    icon: AlertTriangle,
  },
  analysis_review: {
    title: "Review Patent Analysis",
    description:
      "Review the claim-by-claim analysis before generating the report.",
    icon: AlertTriangle,
  },
  report_review: {
    title: "Review Final Report",
    description: "Review the generated report before finalizing.",
    icon: CheckCircle,
  },
};

export function CheckpointGate({
  type,
  data,
  onApprove,
  onReject,
  isSubmitting = false,
  errorMessage,
}: CheckpointGateProps) {
  if (type === "identity_review") {
    return (
      <IdentityReviewCheckpoint
        data={data}
        onApprove={onApprove}
        onReject={onReject}
        isSubmitting={isSubmitting}
        errorMessage={errorMessage}
      />
    );
  }

  if (type === "report_review") {
    return (
      <ReportReviewCheckpoint
        data={data}
        onApprove={onApprove}
        onReject={onReject}
        isSubmitting={isSubmitting}
        errorMessage={errorMessage}
      />
    );
  }

  const config = CHECKPOINT_CONFIG[type];
  const Icon = config.icon;

  const patentCount =
    typeof data.patent_count === "number" ? data.patent_count : null;
  const items = Array.isArray(data.items)
    ? (data.items as Array<Record<string, unknown>>)
    : [];

  return (
    <Card className="border-warning/30 bg-warning/[0.03]">
      <CardHeader>
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-warning/10">
            <Icon className="h-5 w-5 text-warning" />
          </div>
          <div>
            <CardTitle className="text-sm text-[var(--text-primary)]">
              {config.title}
            </CardTitle>
            <p className="text-xs text-[var(--text-secondary)] mt-0.5">
              {config.description}
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {patentCount !== null && (
          <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
            <span className="font-medium tabular-nums">{patentCount}</span>
            <span>patents to review</span>
          </div>
        )}

        {items.length > 0 && (
          <div className="max-h-48 overflow-y-auto space-y-1.5 rounded-md border border-[var(--border-default)] p-3">
            {items.map((item, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between text-xs py-1 border-b border-[var(--border-subtle)] last:border-0"
              >
                <span className="text-[var(--text-primary)] font-mono">
                  {String(item.patent_id ?? item.id ?? `Item ${idx + 1}`)}
                </span>
                {item.title ? (
                  <span className="text-[var(--text-tertiary)] truncate ml-2 max-w-[60%]">
                    {String(item.title)}
                  </span>
                ) : null}
              </div>
            ))}
          </div>
        )}

        <div className="grid grid-cols-1 gap-2 pt-2 min-[360px]:grid-cols-2">
          <Button
            onClick={onApprove}
            className="min-h-11 w-full gap-2"
            disabled={isSubmitting}
          >
            <CheckCircle className="h-4 w-4" aria-hidden="true" />
            Approve &amp; Continue
          </Button>
          <Button
            variant="outline"
            onClick={onReject}
            className="min-h-11 w-full gap-2 border-error/30 text-error hover:bg-error/5"
            disabled={isSubmitting}
          >
            <XCircle className="h-4 w-4" aria-hidden="true" />
            Reject
          </Button>
        </div>
        {errorMessage ? (
          <p className="text-xs text-error" role="alert">
            {errorMessage}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
