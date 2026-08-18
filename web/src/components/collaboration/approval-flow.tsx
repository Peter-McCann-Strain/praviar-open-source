"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { ApprovalFlowActionButtons } from "@/components/collaboration/approval-flow-action-buttons";
import { ApprovalFlowConfirmation } from "@/components/collaboration/approval-flow-confirmation";
import {
  formatApprovalDate,
  statusConfig,
  type ApprovalStatus,
  type PendingAction,
} from "@/components/collaboration/approval-flow-config";

interface ApprovalFlowProps {
  status: ApprovalStatus;
  /** Who approved/reviewed */
  approver?: string;
  /** When it was approved */
  approvedAt?: string;
  /** Called when user confirms Approve (with optional comment) */
  onApprove?: (comment?: string) => void;
  /** Called when user confirms Request Changes (with optional comment) */
  onRequestChanges?: (comment?: string) => void;
  /** Whether the current user can approve */
  canApprove?: boolean;
  className?: string;
}
export type { ApprovalStatus } from "@/components/collaboration/approval-flow-config";

export function ApprovalFlow({
  status,
  approver,
  approvedAt,
  onApprove,
  onRequestChanges,
  canApprove = false,
  className,
}: ApprovalFlowProps) {
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);
  const [comment, setComment] = useState("");
  const approveButtonRef = useRef<HTMLButtonElement>(null);
  const requestChangesButtonRef = useRef<HTMLButtonElement>(null);
  const returnFocusActionRef = useRef<PendingAction>(null);
  const config = statusConfig[status];
  const Icon = config.icon;

  useEffect(() => {
    if (pendingAction || !returnFocusActionRef.current) {
      return;
    }

    const action = returnFocusActionRef.current;
    returnFocusActionRef.current = null;
    const target =
      action === "approve"
        ? approveButtonRef.current
        : requestChangesButtonRef.current;
    target?.focus();
  }, [pendingAction]);

  const handleConfirm = () => {
    const trimmedComment = comment.trim() || undefined;
    if (pendingAction === "approve") {
      onApprove?.(trimmedComment);
    } else if (pendingAction === "request_changes") {
      onRequestChanges?.(trimmedComment);
    }
    setPendingAction(null);
    setComment("");
  };

  const handleCancel = () => {
    returnFocusActionRef.current = pendingAction;
    setPendingAction(null);
    setComment("");
  };

  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex min-w-0 flex-col items-stretch gap-3 sm:flex-row sm:items-center">
        {/* Status badge */}
        <div
          className={cn(
            "flex w-fit max-w-full items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
            config.bg,
            config.color,
            config.border,
          )}
        >
          <Icon className="h-3.5 w-3.5" />
          {config.label}
        </div>

        {/* Approver info */}
        {approver && (
          <span className="min-w-0 text-xs text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
            by {approver}
            {approvedAt ? <> on {formatApprovalDate(approvedAt)}</> : null}
          </span>
        )}

        <ApprovalFlowActionButtons
          approveButtonRef={approveButtonRef}
          canApprove={canApprove}
          onApprove={onApprove}
          onOpenAction={setPendingAction}
          onRequestChanges={onRequestChanges}
          pendingAction={pendingAction}
          requestChangesButtonRef={requestChangesButtonRef}
          status={status}
        />
      </div>

      <ApprovalFlowConfirmation
        comment={comment}
        onCancel={handleCancel}
        onCommentChange={setComment}
        onConfirm={handleConfirm}
        pendingAction={pendingAction}
      />
    </div>
  );
}
export { ApprovalSteps } from "@/components/collaboration/approval-flow-steps";
