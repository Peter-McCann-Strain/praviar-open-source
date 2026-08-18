import { create } from "zustand";
import { persist } from "zustand/middleware";
import {
  JURISDICTION_BUNDLE_DEFINITIONS,
  toggleTargetJurisdiction as toggleTargetJurisdictionUtil,
  normalizeTargetJurisdictions,
} from "@/lib/jurisdiction-bundles";
import type {
  JurisdictionBundle,
  MajorMarketJurisdiction,
} from "@/types/pipeline";

export type TrustMode = "explorer" | "counsel" | "monitor";

export interface ConfigState {
  hydratedAuthScope: string | null;
  trustMode: TrustMode;
  jurisdictionBundle: JurisdictionBundle;
  targetJurisdictions: MajorMarketJurisdiction[];
  searchMaxRankedResults: number;
  searchTanimotoThreshold: number;
  includeExpired: boolean;
  jurisdiction: string;
  enablePubchem: boolean;
  enableBigquery: boolean;
  enableSurechembl: boolean;
  enablePatcid: boolean;
  maxAnalysisPatents: number;
  maxDoeCandidates: number;
  triageBatchSize: number;
  citationTraversalEnabled: boolean;
  citationMaxDepth: number;
  analysisThinkingBudget: number;
  expiredGraceYears: number;
  searchJurisdictions: string[];
  thinkingEffortAnalysis: "high" | "medium" | "low";
  thinkingEffortTriage: "high" | "medium" | "low";
  thinkingEffortReport: "high" | "medium" | "low";
  hitlEnabled: boolean;
  hitlCheckpoints: string[];
  hitlAutoSkipMinutes: number;

  setConfig: (config: Partial<ConfigState>) => void;
  hydrateConfig: (config: Partial<ConfigState>, authScope: string) => void;
  applyJurisdictionBundle: (bundle: JurisdictionBundle) => void;
  setTargetJurisdictions: (jurisdictions: MajorMarketJurisdiction[]) => void;
  toggleTargetJurisdiction: (jurisdiction: MajorMarketJurisdiction) => void;
  applyPreset: (preset: "quick" | "standard" | "thorough") => void;
  reset: () => void;
  clearAuthScope: () => void;
}

const DEFAULT_JURISDICTION_BUNDLE: JurisdictionBundle = "major_markets";

const DEFAULTS = {
  hydratedAuthScope: null as string | null,
  trustMode: "counsel" as const,
  jurisdictionBundle: DEFAULT_JURISDICTION_BUNDLE,
  targetJurisdictions: [
    ...JURISDICTION_BUNDLE_DEFINITIONS[DEFAULT_JURISDICTION_BUNDLE]
      .targetJurisdictions,
  ],
  searchMaxRankedResults: 200,
  searchTanimotoThreshold: 0.55,
  includeExpired: true,
  jurisdiction: "US",
  enablePubchem: true,
  enableBigquery: true,
  enableSurechembl: true,
  enablePatcid: true,
  maxAnalysisPatents: 20,
  maxDoeCandidates: 15,
  triageBatchSize: 10,
  citationTraversalEnabled: true,
  citationMaxDepth: 2,
  analysisThinkingBudget: 12000,
  expiredGraceYears: 5,
  searchJurisdictions: ["US", "EP", "WO", "JP", "KR", "CN", "IN", "CA", "AU"],
  thinkingEffortAnalysis: "high" as const,
  thinkingEffortTriage: "medium" as const,
  thinkingEffortReport: "high" as const,
  hitlEnabled: false,
  hitlCheckpoints: [
    "search_review",
    "triage_review",
    "analysis_review",
    "report_review",
  ],
  hitlAutoSkipMinutes: 10,
};

/** Jurisdiction metadata for UI grouping and display. */
export const JURISDICTION_GROUPS = [
  {
    label: "Americas",
    items: [
      { code: "US", label: "United States" },
      { code: "CA", label: "Canada" },
    ],
  },
  {
    label: "Europe & International",
    items: [
      { code: "EP", label: "Europe (EPO)" },
      { code: "WO", label: "WIPO / PCT" },
    ],
  },
  {
    label: "Asia-Pacific",
    items: [
      { code: "JP", label: "Japan" },
      { code: "KR", label: "South Korea" },
      { code: "CN", label: "China" },
      { code: "IN", label: "India" },
      { code: "AU", label: "Australia" },
    ],
  },
] as const;

/** Preset metadata describing explicit scope and review limits for the UI. */
export const PRESET_META = {
  quick: {
    label: "Quick",
    scope: "US, Europe, PCT",
    reviewProfile: "Lower result and review limits",
    jurisdictionCount: 3,
  },
  standard: {
    label: "Standard",
    scope: "Americas, Europe + Asia",
    reviewProfile: "Balanced result and review limits",
    jurisdictionCount: 6,
  },
  thorough: {
    label: "Thorough",
    scope: "US, EP, WO, JP, KR, CN, IN, CA, AU",
    reviewProfile: "Expanded result and review limits",
    jurisdictionCount: 9,
  },
} as const;

export const PRESETS = {
  quick: {
    searchMaxRankedResults: 50,
    maxAnalysisPatents: 5,
    maxDoeCandidates: 5,
    citationTraversalEnabled: false,
    citationMaxDepth: 1,
    analysisThinkingBudget: 6000,
    expiredGraceYears: 3,
    searchJurisdictions: ["US", "EP", "WO"],
    thinkingEffortAnalysis: "medium" as const,
    thinkingEffortTriage: "low" as const,
    thinkingEffortReport: "medium" as const,
  },
  standard: {
    searchMaxRankedResults: 200,
    maxAnalysisPatents: 20,
    maxDoeCandidates: 15,
    citationTraversalEnabled: true,
    citationMaxDepth: 2,
    analysisThinkingBudget: 12000,
    expiredGraceYears: 5,
    searchJurisdictions: ["US", "EP", "WO", "JP", "KR", "CN"],
    thinkingEffortAnalysis: "high" as const,
    thinkingEffortTriage: "medium" as const,
    thinkingEffortReport: "high" as const,
  },
  thorough: {
    searchMaxRankedResults: 500,
    maxAnalysisPatents: 30,
    maxDoeCandidates: 20,
    citationTraversalEnabled: true,
    citationMaxDepth: 3,
    analysisThinkingBudget: 20000,
    expiredGraceYears: 5,
    searchJurisdictions: ["US", "EP", "WO", "JP", "KR", "CN", "IN", "CA", "AU"],
    thinkingEffortAnalysis: "high" as const,
    thinkingEffortTriage: "high" as const,
    thinkingEffortReport: "high" as const,
  },
};

export const useConfigStore = create<ConfigState>()(
  persist(
    (set) => ({
      ...DEFAULTS,
      setConfig: (config) =>
        set(() => {
          const next = { ...config };

          if (config.targetJurisdictions !== undefined) {
            next.targetJurisdictions = normalizeTargetJurisdictions(
              config.targetJurisdictions,
            );
            next.jurisdictionBundle = config.jurisdictionBundle ?? "custom";
          } else if (config.jurisdictionBundle !== undefined) {
            next.targetJurisdictions = [
              ...JURISDICTION_BUNDLE_DEFINITIONS[config.jurisdictionBundle]
                .targetJurisdictions,
            ];
          }

          return next;
        }),
      hydrateConfig: (config, authScope) =>
        set(() => {
          const next = { ...config, hydratedAuthScope: authScope };

          if (config.targetJurisdictions !== undefined) {
            next.targetJurisdictions = normalizeTargetJurisdictions(
              config.targetJurisdictions,
            );
            next.jurisdictionBundle = config.jurisdictionBundle ?? "custom";
          } else if (config.jurisdictionBundle !== undefined) {
            next.targetJurisdictions = [
              ...JURISDICTION_BUNDLE_DEFINITIONS[config.jurisdictionBundle]
                .targetJurisdictions,
            ];
          }

          return next;
        }),
      applyJurisdictionBundle: (bundle) =>
        set({
          jurisdictionBundle: bundle,
          targetJurisdictions: [
            ...JURISDICTION_BUNDLE_DEFINITIONS[bundle].targetJurisdictions,
          ],
        }),
      setTargetJurisdictions: (jurisdictions) =>
        set({
          jurisdictionBundle: "custom",
          targetJurisdictions: normalizeTargetJurisdictions(jurisdictions),
        }),
      toggleTargetJurisdiction: (jurisdiction) =>
        set((state) => ({
          jurisdictionBundle: "custom",
          targetJurisdictions: toggleTargetJurisdictionUtil(
            state.targetJurisdictions,
            jurisdiction,
          ),
        })),
      applyPreset: (preset) => set({ ...DEFAULTS, ...PRESETS[preset] }),
      reset: () =>
        set((state) => ({
          ...DEFAULTS,
          hydratedAuthScope: state.hydratedAuthScope,
        })),
      clearAuthScope: () => set(DEFAULTS),
    }),
    {
      name: "praviar-config",
      version: 2,
      migrate: (persisted) => {
        if (!persisted || typeof persisted !== "object") {
          return DEFAULTS as ConfigState;
        }
        const state = persisted as Partial<ConfigState> & {
          claudeDeepModel?: unknown;
          claudeTriageModel?: unknown;
        };
        delete state.claudeDeepModel;
        delete state.claudeTriageModel;
        return { ...DEFAULTS, ...state } as ConfigState;
      },
      partialize: (state) => {
        const {
          hydratedAuthScope: _hydratedAuthScope,
          claudeDeepModel: _claudeDeepModel,
          claudeTriageModel: _claudeTriageModel,
          ...safeState
        } = state as ConfigState & {
          claudeDeepModel?: unknown;
          claudeTriageModel?: unknown;
        };
        return safeState;
      },
    },
  ),
);
