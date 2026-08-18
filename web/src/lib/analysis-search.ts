export const ANALYSIS_SEARCH_MAX_LENGTH = 200;

export function clampAnalysisSearchInput(value: string): string {
  return value.slice(0, ANALYSIS_SEARCH_MAX_LENGTH);
}

export function normalizeAnalysisSearch(
  value: string | null | undefined,
): string {
  return clampAnalysisSearchInput(value?.trim() ?? "");
}
