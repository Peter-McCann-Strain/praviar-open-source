import type {
  JurisdictionBundle,
  MajorMarketJurisdiction,
} from "@/types/pipeline";

export const MAJOR_MARKET_JURISDICTIONS: MajorMarketJurisdiction[] = [
  "US",
  "EP",
  "UK",
  "IN",
  "JP",
  "CN",
];

const LAUNCHABLE_JURISDICTIONS = new Set<MajorMarketJurisdiction>([
  "US",
  "EP",
  "IN",
  "JP",
  "CN",
]);

export interface JurisdictionBundleDefinition {
  value: JurisdictionBundle;
  label: string;
  description: string;
  targetJurisdictions: MajorMarketJurisdiction[];
}

export const JURISDICTION_BUNDLE_DEFINITIONS: Record<
  JurisdictionBundle,
  JurisdictionBundleDefinition
> = {
  us_europe: {
    value: "us_europe",
    label: "US + Europe",
    description: "Balanced launch bundle for US and EP clearance lanes.",
    targetJurisdictions: ["US", "EP"],
  },
  europe_uk: {
    value: "europe_uk",
    label: "Europe + UK",
    description:
      "Europe-first posture with EP active and UK staged in this frontend slice.",
    targetJurisdictions: ["EP", "UK"],
  },
  major_markets: {
    value: "major_markets",
    label: "Major Markets",
    description:
      "Six-lane major-markets posture for US, EP, UK, IN, JP, and CN.",
    targetJurisdictions: ["US", "EP", "UK", "IN", "JP", "CN"],
  },
  custom: {
    value: "custom",
    label: "Custom",
    description:
      "Pick the jurisdiction lanes you want legal review and trust surfaces to track.",
    targetJurisdictions: ["US", "EP", "UK", "IN", "JP", "CN"],
  },
};

export function normalizeTargetJurisdictions(
  input: readonly string[] | null | undefined,
): MajorMarketJurisdiction[] {
  const selected = new Set(
    (input ?? [])
      .map((value) => value.trim().toUpperCase())
      .filter((value): value is MajorMarketJurisdiction =>
        MAJOR_MARKET_JURISDICTIONS.includes(value as MajorMarketJurisdiction),
      ),
  );

  const normalized = MAJOR_MARKET_JURISDICTIONS.filter((jurisdiction) =>
    selected.has(jurisdiction),
  );

  return normalized.length > 0 ? normalized : ["US", "EP"];
}

export function getBundleDefinition(
  bundle: JurisdictionBundle,
): JurisdictionBundleDefinition {
  return JURISDICTION_BUNDLE_DEFINITIONS[bundle];
}

export function getLaunchReadyJurisdictions(
  targetJurisdictions: readonly MajorMarketJurisdiction[],
): MajorMarketJurisdiction[] {
  return targetJurisdictions.filter((jurisdiction) =>
    LAUNCHABLE_JURISDICTIONS.has(jurisdiction),
  );
}

export function getStagedJurisdictions(
  targetJurisdictions: readonly MajorMarketJurisdiction[],
): MajorMarketJurisdiction[] {
  return targetJurisdictions.filter(
    (jurisdiction) => !LAUNCHABLE_JURISDICTIONS.has(jurisdiction),
  );
}

function normalizeJurisdictionCodes(values: readonly string[]): string[] {
  return values.map((value) => value.trim().toUpperCase()).filter(Boolean);
}

function uniqueJurisdictionCodes(values: readonly string[]): string[] {
  return Array.from(new Set(normalizeJurisdictionCodes(values)));
}

export function getRuntimeSearchJurisdictions({
  jurisdictionBundle,
  searchJurisdictions,
  targetJurisdictions,
}: {
  jurisdictionBundle: JurisdictionBundle;
  searchJurisdictions: readonly string[];
  targetJurisdictions: readonly string[];
}): string[] {
  const normalizedTargets =
    jurisdictionBundle === "custom"
      ? normalizeJurisdictionCodes(targetJurisdictions)
      : uniqueJurisdictionCodes([
          ...JURISDICTION_BUNDLE_DEFINITIONS[jurisdictionBundle]
            .targetJurisdictions,
          ...targetJurisdictions,
        ]);

  if (jurisdictionBundle !== "custom") {
    return uniqueJurisdictionCodes([...normalizedTargets, "WO"]);
  }

  if (normalizedTargets.length > 0) {
    return uniqueJurisdictionCodes([
      ...searchJurisdictions,
      ...normalizedTargets,
      "WO",
    ]);
  }

  return uniqueJurisdictionCodes(searchJurisdictions);
}

export function toggleTargetJurisdiction(
  current: readonly MajorMarketJurisdiction[],
  jurisdiction: MajorMarketJurisdiction,
): MajorMarketJurisdiction[] {
  const next = current.includes(jurisdiction)
    ? current.filter((value) => value !== jurisdiction)
    : [...current, jurisdiction];

  return normalizeTargetJurisdictions(next);
}

export function formatJurisdictionList(
  values: readonly string[],
  fallback = "None selected",
): string {
  return values.length > 0 ? values.join(", ") : fallback;
}
