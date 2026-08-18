"use client";

import { AlertTriangle, RefreshCw, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { MutationRecoveryMode } from "@/hooks/use-mutation-recovery";
import { cn } from "@/lib/utils";

interface MutationRecoveryNoticeProps {
  actionLabel: string;
  actionPending?: boolean;
  dataTestId: string;
  description: string;
  dismissLabel?: string;
  mode: MutationRecoveryMode;
  onAction: () => void;
  onDismiss?: () => void;
  title: string;
}

export function MutationRecoveryNotice({
  actionLabel,
  actionPending = false,
  dataTestId,
  description,
  dismissLabel = "Dismiss recovery notice",
  mode,
  onAction,
  onDismiss,
  title,
}: MutationRecoveryNoticeProps) {
  const outcomeUnknown = mode === "outcome-unknown";

  return (
    <div
      role="alert"
      aria-atomic="true"
      data-mutation-recovery-mode={mode}
      data-testid={dataTestId}
      className={cn(
        "rounded-lg border px-4 py-3 shadow-[var(--shadow-xs)]",
        outcomeUnknown
          ? "border-warning/30 bg-warning/10"
          : "border-error/25 bg-error/10",
      )}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <AlertTriangle
            className={cn(
              "mt-0.5 h-5 w-5 shrink-0",
              outcomeUnknown ? "text-warning" : "text-error",
            )}
            aria-hidden="true"
          />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {title}
            </p>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              {description}
            </p>
          </div>
        </div>
        <div className="flex w-full shrink-0 flex-col gap-2 sm:w-auto sm:flex-row">
          <Button
            type="button"
            variant={outcomeUnknown ? "default" : "outline"}
            className="min-h-11 w-full gap-2 sm:w-auto"
            loading={actionPending}
            disabled={actionPending}
            onClick={onAction}
            data-testid={`${dataTestId}-action`}
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            {actionLabel}
          </Button>
          {onDismiss ? (
            <Button
              type="button"
              variant="ghost"
              className="min-h-11 w-full gap-2 sm:w-auto"
              disabled={actionPending}
              onClick={onDismiss}
              data-testid={`${dataTestId}-dismiss`}
            >
              <X className="h-4 w-4" aria-hidden="true" />
              {dismissLabel}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
