export function normalizeApplicationRole(
  role: string | null | undefined,
): string {
  return role?.trim().toLowerCase().replace(/^org:/, "") ?? "";
}

export function canManageReportCollaboration(
  role: string | null | undefined,
): boolean {
  const normalized = normalizeApplicationRole(role);
  return normalized === "admin" || normalized === "attorney";
}

export function canAccessFullReport(
  role: string | null | undefined,
  riskRatingsRestricted?: boolean,
): boolean {
  const normalized = normalizeApplicationRole(role);
  if (normalized === "admin" || normalized === "attorney") {
    return true;
  }
  return normalized === "scientist" && riskRatingsRestricted === false;
}

export function getReportAccessHref(
  analysisId: string,
  role: string | null | undefined,
  riskRatingsRestricted?: boolean,
): string {
  const encodedId = encodeURIComponent(analysisId);
  return canAccessFullReport(role, riskRatingsRestricted)
    ? `/analyses/${encodedId}/report`
    : `/analyses/${encodedId}/report/summary`;
}

export function getReportAccessHrefWithQuery(
  analysisId: string,
  role: string | null | undefined,
  riskRatingsRestricted: boolean | undefined,
  query: URLSearchParams | Record<string, string>,
): string {
  const baseHref = getReportAccessHref(analysisId, role, riskRatingsRestricted);
  if (!canAccessFullReport(role, riskRatingsRestricted)) {
    return baseHref;
  }
  const queryString =
    query instanceof URLSearchParams
      ? query.toString()
      : new URLSearchParams(query).toString();
  return queryString ? `${baseHref}?${queryString}` : baseHref;
}
