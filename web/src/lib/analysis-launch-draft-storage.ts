"use client";

export const ANALYSIS_LAUNCH_DRAFT_STORAGE_PREFIX =
  "praviar:analysis-launch-draft:";

export function clearAnalysisLaunchDraftStorage(): void {
  if (typeof window === "undefined") return;

  for (const storage of [window.localStorage, window.sessionStorage]) {
    try {
      const keysToRemove: string[] = [];
      for (let index = 0; index < storage.length; index += 1) {
        const key = storage.key(index);
        if (key?.startsWith(ANALYSIS_LAUNCH_DRAFT_STORAGE_PREFIX)) {
          keysToRemove.push(key);
        }
      }
      keysToRemove.forEach((key) => storage.removeItem(key));
    } catch {
      // Authentication-boundary cleanup is best-effort. Draft reads still fail
      // closed because every envelope is bound to the active auth/org scope.
    }
  }
}
