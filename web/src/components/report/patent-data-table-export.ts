import type { PatentRow } from "./patent-data-table";

export function exportPatentsToCSV(patents: PatentRow[]) {
  const headers = [
    "Patent Number",
    "Title",
    "Assignee",
    "Filing Date",
    "Risk Level",
    "Jurisdiction",
    "Reported Relevance Score",
  ];

  const rows = patents.map((patent) => [
    patent.patentNumber,
    `"${patent.title.replace(/"/g, '""')}"`,
    `"${patent.assignee.replace(/"/g, '""')}"`,
    patent.filingDate,
    patent.riskLevel,
    patent.jurisdiction,
    patent.relevanceScore == null ? "" : String(patent.relevanceScore),
  ]);

  const csv = [headers.join(","), ...rows.map((row) => row.join(","))].join(
    "\n",
  );
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `patent-analysis-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}
