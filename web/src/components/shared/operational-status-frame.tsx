"use client";

import type { ReactNode } from "react";
import {
  AlertTriangle,
  CircleDashed,
  RotateCcw,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import {
  AIRecoveryBrief,
  type AIRecoveryBriefProps,
} from "@/components/shared/ai-recovery-brief";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type OperationalStatusTone = "default" | "warning" | "error";

interface OperationalStatusFrameProps {
  actionLabel?: string;
  className?: string;
  contextItems: string[];
  dataTestId: string;
  description: string;
  eyebrow: string;
  headingLevel?: 1 | 2 | 3;
  icon: LucideIcon;
  aiBrief?: AIRecoveryBriefProps;
  isPending: boolean;
  isLoading?: boolean;
  onRetry?: () => void;
  recoveryExtra?: ReactNode;
  secondaryAction?: ReactNode;
  recoveryBody: string;
  recoveryTitle: string;
  title: string;
  titleId: string;
  tone: OperationalStatusTone;
}

const TONE_CLASS: Record<OperationalStatusTone, string> = {
  default: "border-info/25 bg-info/10 text-info",
  warning: "border-warning/25 bg-warning/10 text-warning",
  error: "border-error/25 bg-error/10 text-error",
};

export function OperationalStatusFrame({
  actionLabel,
  className,
  contextItems,
  dataTestId,
  description,
  eyebrow,
  headingLevel = 2,
  icon: Icon,
  aiBrief,
  isPending,
  isLoading = false,
  onRetry,
  recoveryExtra,
  secondaryAction,
  recoveryBody,
  recoveryTitle,
  title,
  titleId,
  tone,
}: OperationalStatusFrameProps) {
  const Heading = `h${headingLevel}` as "h1" | "h2" | "h3";
  const summaryId = `${titleId}-summary`;
  const ContextIcon =
    tone === "default"
      ? ShieldCheck
      : tone === "warning"
        ? CircleDashed
        : AlertTriangle;
  const isUrgent = !isPending && tone === "error";
  const contextIconClassName =
    tone === "default"
      ? "text-[var(--brand-primary)]"
      : tone === "warning"
        ? "text-warning"
        : "text-error";

  return (
    <section
      aria-labelledby={titleId}
      aria-describedby={summaryId}
      className={cn(
        "praviar-operational-field relative isolate overflow-hidden rounded-lg",
        className,
      )}
      data-praviar-status-frame
      data-praviar-app-state={
        isPending ? "loading" : tone === "error" ? "error" : "ready"
      }
      data-testid={dataTestId}
    >
      <div
        aria-hidden="true"
        className="praviar-evidence-field-pattern pointer-events-none absolute inset-0 -z-10"
      />
      <div className="border-b border-[var(--border-subtle)] bg-[var(--surface-muted)]/45 px-4 py-4 sm:px-6 sm:py-5">
        <div className="flex min-w-0 items-start gap-3 sm:gap-4">
          <PraviarMarkFrame
            size="xs"
            className="sm:h-11 sm:w-11"
            markClassName="sm:h-8 sm:w-8"
          />
          <div
            role={isUrgent ? "alert" : "status"}
            aria-live={isUrgent ? "assertive" : "polite"}
            aria-busy={isPending ? true : undefined}
            aria-atomic="true"
            aria-labelledby={titleId}
            aria-describedby={summaryId}
            className="min-w-0"
          >
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
              {eyebrow}
            </p>
            <Heading
              id={titleId}
              className="mt-1 break-words text-lg font-semibold leading-6 text-[var(--text-primary)] [overflow-wrap:anywhere] sm:type-heading-xl"
            >
              {title}
            </Heading>
            <p
              id={summaryId}
              className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-secondary)]"
            >
              {description}
            </p>
          </div>
        </div>
      </div>

      <div className="grid min-w-0 gap-0 lg:grid-cols-[0.82fr_1.18fr]">
        <div className="order-last border-t border-[var(--border-subtle)] bg-[var(--surface-muted)]/30 p-4 sm:p-6 lg:order-first lg:border-b-0 lg:border-r lg:border-t-0">
          <div
            className={cn(
              "flex h-11 w-11 items-center justify-center rounded-lg border sm:h-14 sm:w-14",
              TONE_CLASS[tone],
            )}
          >
            <Icon
              className={cn(
                "h-6 w-6",
                isLoading && "animate-spin motion-reduce:animate-none",
              )}
              aria-hidden="true"
            />
          </div>

          <div className="mt-4 grid gap-2 sm:mt-5 sm:gap-3">
            {contextItems.map((item) => (
              <div
                key={item}
                className="praviar-glass-chip flex min-w-0 items-center gap-3 rounded-lg px-3 py-2"
              >
                <ContextIcon
                  className={cn("h-4 w-4 shrink-0", contextIconClassName)}
                  aria-hidden="true"
                />
                <span className="min-w-0 text-sm text-[var(--text-secondary)]">
                  {item}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="order-first min-w-0 p-4 sm:p-6 lg:order-last">
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/60 p-4 shadow-[var(--shadow-xs)]">
            <p className="font-semibold text-[var(--text-primary)]">
              {recoveryTitle}
            </p>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              {recoveryBody}
            </p>
            {(onRetry || secondaryAction) && (
              <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
                {onRetry ? (
                  <Button
                    type="button"
                    variant="outline"
                    className="min-h-11 w-full gap-2 sm:w-auto"
                    onClick={onRetry}
                  >
                    <RotateCcw className="h-4 w-4" aria-hidden="true" />
                    {actionLabel ?? "Retry"}
                  </Button>
                ) : null}
                {secondaryAction}
              </div>
            )}
            {recoveryExtra}
            {aiBrief ? <AIRecoveryBrief {...aiBrief} /> : null}
          </div>
        </div>
      </div>
    </section>
  );
}
