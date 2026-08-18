import type { ReactNode } from "react";
import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import { cn } from "@/lib/utils";

interface RouteLoadingFrameProps {
  children: ReactNode;
  description?: string;
  eyebrow: string;
  label: string;
  title: string;
  className?: string;
}

export function RouteLoadingFrame({
  children,
  description,
  eyebrow,
  label,
  title,
  className,
}: RouteLoadingFrameProps) {
  return (
    <section
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-atomic="true"
      className={cn(
        "praviar-operational-field relative isolate overflow-hidden rounded-lg p-5 sm:p-6",
        className,
      )}
      data-praviar-route-loading-frame
      data-praviar-app-state="loading"
    >
      <span className="sr-only">{label}</span>
      <div
        aria-hidden="true"
        className="praviar-evidence-field-pattern pointer-events-none absolute inset-0 -z-10"
      />

      <div className="flex min-w-0 items-start gap-4">
        <PraviarMarkFrame />
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
            {eyebrow}
          </p>
          <h2 className="mt-1 break-words type-heading-xl text-[var(--text-primary)] [overflow-wrap:anywhere]">
            {title}
          </h2>
          {description ? (
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-secondary)]">
              {description}
            </p>
          ) : null}
        </div>
      </div>

      <div className="mt-6 min-w-0">{children}</div>
    </section>
  );
}
