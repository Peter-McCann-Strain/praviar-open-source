"use client";

import { AlertTriangle, Download, Loader2 } from "lucide-react";
import { useId } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ExportDialogActionsProps {
  buttonLabel?: string;
  disabledReason?: string | null;
  disabledTone?: "danger" | "warning" | "neutral";
  isCompleted?: boolean;
  isProcessing: boolean;
  isDisabled: boolean;
  onClose: () => void;
  onExport: () => void;
}

export function ExportDialogActions({
  buttonLabel: buttonLabelOverride,
  disabledReason,
  disabledTone = "danger",
  isCompleted = false,
  isProcessing,
  isDisabled,
  onClose,
  onExport,
}: ExportDialogActionsProps) {
  const disabledReasonId = useId();
  const hasDisabledReason = Boolean(disabledReason) && !isProcessing;
  const buttonLabel = isProcessing
    ? "Exporting..."
    : (buttonLabelOverride ??
      (hasDisabledReason ? "Resolve blockers" : "Export packet"));
  const disabledReasonClass =
    disabledTone === "warning"
      ? "border-warning/25 bg-warning/8 text-warning"
      : disabledTone === "neutral"
        ? "border-[var(--border-default)] bg-[var(--surface-muted)] text-[var(--text-secondary)]"
        : "border-error/25 bg-error/8 text-error";

  return (
    <div className="flex flex-col gap-3">
      {disabledReason ? (
        <p
          id={disabledReasonId}
          className={cn(
            "rounded-md border px-3 py-2 text-xs font-medium leading-5",
            disabledReasonClass,
          )}
        >
          {disabledReason}
        </p>
      ) : null}
      <div
        className={cn(
          "grid gap-3 sm:flex sm:justify-end",
          isCompleted ? "grid-cols-1" : "grid-cols-2",
        )}
      >
        <Button
          variant="outline"
          onClick={onClose}
          className="min-h-11 w-full sm:w-auto"
        >
          {isCompleted ? "Close" : "Cancel"}
        </Button>
        {!isCompleted ? (
          <Button
            onClick={onExport}
            disabled={isDisabled}
            aria-describedby={disabledReason ? disabledReasonId : undefined}
            className={cn(
              "min-h-11 w-full gap-2 whitespace-normal text-center leading-5 sm:w-auto sm:whitespace-nowrap",
              hasDisabledReason && disabledTone === "danger"
                ? "border border-error/30 bg-error/10 text-error hover:bg-error/12 hover:text-error disabled:border-error/30 disabled:bg-error/10 disabled:text-error disabled:opacity-95"
                : hasDisabledReason && disabledTone === "warning"
                  ? "border border-warning/30 bg-warning/10 text-warning hover:bg-warning/12 hover:text-warning disabled:border-warning/30 disabled:bg-warning/10 disabled:text-warning disabled:opacity-95"
                  : "disabled:border disabled:border-[var(--border-default)] disabled:bg-[var(--surface-muted)] disabled:text-[var(--text-secondary)] disabled:opacity-90",
            )}
          >
            {isProcessing ? (
              <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" />
            ) : hasDisabledReason ? (
              <AlertTriangle className="h-4 w-4" />
            ) : (
              <Download className="h-4 w-4" />
            )}
            {buttonLabel}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
