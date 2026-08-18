"use client";

import type { RefObject } from "react";
import { Check } from "lucide-react";
import type {
  ApprovalStatus,
  PendingAction,
} from "@/components/collaboration/approval-flow-config";

interface ApprovalFlowActionButtonsProps {
  approveButtonRef: RefObject<HTMLButtonElement | null>;
  canApprove: boolean;
  onApprove?: (comment?: string) => void;
  onOpenAction: (action: Exclude<PendingAction, null>) => void;
  onRequestChanges?: (comment?: string) => void;
  pendingAction: PendingAction;
  requestChangesButtonRef: RefObject<HTMLButtonElement | null>;
  status: ApprovalStatus;
}

export function ApprovalFlowActionButtons({
  approveButtonRef,
  canApprove,
  onApprove,
  onOpenAction,
  onRequestChanges,
  pendingAction,
  requestChangesButtonRef,
  status,
}: ApprovalFlowActionButtonsProps) {
  if (!canApprove || status === "approved" || pendingAction) {
    return null;
  }

  return (
    <div className="flex w-full flex-col gap-2 sm:ml-auto sm:w-auto sm:flex-row sm:items-center sm:gap-1.5">
      {onApprove ? (
        <button
          ref={approveButtonRef}
          type="button"
          onClick={() => onOpenAction("approve")}
          aria-label="Approve report"
          className="flex min-h-11 w-full items-center justify-center gap-1 rounded-md bg-success-emphasis px-3 py-2 text-xs font-medium text-[var(--brand-paper)] solid-btn-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-success/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)] sm:w-auto"
        >
          <Check className="h-3 w-3" />
          Approve
        </button>
      ) : null}
      {onRequestChanges && status !== "changes_requested" ? (
        <button
          ref={requestChangesButtonRef}
          type="button"
          onClick={() => onOpenAction("request_changes")}
          aria-label="Request changes"
          className="flex min-h-11 w-full items-center justify-center gap-1 rounded-md border border-[var(--border-emphasis)] px-3 py-2 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)] sm:w-auto"
        >
          Request Changes
        </button>
      ) : null}
    </div>
  );
}
