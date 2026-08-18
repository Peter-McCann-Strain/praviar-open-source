import { normalizeDemoAnalysisId } from "@/lib/demo-data";

export type LegacyReportSearchParams = Record<
  string,
  string | string[] | undefined
>;

export function resolveLegacyReportAnalysisId(id: string) {
  const demoAnalysisId = normalizeDemoAnalysisId(id);
  if (demoAnalysisId) {
    return demoAnalysisId;
  }

  if (id.startsWith("rpt_ana_")) {
    return id.slice(4);
  }

  return id;
}

export function buildLegacyReportRedirectPath(
  id: string,
  searchParams?: LegacyReportSearchParams,
) {
  const analysisId = resolveLegacyReportAnalysisId(id);
  const query = new URLSearchParams();

  for (const [key, value] of Object.entries(searchParams ?? {})) {
    if (typeof value === "string") {
      query.append(key, value);
    } else if (Array.isArray(value)) {
      for (const item of value) {
        if (typeof item === "string") {
          query.append(key, item);
        }
      }
    }
  }

  const queryString = query.toString();
  return `/analyses/${encodeURIComponent(analysisId)}/report${
    queryString ? `?${queryString}` : ""
  }`;
}
