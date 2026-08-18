import type { FTOReport } from "@praviar/shared-types";
import type { PatentRow } from "@/components/report/patent-data-table";

const RISK_ORDER: Record<string, number> = {
  high: 0,
  medium: 1,
  low: 2,
  clear: 3,
};

export function getPatentRiskData(report: FTOReport) {
  return [
    {
      level: "HIGH",
      count: report.patent_analyses.filter(
        (analysis) => analysis.risk_level === "high",
      ).length,
    },
    {
      level: "MEDIUM",
      count: report.patent_analyses.filter(
        (analysis) => analysis.risk_level === "medium",
      ).length,
    },
    {
      level: "LOW",
      count: report.patent_analyses.filter(
        (analysis) => analysis.risk_level === "low",
      ).length,
    },
    {
      level: "CLEAR",
      count: report.patent_analyses.filter(
        (analysis) => analysis.risk_level === "clear",
      ).length,
    },
  ];
}

export function getSortedPatentAnalyses(report: FTOReport) {
  return [...report.patent_analyses].sort(
    (first, second) =>
      (RISK_ORDER[first.risk_level] ?? 4) -
      (RISK_ORDER[second.risk_level] ?? 4),
  );
}

export function getPatentRows(
  report: FTOReport,
  patentAnalyses: FTOReport["patent_analyses"],
): PatentRow[] {
  return patentAnalyses.map((analysis) => {
    const detail = report.patent_details?.[analysis.patent_id];
    const jurisdiction = analysis.patent_id.match(/^[A-Z]{2}/)?.[0] ?? "US";

    return {
      patentNumber: analysis.patent_id,
      title: analysis.title,
      assignee: analysis.assignee,
      filingDate: detail?.filing_date ?? "",
      riskLevel: analysis.risk_level,
      jurisdiction,
      relevanceScore:
        detail?.confidence_score != null
          ? Math.round(detail.confidence_score * 100)
          : null,
    };
  });
}
