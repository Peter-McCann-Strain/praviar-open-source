import type { PatentItem, PatentSortOption } from "@/hooks/use-patents";

export type RiskFilter = "all" | "high" | "medium" | "low" | "clear";
export type SortOption = PatentSortOption;
export type ExpiryTone = "active" | "soon" | "expired" | "unknown";

export const RISK_ORDER: Record<Exclude<RiskFilter, "all">, number> = {
  high: 3,
  medium: 2,
  low: 1,
  clear: 0,
};

export const RISK_FILTER_OPTIONS: ReadonlyArray<{
  value: RiskFilter;
  label: string;
}> = [
  { value: "all", label: "All Risk" },
  { value: "high", label: "High Risk" },
  { value: "medium", label: "Medium Risk" },
  { value: "low", label: "Low Risk" },
  { value: "clear", label: "Clear" },
];

export const SORT_OPTIONS: ReadonlyArray<{
  value: SortOption;
  label: string;
}> = [
  { value: "risk-desc", label: "High risk first" },
  { value: "risk-asc", label: "Low risk first" },
  { value: "id-asc", label: "Patent ID A-Z" },
  { value: "id-desc", label: "Patent ID Z-A" },
];

export const ID_SORT_OPTIONS = SORT_OPTIONS.filter(
  (option) => option.value === "id-asc" || option.value === "id-desc",
);

export function filterAndSortPatents(
  patents: PatentItem[],
  searchQuery: string,
  sortBy: SortOption,
): PatentItem[] {
  const query = searchQuery.toLowerCase().trim();

  return patents
    .filter((patent) => {
      if (!query) {
        return true;
      }

      const matchesId = patent.patent_number.toLowerCase().includes(query);
      const matchesTitle = patent.title.toLowerCase().includes(query);
      const matchesAssignee = patent.assignee.toLowerCase().includes(query);
      const matchesCompound = patent.compound_name
        .toLowerCase()
        .includes(query);
      return matchesId || matchesTitle || matchesAssignee || matchesCompound;
    })
    .sort((a, b) => {
      switch (sortBy) {
        case "id-asc":
          return a.patent_number.localeCompare(b.patent_number);
        case "id-desc":
          return b.patent_number.localeCompare(a.patent_number);
        case "risk-desc":
          return compareRiskRank(a, b, "desc");
        case "risk-asc":
          return compareRiskRank(a, b, "asc");
        default:
          return 0;
      }
    });
}

export function formatPatentExpiryDate(expiryDate: string | null): string {
  return getPatentExpirySignal(expiryDate).dateLabel;
}

export function getPatentExpirySignal(
  expiryDate: string | null,
  now = new Date(),
): { dateLabel: string; statusLabel: string; tone: ExpiryTone } {
  if (!expiryDate) {
    return {
      dateLabel: "\u2014",
      statusLabel: "Unknown expiry",
      tone: "unknown",
    };
  }

  const parsed = new Date(expiryDate);
  if (Number.isNaN(parsed.getTime())) {
    return {
      dateLabel: expiryDate,
      statusLabel: "Date unverified",
      tone: "unknown",
    };
  }

  const dateLabel = parsed.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
  const todayUtc = Date.UTC(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    now.getUTCDate(),
  );
  const expiryUtc = Date.UTC(
    parsed.getUTCFullYear(),
    parsed.getUTCMonth(),
    parsed.getUTCDate(),
  );
  const daysUntilExpiry = Math.ceil(
    (expiryUtc - todayUtc) / (24 * 60 * 60 * 1000),
  );

  if (daysUntilExpiry < 0) {
    return { dateLabel, statusLabel: "Expired", tone: "expired" };
  }

  if (daysUntilExpiry <= 730) {
    return { dateLabel, statusLabel: "Expires <2y", tone: "soon" };
  }

  return { dateLabel, statusLabel: "Active term", tone: "active" };
}

export function extractJurisdiction(patentId: string): string {
  const normalized = patentId.trim().toUpperCase();
  if (normalized.startsWith("PCT/")) {
    return "PCT";
  }

  const match = normalized.match(/^([A-Z]{2})(?=\d)/);
  if (!match) {
    return "\u2014";
  }

  return KNOWN_PATENT_AUTHORITY_PREFIXES.has(match[1]) ? match[1] : "\u2014";
}

const KNOWN_PATENT_AUTHORITY_PREFIXES = new Set([
  "AR",
  "AT",
  "AU",
  "BE",
  "BR",
  "CA",
  "CH",
  "CN",
  "DE",
  "DK",
  "EP",
  "ES",
  "FI",
  "FR",
  "GB",
  "IE",
  "IL",
  "IN",
  "IT",
  "JP",
  "KR",
  "MX",
  "NL",
  "NO",
  "NZ",
  "RU",
  "SE",
  "SG",
  "US",
  "WO",
  "ZA",
]);

const SUPPORTED_RISK_LEVELS = new Set<Exclude<RiskFilter, "all">>([
  "high",
  "medium",
  "low",
  "clear",
]);

export function isSupportedRiskLevel(
  riskLevel: string | null | undefined,
): riskLevel is Exclude<RiskFilter, "all"> {
  return normalizeRiskLevel(riskLevel) !== null;
}

export function normalizeRiskLevel(
  riskLevel: string | null | undefined,
): Exclude<RiskFilter, "all"> | null {
  const normalizedRisk = riskLevel?.toLowerCase();
  return normalizedRisk &&
    SUPPORTED_RISK_LEVELS.has(normalizedRisk as Exclude<RiskFilter, "all">)
    ? (normalizedRisk as Exclude<RiskFilter, "all">)
    : null;
}

function compareRiskRank(
  a: PatentItem,
  b: PatentItem,
  direction: "asc" | "desc",
) {
  const aRank = getRiskRank(a.risk_level);
  const bRank = getRiskRank(b.risk_level);
  if (aRank === null && bRank === null) {
    return a.patent_number.localeCompare(b.patent_number);
  }
  if (aRank === null) return 1;
  if (bRank === null) return -1;
  return direction === "asc"
    ? aRank - bRank || a.patent_number.localeCompare(b.patent_number)
    : bRank - aRank || a.patent_number.localeCompare(b.patent_number);
}

function getRiskRank(riskLevel: string | null | undefined) {
  const normalizedRisk = normalizeRiskLevel(riskLevel);
  return normalizedRisk ? RISK_ORDER[normalizedRisk] : null;
}
