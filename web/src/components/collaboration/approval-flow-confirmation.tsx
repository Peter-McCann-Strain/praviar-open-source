"use client";

import { useId } from "react";
import { Check, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PendingAction } from "@/components/collaboration/approval-flow-config";

interface ApprovalFlowConfirmationProps {
  comment: string;
  onCancel: () => void;
  onCommentChange: (value: string) => void;
  onConfirm: () => void;
  pendingAction: PendingAction;
}

export function ApprovalFlowConfirmation({
  comment,
  onCancel,
  onCommentChange,
  onConfirm,
  pendingAction,
}: ApprovalFlowConfirmationProps) {
  const titleId = useId();

  if (!pendingAction) {
    return null;
  }

  const isApprove = pendingAction === "approve";

  return (
    <div
      role="group"
      aria-labelledby={titleId}
      className="space-y-3 rounded-lg border border-[var(--border-emphasis)] bg-[var(--surface-subtle)] p-3"
    >
      <div className="flex min-w-0 items-center justify-between gap-3">
        <span
          id={titleId}
          className="min-w-0 text-xs font-medium text-[var(--text-primary)] [overflow-wrap:anywhere]"
        >
          {isApprove ? "Confirm Approval" : "Confirm Request Changes"}
        </span>
        <button
          type="button"
          onClick={onCancel}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-[var(--text-tertiary)] transition-colors hover:bg-[var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
        >
          <X className="h-3.5 w-3.5" />
          <span className="sr-only">Cancel</span>
        </button>
      </div>

      <textarea
        autoFocus
        value={comment}
        onChange={(event) => onCommentChange(event.target.value)}
        placeholder="Add a note about your decision (optional)..."
        aria-label={
          isApprove
            ? "Approval decision note (optional)"
            : "Request changes note (optional)"
        }
        rows={3}
        className="w-full resize-none rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-muted)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-disabled)] focus:border-brand-primary/40 focus:outline-none focus:ring-2 focus:ring-brand-primary/50"
      />

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button
          type="button"
          onClick={onCancel}
          className="min-h-11 w-full rounded-md border border-[var(--border-default)] px-3 py-2 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)] sm:w-auto"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={onConfirm}
          className={cn(
            "flex min-h-11 w-full items-center justify-center gap-1 rounded-md px-3 py-2 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)] sm:w-auto",
            isApprove
              ? "bg-success-emphasis text-[var(--brand-paper)] solid-btn-hover"
              : "bg-warning-emphasis text-[var(--brand-paper)] solid-btn-hover",
          )}
        >
          <Check className="h-3 w-3" />
          {isApprove ? "Confirm Approval" : "Confirm Request Changes"}
        </button>
      </div>
    </div>
  );
}
