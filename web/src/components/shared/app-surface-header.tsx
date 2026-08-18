import type { HTMLAttributes, ReactNode } from "react";
import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import { cn } from "@/lib/utils";

type AppSurfaceHeaderMarkSize = "sm" | "md" | "lg";
type AppSurfaceHeaderChrome = "default" | "dashboard";
type AppSurfaceHeaderMobileDensity = "default" | "compact";
type AppSurfaceHeaderMobileMetricColumns = "balanced" | "three";
export type AppSurfaceHeaderMetricTone =
  | "active"
  | "default"
  | "success"
  | "warning"
  | "destructive";

export interface AppSurfaceHeaderMetric {
  detail?: string;
  icon?: ReactNode;
  label: string;
  mobileHidden?: boolean;
  tone?: AppSurfaceHeaderMetricTone;
  value: string;
}

interface AppSurfaceHeaderProps extends Omit<
  HTMLAttributes<HTMLElement>,
  "title"
> {
  actions?: ReactNode;
  art?: ReactNode;
  className?: string;
  chrome?: AppSurfaceHeaderChrome;
  dataTestId?: string;
  description: string;
  eyebrow: string;
  markSize?: AppSurfaceHeaderMarkSize;
  metrics?: AppSurfaceHeaderMetric[];
  mobileDensity?: AppSurfaceHeaderMobileDensity;
  mobileMetricColumns?: AppSurfaceHeaderMobileMetricColumns;
  title: string;
}

const METRIC_TONE_CLASS: Record<AppSurfaceHeaderMetricTone, string> = {
  active: "border-brand-primary/25 bg-brand-primary/10",
  default: "border-[var(--border-subtle)] bg-[var(--bg-surface)]/70",
  destructive: "border-error/25 bg-error/10",
  success: "border-success/25 bg-success/10",
  warning: "border-warning/25 bg-warning/10",
};

const HEADER_CHROME_CLASS: Record<AppSurfaceHeaderChrome, string> = {
  default:
    "praviar-control-plane-header rounded-lg border border-[var(--border-subtle)] px-4 py-5 shadow-[var(--shadow-sm)] sm:px-6",
  dashboard:
    "praviar-dashboard-command-deck border-y border-[var(--border-default)] px-4 py-5 shadow-[var(--shadow-xs)] sm:rounded-lg sm:border sm:px-5",
};

export function AppSurfaceHeader({
  actions,
  art,
  chrome = "default",
  className,
  dataTestId = "app-surface-header",
  description,
  eyebrow,
  markSize = "md",
  metrics,
  mobileDensity = "default",
  mobileMetricColumns = "balanced",
  title,
  ...props
}: AppSurfaceHeaderProps) {
  const compactMobile = mobileDensity === "compact";

  return (
    <header
      className={cn(
        "relative isolate overflow-hidden",
        HEADER_CHROME_CLASS[chrome],
        compactMobile && "py-4 sm:py-5",
        compactMobile && chrome === "default" && "px-3 sm:px-6",
        className,
      )}
      data-praviar-app-surface-header
      data-praviar-app-surface-density={mobileDensity}
      data-testid={dataTestId}
      {...props}
    >
      {art}
      <div
        className={cn(
          "grid min-w-0 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start",
          compactMobile ? "gap-4 sm:gap-5" : "gap-5",
        )}
      >
        <div
          className={cn(
            "flex min-w-0 items-start",
            compactMobile ? "gap-3 sm:gap-4" : "gap-4",
          )}
        >
          <PraviarMarkFrame
            size={markSize}
            className={compactMobile ? "max-[359px]:hidden" : undefined}
          />
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
              {eyebrow}
            </p>
            <h1 className="mt-1 break-words type-heading-xl text-[var(--text-primary)] [overflow-wrap:anywhere]">
              {title}
            </h1>
            <p className="mt-1 max-w-3xl break-words type-body-md text-[var(--text-secondary)] [overflow-wrap:anywhere]">
              {description}
            </p>
          </div>
        </div>

        {actions ? (
          <div className="flex w-full min-w-0 justify-stretch lg:w-auto lg:justify-end">
            {actions}
          </div>
        ) : null}
      </div>

      {metrics && metrics.length > 0 ? (
        <div
          className={cn(
            "grid gap-2 sm:[grid-template-columns:repeat(auto-fit,minmax(10.5rem,1fr))] xl:max-w-5xl",
            compactMobile
              ? mobileMetricColumns === "three"
                ? "mt-4 grid-cols-2 min-[420px]:grid-cols-3"
                : "mt-4 grid-cols-2 min-[420px]:grid-cols-3"
              : "mt-5 grid-cols-2",
          )}
        >
          {metrics.map((metric) => (
            <div
              key={`${metric.label}-${metric.value}`}
              role="group"
              aria-label={`${metric.label}: ${metric.value}${
                metric.detail ? `. ${metric.detail}` : ""
              }`}
              className={cn(
                "min-w-0 rounded-md border py-2",
                compactMobile ? "px-2 sm:px-3" : "px-3",
                METRIC_TONE_CLASS[metric.tone ?? "default"],
                metric.mobileHidden && "hidden sm:block",
              )}
            >
              <div className="flex min-w-0 items-start gap-2">
                {metric.icon ? (
                  <span
                    className="mt-0.5 shrink-0 text-brand-primary"
                    aria-hidden="true"
                  >
                    {metric.icon}
                  </span>
                ) : null}
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                    {metric.label}
                  </p>
                  <p
                    title={metric.value}
                    className={cn(
                      "mt-0.5 min-w-0 font-semibold text-[var(--text-primary)]",
                      compactMobile
                        ? "break-words text-xs leading-5 [overflow-wrap:anywhere] [word-break:normal]"
                        : "break-words text-sm [overflow-wrap:anywhere]",
                    )}
                  >
                    {metric.value}
                  </p>
                  {metric.detail ? (
                    <p className="mt-0.5 break-words text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                      {metric.detail}
                    </p>
                  ) : null}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </header>
  );
}
