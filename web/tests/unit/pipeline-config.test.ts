import { describe, expect, it } from "vitest";
import {
  pipelineConfigToStore,
  storeToPipelineConfig,
} from "@/lib/pipeline-config";

const storeSnapshot = {
  searchMaxRankedResults: 250,
  searchTanimotoThreshold: 0.72,
  includeExpired: true,
  enablePubchem: true,
  enableBigquery: false,
  enableSurechembl: true,
  enablePatcid: false,
  maxAnalysisPatents: 42,
  maxDoeCandidates: 7,
  triageBatchSize: 9,
  claudeDeepModel: "claude-deep",
  claudeTriageModel: "claude-triage",
  citationTraversalEnabled: true,
  citationMaxDepth: 3,
  analysisThinkingBudget: 12000,
  expiredGraceYears: 4,
  searchJurisdictions: ["US", "EP", "WO"],
  thinkingEffortAnalysis: "high",
  thinkingEffortTriage: "medium",
  thinkingEffortReport: "low",
  hitlEnabled: true,
  hitlCheckpoints: ["search_review", "report_review"],
  hitlAutoSkipMinutes: 12,
} as any;

describe("pipeline config mapping", () => {
  it("converts config store state to API pipeline config keys", () => {
    expect(storeToPipelineConfig(storeSnapshot)).toEqual({
      search_max_ranked_results: 250,
      search_tanimoto_threshold: 0.72,
      include_expired: true,
      enable_pubchem: true,
      enable_bigquery: false,
      enable_surechembl: true,
      enable_patcid: false,
      max_analysis_patents: 42,
      max_doe_candidates: 7,
      triage_batch_size: 9,
      citation_traversal_enabled: true,
      citation_max_depth: 3,
      analysis_thinking_budget_tokens: 12000,
      search_expired_grace_years: 4,
      search_jurisdictions: ["US", "EP", "WO"],
      thinking_effort_analysis: "high",
      thinking_effort_triage: "medium",
      thinking_effort_report: "low",
      hitl_enabled: true,
      hitl_checkpoints: ["search_review", "report_review"],
      hitl_auto_skip_minutes: 12,
    });
  });

  it("converts partial API config payloads back to store keys", () => {
    expect(
      pipelineConfigToStore({
        search_max_ranked_results: 300,
        search_tanimoto_threshold: 0.66,
        include_expired: false,
        enable_pubchem: false,
        enable_bigquery: true,
        enable_surechembl: false,
        enable_patcid: true,
        max_analysis_patents: 15,
        max_doe_candidates: 5,
        triage_batch_size: 12,
        claude_deep_model: "deep-v2",
        claude_triage_model: "triage-v2",
        citation_traversal_enabled: false,
        citation_max_depth: 2,
        analysis_thinking_budget_tokens: 8000,
        search_expired_grace_years: 8,
        search_jurisdictions: ["JP"],
        thinking_effort_analysis: "medium",
        thinking_effort_triage: "low",
        thinking_effort_report: "high",
        hitl_enabled: true,
        hitl_checkpoints: ["triage_review"],
        hitl_auto_skip_minutes: 15,
      } as any),
    ).toEqual({
      searchMaxRankedResults: 300,
      searchTanimotoThreshold: 0.66,
      includeExpired: false,
      enablePubchem: false,
      enableBigquery: true,
      enableSurechembl: false,
      enablePatcid: true,
      maxAnalysisPatents: 15,
      maxDoeCandidates: 5,
      triageBatchSize: 12,
      citationTraversalEnabled: false,
      citationMaxDepth: 2,
      analysisThinkingBudget: 8000,
      expiredGraceYears: 8,
      searchJurisdictions: ["JP"],
      thinkingEffortAnalysis: "medium",
      thinkingEffortTriage: "low",
      thinkingEffortReport: "high",
      hitlEnabled: true,
      hitlCheckpoints: ["triage_review"],
      hitlAutoSkipMinutes: 15,
    });
  });

  it("leaves omitted API config fields untouched", () => {
    expect(pipelineConfigToStore({ enable_pubchem: true } as any)).toEqual({
      enablePubchem: true,
    });
  });
});
