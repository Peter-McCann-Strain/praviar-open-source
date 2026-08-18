import type { CompoundItem } from "@/hooks/use-compounds";

export const MAX_COMPOUND_SEARCH_LENGTH = 200;

const COMPOUND_DATE_FORMATTER = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});

export interface CompoundIdentityReadiness {
  completeIdentityCount: number;
  pubchemLinkedCount: number;
  repeatAnalysisCount: number;
  enrichmentGapCount: number;
}

export function normalizeCompoundSearchInput(value: string): string {
  return value.slice(0, MAX_COMPOUND_SEARCH_LENGTH);
}

export function formatWeight(weight: number | null): string {
  if (weight === null) return "\u2014";
  return `${weight.toFixed(1)} g/mol`;
}

export function formatCompoundDate(date: string | Date | null): string {
  if (!date) return "\u2014";
  const parsedDate = typeof date === "string" ? new Date(date) : date;
  if (Number.isNaN(parsedDate.getTime())) return "\u2014";
  return COMPOUND_DATE_FORMATTER.format(parsedDate);
}

export function formatAnalysisCount(count: number): string {
  return `${count.toLocaleString()} ${count === 1 ? "analysis" : "analyses"}`;
}

export function getLatestCompoundDate(compounds: CompoundItem[]): string {
  let latestTimestamp = 0;

  compounds.forEach((compound) => {
    const timestamp = Date.parse(compound.first_analyzed_at);
    if (!Number.isNaN(timestamp) && timestamp > latestTimestamp) {
      latestTimestamp = timestamp;
    }
  });

  return latestTimestamp
    ? formatCompoundDate(new Date(latestTimestamp))
    : "\u2014";
}

export function getVisibleFunctionalGroupCount(
  compounds: CompoundItem[],
): number {
  const groups = new Set<string>();

  compounds.forEach((compound) => {
    normalizeFunctionalGroups(compound.functional_groups).forEach((group) => {
      groups.add(group.toLowerCase());
    });
  });

  return groups.size;
}

export function getCompoundIdentityReadiness(
  compounds: CompoundItem[],
): CompoundIdentityReadiness {
  return compounds.reduce<CompoundIdentityReadiness>(
    (summary, compound) => {
      const hasCoreIdentity =
        Boolean(compound.canonical_smiles.trim()) &&
        Boolean(compound.inchi_key.trim()) &&
        Boolean(compound.molecular_formula.trim()) &&
        compound.molecular_weight !== null;
      const hasEnrichmentGap =
        !hasCoreIdentity ||
        compound.pubchem_cid === null ||
        normalizeFunctionalGroups(compound.functional_groups).length === 0;

      if (hasCoreIdentity) summary.completeIdentityCount += 1;
      if (compound.pubchem_cid !== null) summary.pubchemLinkedCount += 1;
      if (compound.analysis_count > 1) summary.repeatAnalysisCount += 1;
      if (hasEnrichmentGap) summary.enrichmentGapCount += 1;

      return summary;
    },
    {
      completeIdentityCount: 0,
      pubchemLinkedCount: 0,
      repeatAnalysisCount: 0,
      enrichmentGapCount: 0,
    },
  );
}

export function getCompoundDetailId(compoundId: string): string {
  return `compound-detail-${compoundId.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

export function normalizeFunctionalGroups(groups: string[]): string[] {
  const normalizedGroups = new Map<string, string>();

  groups.forEach((group) => {
    const displayGroup = group.trim();
    const normalizedKey = displayGroup.toLowerCase();

    if (displayGroup && !normalizedGroups.has(normalizedKey)) {
      normalizedGroups.set(normalizedKey, displayGroup);
    }
  });

  return Array.from(normalizedGroups.values());
}
