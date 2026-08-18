/**
 * Shared contract barrel for the web app.
 *
 * The generated payload lives in `generated.ts` and is rewritten by
 * `bash scripts/generate-types.sh`.
 */

import type * as Generated from "./generated";

export * from "./generated";

type StripIndex<T> = {
  [K in keyof T as K extends string
    ? string extends K
      ? never
      : K
    : K extends number
      ? number extends K
        ? never
        : K
      : K extends symbol
        ? symbol extends K
          ? never
          : K
        : never]: T[K];
};

type Simplify<T> = { [K in keyof T]: T[K] } & {};

type Replace<T, R> = Simplify<Omit<StripIndex<T>, keyof R> & R>;

export type SourceStatus = Generated.SourceStatus2;

export type PatentTermBreakdown = {
  a_delay_days: number;
  b_delay_days: number;
  c_delay_days: number;
  overlap_days: number;
  applicant_delay_days: number;
  total_days: number;
};

export type PatentTermInfo = {
  patent_id: string;
  effective_filing_date?: string | null;
  grant_date?: string | null;
  base_expiry?: string | null;
  pta_days: number;
  pta_breakdown?: PatentTermBreakdown | null;
  pte_days: number;
  terminal_disclaimer: boolean;
  td_linked_patent: string;
  td_linked_expiry?: string | null;
  maintenance_fee_status: "paid" | "lapsed" | "grace_period" | "unknown";
  maintenance_fee_next_due?: string | null;
  adjusted_expiry?: string | null;
  calculation_confidence: number;
  calculation_notes: string[];
};

export type LegalEvent = {
  event_date?: string | null;
  event_code: string;
  event_description: string;
  country: string;
};

export type PatentFamilyMember = {
  country: string;
  doc_number: string;
  kind: string;
};

export type PatentFamily = {
  family_id: string;
  members: PatentFamilyMember[];
  jurisdictions?: string[];
  earliest_priority_date?: string | null;
};

export type PatentHit = {
  patent_id: string;
  title: string;
  abstract: string;
  claims_text: string;
  claims_text_source?: string;
  sources: string[];
  confidence_score: number;
  filing_date: string | null;
  priority_date?: string | null;
  expiry_date?: string | null;
  assignees: string[];
  inventors: string[];
  cpc_codes: string[];
  legal_status: string;
  match_type: string;
  tanimoto_score?: number | null;
  jurisdiction?: string;
  family_id?: string;
  citations?: string[];
  cited_by?: string[];
  is_granted: boolean;
  application_number?: string;
  examiner?: string;
  attorney?: string;
  legal_events: LegalEvent[];
  family?: PatentFamily | null;
  family_broadest?: boolean;
  family_role?: string;
  parent_application_id?: string;
  patent_term_info?: PatentTermInfo | null;
};

export type AgentToolCall = {
  tool_name: string;
  tool_input?: Record<string, unknown>;
  tool_input_summary?: string;
  tool_output_summary: string;
  duration_ms: number;
};

export type AgentRound = {
  round_number: number;
  agent_name?: string;
  role?: string;
  reasoning?: string;
  output?: string;
  thinking_summary: string;
  tool_calls: AgentToolCall[];
  observations: string;
  scratchpad_delta: Record<string, unknown>;
  decision: string;
  input_tokens?: number;
  output_tokens?: number;
  duration_ms?: number;
  revisions?: string[];
};

export type ReasoningTrace = {
  patent_id: string;
  step?: string;
  model: string;
  summary?: string;
  agent_type: string;
  confidence: number;
  self_critique: string;
  revisions_made: string[];
  final_output_summary: string;
  rounds: AgentRound[];
  total_input_tokens: number;
  total_output_tokens: number;
  total_duration_ms: number;
};

export type ResolvedCompound = Replace<
  Generated.ResolvedCompound,
  {
    name: string;
    canonical_smiles: string;
    inchi_key: string;
    molecular_formula: string;
    synonyms: string[];
    cas_numbers: string[];
    functional_groups: string[];
    related_compounds: Generated.RelatedCompound[];
  }
>;

export type RiskSummary = Replace<
  Generated.RiskSummary,
  {
    blocking_patents_count: number;
    total_patents_analyzed: number;
    key_risks: string[];
    summary_validation_issues: string[];
  }
>;

export type ClaimElement = Replace<
  Generated.ClaimElement,
  {
    confidence: number;
    evidence: string;
  }
>;

export type ClaimAnalysis = Replace<
  Generated.ClaimAnalysis,
  {
    preamble: string;
    transitional_phrase: string | null;
    elements: ClaimElement[];
    reasoning: string;
    overall_confidence: number;
  }
>;

export type DesignAroundSuggestion = Replace<
  Generated.DesignAroundSuggestion,
  {
    feasibility: string;
  }
>;

export type EstoppelResult = Replace<
  Generated.EstoppelResult,
  {
    amendments_found: string[];
    estoppel_applies: boolean;
    surrendered_scope: string;
    file_wrapper_available: boolean;
    rejections_found: string[];
    prosecution_narrowing_count: number;
  }
>;

export type DoEAssessment = Replace<
  Generated.DoEAssessment,
  {
    element_text: string;
    estoppel: EstoppelResult;
    fwr: Generated.FWRAssessment | null;
    overall_equivalent: boolean;
    confidence: number;
    confidence_band: "HIGH" | "MODERATE" | "LOW";
    reasoning: string;
  }
>;

export type OrangeBookInfo = Replace<
  Generated.OrangeBookInfo,
  {
    is_listed: boolean;
    nda_numbers: string[];
    product_names: string[];
    active_ingredients: string[];
    drug_substance_patent: boolean;
    drug_product_patent: boolean;
    patent_use_codes: string[];
    exclusivities: Array<{
      code: string;
      expiration_date: string;
    }>;
    pediatric_exclusivity: boolean;
    delist_requested: boolean;
    delisted?: never;
  }
>;

export type ClaimChart = Replace<
  Generated.ClaimChart,
  {
    entries: Generated.ClaimChartEntry[];
    all_elements_disclosed: boolean;
    chart_summary: string;
  }
>;

export type PTABProceeding = Replace<
  Generated.PTABProceeding,
  {
    claims_challenged: number[];
    claims_cancelled: number[];
    claims_survived: number[];
    outcome_summary: string;
  }
>;

export type PTABResult = Replace<
  Generated.PTABResult,
  {
    has_been_challenged: boolean;
    proceedings: PTABProceeding[];
    all_claims_cancelled: number[];
  }
>;

export type PriorArtReference = Replace<
  Generated.PriorArtReference,
  {
    title: string;
    publication_date: string | null;
    relevance: string;
    anticipation_score: number;
    obviousness_score: number;
    reference_type: "patent" | "journal_article" | "conference_paper" | "preprint";
    authors: string[];
    journal: string;
    doi: string;
    url: string;
    abstract: string;
    source_database: "semantic_scholar" | "openalex" | "lens" | "bigquery" | "pubmed" | "";
  }
>;

export type EnablementScreening = Replace<
  Generated.EnablementScreening,
  {
    genus_claim_detected: boolean;
    genus_indicators: string[];
    specification_enables_full_scope: "yes" | "no" | "unclear";
    amgen_v_sanofi_flags: string[];
    reasoning: string;
  }
>;

export type InvalidityAssessment = Replace<
  Generated.InvalidityAssessment,
  {
    claim_numbers: number[];
    ptab: PTABResult;
    prior_art: PriorArtReference[];
    written_description_issues: string[];
    claim_charts: ClaimChart[];
    graham_factors: Generated.GrahamFactors | null;
    enablement_screening: EnablementScreening | null;
    overall_invalidity_strength: string;
    reasoning: string;
    confidence: number;
    confidence_band: "HIGH" | "MODERATE" | "LOW";
    screening_disclaimer: string;
  }
>;

export type PatentAnalysis = Replace<
  Generated.PatentAnalysis,
  {
    title: string;
    assignee: string;
    expiry_date: string | null;
    claims_analyzed: ClaimAnalysis[];
    design_around_suggestions: DesignAroundSuggestion[];
    orange_book_info: OrangeBookInfo | null;
    model_used: string;
    thinking_text: string;
    input_tokens: number;
    output_tokens: number;
  }
>;

export type ActionItem = Replace<
  Generated.ActionItem,
  {
    patent_ids: string[];
    reasoning: string;
    estimated_timeline: string;
  }
>;

export type SourceHealthEntry = Replace<
  Generated.SourceHealthEntry,
  {
    status: SourceStatus;
    patent_count: number;
    error_message: string;
  }
>;

export type SourceHealth = Replace<
  Generated.SourceHealth,
  {
    entries: SourceHealthEntry[];
  }
>;

export type SearchFunnelEntry = Replace<
  Generated.SearchFunnelEntry,
  {
    sources_found_in: string[];
    passed_hard_filter: boolean;
    filter_reason: string;
    composite_score: number | null;
    bm25_score: number | null;
    final_blend_score: number | null;
    final_rank: number | null;
    included_in_triage: boolean;
    family_broadest?: boolean;
  }
>;

export type TriageAuditEntry = Replace<
  Generated.TriageAuditEntry,
  {
    confidence: number;
    passed_triage: boolean;
  }
>;

export type AnalysisAuditEntry = Replace<
  Generated.AnalysisAuditEntry,
  {
    selection_reason: string;
    risk_level: Generated.RiskLevel | string | null;
    selected_for_doe: boolean;
    selected_for_invalidity: boolean;
  }
>;

export type PipelineAuditTrail = Replace<
  Generated.PipelineAuditTrail,
  {
    search_funnel: SearchFunnelEntry[];
    triage_audit: TriageAuditEntry[];
    analysis_audit: AnalysisAuditEntry[];
    timing_data: Generated.StepTiming[];
    total_patents_discovered: number;
    patents_after_hard_filter: number;
    patents_after_ranking: number;
    patents_after_triage: number;
    patents_analyzed: number;
  }
>;

export type VerificationCheck = Replace<
  Generated.VerificationCheck,
  {
    severity: "pass" | "warning" | "fail";
    details: string;
  }
>;

export type VerificationResult = Replace<
  Generated.VerificationResult,
  {
    checks: VerificationCheck[];
    all_citations_valid: boolean;
    all_claims_grounded: boolean;
    all_entities_valid: boolean;
    dates_consistent: boolean;
    risk_levels_justified: boolean;
    issues: string[];
  }
>;

export type StepTokenUsage = Replace<
  Generated.StepTokenUsage,
  {
    model_name: string;
    input_tokens: number;
    output_tokens: number;
  }
>;

export type FTOReport = Replace<
  Generated.FTOReport,
  {
    report_id: string;
    generated_at: string;
    praviar_pipeline_version: string;
    compound: ResolvedCompound;
    risk_summary: RiskSummary;
    patent_analyses: PatentAnalysis[];
    doe_assessments: DoEAssessment[];
    invalidity_assessments: InvalidityAssessment[];
    verification: VerificationResult;
    total_patents_found: number;
    patents_after_triage: number;
    search_sources_used: string[];
    source_health: SourceHealth;
    analysis_failures: Generated.AnalysisFailure[];
    data_limitations: Generated.DataLimitation[];
    audit_trail: PipelineAuditTrail;
    patent_narratives: Record<string, string>;
    disclaimer: string;
    llm_models_used: Record<string, string>;
    reasoning_traces?: ReasoningTrace[];
    patent_details?: Record<string, PatentHit>;
    action_items?: ActionItem[];
    step_token_usage: StepTokenUsage[];
    total_input_tokens: number;
    total_output_tokens: number;
  }
>;
