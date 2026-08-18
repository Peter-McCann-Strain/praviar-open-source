import {
  ClipboardCheck,
  Building2,
  Database,
  Layers3,
  Link2,
  MapPinned,
  ShieldAlert,
  TimerReset,
  type LucideIcon,
} from "lucide-react";
import type { PatentItem } from "@/hooks/use-patents";
import {
  extractJurisdiction,
  getPatentExpirySignal,
  normalizeRiskLevel,
} from "./helpers";

interface PatentsPageSummaryProps {
  patents: PatentItem[];
  total: number;
  canViewRisk?: boolean;
}

export function PatentsPageSummary({
  patents,
  total,
  canViewRisk = false,
}: PatentsPageSummaryProps) {
  const visibleRecords = patents.length;
  const visibleHighRisk = canViewRisk
    ? patents.filter(
        (patent) => normalizeRiskLevel(patent.risk_level) === "high",
      ).length
    : 0;
  const expiringSoon = patents.filter(
    (patent) => getPatentExpirySignal(patent.expiry_date).tone === "soon",
  ).length;
  const visibleCompounds = new Set(
    patents.map((patent) => patent.compound_name).filter(Boolean),
  ).size;
  const visibleAssignees = new Set(
    patents.map((patent) => patent.assignee).filter(Boolean),
  ).size;
  const jurisdictions = Array.from(
    new Set(
      patents
        .map((patent) => extractJurisdiction(patent.patent_number))
        .filter((jurisdiction) => jurisdiction !== "\u2014"),
    ),
  );
  const cpcIndexed = patents.filter((patent) =>
    patent.cpc_codes.some(Boolean),
  ).length;
  const termSignals = patents.filter(
    (patent) => getPatentExpirySignal(patent.expiry_date).tone !== "unknown",
  ).length;
  const reportLinks = patents.filter((patent) => patent.analysis_id).length;
  const readyLabel =
    visibleRecords === 0
      ? "No visible page"
      : cpcIndexed === visibleRecords &&
          termSignals === visibleRecords &&
          reportLinks === visibleRecords
        ? "Ready for review"
        : "Partial metadata";

  return (
    <section aria-label="Patent evidence summary" className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <PatentSummaryMetric
          icon={Database}
          label="Matching records"
          value={total.toLocaleString()}
          detail="Server-filtered result set"
        />
        {canViewRisk ? (
          <PatentSummaryMetric
            icon={ShieldAlert}
            label="Visible high risk"
            value={visibleHighRisk.toLocaleString()}
            detail="On this page"
            tone={visibleHighRisk > 0 ? "risk" : "neutral"}
          />
        ) : (
          <PatentSummaryMetric
            icon={Building2}
            label="Visible assignees"
            value={visibleAssignees.toLocaleString()}
            detail="Organizations on this page"
          />
        )}
        <PatentSummaryMetric
          icon={TimerReset}
          label="Expiring <2y"
          value={expiringSoon.toLocaleString()}
          detail="Visible term signals"
          tone={expiringSoon > 0 ? "warning" : "neutral"}
        />
        <PatentSummaryMetric
          icon={visibleCompounds > 1 ? Layers3 : MapPinned}
          label={visibleCompounds > 1 ? "Visible compounds" : "Jurisdictions"}
          value={
            visibleCompounds > 1
              ? visibleCompounds.toLocaleString()
              : jurisdictions.slice(0, 3).join(", ") || "\u2014"
          }
          detail={
            visibleCompounds > 1
              ? "Compounds represented on page"
              : "Recognized patent prefixes"
          }
        />
      </div>

      <div className="overflow-hidden rounded-lg border border-brand-primary/20 bg-[var(--bg-surface)] shadow-[var(--shadow-xs)]">
        <div className="grid gap-0 min-[1440px]:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)]">
          <div className="border-b border-[var(--border-subtle)] bg-brand-primary/5 p-4 min-[1440px]:border-b-0 min-[1440px]:border-r">
            <div className="flex min-w-0 items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-brand-primary/25 bg-brand-primary/10 text-brand-primary">
                <ClipboardCheck className="h-4 w-4" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  Evidence readiness
                </p>
                <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                  {readyLabel}. Indicators describe the current visible page;
                  {canViewRisk
                    ? " legal risk and source completeness remain separate checks."
                    : " counsel-governed risk remains available through attorney review."}
                </p>
              </div>
            </div>
          </div>
          <div className="grid gap-3 p-4 sm:grid-cols-3">
            <ReadinessMetric
              label="CPC indexed"
              value={`${cpcIndexed}/${visibleRecords}`}
            />
            <ReadinessMetric
              label="Term signals"
              value={`${termSignals}/${visibleRecords}`}
            />
            <ReadinessMetric
              icon={Link2}
              label="Report handoff"
              value={`${reportLinks}/${visibleRecords}`}
            />
          </div>
        </div>
      </div>
    </section>
  );
}

function ReadinessMetric({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon?: LucideIcon;
}) {
  return (
    <div className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)]/45 px-3 py-2">
      <span className="flex min-w-0 items-center gap-2 text-xs font-semibold uppercase text-[var(--text-tertiary)]">
        {Icon ? <Icon className="h-3 w-3 shrink-0" aria-hidden="true" /> : null}
        <span className="min-w-0 leading-4 [overflow-wrap:anywhere]">
          {label}
        </span>
      </span>
      <span className="mt-1 block text-sm font-semibold tabular-nums text-[var(--text-primary)]">
        {value}
      </span>
    </div>
  );
}

function PatentSummaryMetric({
  icon: Icon,
  label,
  value,
  detail,
  tone = "neutral",
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  detail: string;
  tone?: "neutral" | "risk" | "warning";
}) {
  const iconClass =
    tone === "risk"
      ? "bg-error/10 text-error border-error/20"
      : tone === "warning"
        ? "bg-warning/10 text-warning border-warning/20"
        : "bg-brand-primary/10 text-[var(--brand-primary)] border-brand-primary/20";

  return (
    <div className="praviar-surface-premium flex min-w-0 items-start gap-3 rounded-lg border border-[var(--card-border)] p-4">
      <span
        className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-md border ${iconClass}`}
      >
        <Icon className="h-4 w-4" aria-hidden="true" />
      </span>
      <span className="min-w-0">
        <span className="block text-xs font-semibold uppercase text-[var(--text-tertiary)]">
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
