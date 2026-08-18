"use client";

import { AlertTriangle, CheckCircle2, Globe2, TimerReset } from "lucide-react";
import type { FTOReport } from "@praviar/shared-types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RiskDonut } from "@/components/charts/risk-donut";
import { cn } from "@/lib/utils";
import { PatentRiskOverview } from "./patents-tab-risk-overview";
import { ReportMobileDisclosure } from "@/components/report/report-mobile-disclosure";

interface EnforceabilityMetric {
  detail: string;
  label: string;
  tone: "default" | "warning";
  value: string;
}

export function PatentsTabSummary({
  report,
  riskData,
  sortedAnalyses,
  analysisId,
  onPatentSelect,
}: {
  report: FTOReport;
  riskData: Array<{ level: string; count: number }>;
  sortedAnalyses: FTOReport["patent_analyses"];
  analysisId?: string;
  onPatentSelect: (patentId: string) => void;
}) {
  return (
    <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-3">
      <ReportMobileDisclosure
        label="Risk distribution"
        description={riskData
          .map((entry) => `${entry.count} ${entry.level.toLowerCase()}`)
          .join(" · ")}
      >
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Risk Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            <RiskDonut data={riskData} size={220} />
          </CardContent>
        </Card>
      </ReportMobileDisclosure>

      <PatentRiskOverview
        report={report}
        sortedAnalyses={sortedAnalyses}
        analysisId={analysisId}
        onPatentSelect={onPatentSelect}
      />

      <div className="min-w-0 lg:col-span-3">
        <EnforceabilityConfidenceCard report={report} />
      </div>
    </div>
  );
}

function EnforceabilityConfidenceCard({ report }: { report: FTOReport }) {
  const detailsByPatentId = new Map(
    Object.values(report.patent_details ?? {}).map((patent) => [
      patent.patent_id,
      patent,
    ]),
  );
  const analyzedCount = report.patent_analyses.length;
  const analyzedDetails = report.patent_analyses.map((analysis) =>
    detailsByPatentId.get(analysis.patent_id),
  );
  const missingDetailsCount = analyzedDetails.filter(Boolean).length
    ? analyzedDetails.filter((detail) => !detail).length
    : analyzedCount;
  const familyCoveredCount = analyzedDetails.filter(
    (detail) => detail?.family?.members?.length,
  ).length;
  const activeStatusCount = analyzedDetails.filter((detail) =>
    (detail?.legal_status ?? "").toLowerCase().includes("active"),
  ).length;
  const unknownStatusCount = analyzedDetails.filter(
    (detail) => !detail?.legal_status?.trim(),
  ).length;
  const maintenanceStatuses = analyzedDetails.map(
    (detail) => detail?.patent_term_info?.maintenance_fee_status ?? "unknown",
  );
  const maintenanceRiskCount = maintenanceStatuses.filter(
    (status) => status !== "paid",
  ).length;
  const termConfidenceValues = analyzedDetails
    .map((detail) => detail?.patent_term_info?.calculation_confidence)
    .filter((value): value is number => Number.isFinite(value));
  const lowConfidenceCount = termConfidenceValues.filter(
    (value) => value < 0.8,
  ).length;
  const averageTermConfidence =
    termConfidenceValues.length > 0
      ? termConfidenceValues.reduce((sum, value) => sum + value, 0) /
        termConfidenceValues.length
      : null;
  const registerReviewRequired =
    missingDetailsCount > 0 ||
    unknownStatusCount > 0 ||
    maintenanceRiskCount > 0 ||
    lowConfidenceCount > 0 ||
    familyCoveredCount < analyzedCount;
  const postureLabel = registerReviewRequired
    ? "Register review required"
    : "Register posture complete";
  const metrics: EnforceabilityMetric[] = [
    {
      label: "Legal status",
      value: `${activeStatusCount}/${analyzedCount || 0} active`,
      detail:
        missingDetailsCount > 0 || unknownStatusCount > 0
          ? `${missingDetailsCount + unknownStatusCount} status gap${missingDetailsCount + unknownStatusCount === 1 ? "" : "s"}`
          : "Status present for analyzed patents.",
      tone:
        missingDetailsCount > 0 || unknownStatusCount > 0
          ? "warning"
          : "default",
    },
    {
      label: "Maintenance",
      value:
        maintenanceRiskCount > 0
          ? `${maintenanceRiskCount} need review`
          : "Fees current",
      detail: "Paid, lapsed, grace-period, or unknown fee posture.",
      tone: maintenanceRiskCount > 0 ? "warning" : "default",
    },
    {
      label: "Family coverage",
      value: `${familyCoveredCount}/${analyzedCount || 0} with family`,
      detail: "Family context changes expiry and jurisdiction risk.",
      tone: familyCoveredCount < analyzedCount ? "warning" : "default",
    },
    {
      label: "Term confidence",
      value:
        averageTermConfidence === null
          ? "No term model"
          : `${Math.round(averageTermConfidence * 100)}% avg`,
      detail:
        lowConfidenceCount > 0
          ? `${lowConfidenceCount} calculation${lowConfidenceCount === 1 ? "" : "s"} below 80%`
          : "Expiry model confidence cleared.",
      tone:
        lowConfidenceCount > 0 || averageTermConfidence === null
          ? "warning"
          : "default",
    },
  ];

  return (
    <Card
      className={cn(
        "overflow-hidden",
        registerReviewRequired && "border-warning/25 bg-warning/5",
      )}
      role="region"
      aria-label="Enforceability confidence"
    >
      <CardHeader className="space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="text-sm">Enforceability Confidence</CardTitle>
            <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
              Legal status, maintenance fees, family coverage, and term model
              confidence before reliance.
            </p>
          </div>
          <span
            className={cn(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-md border",
              registerReviewRequired
                ? "border-warning/25 bg-warning/10 text-warning"
                : "border-success/25 bg-success/10 text-success",
            )}
            aria-hidden="true"
          >
            {registerReviewRequired ? (
              <AlertTriangle className="h-4 w-4" />
            ) : (
              <CheckCircle2 className="h-4 w-4" />
            )}
          </span>
        </div>
        <p
          className={cn(
            "inline-flex w-fit rounded-full border px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.12em]",
            registerReviewRequired
              ? "border-warning/25 bg-warning/10 text-warning"
              : "border-success/25 bg-success/10 text-success",
          )}
        >
          {postureLabel}
        </p>
      </CardHeader>
      <CardContent className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map((metric, index) => (
          <EnforceabilityMetricRow
            key={metric.label}
            metric={metric}
            icon={index === 2 ? "family" : index === 3 ? "term" : "status"}
          />
        ))}
      </CardContent>
    </Card>
  );
}

function EnforceabilityMetricRow({
  icon,
  metric,
}: {
  icon: "family" | "status" | "term";
  metric: EnforceabilityMetric;
}) {
  const Icon =
    icon === "family" ? Globe2 : icon === "term" ? TimerReset : CheckCircle2;

  return (
    <div
      className={cn(
        "grid min-w-0 grid-cols-[1.75rem_minmax(0,1fr)] gap-2 rounded-md border px-2.5 py-2",
        metric.tone === "warning"
          ? "border-warning/20 bg-warning/10"
          : "border-[var(--border-subtle)] bg-[var(--bg-surface)]/70",
      )}
    >
      <span
        className={cn(
          "mt-0.5 flex h-7 w-7 items-center justify-center rounded-md",
          metric.tone === "warning"
            ? "bg-warning/10 text-warning"
            : "bg-brand-primary/10 text-brand-primary",
        )}
        aria-hidden="true"
      >
        <Icon className="h-3.5 w-3.5" />
      </span>
      <span className="min-w-0">
        <span className="block text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
          {metric.label}
        </span>
        <span className="mt-0.5 block break-words text-xs font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
          {metric.value}
        </span>
        <span className="mt-0.5 block break-words text-xs leading-4 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
          {metric.detail}
        </span>
      </span>
    </div>
  );
}
