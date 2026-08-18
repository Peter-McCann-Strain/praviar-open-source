import type { PipelineConfig } from "@/types/pipeline";
import type { ConfigState } from "@/stores/config-store";

type ConfigSnapshot = Pick<
  ConfigState,
  | "searchMaxRankedResults"
  | "searchTanimotoThreshold"
  | "includeExpired"
  | "enablePubchem"
  | "enableBigquery"
  | "enableSurechembl"
  | "enablePatcid"
  | "maxAnalysisPatents"
  | "maxDoeCandidates"
  | "triageBatchSize"
  | "citationTraversalEnabled"
  | "citationMaxDepth"
  | "analysisThinkingBudget"
  | "expiredGraceYears"
  | "searchJurisdictions"
  | "thinkingEffortAnalysis"
  | "thinkingEffortTriage"
  | "thinkingEffortReport"
  | "hitlEnabled"
  | "hitlCheckpoints"
  | "hitlAutoSkipMinutes"
>;

export function storeToPipelineConfig(state: ConfigSnapshot): PipelineConfig {
  return {
    search_max_ranked_results: state.searchMaxRankedResults,
    search_tanimoto_threshold: state.searchTanimotoThreshold,
    include_expired: state.includeExpired,
    enable_pubchem: state.enablePubchem,
    enable_bigquery: state.enableBigquery,
    enable_surechembl: state.enableSurechembl,
    enable_patcid: state.enablePatcid,
    max_analysis_patents: state.maxAnalysisPatents,
    max_doe_candidates: state.maxDoeCandidates,
    triage_batch_size: state.triageBatchSize,
    citation_traversal_enabled: state.citationTraversalEnabled,
    citation_max_depth: state.citationMaxDepth,
    analysis_thinking_budget_tokens: state.analysisThinkingBudget,
    search_expired_grace_years: state.expiredGraceYears,
    search_jurisdictions: state.searchJurisdictions,
    thinking_effort_analysis: state.thinkingEffortAnalysis,
    thinking_effort_triage: state.thinkingEffortTriage,
    thinking_effort_report: state.thinkingEffortReport,
    hitl_enabled: state.hitlEnabled,
    hitl_checkpoints: state.hitlCheckpoints,
    hitl_auto_skip_minutes: state.hitlAutoSkipMinutes,
  };
}

export function pipelineConfigToStore(
  config: Partial<PipelineConfig>,
): Partial<ConfigState> {
  const next: Partial<ConfigState> = {};

  if (config.search_max_ranked_results !== undefined) {
    next.searchMaxRankedResults = config.search_max_ranked_results;
  }
  if (config.search_tanimoto_threshold !== undefined) {
    next.searchTanimotoThreshold = config.search_tanimoto_threshold;
  }
  if (config.include_expired !== undefined) {
    next.includeExpired = config.include_expired;
  }
  if (config.enable_pubchem !== undefined) {
    next.enablePubchem = config.enable_pubchem;
  }
  if (config.enable_bigquery !== undefined) {
    next.enableBigquery = config.enable_bigquery;
  }
  if (config.enable_surechembl !== undefined) {
    next.enableSurechembl = config.enable_surechembl;
  }
  if (config.enable_patcid !== undefined) {
    next.enablePatcid = config.enable_patcid;
  }
  if (config.max_analysis_patents !== undefined) {
    next.maxAnalysisPatents = config.max_analysis_patents;
  }
  if (config.max_doe_candidates !== undefined) {
    next.maxDoeCandidates = config.max_doe_candidates;
  }
  if (config.triage_batch_size !== undefined) {
    next.triageBatchSize = config.triage_batch_size;
  }
  if (config.citation_traversal_enabled !== undefined) {
    next.citationTraversalEnabled = config.citation_traversal_enabled;
  }
  if (config.citation_max_depth !== undefined) {
    next.citationMaxDepth = config.citation_max_depth;
  }
  if (config.analysis_thinking_budget_tokens !== undefined) {
    next.analysisThinkingBudget = config.analysis_thinking_budget_tokens;
  }
  if (config.search_expired_grace_years !== undefined) {
    next.expiredGraceYears = config.search_expired_grace_years;
  }
  if (config.search_jurisdictions !== undefined) {
    next.searchJurisdictions = config.search_jurisdictions;
  }
  if (config.thinking_effort_analysis !== undefined) {
    next.thinkingEffortAnalysis = config.thinking_effort_analysis;
  }
  if (config.thinking_effort_triage !== undefined) {
    next.thinkingEffortTriage = config.thinking_effort_triage;
  }
  if (config.thinking_effort_report !== undefined) {
    next.thinkingEffortReport = config.thinking_effort_report;
  }
  if (config.hitl_enabled !== undefined) {
    next.hitlEnabled = config.hitl_enabled;
  }
  if (config.hitl_checkpoints !== undefined) {
    next.hitlCheckpoints = config.hitl_checkpoints;
  }
  if (config.hitl_auto_skip_minutes !== undefined) {
    next.hitlAutoSkipMinutes = config.hitl_auto_skip_minutes;
  }

  return next;
}
