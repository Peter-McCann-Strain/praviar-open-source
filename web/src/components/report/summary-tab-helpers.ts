import type { FTOReport } from "@praviar/shared-types";
import { isHealthySourceStatus } from "@/components/report-page/report-reliance-readiness";

export const PATENT_ID_RE =
  /(?:US|EP|WO|JP|KR|CN|IN|CA|AU)\d[\d,]*(?:[A-Z]\d?)?/g;

export const SOURCE_LABELS: Record<
  string,
  {
    label: string;
    jurisdictions: string[];
    addsCrossJurisdictionSource?: boolean;
  }
> = {
  pubchem_sdq: { label: "PubChem", jurisdictions: ["Chemical index"] },
  bigquery: {
    label: "Google Patents",
    jurisdictions: ["Configured dataset"],
    addsCrossJurisdictionSource: true,
  },
  bigquery_translated: {
    label: "Google Patents (Translated)",
    jurisdictions: ["JP", "KR", "CN", "IN", "DE", "FR"],
    addsCrossJurisdictionSource: true,
  },
  bigquery_annotations: {
    label: "Patent Annotations (NLP)",
    jurisdictions: ["Configured dataset"],
  },
  surechembl: { label: "SureChEMBL", jurisdictions: ["Chemical index"] },
  patcid: { label: "PatCID Index", jurisdictions: ["Local index"] },
  cpc_search: {
    label: "CPC Classification",
    jurisdictions: ["Configured dataset"],
  },
  assignee_search: {
    label: "Assignee Search",
    jurisdictions: ["Configured dataset"],
  },
  epo_search: {
    label: "EPO OPS",
    jurisdictions: ["EP", "WO", "US", "JP", "KR", "CN"],
    addsCrossJurisdictionSource: true,
  },
  lens: {
    label: "Lens.org",
    jurisdictions: ["Configured Lens dataset"],
    addsCrossJurisdictionSource: true,
  },
  kipris: {
    label: "KIPRIS (Korea)",
    jurisdictions: ["KR"],
    addsCrossJurisdictionSource: true,
  },
  patentscope: {
    label: "WIPO PatentScope",
    jurisdictions: ["Configured WIPO dataset"],
    addsCrossJurisdictionSource: true,
  },
};

export const SOURCE_STATUS_SWATCH_COLORS: Record<string, string> = {
  ok: "var(--color-success)",
  success: "var(--color-success)",
  healthy: "var(--color-success)",
  available: "var(--color-success)",
  failed: "var(--color-error)",
  error: "var(--color-error)",
  unavailable: "var(--color-error)",
  skipped: "var(--color-warning)",
  not_configured: "var(--color-warning)",
  "not configured": "var(--color-warning)",
};

export const SOURCE_STATUS_FALLBACK_SWATCH_COLOR = "var(--text-tertiary)";

export function formatJurisdictionScopeLabel(jurisdiction: string) {
  return jurisdiction.replace(/[()]/g, "").replace(/\s+/g, " ").trim();
}

export function getSummaryDataIntegrity(report: FTOReport) {
  const failures = report.analysis_failures ?? [];
  const failureCount = failures.length;
  const limitationCount = report.data_limitations?.length ?? 0;
  const reviewIssueCount = report.review_issues?.length ?? 0;
  const recoverableFailureCount = failures.filter(
    (failure) => failure.recoverable,
  ).length;
  const auditFailureCount =
    report.clearance_decision?.decision_audit?.analysis_failures_count;
  const coverageFailureCount =
    report.clearance_decision?.decision_audit?.coverage_summary
      ?.failed_analysis_patent_ids?.length;
  const evidenceSufficientForClearance =
    report.clearance_decision?.decision_audit
      ?.evidence_sufficient_for_clearance;
  const metadataCounts = [
    failureCount,
    auditFailureCount,
    coverageFailureCount,
  ].filter((count): count is number => typeof count === "number");
  const hasMetadataInconsistency = new Set(metadataCounts).size > 1;
  const reportedFailureCount = Math.max(...metadataCounts, failureCount);

  return {
    evidenceSufficientForClearance,
    failureCount: reportedFailureCount,
    hasMetadataInconsistency,
    limitationCount,
    reviewIssueCount,
    recoverableFailureCount,
    needsReviewFailureCount: reportedFailureCount - recoverableFailureCount,
    hasDataIntegrityWarnings:
      reportedFailureCount > 0 ||
      limitationCount > 0 ||
      reviewIssueCount > 0 ||
      hasMetadataInconsistency ||
      evidenceSufficientForClearance === false,
  };
}

export function getSummaryHasDesignArounds(report: FTOReport) {
  return (report.patent_analyses ?? []).some(
    (analysis) =>
      (analysis.risk_level === "high" || analysis.risk_level === "medium") &&
      (analysis.design_around_suggestions?.length ?? 0) > 0,
  );
}

export function getSummaryFunnelData(report: FTOReport) {
  const audit = report.audit_trail;
  return [
    { stage: "Discovered", count: audit?.total_patents_discovered ?? 0 },
    {
      stage: "After Hard Filter",
      count: audit?.patents_after_hard_filter ?? 0,
    },
    { stage: "After Ranking", count: audit?.patents_after_ranking ?? 0 },
    { stage: "After Triage", count: audit?.patents_after_triage ?? 0 },
    { stage: "Analyzed", count: audit?.patents_analyzed ?? 0 },
  ];
}

export function getSummaryCoveredJurisdictions(report: FTOReport) {
  const activeEntries = (report.source_health?.entries ?? []).filter((entry) =>
    isHealthySourceStatus(entry.status),
  );
  const specificJurisdictions = new Set(
    activeEntries
      .flatMap((entry) => SOURCE_LABELS[entry.source]?.jurisdictions ?? [])
      .filter((jurisdiction) => /^[A-Z]{2}$/.test(jurisdiction)),
  );

  return specificJurisdictions.size;
}

export function getSummaryHasAdditionalConfiguredSources(report: FTOReport) {
  return (report.source_health?.entries ?? []).some((entry) => {
    if (!isHealthySourceStatus(entry.status)) return false;
    const meta = SOURCE_LABELS[entry.source];

    return (
      Boolean(meta?.addsCrossJurisdictionSource) &&
      meta.jurisdictions.length > 0
    );
  });
}
