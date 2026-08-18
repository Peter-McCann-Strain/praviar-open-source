import { describe, it, expect, beforeEach } from "vitest";
import { useConfigStore } from "@/stores/config-store";

const DEFAULTS = {
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
};

beforeEach(() => {
  useConfigStore.getState().reset();
});

describe("config-store", () => {
  describe("default values", () => {
    it("has correct default searchMaxRankedResults", () => {
      expect(useConfigStore.getState().searchMaxRankedResults).toBe(200);
    });

    it("has correct default searchTanimotoThreshold", () => {
      expect(useConfigStore.getState().searchTanimotoThreshold).toBe(0.55);
    });

    it("has correct default includeExpired", () => {
      expect(useConfigStore.getState().includeExpired).toBe(true);
    });

    it("has correct default jurisdiction", () => {
      expect(useConfigStore.getState().jurisdiction).toBe("US");
    });

    it("has all data sources enabled by default", () => {
      const state = useConfigStore.getState();
      expect(state.enablePubchem).toBe(true);
      expect(state.enableBigquery).toBe(true);
      expect(state.enableSurechembl).toBe(true);
      expect(state.enablePatcid).toBe(true);
    });

    it("has correct default maxAnalysisPatents", () => {
      expect(useConfigStore.getState().maxAnalysisPatents).toBe(20);
    });

    it("has correct default maxDoeCandidates", () => {
      expect(useConfigStore.getState().maxDoeCandidates).toBe(15);
    });

    it("has correct default triageBatchSize", () => {
      expect(useConfigStore.getState().triageBatchSize).toBe(10);
    });

    it("does not expose public claude model controls", () => {
      const state = useConfigStore.getState();
      expect((state as any).claudeDeepModel).toBeUndefined();
      expect((state as any).claudeTriageModel).toBeUndefined();
    });

    it("has correct default citation settings", () => {
      const state = useConfigStore.getState();
      expect(state.citationTraversalEnabled).toBe(true);
      expect(state.citationMaxDepth).toBe(2);
    });

    it("has correct default analysisThinkingBudget", () => {
      expect(useConfigStore.getState().analysisThinkingBudget).toBe(12000);
    });

    it("has correct default expiredGraceYears", () => {
      expect(useConfigStore.getState().expiredGraceYears).toBe(5);
    });
  });

  describe("setConfig", () => {
    it("partially updates state", () => {
      useConfigStore.getState().setConfig({ searchMaxRankedResults: 300 });
      expect(useConfigStore.getState().searchMaxRankedResults).toBe(300);
    });

    it("preserves other values when partially updating", () => {
      useConfigStore.getState().setConfig({ jurisdiction: "EU" });

      const state = useConfigStore.getState();
      expect(state.jurisdiction).toBe("EU");
      expect(state.searchMaxRankedResults).toBe(200);
      expect(state.searchTanimotoThreshold).toBe(0.55);
    });

    it("can update multiple values at once", () => {
      useConfigStore.getState().setConfig({
        searchMaxRankedResults: 400,
        maxAnalysisPatents: 25,
        includeExpired: false,
      });

      const state = useConfigStore.getState();
      expect(state.searchMaxRankedResults).toBe(400);
      expect(state.maxAnalysisPatents).toBe(25);
      expect(state.includeExpired).toBe(false);
    });
  });

  describe("applyPreset", () => {
    it("applies quick preset correctly", () => {
      useConfigStore.getState().applyPreset("quick");

      const state = useConfigStore.getState();
      expect(state.searchMaxRankedResults).toBe(50);
      expect(state.maxAnalysisPatents).toBe(5);
      expect(state.maxDoeCandidates).toBe(5);
      expect((state as any).claudeDeepModel).toBeUndefined();
      expect((state as any).claudeTriageModel).toBeUndefined();
      expect(state.citationTraversalEnabled).toBe(false);
      expect(state.citationMaxDepth).toBe(1);
      expect(state.analysisThinkingBudget).toBe(6000);
      expect(state.expiredGraceYears).toBe(3);
    });

    it("applies quick preset and resets non-preset values to defaults", () => {
      useConfigStore.getState().setConfig({ jurisdiction: "EU" });
      useConfigStore.getState().applyPreset("quick");

      expect(useConfigStore.getState().jurisdiction).toBe("US");
    });

    it("applies standard preset correctly", () => {
      // First apply quick to change values
      useConfigStore.getState().applyPreset("quick");
      // Then apply standard
      useConfigStore.getState().applyPreset("standard");

      const state = useConfigStore.getState();
      expect(state.searchMaxRankedResults).toBe(200);
      expect(state.maxAnalysisPatents).toBe(20);
      expect(state.maxDoeCandidates).toBe(15);
      expect((state as any).claudeDeepModel).toBeUndefined();
      expect((state as any).claudeTriageModel).toBeUndefined();
      expect(state.citationTraversalEnabled).toBe(true);
      expect(state.citationMaxDepth).toBe(2);
      expect(state.analysisThinkingBudget).toBe(12000);
      expect(state.expiredGraceYears).toBe(5);
    });

    it("applies thorough preset correctly", () => {
      useConfigStore.getState().applyPreset("thorough");

      const state = useConfigStore.getState();
      expect(state.searchMaxRankedResults).toBe(500);
      expect(state.maxAnalysisPatents).toBe(30);
      expect(state.maxDoeCandidates).toBe(20);
      expect((state as any).claudeDeepModel).toBeUndefined();
      expect((state as any).claudeTriageModel).toBeUndefined();
      expect(state.citationTraversalEnabled).toBe(true);
      expect(state.citationMaxDepth).toBe(3);
      expect(state.analysisThinkingBudget).toBe(20000);
      expect(state.expiredGraceYears).toBe(5);
    });
  });

  describe("reset", () => {
    it("restores all values to defaults", () => {
      useConfigStore.getState().setConfig({
        searchMaxRankedResults: 500,
        jurisdiction: "EU",
        enablePubchem: false,
        maxAnalysisPatents: 30,
      });

      useConfigStore.getState().reset();

      const state = useConfigStore.getState();
      expect(state.searchMaxRankedResults).toBe(
        DEFAULTS.searchMaxRankedResults,
      );
      expect(state.searchTanimotoThreshold).toBe(
        DEFAULTS.searchTanimotoThreshold,
      );
      expect(state.includeExpired).toBe(DEFAULTS.includeExpired);
      expect(state.jurisdiction).toBe(DEFAULTS.jurisdiction);
      expect(state.enablePubchem).toBe(DEFAULTS.enablePubchem);
      expect(state.maxAnalysisPatents).toBe(DEFAULTS.maxAnalysisPatents);
      expect(state.maxDoeCandidates).toBe(DEFAULTS.maxDoeCandidates);
      expect(state.triageBatchSize).toBe(DEFAULTS.triageBatchSize);
    });

    it("restores defaults after a preset was applied", () => {
      useConfigStore.getState().applyPreset("quick");
      useConfigStore.getState().reset();

      const state = useConfigStore.getState();
      expect(state.searchMaxRankedResults).toBe(200);
      expect(state.maxAnalysisPatents).toBe(20);
      expect((state as any).claudeDeepModel).toBeUndefined();
      expect((state as any).claudeTriageModel).toBeUndefined();
    });
  });
});
