import type { FTOReport } from "@praviar/shared-types";

export function getPatentNarrativePreview(report: FTOReport, patentId: string) {
  const narrative = report.patent_narratives?.[patentId];

  if (!narrative) {
    return null;
  }

  return `${narrative.slice(0, 80)}…`;
}

export function isBroadestSearchFunnelHit(report: FTOReport, patentId: string) {
  return (report.audit_trail?.search_funnel ?? []).some(
    (searchFunnelEntry) =>
      searchFunnelEntry.patent_id === patentId &&
      searchFunnelEntry.family_broadest,
  );
}
