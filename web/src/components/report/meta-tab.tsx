"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Database,
  ShieldCheck,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TimingWaterfall } from "@/components/charts/timing-waterfall";
import { UsageChart } from "@/components/charts/usage-chart";
import { ReportMobileDisclosure } from "@/components/report/report-mobile-disclosure";
import { isHealthySourceStatus } from "@/components/report-page/report-reliance-readiness";
import type { FTOReport } from "@praviar/shared-types";
import {
  getMetaTimingData,
  getMetaUsageData,
  getMetaVerificationFlags,
} from "./meta-tab-helpers";
import {
  AnalysisFailuresCard,
  DataLimitationsCard,
  DisclaimerCard,
  ModelsUsedCard,
  ReportMetadataFooter,
  ReviewIssuesCard,
  TokenUsageSummaryCard,
  VerificationCard,
} from "./meta-tab-sections";

interface MetaTabProps {
  report: FTOReport;
}

export function MetaTab({ report }: MetaTabProps) {
  const timingData = getMetaTimingData(report);
  const usageData = getMetaUsageData(report);
  const verificationFlags = getMetaVerificationFlags(report);
  const modelEntries = Object.entries(report.llm_models_used ?? {});
  const analysisFailures = report.analysis_failures ?? [];
  const dataLimitations = report.data_limitations ?? [];
  const reviewIssues = report.review_issues ?? [];
  const decisionAudit = report.clearance_decision?.decision_audit;
  const sourceEntries = report.source_health?.entries ?? [];
  const healthySourceCount = sourceEntries.filter((entry) =>
    isHealthySourceStatus(entry.status),
  ).length;
  const factualAccuracy = formatFactualAccuracy(report.factual_accuracy_rate);
  const syntheticEvidence = hasSyntheticFixtureEvidence(report);

  return (
    <div className="space-y-6">
      <Card className="overflow-hidden border-[var(--border-emphasis)]">
        <CardHeader className="border-b border-[var(--border-subtle)] bg-[var(--surface-muted)]/45 p-4 sm:p-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-primary">
                Quality and provenance
              </p>
              <CardTitle className="mt-1 text-lg">
                Verification record at a glance
              </CardTitle>
            </div>
            <Badge variant={syntheticEvidence ? "warning" : "secondary"}>
              {syntheticEvidence
                ? "Synthetic evidence fixture"
                : "No synthetic marker detected"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 p-4 sm:p-6">
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <QualityMetric
              icon={<ShieldCheck className="h-4 w-4" aria-hidden="true" />}
              label="Factual accuracy"
              value={factualAccuracy ?? "Not reported"}
            />
            <QualityMetric
              icon={<Database className="h-4 w-4" aria-hidden="true" />}
              label="Source health"
              value={
                sourceEntries.length > 0
                  ? `${healthySourceCount}/${sourceEntries.length} healthy`
                  : "Not reported"
              }
            />
            <QualityMetric
              className="col-span-2 sm:col-span-1"
              icon={
                syntheticEvidence ? (
                  <AlertTriangle className="h-4 w-4" aria-hidden="true" />
                ) : (
                  <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                )
              }
              label="Evidence origin"
              value={
                syntheticEvidence ? "Development fixture" : "No fixture marker"
              }
            />
          </dl>
          <p className="text-xs leading-5 text-[var(--text-secondary)]">
            Factual accuracy is the report-level verifier rate for statements
            checked. It is distinct from claim-mapping confidence, does not
            measure omissions, and is not a legal-accuracy score.
          </p>
          {syntheticEvidence ? (
            <p className="rounded-md border border-warning/25 bg-warning/10 p-3 text-xs leading-5 text-warning">
              Synthetic fixture evidence proves persisted API, database, and UI
              wiring only. It is not production-corpus, counsel-validation, or
              buyer-validation evidence.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <ReportMobileDisclosure
        label="Inspect failures and limitations"
        description={`${reviewIssues.length} critic issues, ${analysisFailures.length} analysis failures, and ${dataLimitations.length} recorded limitations.`}
      >
        <div className="space-y-6">
          <ReviewIssuesCard reviewIssues={reviewIssues} />
          <AnalysisFailuresCard
            analysisFailures={analysisFailures}
            auditFailureCount={decisionAudit?.analysis_failures_count}
            coverageFailureCount={
              decisionAudit?.coverage_summary?.failed_analysis_patent_ids
                ?.length
            }
            evidenceSufficientForClearance={
              decisionAudit?.evidence_sufficient_for_clearance
            }
          />
          <DataLimitationsCard
            dataLimitations={dataLimitations}
            syntheticEvidence={syntheticEvidence}
          />
        </div>
      </ReportMobileDisclosure>

      <ReportMobileDisclosure
        label="Inspect timing and analysis effort"
        description="Open stage timing and evidence-context versus review-output charts."
      >
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">
                Report Preparation Timing
              </CardTitle>
            </CardHeader>
            <CardContent>
              {timingData.length > 0 ? (
                <TimingWaterfall data={timingData} height={280} />
              ) : (
                <TelemetryUnavailable label="Preparation timing was not recorded in this report payload." />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">
                Analysis Effort by Stage
              </CardTitle>
            </CardHeader>
            <CardContent>
              {usageData.length > 0 ? (
                <UsageChart
                  ariaLabel="Analysis effort chart"
                  data={usageData}
                  emptyDescription="Analysis effort appears after report preparation."
                  emptyTitle="No analysis effort data"
                  height={280}
                  inputLabel="Evidence Context"
                  outputLabel="Review Output"
                />
              ) : (
                <TelemetryUnavailable label="Stage-level analysis effort was not recorded in this report payload." />
              )}
            </CardContent>
          </Card>
        </div>
      </ReportMobileDisclosure>

      <ReportMobileDisclosure
        label="Inspect technical provenance"
        description="Open model usage, verification checks, report metadata, and disclaimer."
      >
        <div className="space-y-6">
          <TokenUsageSummaryCard
            totalInputTokens={report.total_input_tokens}
            totalOutputTokens={report.total_output_tokens}
          />
          <ModelsUsedCard modelEntries={modelEntries} />
          <VerificationCard
            verification={report.verification}
            verificationFlags={verificationFlags}
          />
          <ReportMetadataFooter
            reportId={report.report_id}
            praviarPipelineVersion={report.praviar_pipeline_version}
            generatedAt={report.generated_at}
          />
          <DisclaimerCard disclaimer={report.disclaimer} />
        </div>
      </ReportMobileDisclosure>
    </div>
  );
}

function TelemetryUnavailable({ label }: { label: string }) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-4">
      <p className="text-sm font-semibold text-[var(--text-primary)]">
        Telemetry not reported
      </p>
      <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
        {label} This does not change the report findings.
      </p>
    </div>
  );
}

function QualityMetric({
  className,
  icon,
  label,
  value,
}: {
  className?: string;
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div
      className={`rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/45 p-3 ${className ?? ""}`}
    >
      <dt className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
        {icon}
        {label}
      </dt>
      <dd className="mt-2 text-base font-semibold text-[var(--text-primary)]">
        {value}
      </dd>
    </div>
  );
}

function formatFactualAccuracy(value: number | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return null;
  }
  const percent = value <= 1 ? value * 100 : value;
  if (percent > 100) return null;
  return `${Math.round(percent)}%`;
}

function hasSyntheticFixtureEvidence(report: FTOReport) {
  const spanValues = Object.values(report.claim_source_span_map?.spans ?? {});
  const generatedFrom = String(
    report.claim_source_span_map?.generated_from ?? "",
  );
  const markers = [
    String(report.disclaimer ?? ""),
    generatedFrom,
    ...spanValues.flatMap((span) => [
      String(span.source_name ?? ""),
      String(span.collector_identity ?? ""),
    ]),
  ];

  return markers.some((value) =>
    /synthetic component-test fixture|synthetic_fixture|dev_seed_fixture|dev\.synthetic_fixture/i.test(
      value,
    ),
  );
}
