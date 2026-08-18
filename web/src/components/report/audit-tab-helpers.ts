import type { FTOReport } from "@praviar/shared-types";

export function getHardFilterRejectionEntries(audit: FTOReport["audit_trail"]) {
  const rejectionsByReason = new Map<string, number>();

  // audit_trail is OPTIONAL in the generated contract (the web barrel widens it
  // to required); a report may omit it entirely. Guard the array reads so the
  // Audit tab renders empty rather than throwing into its ErrorBoundary.
  for (const entry of audit?.search_funnel ?? []) {
    if (!entry.passed_hard_filter && entry.filter_reason) {
      rejectionsByReason.set(
        entry.filter_reason,
        (rejectionsByReason.get(entry.filter_reason) ?? 0) + 1,
      );
    }
  }

  return Array.from(rejectionsByReason.entries()).sort(
    (first, second) => second[1] - first[1],
  );
}

export function getSortedTriageEntries(audit: FTOReport["audit_trail"]) {
  return [...(audit?.triage_audit ?? [])].sort(
    (first, second) => second.confidence - first.confidence,
  );
}

export function getThinkingPatents(report: FTOReport) {
  return report.patent_analyses.filter(
    (patentAnalysis) => patentAnalysis.thinking_text,
  );
}
