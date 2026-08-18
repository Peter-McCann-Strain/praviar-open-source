import { AlertTriangle, BarChart3, RotateCcw, ShieldCheck } from "lucide-react";
import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

interface AnalyticsStatusStateProps {
  variant: "access" | "restricted" | "temporary";
  onRetry?: () => void;
}

export function AnalyticsStatusState({
  variant,
  onRetry,
}: AnalyticsStatusStateProps) {
  const isAccess = variant === "access";
  const isRestricted = variant === "restricted";
  const titleId = `admin-analytics-status-${variant}-title`;
  const iconToneClassName = isAccess
    ? "border-info/25 bg-info/10 text-info"
    : "border-error/25 bg-error/10 text-error";

  return (
    <section
      role={isAccess ? "status" : "alert"}
      aria-live={isAccess ? "polite" : "assertive"}
      aria-busy={isAccess ? true : undefined}
      aria-atomic="true"
      aria-labelledby={titleId}
      className="praviar-operational-field overflow-hidden rounded-lg"
      data-testid={`admin-analytics-status-${variant}`}
    >
      <div className="praviar-glass-strip border-b border-[var(--border-subtle)] px-5 py-5 sm:px-6">
        <div className="flex min-w-0 items-start gap-4">
          <PraviarMarkFrame size="dialog" />
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
              Analytics control plane
            </p>
            <h1
              id={titleId}
              className="mt-1 break-words type-heading-xl text-[var(--text-primary)] [overflow-wrap:anywhere]"
            >
              {isAccess
                ? "Checking analytics access"
                : isRestricted
                  ? "Analytics access restricted"
                  : "Analytics temporarily unavailable"}
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-secondary)]">
              {isAccess
                ? "Praviar waits for an administrator-scoped session before requesting cost, usage, model, and audit telemetry."
                : isRestricted
                  ? "Your current session is not authorized to view administrator-scoped telemetry. Cached analytics are hidden until access is confirmed again."
                  : "The analytics service did not return a usable view. Existing cost controls, model settings, and audit records are unchanged."}
            </p>
          </div>
        </div>
      </div>

      <div className="grid min-w-0 gap-0 lg:grid-cols-[0.82fr_1.18fr]">
        <div className="praviar-glass-panel-soft border-b border-[var(--border-subtle)] p-5 sm:p-6 lg:border-b-0 lg:border-r">
          <div
            className={`flex h-14 w-14 items-center justify-center rounded-lg border ${iconToneClassName}`}
          >
            {isAccess ? (
              <ShieldCheck className="h-6 w-6" aria-hidden="true" />
            ) : (
              <AlertTriangle className="h-6 w-6" aria-hidden="true" />
            )}
          </div>
          <div className="mt-5 grid gap-3">
            {[
              "No tenant telemetry exposed",
              "Existing controls unchanged",
              "Actions unlock after a fresh view",
            ].map((item) => (
              <div
                key={item}
                className="praviar-glass-chip flex min-w-0 items-center gap-3 rounded-lg px-3 py-2"
              >
                <BarChart3
                  className="h-4 w-4 shrink-0 text-[var(--brand-primary)]"
                  aria-hidden="true"
                />
                <span className="min-w-0 text-sm text-[var(--text-secondary)]">
                  {item}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="min-w-0 p-5 sm:p-6">
          <div className="praviar-glass-panel-soft rounded-lg p-4">
            <p className="font-semibold text-[var(--text-primary)]">
              {isAccess
                ? "Preparing governed analytics"
                : isRestricted
                  ? "Confirm analytics access"
                  : "Retry analytics load"}
            </p>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              {isAccess
                ? "Costs, model usage, and audit telemetry are requested only after administrator access is available."
                : isRestricted
                  ? "A retry requests a fresh authorization check before any analytics telemetry is shown."
                  : "A retry requests the latest administrator-scoped telemetry without changing tenant records."}
            </p>
            {onRetry ? (
              <Button
                type="button"
                variant="outline"
                className="mt-4 min-h-11 w-full gap-2 sm:w-auto"
                onClick={onRetry}
              >
                <RotateCcw className="h-4 w-4" aria-hidden="true" />
                Retry analytics load
              </Button>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}

export function AnalyticsRefreshWarning({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      role="status"
      aria-atomic="true"
      className="rounded-lg border border-warning/20 bg-warning/10 px-4 py-3"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-2">
          <AlertTriangle
            className="mt-0.5 h-4 w-4 shrink-0 text-warning"
            aria-hidden="true"
          />
          <p className="text-sm leading-6 text-[var(--text-secondary)]">
            Analytics refresh failed. Existing telemetry remains visible, and no
            tenant settings or audit records were changed.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="min-h-11 w-full sm:w-auto"
          onClick={onRetry}
        >
          Retry refresh
        </Button>
      </div>
    </div>
  );
}

export function AnalyticsPanelStatus({
  title,
  description,
  onRetry,
}: {
  title: string;
  description: string;
  onRetry: () => void;
}) {
  return (
    <Card role="alert">
      <CardContent className="p-5 sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {title}
            </p>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              {description}
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            className="min-h-11 w-full gap-2 sm:w-auto"
            onClick={onRetry}
          >
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            Retry
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
