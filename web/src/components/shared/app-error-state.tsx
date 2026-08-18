import { RefreshCcw } from "lucide-react";
import { useId, type ReactNode } from "react";
import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import {
  AIRecoveryBrief,
  type AIRecoveryBriefProps,
} from "@/components/shared/ai-recovery-brief";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface AppErrorStateProps {
  title: string;
  description: string;
  detail?: string | null;
  actionLabel?: string;
  aiBrief?: AIRecoveryBriefProps;
  onAction?: () => void;
  secondaryAction?: ReactNode;
  tone?: "error" | "warning";
  className?: string;
  headingLevel?: 1 | 2 | 3;
}

export function AppErrorState({
  title,
  description,
  detail,
  actionLabel = "Retry",
  aiBrief,
  onAction,
  secondaryAction,
  tone = "error",
  className,
  headingLevel = 2,
}: AppErrorStateProps) {
  const Heading = `h${headingLevel}` as "h1" | "h2" | "h3";
  const titleId = `${useId()}-${slugifyTitle(title)}`;
  const summaryId = `${titleId}-summary`;
  const safeDetail = formatSupportReference(detail);
  const toneClassName =
    tone === "warning" ? "ring-2 ring-warning/20" : "ring-2 ring-error/15";

  return (
    <Card
      aria-labelledby={titleId}
      aria-describedby={summaryId}
      data-praviar-app-state="error"
      className={cn(
        "praviar-operational-field relative isolate overflow-hidden border-[var(--border-default)]",
        className,
      )}
    >
      <div
        aria-hidden="true"
        className="praviar-evidence-field-pattern pointer-events-none absolute inset-0 -z-10"
      />
      <CardContent className="relative space-y-4 p-5 sm:p-6">
        <div className="flex items-start gap-3">
          <PraviarMarkFrame className={cn("mt-0.5", toneClassName)} size="sm" />
          <div
            role="alert"
            aria-live="assertive"
            aria-atomic="true"
            aria-labelledby={titleId}
            aria-describedby={summaryId}
            className="min-w-0"
          >
            <Heading
              id={titleId}
              className="type-heading-sm text-[var(--text-primary)] [overflow-wrap:anywhere]"
            >
              {title}
            </Heading>
            <p
              id={summaryId}
              className="mt-1 text-sm leading-6 text-[var(--text-secondary)]"
            >
              {description}
            </p>
          </div>
        </div>

        {(onAction || secondaryAction || safeDetail) && (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:flex-wrap">
            {onAction ? (
              <Button
                type="button"
                variant="outline"
                className="min-h-11 w-full gap-2 sm:w-auto"
                onClick={onAction}
              >
                <RefreshCcw className="h-3.5 w-3.5" aria-hidden="true" />
                {actionLabel}
              </Button>
            ) : null}
            {secondaryAction}
            {safeDetail ? (
              <p className="min-w-0 text-xs leading-5 text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
                Reference: {safeDetail}
              </p>
            ) : null}
          </div>
        )}

        {aiBrief ? <AIRecoveryBrief {...aiBrief} /> : null}
      </CardContent>
    </Card>
  );
}

function slugifyTitle(title: string): string {
  return (
    title
      .toLowerCase()
      .replace(/[^a-z0-9]+/gu, "-")
      .replace(/^-|-$/gu, "") || "state"
  );
}

function formatSupportReference(detail?: string | null): string | null {
  if (!detail) {
    return null;
  }

  const reference = detail
    .replace(/^(?:reference|ref)\s*:\s*/iu, "")
    .replace(/\s+/gu, " ")
    .trim();

  if (!reference) {
    return null;
  }

  const opaqueReferencePattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{2,95}$/u;

  return opaqueReferencePattern.test(reference) ? reference : null;
}
