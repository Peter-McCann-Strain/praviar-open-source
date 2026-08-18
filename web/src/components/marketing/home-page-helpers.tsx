import type { ComponentType, ReactNode } from "react";
import { CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { PUBLIC_PRIMARY_ACTION } from "@/marketing/public-readiness";
import type { RiskLevel } from "@praviar/shared-types";

export function formatFictionalFamiliesFlaggedForReview(count: number): string {
  return `${count.toLocaleString()} fictional ${count === 1 ? "family" : "families"} flagged for review`;
}

export function getSamplePriorityLabel(risk: RiskLevel): string {
  const normalizedRisk = String(risk).trim().toLowerCase();
  if (normalizedRisk === "high" || normalizedRisk === "critical") {
    return "High sample priority";
  }
  if (normalizedRisk === "medium" || normalizedRisk === "moderate") {
    return "Medium sample priority";
  }
  if (normalizedRisk === "low") return "Low sample priority";
  if (normalizedRisk === "clear") return "No overlap in sample";
  return "Sample review status pending";
}

export function buildPrimaryHref(mode: "adaptive", compound: string) {
  void mode;
  void compound;
  return PUBLIC_PRIMARY_ACTION.href;
}

export function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="praviar-surface-premium rounded-lg px-4 py-3">
      <p className="text-lg font-semibold text-[var(--text-primary)]">
        {value}
      </p>
      <p className="mt-1 text-xs uppercase text-[var(--text-tertiary)]">
        {label}
      </p>
    </div>
  );
}

export function StripMetric({
  label,
  source,
  value,
}: {
  label: string;
  source?: string;
  value: string;
}) {
  return (
    <div className="praviar-surface-premium rounded-lg px-5 py-4">
      <p className="text-2xl font-semibold text-[var(--text-primary)]">
        {value}
      </p>
      <p className="mt-1 text-xs uppercase text-[var(--text-tertiary)]">
        {label}
      </p>
      {source ? (
        <p className="mt-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
          {source}
        </p>
      ) : null}
    </div>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  description,
  headingId,
}: {
  eyebrow: string;
  title: string;
  description: string;
  headingId?: string;
}) {
  return (
    <div className="max-w-3xl space-y-4">
      <p className="text-sm font-semibold uppercase text-[var(--text-tertiary)]">
        {eyebrow}
      </p>
      <h2
        id={headingId}
        className="[font-family:var(--font-newsreader)] text-4xl leading-[1.04] text-[var(--text-primary)] md:text-5xl"
      >
        {title}
      </h2>
      <p className="text-lg leading-8 text-[var(--text-secondary)]">
        {description}
      </p>
    </div>
  );
}

export function EditorialBlock({
  eyebrow,
  title,
  summary,
  bullets,
  visual,
  reverse = false,
  mobileVisualFirst = false,
  icon: Icon,
}: {
  eyebrow: string;
  title: string;
  summary: string;
  bullets?: string[];
  visual: ReactNode;
  reverse?: boolean;
  mobileVisualFirst?: boolean;
  icon: ComponentType<{ className?: string }>;
}) {
  return (
    <div
      className={cn(
        "grid gap-10 lg:grid-cols-[0.95fr_1.05fr] lg:items-center",
        reverse && "lg:grid-cols-[1.05fr_0.95fr]",
      )}
    >
      <div
        className={cn(
          "space-y-5",
          mobileVisualFirst && "order-2 lg:order-none",
          reverse && "lg:order-2",
        )}
      >
        <div className="inline-flex items-center gap-2 rounded-full bg-[var(--bg-elevated)] px-4 py-2 text-xs font-semibold uppercase text-[var(--text-secondary)]">
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
          {eyebrow}
        </div>
        <h3 className="[font-family:var(--font-newsreader)] text-4xl leading-[1.04] text-[var(--text-primary)]">
          {title}
        </h3>
        <p className="text-lg leading-8 text-[var(--text-secondary)]">
          {summary}
        </p>
        {bullets && bullets.length > 0 ? (
          <ul className="space-y-3">
            {bullets.map((bullet) => (
              <li
                key={bullet}
                className="flex gap-3 text-sm leading-7 text-[var(--text-secondary)]"
              >
                <CheckCircle2
                  className="mt-1 h-4 w-4 shrink-0 text-success"
                  aria-hidden="true"
                />
                <span>{bullet}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      <div
        className={cn(
          mobileVisualFirst && "order-1 lg:order-none",
          reverse && "lg:order-1",
        )}
      >
        {visual}
      </div>
    </div>
  );
}

export function OutcomeCard({
  icon: Icon,
  title,
  description,
}: {
  icon: ComponentType<{ className?: string }>;
  title: string;
  description: string;
}) {
  return (
    <div className="praviar-surface-premium rounded-lg p-6">
      <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-[var(--bg-elevated)] text-[var(--text-primary)]">
        <Icon className="h-5 w-5" aria-hidden="true" />
      </div>
      <h3 className="mt-5 text-xl font-semibold text-[var(--text-primary)]">
        {title}
      </h3>
      <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
        {description}
      </p>
    </div>
  );
}
