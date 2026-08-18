export const TRIAGE_RELEVANCE_SWATCH_COLORS: Record<string, string> = {
  relevant: "var(--color-success)",
  possibly_relevant: "var(--color-warning)",
  not_relevant: "var(--text-tertiary)",
};

export const TRIAGE_RELEVANCE_FALLBACK_SWATCH_COLOR = "var(--text-tertiary)";

export function formatTriageRelevanceLabel(relevance: string) {
  return relevance.replace(/_/g, " ");
}
