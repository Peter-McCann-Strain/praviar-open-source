import type { ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  ExternalLink,
  FileSearch,
  Fingerprint,
  ListChecks,
} from "lucide-react";
import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import { RiskBadge } from "@/components/shared/risk-badge";
import { cn } from "@/lib/utils";
import type { RiskLevel } from "@praviar/shared-types";

export interface DossierMetric {
  label: string;
  value: string;
}

export interface DossierRiskDriver {
  label: string;
  reference: string;
  detail: string;
  severity?: RiskLevel;
}

export interface DossierEvidenceRow {
  reference: string;
  assignee?: string;
  claimReference?: string;
  expiry?: string;
  rationale: string;
  risk: RiskLevel;
  sourceLabel?: string;
  sourceUrl?: string;
}

export interface DossierClaimPreview {
  title: string;
  reference: string;
  text: string;
  rationale: string;
}

interface DossierNotice {
  title: string;
  body: string;
  tone?: "info" | "warning";
}

interface FtoDossierPreviewProps {
  compoundName: string;
  risk: RiskLevel;
  summary: string;
  metrics: DossierMetric[];
  riskDrivers?: DossierRiskDriver[];
  evidenceRows?: DossierEvidenceRow[];
  claimPreview?: DossierClaimPreview;
  visual?: ReactNode;
  eyebrow?: string;
  scopeLabel?: string;
  evidenceLabel?: string;
  statusLabel?: string;
  notice?: DossierNotice;
  provenanceItems?: string[];
  emptyEvidenceMessage?: string;
  compact?: boolean;
  compactItemLimit?: number;
  mobileSummaryOnly?: boolean;
  mobileVisualHidden?: boolean;
  riskLabelOverrides?: Partial<Record<string, string>>;
  className?: string;
}

export function FtoDossierPreview({
  compoundName,
  risk,
  summary,
  metrics,
  riskDrivers = [],
  evidenceRows = [],
  claimPreview,
  visual,
  eyebrow = "FTO dossier",
  scopeLabel = "US patent landscape",
  evidenceLabel,
  statusLabel = "Read-only preview",
  notice,
  provenanceItems = [],
  emptyEvidenceMessage = "Evidence rows were not included in this preview.",
  compact = false,
  compactItemLimit = 2,
  mobileSummaryOnly = false,
  mobileVisualHidden = false,
  riskLabelOverrides,
  className,
}: FtoDossierPreviewProps) {
  const resolvedCompactItemLimit = Math.max(1, compactItemLimit);
  const visibleDrivers = compact
    ? riskDrivers.slice(0, resolvedCompactItemLimit)
    : riskDrivers;
  const visibleRows = compact
    ? evidenceRows.slice(0, resolvedCompactItemLimit)
    : evidenceRows;
  const leadEvidenceRow = compact ? visibleRows[0] : undefined;
  const displayedSummary = compact
    ? truncateDossierText(summary, 220)
    : summary;
  const resolvedEvidenceLabel =
    evidenceLabel ??
    `${evidenceRows.length.toLocaleString()} evidence ${
      evidenceRows.length === 1 ? "record" : "records"
    }`;

  return (
    <article
      aria-label={`${compoundName} FTO dossier preview`}
      className={cn(
        "light praviar-evidence-paper overflow-hidden rounded-lg border border-[var(--border-default)] shadow-[var(--shadow-md)]",
        className,
      )}
      data-praviar-visual="fto-dossier"
      data-testid="fto-dossier-preview"
    >
      <div className="praviar-glass-strip border-b border-[var(--border-default)] px-4 py-3 sm:px-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 gap-3">
            <PraviarMarkFrame size="sm" />
            <div className="min-w-0">
              <p className="type-marketing-label">{eyebrow}</p>
              <h2 className="mt-1 break-words text-2xl font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
                {compoundName}
              </h2>
              <div className="mt-2 flex flex-wrap gap-x-2 gap-y-1 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                <span className="min-w-0 break-words [overflow-wrap:anywhere]">
                  {scopeLabel}
                </span>
                <span className="inline-flex min-w-0 items-baseline gap-2">
                  <span aria-hidden="true" className="shrink-0">
                    /
                  </span>
                  <span className="min-w-0 break-words [overflow-wrap:anywhere]">
                    {resolvedEvidenceLabel}
                  </span>
                </span>
              </div>
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end">
            <RiskBadge
              risk={risk}
              showIcon
              label={getRiskLabel(risk, riskLabelOverrides)}
            />
            <span className="praviar-glass-pill max-w-full break-words rounded-md px-3 py-1 text-center text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)] [overflow-wrap:anywhere]">
              {statusLabel}
            </span>
          </div>
        </div>
      </div>

      <div
        className={cn(
          "grid gap-0",
          !compact && "lg:grid-cols-[minmax(18rem,0.74fr)_1.26fr]",
        )}
      >
        <div
          className={cn(
            "praviar-glass-strip border-b border-[var(--border-default)] p-4 sm:p-5",
            !compact && "lg:border-b-0 lg:border-r",
          )}
        >
          {leadEvidenceRow ? (
            <div
              className="praviar-glass-chip mb-4 rounded-lg border-l-[3px] border-l-[var(--brand-primary)] p-3 md:hidden"
              data-testid="fto-dossier-lead-evidence"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                    Lead evidence
                  </p>
                  <p className="mt-1 break-all font-mono text-sm font-semibold text-[var(--text-primary)]">
                    {leadEvidenceRow.reference}
                  </p>
                </div>
                <RiskBadge
                  risk={leadEvidenceRow.risk}
                  size="md"
                  label={getRiskLabel(leadEvidenceRow.risk, riskLabelOverrides)}
                  className="shrink-0"
                />
              </div>
              <p className="mt-2 break-words text-xs font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
                {leadEvidenceRow.claimReference ??
                  leadEvidenceRow.assignee ??
                  "Claim relevance"}
              </p>
              <p
                className={cn(
                  "mt-1 break-words text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]",
                  mobileSummaryOnly && "line-clamp-4 md:line-clamp-none",
                )}
              >
                {leadEvidenceRow.rationale}
              </p>
            </div>
          ) : null}

          {visual ? (
            <div
              className={cn(
                "mb-5 overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]",
                mobileVisualHidden && "hidden md:block",
              )}
              data-testid="fto-dossier-visual"
            >
              {visual}
            </div>
          ) : null}

          <div
            className={cn(
              "grid gap-3 sm:grid-cols-3 sm:gap-2",
              mobileSummaryOnly ? "grid-cols-2" : "grid-cols-1",
            )}
            data-testid="fto-dossier-metrics"
          >
            {metrics.map((metric, index) => (
              <div
                key={metric.label}
                className={cn(
                  "min-w-0 border-l border-[var(--border-default)] pl-3 first:border-l-0 first:pl-0",
                  mobileSummaryOnly &&
                    index === metrics.length - 1 &&
                    metrics.length % 2 === 1 &&
                    "col-span-2 border-l-0 pl-0 sm:col-span-1 sm:border-l sm:pl-3",
                )}
              >
                <p className="break-words text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
                  {metric.label}
                </p>
                <p className="mt-1 break-words text-base font-semibold leading-tight text-[var(--text-primary)] [overflow-wrap:anywhere] sm:text-lg">
                  {metric.value}
                </p>
              </div>
            ))}
          </div>

          <p
            className={cn(
              "mt-5 break-words text-sm leading-7 text-[var(--text-secondary)] [overflow-wrap:anywhere]",
              mobileSummaryOnly && "line-clamp-4 md:line-clamp-none",
            )}
          >
            {displayedSummary}
          </p>

          {notice ? (
            <div
              className={cn(
                "mt-5 flex gap-3 rounded-lg border p-3 text-sm leading-6",
                notice.tone === "warning"
                  ? "border-warning/25 bg-warning/10 text-[var(--text-primary)]"
                  : "border-info/25 bg-info/10 text-[var(--text-primary)]",
              )}
            >
              <AlertTriangle
                className={cn(
                  "mt-0.5 h-4 w-4 shrink-0",
                  notice.tone === "warning" ? "text-warning" : "text-info",
                )}
                aria-hidden="true"
              />
              <div>
                <p className="break-words font-semibold [overflow-wrap:anywhere]">
                  {notice.title}
                </p>
                <p className="mt-1 break-words text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                  {notice.body}
                </p>
              </div>
            </div>
          ) : null}
        </div>

        <div
          data-testid="fto-dossier-detail"
          className={cn(
            "praviar-glass-strip divide-y divide-[var(--border-default)]",
            mobileSummaryOnly && "hidden md:block",
          )}
        >
          <DossierSection
            icon={<ListChecks className="h-4 w-4" aria-hidden="true" />}
            title="Risk drivers"
          >
            {visibleDrivers.length > 0 ? (
              <ol className="divide-y divide-[var(--border-subtle)]">
                {visibleDrivers.map((driver) => (
                  <li
                    key={`${driver.reference}-${driver.label}`}
                    className="grid min-w-0 gap-2 py-3 first:pt-0 last:pb-0 sm:grid-cols-[minmax(0,8rem)_minmax(0,1fr)]"
                  >
                    <div className="min-w-0">
                      <p className="break-words text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
                        {driver.label}
                      </p>
                      <p className="mt-1 break-all font-mono text-xs text-[var(--text-primary)]">
                        {driver.reference}
                      </p>
                    </div>
                    <div className="min-w-0 space-y-2">
                      <p className="break-words text-sm leading-6 text-[var(--text-primary)] [overflow-wrap:anywhere]">
                        {compact
                          ? truncateDossierText(driver.detail, 140)
                          : driver.detail}
                      </p>
                      {driver.severity ? (
                        <RiskBadge
                          risk={driver.severity}
                          size="md"
                          label={getRiskLabel(
                            driver.severity,
                            riskLabelOverrides,
                          )}
                        />
                      ) : null}
                    </div>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-sm leading-6 text-[var(--text-secondary)]">
                No ranked risk drivers were included in this preview.
              </p>
            )}
          </DossierSection>

          <DossierSection
            icon={<FileSearch className="h-4 w-4" aria-hidden="true" />}
            title="Evidence rows"
          >
            {visibleRows.length > 0 ? (
              <ul className="divide-y divide-[var(--border-subtle)]">
                {visibleRows.map((row) => {
                  const isInternalSourceUrl =
                    row.sourceUrl?.startsWith("#") ?? false;
                  const SourceIcon = isInternalSourceUrl
                    ? ArrowRight
                    : ExternalLink;

                  return (
                    <li
                      key={`${row.reference}-${row.claimReference ?? row.assignee ?? row.rationale}`}
                      className="grid min-w-0 gap-3 py-3 first:pt-0 last:pb-0 md:grid-cols-[minmax(0,8rem)_minmax(8rem,0.75fr)_minmax(0,1fr)_auto] md:items-start"
                    >
                      <div className="min-w-0">
                        <p className="break-all font-mono text-sm font-semibold text-[var(--text-primary)]">
                          {row.reference}
                        </p>
                        {row.expiry ? (
                          <p className="mt-1 break-words text-xs uppercase tracking-[0.12em] text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
                            Exp. {row.expiry}
                          </p>
                        ) : null}
                        {row.sourceUrl ? (
                          <a
                            href={row.sourceUrl}
                            target={isInternalSourceUrl ? undefined : "_blank"}
                            rel={isInternalSourceUrl ? undefined : "noreferrer"}
                            className="mt-2 inline-flex min-h-11 max-w-full items-center gap-1 rounded-md border border-brand-primary/20 bg-brand-primary/8 px-2 py-1 text-left text-xs font-semibold text-brand-primary transition-colors hover:border-brand-primary/40 hover:bg-brand-primary/12"
                            aria-label={`${isInternalSourceUrl ? "Inspect" : "Open"} source record for ${row.reference}`}
                          >
                            <SourceIcon
                              className="h-3 w-3 shrink-0"
                              aria-hidden="true"
                            />
                            <span className="min-w-0 break-words [overflow-wrap:anywhere]">
                              {row.sourceLabel ?? "Source record"}
                            </span>
                          </a>
                        ) : row.sourceLabel ? (
                          <p className="mt-2 inline-flex max-w-full rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-2 py-1 text-xs font-semibold text-[var(--text-secondary)]">
                            <span className="min-w-0 break-words [overflow-wrap:anywhere]">
                              {row.sourceLabel}
                            </span>
                          </p>
                        ) : null}
                      </div>
                      <div className="min-w-0 break-words text-sm leading-6 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                        <p className="font-medium text-[var(--text-primary)]">
                          {row.assignee ?? "Assignee pending"}
                        </p>
                        <p>{row.claimReference ?? "Claim relevance"}</p>
                      </div>
                      <p className="min-w-0 break-words text-sm leading-6 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                        {compact
                          ? truncateDossierText(row.rationale, 110)
                          : row.rationale}
                      </p>
                      <RiskBadge
                        risk={row.risk}
                        size="md"
                        label={getRiskLabel(row.risk, riskLabelOverrides)}
                        className="w-fit"
                      />
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="text-sm leading-6 text-[var(--text-secondary)]">
                {emptyEvidenceMessage}
              </p>
            )}
          </DossierSection>

          {claimPreview && !compact ? (
            <DossierSection
              icon={<Fingerprint className="h-4 w-4" aria-hidden="true" />}
              title="Claim preview"
            >
              <div className="space-y-3">
                <div>
                  <p className="break-all font-mono text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                    {claimPreview.reference}
                  </p>
                  <h3 className="mt-1 break-words text-base font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
                    {claimPreview.title}
                  </h3>
                </div>
                <blockquote className="break-words border-l-2 border-[var(--border-emphasis)] pl-3 text-sm leading-6 text-[var(--text-primary)] [overflow-wrap:anywhere]">
                  {compact
                    ? truncateDossierText(claimPreview.text, 180)
                    : claimPreview.text}
                </blockquote>
                <p className="break-words text-sm leading-6 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                  {compact
                    ? truncateDossierText(claimPreview.rationale, 200)
                    : claimPreview.rationale}
                </p>
              </div>
            </DossierSection>
          ) : null}

          {provenanceItems.length > 0 ? (
            <div className="flex flex-wrap gap-2 px-4 py-3 sm:px-5">
              {provenanceItems.map((item) => (
                <span
                  key={item}
                  className="max-w-full break-words rounded-md bg-[var(--surface-muted)] px-3 py-1 text-xs font-medium text-[var(--text-tertiary)] [overflow-wrap:anywhere]"
                >
                  {item}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </article>
  );
}

function getRiskLabel(
  risk: RiskLevel,
  overrides: Partial<Record<string, string>> | undefined,
): string {
  return overrides?.[risk.toLowerCase()] ?? risk.toUpperCase();
}

function truncateDossierText(value: string, maxLength: number) {
  if (value.length <= maxLength) return value;

  const trimmed = value
    .slice(0, maxLength)
    .replace(/\s+\S*$/, "")
    .trim();
  return `${trimmed}...`;
}

function DossierSection({
  icon,
  title,
  children,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="px-4 py-3.5 sm:px-5">
      <div className="mb-3 flex min-w-0 items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
        {icon}
        <h3 className="min-w-0 break-words [overflow-wrap:anywhere]">
          {title}
        </h3>
      </div>
      {children}
    </section>
  );
}
