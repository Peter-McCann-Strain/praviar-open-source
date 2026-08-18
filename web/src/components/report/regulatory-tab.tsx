"use client";

import { Database, Landmark, ShieldAlert } from "lucide-react";
import type {
  FTOReport,
  ParagraphIVEntry,
  PTEEntry,
  RegulatoryExclusivity,
  SourceHealthEntry,
} from "@praviar/shared-types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { sanitizeReportDiagnosticText } from "./report-diagnostic-copy";

interface RegulatoryTabProps {
  report: FTOReport;
}

type RegulatorySourceStatus = {
  error_message?: string | null;
  patent_count?: number | null;
  source: string;
  status: SourceHealthEntry["status"];
};

const REGULATORY_GRID_CLASS =
  "grid grid-cols-1 gap-x-4 gap-y-2 text-sm sm:grid-cols-[minmax(8rem,0.42fr)_minmax(0,1fr)]";
const REGULATORY_VALUE_CLASS = "min-w-0 font-medium [overflow-wrap:anywhere]";
const SOURCE_STATUS_COPY = {
  failed: "Failed",
  not_configured: "Not configured",
  ok: "Healthy",
  skipped: "Skipped",
} as const satisfies Record<RegulatorySourceStatus["status"], string>;

function getSourceStatusVariant(status: RegulatorySourceStatus["status"]) {
  if (status === "failed") return "destructive";
  if (status === "not_configured") return "warning";
  if (status === "ok") return "success";
  return "secondary";
}

function hasSourceIssue(statuses: RegulatorySourceStatus[]) {
  return statuses.some(
    (entry) => entry.status === "failed" || entry.status === "not_configured",
  );
}

function PurpleBookSection({ data }: { data: RegulatoryExclusivity }) {
  const entry = data.purple_book_entry;
  const expiry = data.bpcia_exclusivity_expiry;

  if (!entry && !expiry) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">FDA Purple Book (Biologics)</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {entry && (
          <dl className={REGULATORY_GRID_CLASS} data-testid="purple-book-grid">
            {entry.proprietary_name && (
              <>
                <dt className="text-[var(--text-tertiary)]">Brand name</dt>
                <dd className={REGULATORY_VALUE_CLASS}>
                  {entry.proprietary_name}
                </dd>
              </>
            )}
            {entry.proper_name && (
              <>
                <dt className="text-[var(--text-tertiary)]">
                  Proper name (INN)
                </dt>
                <dd className={REGULATORY_VALUE_CLASS}>{entry.proper_name}</dd>
              </>
            )}
            {entry.bla_number && (
              <>
                <dt className="text-[var(--text-tertiary)]">BLA number</dt>
                <dd className={REGULATORY_VALUE_CLASS}>{entry.bla_number}</dd>
              </>
            )}
            {entry.applicant && (
              <>
                <dt className="text-[var(--text-tertiary)]">Applicant</dt>
                <dd className={REGULATORY_VALUE_CLASS}>{entry.applicant}</dd>
              </>
            )}
            {entry.bla_type && (
              <>
                <dt className="text-[var(--text-tertiary)]">BLA type</dt>
                <dd className="min-w-0">
                  <Badge variant="outline">{entry.bla_type}</Badge>
                </dd>
              </>
            )}
            {entry.approval_date && (
              <>
                <dt className="text-[var(--text-tertiary)]">Approval date</dt>
                <dd className={REGULATORY_VALUE_CLASS}>
                  {entry.approval_date}
                </dd>
              </>
            )}
            {entry.marketing_status && (
              <>
                <dt className="text-[var(--text-tertiary)]">
                  Marketing status
                </dt>
                <dd className={REGULATORY_VALUE_CLASS}>
                  {entry.marketing_status}
                </dd>
              </>
            )}
            {entry.exclusivity_expiration && (
              <>
                <dt className="text-[var(--text-tertiary)]">
                  Exclusivity expiration
                </dt>
                <dd className={REGULATORY_VALUE_CLASS}>
                  {entry.exclusivity_expiration}
                </dd>
              </>
            )}
          </dl>
        )}
        {expiry && (
          <p className="text-sm">
            <span className="text-[var(--text-tertiary)]">
              BPCIA 12-year exclusivity expiry:{" "}
            </span>
            <span className="font-medium">{expiry}</span>
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function PTESection({ entries }: { entries: PTEEntry[] }) {
  if (entries.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          Patent Term Extensions ({entries.length})
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {entries.map((entry, i) => (
            <div
              key={`${entry.patent_number}-${i}`}
              className="border-b border-[var(--border-subtle)] py-3 text-sm last:border-b-0"
              data-testid="pte-entry"
            >
              <dl className={REGULATORY_GRID_CLASS}>
                <dt className="text-[var(--text-tertiary)]">Patent</dt>
                <dd className={`${REGULATORY_VALUE_CLASS} font-mono`}>
                  {entry.patent_number}
                </dd>
                {entry.product_name && (
                  <>
                    <dt className="text-[var(--text-tertiary)]">Product</dt>
                    <dd className="min-w-0 [overflow-wrap:anywhere]">
                      {entry.product_name}
                    </dd>
                  </>
                )}
                {entry.extension_days && (
                  <>
                    <dt className="text-[var(--text-tertiary)]">Extension</dt>
                    <dd className="min-w-0">{entry.extension_days} days</dd>
                  </>
                )}
                {entry.status && (
                  <>
                    <dt className="text-[var(--text-tertiary)]">Status</dt>
                    <dd className="min-w-0">
                      <Badge variant="outline">{entry.status}</Badge>
                    </dd>
                  </>
                )}
              </dl>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function ParagraphIVSection({ entries }: { entries: ParagraphIVEntry[] }) {
  if (entries.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          Paragraph IV Challenges ({entries.length})
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-3 text-xs text-[var(--text-tertiary)]">
          Active Paragraph IV ANDA certifications indicate this product&apos;s
          patents are being actively contested under the Hatch-Waxman Act, which
          materially elevates FTO risk.
        </p>
        <div className="space-y-3">
          {entries.map((entry, i) => (
            <div
              key={`${entry.drug_name}-${i}`}
              className="border-b border-[var(--border-subtle)] py-3 text-sm last:border-b-0"
              data-testid="paragraph-iv-entry"
            >
              <dl className={REGULATORY_GRID_CLASS}>
                <dt className="text-[var(--text-tertiary)]">Drug name</dt>
                <dd className={REGULATORY_VALUE_CLASS}>{entry.drug_name}</dd>
                {entry.nda_number && (
                  <>
                    <dt className="text-[var(--text-tertiary)]">NDA number</dt>
                    <dd className="min-w-0 font-mono [overflow-wrap:anywhere]">
                      {entry.nda_number}
                    </dd>
                  </>
                )}
                {entry.dosage_form && (
                  <>
                    <dt className="text-[var(--text-tertiary)]">Dosage form</dt>
                    <dd className="min-w-0 [overflow-wrap:anywhere]">
                      {entry.dosage_form}
                    </dd>
                  </>
                )}
                {entry.strength && (
                  <>
                    <dt className="text-[var(--text-tertiary)]">Strength</dt>
                    <dd className="min-w-0 [overflow-wrap:anywhere]">
                      {entry.strength}
                    </dd>
                  </>
                )}
                {entry.submission_count != null && (
                  <>
                    <dt className="text-[var(--text-tertiary)]">
                      ANDA submissions
                    </dt>
                    <dd className="min-w-0">{entry.submission_count}</dd>
                  </>
                )}
                {entry.first_filing_date && (
                  <>
                    <dt className="text-[var(--text-tertiary)]">
                      First filing
                    </dt>
                    <dd className="min-w-0">{entry.first_filing_date}</dd>
                  </>
                )}
                {entry.patent_expiry_date && (
                  <>
                    <dt className="text-[var(--text-tertiary)]">
                      Patent expiry
                    </dt>
                    <dd className="min-w-0">{entry.patent_expiry_date}</dd>
                  </>
                )}
                {entry.has_180_day_exclusivity != null && (
                  <>
                    <dt className="text-[var(--text-tertiary)]">
                      180-day exclusivity
                    </dt>
                    <dd className="min-w-0">
                      <Badge
                        variant={
                          entry.has_180_day_exclusivity
                            ? "secondary"
                            : "outline"
                        }
                      >
                        {entry.has_180_day_exclusivity ? "Yes" : "No"}
                      </Badge>
                    </dd>
                  </>
                )}
              </dl>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function SourceHealthSection({
  statuses,
}: {
  statuses: RegulatorySourceStatus[];
}) {
  if (statuses.length === 0) return null;

  const sourceIssue = hasSourceIssue(statuses);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Regulatory Source Health</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {sourceIssue ? (
          <p className="text-sm text-[var(--text-secondary)]">
            At least one regulatory enrichment source did not complete. Treat
            the result as incomplete until the source status is resolved.
          </p>
        ) : null}
        <div className="space-y-2">
          {statuses.map((entry) => (
            <div
              key={entry.source}
              className="grid gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/70 p-3 text-sm sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start"
              data-testid="regulatory-source-health-row"
            >
              <div className="min-w-0">
                <p className="font-medium text-[var(--text-primary)] [overflow-wrap:anywhere]">
                  {entry.source}
                </p>
                {entry.error_message ? (
                  <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                    {sanitizeReportDiagnosticText(
                      entry.error_message,
                      "Source did not complete; diagnostic details are available to support.",
                    )}
                  </p>
                ) : entry.patent_count != null ? (
                  <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
                    {entry.patent_count.toLocaleString()} patent records checked
                  </p>
                ) : null}
              </div>
              <Badge variant={getSourceStatusVariant(entry.status)}>
                {SOURCE_STATUS_COPY[entry.status]}
              </Badge>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function DataSourcesSection({ sources }: { sources: string[] }) {
  if (sources.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Data Sources Queried</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="list-inside list-disc space-y-1 text-sm text-[var(--text-secondary)]">
          {sources.map((src) => (
            <li key={src}>{src}</li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

export function RegulatoryTab({ report }: RegulatoryTabProps) {
  const data = report.regulatory_exclusivity;

  if (!data) {
    return (
      <Card className="overflow-hidden border-warning/25">
        <CardHeader className="border-b border-[var(--border-subtle)] bg-warning/5 p-4 sm:p-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex min-w-0 items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-warning/25 bg-warning/10 text-warning">
                <Landmark className="h-5 w-5" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-warning">
                  Regulatory boundary
                </p>
                <CardTitle className="mt-1 text-lg">
                  Exclusivity posture has not been enriched
                </CardTitle>
              </div>
            </div>
            <Badge variant="warning">Not assessed</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-5 p-4 sm:p-6">
          <p className="max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
            No Purple Book, patent-term-extension, or Paragraph IV record is
            attached to this report. This is an evidence gap—not a clean
            exclusivity result.
          </p>
          <dl className="grid gap-3 sm:grid-cols-3">
            <RegulatoryGapFact
              icon={Database}
              label="Attached records"
              value="None"
            />
            <RegulatoryGapFact
              icon={ShieldAlert}
              label="Decision effect"
              value="Exclusivity remains unknown"
            />
            <RegulatoryGapFact
              icon={Landmark}
              label="Required next step"
              value="Verify official registers"
            />
          </dl>
          <p className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-3 text-xs leading-5 text-[var(--text-secondary)]">
            Confirm the relevant FDA and patent-office records before treating
            patent clearance as commercial launch clearance.
          </p>
        </CardContent>
      </Card>
    );
  }

  const pteEntries = data.pte_extensions ?? [];
  const paragraphIVEntries = data.paragraph_iv_challenges ?? [];
  const sources = data.data_sources_queried ?? [];
  const sourceStatuses: RegulatorySourceStatus[] = (
    data.source_statuses ?? []
  ).map((entry) => ({
    error_message: entry.error_message ?? null,
    patent_count: entry.patent_count ?? null,
    source: entry.source,
    status: entry.status,
  }));
  const sourceIssue = hasSourceIssue(sourceStatuses);

  return (
    <div className="space-y-6">
      <PurpleBookSection data={data} />
      <PTESection entries={pteEntries} />
      <ParagraphIVSection entries={paragraphIVEntries} />
      <SourceHealthSection statuses={sourceStatuses} />
      <DataSourcesSection sources={sources} />

      {!data.purple_book_entry &&
        pteEntries.length === 0 &&
        paragraphIVEntries.length === 0 && (
          <Card>
            <CardContent className="p-8 text-center">
              <p className="text-[var(--text-tertiary)]">
                {sourceIssue
                  ? "Regulatory enrichment did not complete for every configured source. Review source status before treating this as a clean no-hit result."
                  : "Regulatory sources were queried but returned no matching entries for this compound."}
              </p>
            </CardContent>
          </Card>
        )}
    </div>
  );
}

function RegulatoryGapFact({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Landmark;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-card)] p-3">
      <Icon className="h-4 w-4 text-brand-primary" aria-hidden="true" />
      <dt className="mt-3 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        {label}
      </dt>
      <dd className="mt-1 text-sm font-semibold leading-5 text-[var(--text-primary)]">
        {value}
      </dd>
    </div>
  );
}
