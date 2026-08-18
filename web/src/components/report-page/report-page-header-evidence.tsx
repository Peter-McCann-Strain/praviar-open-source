import type { ReactNode } from "react";
import { DatabaseZap, FileCheck2, Scale, ShieldAlert } from "lucide-react";

import { formatReportRiskLabel } from "@/components/report-page/report-command-summary";
import { getReportSourceHealthReadiness } from "@/components/report-page/report-reliance-readiness";
import type { FTOReport } from "@praviar/shared-types";

export interface ReportEvidenceFactItem {
  icon: ReactNode;
  label: string;
  value: string;
  detail: string;
  step?: number;
  tone?: "neutral" | "warning" | "danger" | "success" | "info";
}

export function ReportEvidenceFact({
  icon,
  label,
  value,
  detail,
  step,
  tone = "neutral",
}: ReportEvidenceFactItem) {
  const toneClass =
    tone === "danger"
      ? "border-error/25 bg-error/10 text-error"
      : tone === "warning"
        ? "border-warning/25 bg-warning/10 text-warning"
        : tone === "success"
          ? "border-success/25 bg-success/10 text-success"
          : tone === "info"
            ? "border-info/25 bg-info/10 text-info"
            : "border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-surface)_72%,transparent)] text-[var(--brand-primary)]";

  return (
    <div
      className="praviar-evidence-fact-card min-w-0 rounded-lg p-3"
      data-evidence-tone={tone}
    >
      {typeof step === "number" ? (
        <span className="mb-3 block text-xs font-semibold uppercase text-[var(--text-tertiary)]">
          {String(step).padStart(2, "0")}
        </span>
      ) : null}
      <div className="flex items-start gap-3">
        <span
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border ${toneClass}`}
          aria-hidden="true"
        >
          {icon}
        </span>
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
            {label}
          </p>
          <p className="mt-1 text-sm font-semibold leading-5 text-[var(--text-primary)]">
            {value}
          </p>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            {detail}
          </p>
        </div>
      </div>
    </div>
  );
}

function getPatentCoverageContext(report: FTOReport) {
  const audit = report.clearance_decision?.decision_audit;
  const materialPatents =
    audit?.material_patents_reviewed ??
    report.risk_summary.total_patents_analyzed ??
    report.patent_analyses?.length ??
    0;
  const patentsAfterTriage = report.patents_after_triage ?? materialPatents;
  const totalPatentsFound =
    typeof report.total_patents_found === "number" &&
    Number.isFinite(report.total_patents_found)
      ? report.total_patents_found
      : null;

  return { materialPatents, patentsAfterTriage, totalPatentsFound };
}

function getDecisionEvidenceContext(report: FTOReport) {
  const audit = report.clearance_decision?.decision_audit;
  return {
    epPatents:
      audit?.material_ep_patents ??
      audit?.coverage_summary?.reviewed_ep_patent_ids?.length ??
      0,
    evidenceQuality: getEvidenceQualityMeta(
      report.clearance_decision?.evidence_quality,
    ),
    usPatents:
      audit?.material_us_patents ??
      audit?.coverage_summary?.reviewed_us_patent_ids?.length ??
      0,
  };
}

function getReportEvidenceContext(report: FTOReport) {
  const coverage = getPatentCoverageContext(report);
  const decisionEvidence = getDecisionEvidenceContext(report);
  const blockerCounts = getCanonicalBlockerCounts(report);
  const sourceEntries = report.source_health?.entries ?? [];
  const hasSourceHealth = sourceEntries.length > 0;
  const sourceHealthReadiness = getReportSourceHealthReadiness(report);
  const riskLabel = formatReportRiskLabel(report.risk_summary.overall_risk);
  const riskTone = getRiskFactTone(report.risk_summary.overall_risk);

  return {
    blockerCounts,
    ...coverage,
    ...decisionEvidence,
    hasSourceHealth,
    riskLabel,
    riskTone,
    sourceHealthReadiness,
  };
}

type ReportEvidenceContext = ReturnType<typeof getReportEvidenceContext>;

function getScreeningVerdictEvidenceFact(
  context: ReportEvidenceContext,
): ReportEvidenceFactItem {
  const { blockerCounts, riskLabel, riskTone } = context;
  return {
    icon: <ShieldAlert className="h-4 w-4" />,
    label: "Screening verdict",
    value: riskLabel,
    detail:
      blockerCounts.familyCount > 0
        ? `${blockerCounts.familyCount} famil${blockerCounts.familyCount === 1 ? "y" : "ies"} containing blocking national claims across ${blockerCounts.referenceCount} canonical patent or publication reference${blockerCounts.referenceCount === 1 ? "" : "s"}; counsel must confirm the enforceable national or regional rights.`
        : "Screening result still requires legal verification.",
    tone: blockerCounts.familyCount > 0 ? "danger" : riskTone,
  };
}

function getEvidenceCoverageFact(
  context: ReportEvidenceContext,
): ReportEvidenceFactItem {
  const { materialPatents, patentsAfterTriage, totalPatentsFound } = context;
  return {
    icon: <FileCheck2 className="h-4 w-4" />,
    label: "Evidence coverage",
    value: `${materialPatents.toLocaleString()} patent${
      materialPatents === 1 ? "" : "s"
    }`,
    detail:
      totalPatentsFound === null
        ? `${patentsAfterTriage.toLocaleString()} triaged; found count not reported.`
        : `${patentsAfterTriage.toLocaleString()} triaged from ${totalPatentsFound.toLocaleString()} found.`,
    tone: "neutral",
  };
}

function getSourceAuditEvidenceFact(
  context: ReportEvidenceContext,
): ReportEvidenceFactItem {
  const { hasSourceHealth, sourceHealthReadiness } = context;
  return {
    icon: <DatabaseZap className="h-4 w-4" />,
    label: "Source audit",
    value: sourceHealthReadiness.value,
    detail:
      !hasSourceHealth || sourceHealthReadiness.hasCaveats
        ? sourceHealthReadiness.detail
        : "Queried sources are disclosed for review.",
    tone: sourceHealthReadiness.tone,
  };
}

function getDecisionEvidenceFact(
  context: ReportEvidenceContext,
): ReportEvidenceFactItem {
  const { epPatents, evidenceQuality, usPatents } = context;
  return {
    icon: <Scale className="h-4 w-4" />,
    label: "Decision evidence",
    value: evidenceQuality.label,
    detail:
      usPatents || epPatents
        ? `${usPatents} US / ${epPatents} EP material records; source health is shown separately.`
        : "Weighted decision-input coverage; source health is shown separately.",
    tone: evidenceQuality.tone,
  };
}

export function getReportEvidenceItems(
  report: FTOReport,
): ReportEvidenceFactItem[] {
  const context = getReportEvidenceContext(report);

  return [
    getScreeningVerdictEvidenceFact(context),
    getEvidenceCoverageFact(context),
    getSourceAuditEvidenceFact(context),
    getDecisionEvidenceFact(context),
  ];
}

export function getCanonicalBlockerCounts(report: FTOReport) {
  const families =
    report.clearance_decision?.decision_audit?.blocker_families ?? [];
  return {
    familyCount: families.length,
    referenceCount: new Set(
      families.flatMap((family) => family.blocking_patent_ids),
    ).size,
  };
}

function getRiskFactTone(value: string): ReportEvidenceFactItem["tone"] {
  const risk = value.toLowerCase();
  if (risk === "high") return "danger";
  if (risk === "medium") return "warning";
  if (risk === "low") return "success";
  if (risk === "clear") return "info";
  return "neutral";
}

export function getEvidenceQualityMeta(value: number | undefined): {
  label: string;
  tone: ReportEvidenceFactItem["tone"];
} {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return { label: "Counsel verify", tone: "warning" };
  }

  const percent = value <= 1 ? value * 100 : value;
  if (percent < 60) {
    return {
      label: `Low decision-evidence score (${Math.round(percent)}%)`,
      tone: "danger",
    };
  }

  if (percent < 80) {
    return {
      label: `${Math.round(percent)}% decision-evidence score`,
      tone: "warning",
    };
  }

  return {
    label: `${Math.round(percent)}% decision-evidence score`,
    tone: "neutral",
  };
}
