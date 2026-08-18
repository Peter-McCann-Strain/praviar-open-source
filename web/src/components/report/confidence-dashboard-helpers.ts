import type { FTOReport } from "@praviar/shared-types";

import {
  formatEvidenceScore,
  getClearanceDecision,
  getCoverageSummary,
  getDecisionWarnings,
} from "./report-decision-helpers";

export type ConfidenceBand = "HIGH" | "MODERATE" | "LOW";

export interface DisplayedSourceEntry {
  source: string;
  status: "ok" | "failed" | "skipped" | "not_configured" | "not_reported";
  patent_count: number;
  error_message: string;
}

export const BAND_STYLES = {
  HIGH: {
    bg: "bg-success/10",
    text: "text-success",
    border: "border-success/20",
  },
  MODERATE: {
    bg: "bg-warning/10",
    text: "text-warning",
    border: "border-warning/20",
  },
  LOW: { bg: "bg-error/10", text: "text-error", border: "border-error/20" },
} as const;

export interface ConfidenceDashboardState {
  band: ConfidenceBand;
  coverageLabel: string;
  decisionEvidenceLabel: string;
  displayDateLabel: string;
  displayedSources: DisplayedSourceEntry[];
  failedSources: DisplayedSourceEntry[];
  sourceCoverage: number;
  limitations: NonNullable<FTOReport["data_limitations"]>;
  failures: NonNullable<FTOReport["analysis_failures"]>;
  decisionWarnings: string[];
  coverageSummary: ReturnType<typeof getCoverageSummary>;
  structuredDecision: ReturnType<typeof getClearanceDecision>;
  summaryLabel: string;
}

function buildDisplayedSources(report: FTOReport): DisplayedSourceEntry[] {
  const sourcesUsed = report.search_sources_used ?? [];
  const sourceHealth = report.source_health?.entries ?? [];

  if (sourceHealth.length > 0) {
    return sourceHealth.map((entry) => ({
      source: entry.source,
      status: entry.status,
      patent_count: entry.patent_count ?? 0,
      error_message: entry.error_message ?? "",
    }));
  }

  return sourcesUsed.map((source) => ({
    source,
    status: "not_reported" as const,
    patent_count: 0,
    error_message: "Source was listed, but health status was not reported.",
  }));
}

function resolveConfidenceBand({
  evidenceQuality,
  sourceCoverage,
  failureCount,
  limitationCount,
  warningCount,
}: {
  evidenceQuality: number | null;
  sourceCoverage: number;
  failureCount: number;
  limitationCount: number;
  warningCount: number;
}): ConfidenceBand {
  if (
    (evidenceQuality != null && evidenceQuality < 0.6) ||
    sourceCoverage < 0.5 ||
    failureCount > 5
  ) {
    return "LOW";
  }

  if (
    (evidenceQuality != null && evidenceQuality < 0.8) ||
    sourceCoverage < 0.8 ||
    failureCount > 0 ||
    limitationCount > 2 ||
    warningCount > 0
  ) {
    return "MODERATE";
  }

  return "HIGH";
}

function buildSummaryLabel(
  structuredDecision: ReturnType<typeof getClearanceDecision>,
  displayedSources: DisplayedSourceEntry[],
  failures: NonNullable<FTOReport["analysis_failures"]>,
  hasSourceHealth: boolean,
): string {
  const patentPrefix = structuredDecision
    ? `${structuredDecision.decision_audit.material_patents_reviewed} patents · `
    : "";
  const failedCount = displayedSources.filter(
    (entry) => entry.status === "failed",
  ).length;
  const gapCount = displayedSources.filter(
    (entry) => entry.status !== "ok",
  ).length;
  const sourceSummary = hasSourceHealth
    ? `${displayedSources.filter((entry) => entry.status === "ok").length}/${displayedSources.length} source providers healthy${
        failedCount > 0
          ? ` · ${failedCount} failed`
          : gapCount > 0
            ? ` · ${gapCount} need review`
            : ""
      }`
    : displayedSources.length > 0
      ? `${displayedSources.length} source providers listed · health unreported`
      : "Source health not reported";
  const base = `${patentPrefix}${sourceSummary}`;

  return failures.length > 0 ? `${base} · ${failures.length} failures` : base;
}

export function buildConfidenceDashboardState(
  report: FTOReport,
): ConfidenceDashboardState {
  const structuredDecision = getClearanceDecision(report);
  const coverageSummary = getCoverageSummary(report);
  const displayedSources = buildDisplayedSources(report);
  const hasSourceHealth = (report.source_health?.entries ?? []).length > 0;
  const failedSources = displayedSources.filter(
    (entry) => entry.status !== "ok",
  );
  const limitations = report.data_limitations ?? [];
  const failures = report.analysis_failures ?? [];
  const decisionWarnings = getDecisionWarnings(report);
  const sourceCoverage = hasSourceHealth
    ? displayedSources.filter((entry) => entry.status === "ok").length /
      displayedSources.length
    : 0;

  const band = resolveConfidenceBand({
    evidenceQuality: structuredDecision?.evidence_quality ?? null,
    sourceCoverage,
    failureCount: failures.length,
    limitationCount: limitations.length,
    warningCount: decisionWarnings.length,
  });

  return {
    band,
    coverageLabel: `${(sourceCoverage * 100).toFixed(0)}%`,
    decisionEvidenceLabel: structuredDecision
      ? `${formatEvidenceScore(structuredDecision.evidence_quality)} evidence-completeness score`
      : "",
    displayDateLabel: new Date(report.generated_at).toLocaleDateString(
      "en-US",
      {
        month: "short",
        day: "numeric",
        year: "numeric",
      },
    ),
    displayedSources,
    failedSources,
    sourceCoverage,
    limitations,
    failures,
    decisionWarnings,
    coverageSummary,
    structuredDecision,
    summaryLabel: buildSummaryLabel(
      structuredDecision,
      displayedSources,
      failures,
      hasSourceHealth,
    ),
  };
}
