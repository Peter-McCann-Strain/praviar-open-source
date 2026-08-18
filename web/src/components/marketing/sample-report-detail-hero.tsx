import Link from "next/link";
import { ArrowRight, ShieldAlert } from "lucide-react";
import {
  SYNTHETIC_SAMPLE_DISCLAIMER,
  type SampleReportEntry,
} from "@/marketing/content";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { PUBLIC_METHODOLOGY_ACTION } from "@/marketing/public-readiness";

interface SampleReportDetailHeroProps {
  entry: SampleReportEntry;
  familiesFlaggedForReviewCount: number;
  isSyntheticSample: boolean;
}

export function SampleReportDetailHero({
  entry,
  familiesFlaggedForReviewCount,
  isSyntheticSample,
}: SampleReportDetailHeroProps) {
  const analyzedMetric =
    entry.metrics.find((metric) => /analyzed/i.test(metric.label)) ??
    entry.metrics.at(-1);

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        {isSyntheticSample ? (
          <p className="inline-flex w-fit rounded-full border border-warning/25 bg-warning/10 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.12em] text-warning-emphasis">
            Synthetic sample · fictional patent data
          </p>
        ) : null}
        <h1 className="[font-family:var(--font-newsreader)] text-4xl leading-[1.02] text-[var(--text-primary)] sm:text-5xl">
          {entry.compoundName}
        </h1>
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
          {entry.category}
        </p>
        <p className="text-lg leading-8 text-[var(--text-secondary)]">
          {entry.summary}
        </p>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
        <a
          href="#sample-trace-packet"
          className={cn(
            buttonVariants({ size: "lg" }),
            "w-full rounded-lg sm:w-auto",
          )}
        >
          Inspect fictional evidence
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </a>
        <Link
          href={PUBLIC_METHODOLOGY_ACTION.href}
          className={cn(
            buttonVariants({ variant: "outline", size: "lg" }),
            "w-full rounded-lg sm:w-auto",
          )}
        >
          {PUBLIC_METHODOLOGY_ACTION.label}
        </Link>
      </div>

      <div className="rounded-lg border border-error/20 bg-[linear-gradient(135deg,color-mix(in_srgb,var(--semantic-error)_10%,var(--bg-surface)),var(--bg-surface)_64%)] p-4 shadow-[var(--shadow-xs)]">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-error/25 bg-error/10 text-error">
            <ShieldAlert className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              What the fictional scenario flags
            </p>
            <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
              Illustrative priority: {entry.verdictLabel}
              {` · ${familiesFlaggedForReviewCount} sample ${
                familiesFlaggedForReviewCount === 1 ? "family" : "families"
              } flagged for review`}
            </p>
            <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
              Follow the claim evidence, open questions, and possible research
              hypotheses to see how the finished brief works.
            </p>
          </div>
        </div>
        {analyzedMetric ? (
          <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-surface)_72%,transparent)] px-3 py-2 text-xs font-semibold text-[var(--text-secondary)]">
            Illustrative sample count: {analyzedMetric.value}{" "}
            {analyzedMetric.label.toLowerCase()}
          </div>
        ) : null}
      </div>

      <details className="group rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)] p-4 lg:hidden">
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 font-semibold text-[var(--text-primary)] marker:content-none">
          About this fictional sample
          <span aria-hidden="true" className="text-[var(--text-tertiary)]">
            <span className="group-open:hidden">＋</span>
            <span className="hidden group-open:inline">−</span>
          </span>
        </summary>
        <div className="space-y-4 border-t border-[var(--border-subtle)] pt-4 text-sm leading-7 text-[var(--text-secondary)]">
          {isSyntheticSample ? <p>{SYNTHETIC_SAMPLE_DISCLAIMER}</p> : null}
          <dl className="grid grid-cols-3 gap-2">
            {entry.metrics.map((metric) => (
              <div key={`${entry.slug}-mobile-${metric.label}`}>
                <dt className="text-xs uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                  Illustrative {metric.label}
                </dt>
                <dd className="mt-1 font-semibold text-[var(--text-primary)]">
                  {metric.value}
                </dd>
              </div>
            ))}
          </dl>
          <p>{entry.teaser}</p>
          <p className="text-xs leading-6 text-[var(--text-tertiary)]">
            <span className="font-semibold uppercase tracking-[0.12em]">
              Sample data source
            </span>{" "}
            <span className="font-mono [overflow-wrap:anywhere]">
              {entry.sourceReference}
            </span>
          </p>
        </div>
      </details>

      <div className="hidden space-y-4 lg:block">
        {isSyntheticSample ? (
          <div className="rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)] p-4 text-sm leading-7 text-[var(--text-secondary)]">
            {SYNTHETIC_SAMPLE_DISCLAIMER}
          </div>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-3">
          {entry.metrics.map((metric) => (
            <div
              key={`${entry.slug}-${metric.label}`}
              className="praviar-glass-chip rounded-lg px-5 py-4"
            >
              <p className="text-xl font-semibold text-[var(--text-primary)]">
                {metric.value}
              </p>
              <p className="mt-1 text-xs uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                Illustrative {metric.label}
              </p>
            </div>
          ))}
        </div>

        <div className="praviar-glass-panel rounded-lg border-dashed border-[var(--border-emphasis)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
          {entry.teaser}
        </div>

        <div className="praviar-glass-panel-soft rounded-lg p-4 text-xs leading-6 text-[var(--text-secondary)]">
          <span className="font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
            Sample data source
          </span>{" "}
          <span className="font-mono [overflow-wrap:anywhere]">
            {entry.sourceReference}
          </span>
        </div>
      </div>
    </div>
  );
}
