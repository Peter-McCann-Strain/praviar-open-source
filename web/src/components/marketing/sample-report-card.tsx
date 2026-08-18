import Link from "next/link";
import { ArrowRight, FileSearch, FileStack } from "lucide-react";
import {
  SAMPLE_REPORTS,
  SYNTHETIC_SAMPLE_DISCLAIMER,
  type SampleReportEntry,
} from "@/marketing/content";
import { cn } from "@/lib/utils";

interface SampleReportCardProps {
  report: SampleReportEntry;
  featured?: boolean;
}

export function SampleReportCard({
  report,
  featured = false,
}: SampleReportCardProps) {
  return (
    <article
      className={cn(
        "praviar-surface-premium group flex h-full flex-col justify-between rounded-lg p-5 transition-colors duration-300 hover:border-[var(--border-emphasis)]",
        featured && "lg:p-6",
      )}
    >
      <div className="space-y-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
          <div className="space-y-2">
            <div className="inline-flex items-center gap-2 rounded-md bg-[var(--surface-muted)] px-3 py-1 text-xs font-semibold uppercase text-[var(--text-tertiary)]">
              <FileSearch className="h-3 w-3" aria-hidden="true" />
              {report.category}
            </div>
            <div>
              <h3 className="text-2xl font-semibold text-[var(--text-primary)]">
                {report.compoundName}
              </h3>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                {report.title}
              </p>
            </div>
          </div>
          <span className="w-fit shrink-0 rounded-md bg-warning/12 px-3 py-1 text-xs font-semibold uppercase text-warning">
            Synthetic sample
          </span>
        </div>

        <div className="rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)] px-4 py-3 text-xs leading-6 text-[var(--text-secondary)]">
          {SYNTHETIC_SAMPLE_DISCLAIMER}
        </div>

        <div className="rounded-lg bg-[var(--surface-muted)] px-4 py-3 text-xs leading-5 text-[var(--text-tertiary)]">
          <span className="font-semibold uppercase">Sample source</span>{" "}
          <span className="font-mono [overflow-wrap:anywhere]">
            {report.sourceReference}
          </span>
        </div>

        <p className="max-w-xl text-sm leading-6 text-[var(--text-secondary)]">
          {report.summary}
        </p>

        <div className="grid divide-y divide-[var(--border-subtle)] border-y border-[var(--border-subtle)] sm:grid-cols-3 sm:divide-x sm:divide-y-0">
          {report.metrics.map((metric) => (
            <div
              key={`${report.slug}-${metric.label}`}
              className="px-0 py-3 sm:px-4"
            >
              <p className="text-lg font-semibold text-[var(--text-primary)]">
                {metric.value}
              </p>
              <p className="mt-1 text-xs uppercase text-[var(--text-tertiary)]">
                {metric.label}
              </p>
            </div>
          ))}
        </div>

        <div className="rounded-lg border border-dashed border-[var(--border-default)] px-4 py-3 text-sm leading-6 text-[var(--text-secondary)]">
          {report.teaser}
        </div>
      </div>

      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
        <div className="inline-flex items-center gap-2 text-xs uppercase text-[var(--text-tertiary)]">
          <FileStack className="h-3.5 w-3.5" aria-hidden="true" />
          {report.verdictLabel}
        </div>
        <Link
          href={report.publicHref}
          className="inline-flex min-h-11 items-center gap-2 rounded-lg text-sm font-medium text-[var(--brand-primary)] transition-transform group-hover:translate-x-0.5"
        >
          View details
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </Link>
      </div>
    </article>
  );
}

export function getSampleReportEntry(slug: string) {
  return SAMPLE_REPORTS.find((entry) => entry.slug === slug) ?? null;
}
