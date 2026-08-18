import {
  CalendarClock,
  CheckCircle2,
  Database,
  ExternalLink,
  FileSearch,
  RotateCcw,
  ShieldCheck,
  Tags,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import type { CompoundItem } from "@/hooks/use-compounds";
import {
  getCompoundIdentityReadiness,
  getLatestCompoundDate,
  getVisibleFunctionalGroupCount,
} from "@/components/compounds/helpers";

interface CompoundsPageSummaryProps {
  compounds: CompoundItem[];
  total: number;
}

export function CompoundsPageSummary({
  compounds,
  total,
}: CompoundsPageSummaryProps) {
  const visibleAnalysisCount = compounds.reduce(
    (sum, compound) => sum + compound.analysis_count,
    0,
  );
  const readiness = getCompoundIdentityReadiness(compounds);
  const functionalGroupCount = getVisibleFunctionalGroupCount(compounds);
  const latestDate = getLatestCompoundDate(compounds);

  return (
    <section aria-label="Compound library summary" className="space-y-3">
      <div className="praviar-surface-premium overflow-hidden rounded-lg border border-[var(--card-border)]">
        <div className="flex flex-col gap-1 border-b border-[var(--border-subtle)] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">
              Identity readiness
            </h2>
            <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
              Visible-record field completeness for diligence prep, not an FTO
              clearance signal.
            </p>
          </div>
          <span className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-disabled)]">
            Workspace scoped
          </span>
        </div>
        <div
          aria-label="Visible compound identity readiness"
          className="grid divide-y divide-[var(--border-subtle)] sm:grid-cols-2 sm:divide-x sm:divide-y-0 xl:grid-cols-4"
        >
          <CompoundReadinessItem
            icon={CheckCircle2}
            label="Core identity complete"
            value={readiness.completeIdentityCount}
            detail="SMILES, InChI Key, formula, and MW present"
          />
          <CompoundReadinessItem
            icon={ExternalLink}
            label="PubChem linked"
            value={readiness.pubchemLinkedCount}
            detail="External reference available"
          />
          <CompoundReadinessItem
            icon={RotateCcw}
            label="Repeat analyses"
            value={readiness.repeatAnalysisCount}
            detail="More than one workspace run"
          />
          <CompoundReadinessItem
            icon={TriangleAlert}
            label="Needs enrichment"
            value={readiness.enrichmentGapCount}
            detail="Missing at least one indexed field"
          />
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <CompoundSummaryMetric
          icon={Database}
          label="Matching records"
          value={total.toLocaleString()}
          detail="Workspace records matching filters"
        />
        <CompoundSummaryMetric
          icon={FileSearch}
          label="Visible analyses"
          value={visibleAnalysisCount.toLocaleString()}
          detail="FTO runs represented on this page"
        />
        <CompoundSummaryMetric
          icon={functionalGroupCount > 0 ? Tags : ShieldCheck}
          label="Functional groups"
          value={functionalGroupCount.toLocaleString()}
          detail={
            functionalGroupCount > 0
              ? "Unique groups on this page"
              : "No indexed groups on this page"
          }
        />
        <CompoundSummaryMetric
          icon={CalendarClock}
          label="Newest on this page"
          value={latestDate}
          detail="UTC-normalized library date"
        />
      </div>
    </section>
  );
}

function CompoundReadinessItem({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: LucideIcon;
  label: string;
  value: number;
  detail: string;
}) {
  return (
    <div className="flex min-w-0 items-start gap-3 px-4 py-3">
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
        <Icon className="h-4 w-4" aria-hidden="true" />
      </span>
      <span className="min-w-0">
        <span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
          {label}
        </span>
        <span className="mt-0.5 block text-lg font-semibold leading-tight tabular-nums text-[var(--text-primary)]">
          {value.toLocaleString()}
        </span>
        <span className="mt-0.5 block text-xs leading-5 text-[var(--text-secondary)]">
          {detail}
        </span>
      </span>
    </div>
  );
}

function CompoundSummaryMetric({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="praviar-surface-premium flex min-w-0 items-start gap-3 rounded-lg border border-[var(--card-border)] p-4">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-brand-primary/20 bg-brand-primary/10 text-[var(--brand-primary)]">
        <Icon className="h-4 w-4" aria-hidden="true" />
      </span>
      <span className="min-w-0">
        <span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
          {label}
        </span>
        <span className="mt-1 block break-words text-xl font-semibold leading-tight text-[var(--text-primary)]">
          {value}
        </span>
        <span className="mt-1 block text-xs leading-5 text-[var(--text-secondary)]">
          {detail}
        </span>
      </span>
    </div>
  );
}
