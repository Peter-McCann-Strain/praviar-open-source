/**
 * AUTO-GENERATED FILE.
 *
 * Source of truth: praviar_pipeline.models.shared_contracts
 * Regenerate with: bash scripts/generate-types.sh
 */

/* tslint:disable */
/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

/**
 * Overall FTO risk level for a patent.
 */
export type RiskLevel = "high" | "medium" | "low" | "clear";
/**
 * Top-line clearance decision for the matter.
 */
export type ClearanceOutcome = "clear" | "unclear" | "blocked";
/**
 * Structured categories for decisive evidence references.
 */
export type DecisionEvidenceCategory =
  | "blocking_patent"
  | "clearance_support"
  | "source_failure"
  | "coverage_gap"
  | "verification_gap"
  | "future_risk"
  | "prosecution_signal";
/**
 * Certification status of the current matter cohort.
 */
export type CohortStatus = "certified" | "attorney_supervised" | "supporting_only";
/**
 * Top-line clearance decision for the matter.
 */
export type ClearanceOutcome1 = "clear" | "unclear" | "blocked";
/**
 * Whether the target compound meets a claim element.
 */
export type ElementStatus = "met" | "not_met" | "partially_met" | "unclear";
/**
 * Whether the target compound meets a claim element.
 */
export type ElementStatus1 = "met" | "not_met" | "partially_met" | "unclear";
/**
 * Expert perspective for multi-perspective analysis.
 */
export type PerspectiveType = "patent_attorney" | "medicinal_chemist" | "business_analyst";
/**
 * Canonical evidence artifact types captured during a run.
 */
export type EvidenceArtifactType =
  | "search_hit"
  | "claims_text"
  | "family_context"
  | "prosecution_dossier"
  | "ep_register_record"
  | "ptab_record"
  | "orange_book_record"
  | "claim_analysis"
  | "doe_assessment"
  | "invalidity_assessment"
  | "critic_review"
  | "verification"
  | "coverage_gap";
/**
 * Authority tier assigned to an evidence artifact.
 */
export type EvidenceAuthorityTier = "authoritative" | "supporting" | "discovery";
/**
 * Canonical adapter categories for the evidence fabric.
 */
export type EvidenceAdapterKind = "search" | "legal_record" | "regulatory" | "pipeline" | "policy" | "derived";
/**
 * Authority tier assigned to an evidence artifact.
 */
export type EvidenceAuthorityTier1 = "authoritative" | "supporting" | "discovery";
/**
 * Outcome of querying a single data source.
 */
export type SourceStatus = "ok" | "failed" | "skipped" | "not_configured";
/**
 * Collector state for one adapter against its expected record targets.
 */
export type EvidenceCollectionState = "collected" | "partial" | "missing" | "failed" | "not_applicable";
/**
 * Canonical adapter categories for the evidence fabric.
 */
export type EvidenceAdapterKind1 = "search" | "legal_record" | "regulatory" | "pipeline" | "policy" | "derived";
/**
 * Authority tier assigned to an evidence artifact.
 */
export type EvidenceAuthorityTier2 = "authoritative" | "supporting" | "discovery";
/**
 * Collector state for one adapter against its expected record targets.
 */
export type EvidenceCollectionState1 = "collected" | "partial" | "missing" | "failed" | "not_applicable";
/**
 * Outcome of querying a single data source.
 */
export type SourceStatus1 = "ok" | "failed" | "skipped" | "not_configured";
/**
 * Collector state for one adapter against its expected record targets.
 */
export type EvidenceCollectionState2 = "collected" | "partial" | "missing" | "failed" | "not_applicable";
/**
 * Priority assigned to an evidence-collection directive.
 */
export type EvidenceDirectivePriority = "critical" | "high" | "medium" | "low";
/**
 * Canonical node types for the matter graph.
 */
export type MatterNodeType =
  | "compound_variant"
  | "patent"
  | "application"
  | "family"
  | "claim"
  | "amendment"
  | "office_action"
  | "ptab_matter"
  | "ep_register_event"
  | "orange_book_entry"
  | "purple_book_entry"
  | "prior_art_reference"
  | "commercial_product";
/**
 * Canonical edge types for the matter graph.
 */
export type MatterEdgeType =
  | "roots"
  | "belongs_to_family"
  | "prosecuted_as"
  | "contains_claim"
  | "amended_by"
  | "challenged_by"
  | "listed_in"
  | "tracked_by";
/**
 * Collection status for one required evidence component.
 */
export type RecordComponentStatusValue = "collected" | "missing" | "failed" | "not_applicable";
/**
 * Severity assigned to an unresolved record contradiction.
 */
export type RecordContradictionSeverity = "critical" | "high" | "medium" | "low";
/**
 * Type of quality issue found by the critic.
 */
export type CriticIssueType =
  | "risk_claim_mismatch"
  | "internal_inconsistency"
  | "cross_patent_inconsistency"
  | "missing_limitation"
  | "infeasible_design_around"
  | "confidence_calibration"
  | "assignee_logic_inconsistency"
  | "missing_dependent_claim"
  | "transitional_phrase_issue";
/**
 * Severity of a critic finding.
 */
export type CriticIssueSeverity = "critical" | "major" | "minor" | "info";
/**
 * Outcome of querying a single data source.
 */
export type SourceStatus2 = "ok" | "failed" | "skipped" | "not_configured";
/**
 * Risk signal from drawing structure comparison to target compound.
 */
export type DrawingRiskLevel = "high" | "medium" | "low" | "none";
/**
 * Risk signal from drawing structure comparison to target compound.
 */
export type DrawingRiskLevel1 = "high" | "medium" | "low" | "none";
/**
 * Types of recommended next steps.
 */
export type ActionType = "license" | "design_around" | "challenge_ipr" | "monitor" | "accept_risk" | "halt";
/**
 * Priority level for action items.
 */
export type ActionPriority = "critical" | "high" | "medium" | "low";

/**
 * Server-attested counsel verification for one patent claim and proposed use.
 */
export interface ClaimedUseMatchReceipt {
  schema_version: "claimed-use-match-v3";
  analysis_id: string;
  org_id: string;
  report_id: string;
  report_fingerprint: string;
  accused_act_index: number;
  accused_act_sha256: string;
  patent_id: string;
  claim_number: number;
  controlling_claim_text_sha256: string;
  current_claim_receipt_sha256: string;
  /**
   * @minItems 1
   * @maxItems 20
   */
  controlling_claim_document_ids:
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ];
  declared_target_product_sha256: string;
  resolved_compound_identity_sha256: string;
  proposed_indication_sha256: string;
  proposed_label_use_sha256: string;
  label_carve_out_state: "none" | "partial" | "complete" | "unknown";
  claimed_use_match: true;
  product_identity_match: true;
  issuer_user_id: string;
  reviewer_role: "attorney";
  attestation_statement_version: "claimed-use-counsel-affirmation-v1";
  verified_at: string;
  /**
   * @minItems 1
   * @maxItems 50
   */
  evidence_references: [string, ...string[]];
  attestation_key_id: string;
  attestation_hmac_sha256: string;
  receipt_sha256: string;
}
/**
 * Complete Freedom-to-Operate report.
 */
export interface FTOReport {
  report_id?: string;
  generated_at?: string;
  praviar_pipeline_version?: string;
  compound: ResolvedCompound;
  risk_summary: RiskSummary;
  clearance_decision?: ClearanceDecision;
  decision_scope?: DecisionScope;
  supporting_scope?: DecisionScope;
  certification_scope?: CertificationScope;
  trust_mode?: "explorer" | "counsel" | "monitor";
  intended_actions?: string[];
  target_jurisdictions?: string[];
  jurisdiction_bundle?: string;
  development_stage?: string;
  asset_type_hint?: string;
  routing_profile?: {
    [k: string]: unknown;
  };
  opinion_readiness?: OpinionReadiness;
  cohort_status?: CohortStatus | null;
  jurisdiction_decisions?: JurisdictionDecision[];
  patent_analyses?: PatentAnalysis[];
  doe_assessments?: DoEAssessment[];
  invalidity_assessments?: InvalidityAssessment[];
  verification?: VerificationResult;
  prosecution_findings?: ProsecutionFinding[];
  prosecution_dossiers?: ProsecutionDossier[];
  claim_construction_record?: ClaimConstructionRecord;
  future_risk?: FutureRiskFinding[];
  commercial_exposure?: CommercialExposure;
  claim_program_decisions?: ClaimProgramDecision[];
  evidence_artifacts?: EvidenceArtifact[];
  evidence_adapter_results?: EvidenceAdapterResult[];
  collector_runs?: EvidenceCollectorRun[];
  evidence_collection_plan?: EvidenceCollectionDirective[];
  coverage_gaps?: CoverageGap[];
  matter_graph?: MatterGraph;
  matter_graph_summary?: MatterGraphSummary;
  matter_store?: MatterStore;
  authority_coverage?: AuthorityCoverage;
  record_completeness?: RecordCompleteness;
  run_observability?: RunObservability;
  matter_evidence_index?: MatterEvidenceIndex;
  claim_source_span_map?: ClaimSourceSpanMap;
  critic_report?: CriticReport | null;
  review_issues?: CriticFinding[];
  total_patents_found?: number;
  patents_after_triage?: number;
  search_sources_used?: string[];
  source_health?: SourceHealth;
  scholarly_prior_art_count?: number;
  /**
   * Patents that failed during analysis — never silently dropped
   */
  analysis_failures?: AnalysisFailure[];
  /**
   * Known gaps in data coverage that affect reliability
   */
  data_limitations?: DataLimitation[];
  audit_trail?: PipelineAuditTrail;
  /**
   * Per-patent natural language summaries keyed by patent_id
   */
  patent_narratives?: {
    [k: string]: string;
  };
  disclaimer?: string;
  /**
   * LLM model identifiers used for each pipeline role
   */
  llm_models_used?: {
    [k: string]: string;
  };
  /**
   * Per-patent drawing OCSR analysis from step 2.75
   */
  drawing_analyses?: PatentDrawingAnalysis[];
  /**
   * Aggregate drawing analysis statistics
   */
  drawing_summary?: {
    [k: string]: unknown;
  };
  search_loop_result?: SearchLoopResult | null;
  regulatory_exclusivity?: RegulatoryExclusivity | null;
  /**
   * Runtime profile that produced the report
   */
  execution_profile?: "world_class_adaptive";
  /**
   * Report assembly profile used by the unified pipeline
   */
  report_pipeline?: "world_class_adaptive";
  /**
   * Serialized ReasoningTrace objects from agentic escalation
   */
  reasoning_traces?: {
    [k: string]: unknown;
  }[];
  /**
   * Raw PatentHit data keyed by patent_id for frontend display
   */
  patent_details?: {
    [k: string]: {
      [k: string]: unknown;
    };
  };
  /**
   * Recommended next steps derived from analysis results
   */
  action_items?: ActionItem[];
  /**
   * Reference appendix entries from the unified report pipeline
   */
  bibliography?: {
    [k: string]: unknown;
  }[];
  /**
   * LLM verification results from the unified report pipeline
   */
  verification_summary?: {
    [k: string]: unknown;
  };
  /**
   * Fraction of verified claims that are correct in the unified report pipeline
   */
  factual_accuracy_rate?: number;
  total_input_tokens?: number;
  total_output_tokens?: number;
  estimated_cost_usd?: number;
  step_token_usage?: StepTokenUsage[];
  /**
   * Provenance manifest pinning prompt hashes, models, and run metadata.
   */
  manifest?: ReportManifest | null;
}
/**
 * Fully resolved compound identity — the foundation for all downstream steps.
 */
export interface ResolvedCompound {
  name: string;
  canonical_smiles?: string;
  inchi?: string;
  inchi_key?: string;
  pubchem_cid?: number | null;
  synonyms?: string[];
  cas_numbers?: string[];
  molecular_formula?: string;
  molecular_weight?: number | null;
  /**
   * Morgan/ECFP4 fingerprint, hex-encoded
   */
  morgan_fp?: string;
  /**
   * MACCS keys fingerprint, hex-encoded
   */
  maccs_keys?: string;
  functional_groups?: string[];
  /**
   * Murcko scaffold SMILES stripped of side chains. Used to broaden searches to Markush/genus claims covering the core ring system.
   */
  scaffold_smiles?: string;
  /**
   * Canonical SMILES after salt/counter-ion removal (e.g. HCl, Na, K stripped). Used to search for patents on the pharmacologically active free base rather than a specific salt form.
   */
  free_base_smiles?: string;
  /**
   * Canonical SMILES with all stereocentres and geometric isomerism removed. Used to search for patents covering the racemate when the query compound is a single enantiomer/diastereomer.
   */
  stereo_stripped_smiles?: string;
  /**
   * Short label when the input SMILES matches a supported prodrug-candidate motif (e.g. 'ester_prodrug', 'phosphate_prodrug'). It does not establish prodrug status; only validated, reviewer-approved candidate structures can extend search.
   */
  prodrug_pattern?: string | null;
  /**
   * Bounded RDKit tautomer-enumeration receipt. Alternate candidates never replace the resolved canonical identity.
   */
  tautomer_enumeration?: TautomerEnumerationRecord | null;
  /**
   * Conservative deprotection/hydrolysis hypotheses approved only as additional structure-search lanes; never substituted for the resolved identity.
   */
  prodrug_candidates?: DerivedStructureCandidate[];
  /**
   * Detected motifs for which no defensible one-step parent structure is generated.
   */
  unsupported_prodrug_motifs?: string[];
  related_compounds?: RelatedCompound[];
  /**
   * What the user originally typed
   */
  original_input: string;
  /**
   * Detected input type
   */
  input_type: "name" | "smiles" | "cas" | "inchi" | "inchikey";
  /**
   * Compound classification: small_molecule, biologic, or peptide
   */
  compound_type?: "small_molecule" | "biologic" | "peptide";
  /**
   * BLA number from FDA Purple Book
   */
  bla_number?: string;
  /**
   * Reference biologic product name
   */
  reference_product?: string;
  /**
   * Number of approved biosimilars
   */
  biosimilar_count?: number;
  /**
   * FDA GSRS Unique Ingredient Identifier
   */
  unii?: string;
  /**
   * FDA GSRS substance-record UUID
   */
  gsrs_uuid?: string;
  /**
   * FDA GSRS substance class
   */
  gsrs_substance_class?: string;
  /**
   * FDA GSRS definition type
   */
  gsrs_definition_type?: string;
  /**
   * FDA GSRS definition level
   */
  gsrs_definition_level?: string;
  /**
   * FDA GSRS record version
   */
  gsrs_record_version?: string;
  /**
   * openFDA UNII name-index update date returned with the exact-name lookup
   */
  gsrs_names_last_updated?: string;
  /**
   * openFDA substance-record dataset update date
   */
  gsrs_record_last_updated?: string;
  /**
   * Public, complete L-amino-acid subunit sequences bound to the exact FDA GSRS identity and eligible for patent-sequence retrieval.
   *
   * @maxItems 20
   */
  protein_subunit_sequences?:
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ];
}
/**
 * Deterministic RDKit tautomer-enumeration receipt.
 */
export interface TautomerEnumerationRecord {
  source_smiles: string;
  source_form: "canonical" | "salt_stripped_largest_fragment";
  engine: "RDKit MolStandardize TautomerEnumerator";
  engine_version: string;
  score_version: string;
  max_tautomers: number;
  max_transforms: number;
  status:
    | "completed"
    | "max_tautomers_reached"
    | "max_transforms_reached"
    | "parse_failed"
    | "enumeration_failed"
    | "not_applicable";
  enumerated_count: number;
  canonical_tautomer_smiles?: string;
  candidates?: DerivedStructureCandidate[];
  search_expansion_allowed: boolean;
  limitation: string;
}
/**
 * A bounded, provenance-bearing structure search candidate.
 */
export interface DerivedStructureCandidate {
  candidate_id: string;
  kind: "tautomer" | "prodrug_parent_hypothesis";
  label: string;
  source_smiles: string;
  canonical_smiles: string;
  rule_id: string;
  rule_version: string;
  engine: string;
  engine_version: string;
  transform_smarts?: string;
  hypothesis: boolean;
  search_eligible: boolean;
  exclusion_reason?: string;
  integrity: StructureIntegrityCheck;
  evidence_references?: string[];
  limitation: string;
}
/**
 * Machine-checkable properties attached to a derived structure.
 */
export interface StructureIntegrityCheck {
  molecular_formula: string;
  exact_mass: number;
  heavy_atom_count: number;
  atom_count: number;
  formal_charge: number;
  fragment_count: number;
  radical_electrons: number;
  retained_heavy_atom_fraction?: number;
  passed: boolean;
  checks?: string[];
}
/**
 * A structurally similar compound found via similarity search.
 */
export interface RelatedCompound {
  cid: number;
  name?: string;
  canonical_smiles: string;
  tanimoto_similarity: number;
}
/**
 * Executive risk summary for the compound.
 */
export interface RiskSummary {
  overall_risk: RiskLevel;
  blocking_patents_count?: number;
  total_patents_analyzed?: number;
  key_risks?: string[];
  /**
   * 2-3 paragraph summary for attorneys
   */
  executive_summary: string;
  summary_validation_issues?: string[];
}
/**
 * Explicit top-line clearance decision for the report.
 */
export interface ClearanceDecision {
  decision?: ClearanceOutcome;
  decision_confidence?: number;
  evidence_quality?: number;
  decision_reasoning?: string[];
  decision_audit?: ClearanceDecisionAudit;
}
/**
 * Structured evidence metrics used to support the top-line decision.
 */
export interface ClearanceDecisionAudit {
  queried_sources_count?: number;
  successful_sources_count?: number;
  material_patents_reviewed?: number;
  material_us_patents?: number;
  material_ep_patents?: number;
  patents_with_claims?: number;
  patents_with_family?: number;
  us_patents_with_prosecution_context?: number;
  us_patents_with_file_wrapper_dossier?: number;
  ep_patents_with_register_context?: number;
  analysis_failures_count?: number;
  authoritative_sources_count?: number;
  clearance_grade_ready_patents?: number;
  incomplete_material_patents?: number;
  clearance_grade_ready_families?: number;
  incomplete_material_families?: number;
  failed_sources?: string[];
  evidence_sufficient_for_clearance?: boolean;
  insufficiency_reasons?: string[];
  evidence_warnings?: string[];
  search_iterations?: number;
  coverage_summary?: EvidenceCoverageSummary;
  claim_program_summary?: ClaimProgramSummary;
  blocker_families?: BlockerFamilyRecord[];
  decisive_references?: DecisionEvidenceReference[];
}
/**
 * Material evidence coverage and gap summary for the final matter.
 */
export interface EvidenceCoverageSummary {
  queried_source_names?: string[];
  successful_source_names?: string[];
  failed_source_names?: string[];
  authoritative_source_names?: string[];
  supporting_source_names?: string[];
  reviewed_patent_ids?: string[];
  reviewed_us_patent_ids?: string[];
  reviewed_ep_patent_ids?: string[];
  patents_missing_claims?: string[];
  patents_missing_claim_level_analysis?: string[];
  patents_missing_authoritative_records?: string[];
  patents_missing_family_context?: string[];
  us_patents_missing_prosecution_context?: string[];
  us_patents_missing_file_wrapper_dossier?: string[];
  ep_patents_missing_register_context?: string[];
  failed_analysis_patent_ids?: string[];
  clearance_grade_ready_patent_ids?: string[];
  incomplete_patent_ids?: string[];
  clearance_grade_ready_family_ids?: string[];
  incomplete_family_ids?: string[];
  verification_gaps?: string[];
  required_record_components?: string[];
}
/**
 * Claim-program level summary used by the top-line decision engine.
 */
export interface ClaimProgramSummary {
  total_claim_programs_reviewed?: number;
  patent_level_fallback_count?: number;
  blocking_claim_ids?: string[];
  contested_claim_ids?: string[];
  medium_risk_claim_ids?: string[];
  claims_with_strong_invalidity?: string[];
  claims_with_insufficient_evidence?: string[];
  /**
   * Claims with positive coverage screens but trusted inactive status and no unresolved past-act or live-family exposure
   */
  inactive_coverage_claim_ids?: string[];
  blocking_patent_ids?: string[];
  contested_patent_ids?: string[];
  medium_risk_patent_ids?: string[];
}
/**
 * Canonical family projection of governed blocking claim decisions.
 */
export interface BlockerFamilyRecord {
  schema_version?: "blocker-family-v1";
  blocker_id: string;
  family_id: string;
  primary_blocking_patent_id: string;
  /**
   * @minItems 1
   */
  material_family_patent_ids: [string, ...string[]];
  /**
   * @minItems 1
   */
  blocking_patent_ids: [string, ...string[]];
  /**
   * @minItems 1
   */
  jurisdictions: [string, ...string[]];
  /**
   * @minItems 1
   */
  blocking_claims: [BlockerClaimRecord, ...BlockerClaimRecord[]];
}
/**
 * Exact decision-bearing claim that passed every blocker gate.
 */
export interface BlockerClaimRecord {
  claim_id: string;
  patent_id: string;
  claim_number: number;
  jurisdiction: string;
  literal_risk: string;
  doe_risk?: string;
  invalidity_strength?: string;
  legal_status: "active";
  legal_status_provenance_verified: true;
  prospective_enforceability: "active";
  /**
   * @minItems 1
   */
  accused_acts: [string, ...string[]];
  accused_acts_verified: true;
  evidence_sufficient: true;
  /**
   * @minItems 1
   */
  record_basis: [string, ...string[]];
}
/**
 * Machine-readable reference supporting the top-line decision.
 */
export interface DecisionEvidenceReference {
  category: DecisionEvidenceCategory;
  summary: string;
  patent_id?: string;
  jurisdiction?: string;
  source_name?: string;
  signal?: string;
}
/**
 * Current report scope that may or may not support a positive clearance conclusion.
 */
export interface DecisionScope {
  matter_type?: string;
  jurisdictions?: string[];
  asset_classes?: string[];
  intended_actions?: string[];
  supports_positive_clearance?: boolean;
  summary?: string;
}
/**
 * Program-level certification boundaries relevant to the current matter.
 */
export interface CertificationScope {
  certified_jurisdictions?: string[];
  supported_jurisdictions?: string[];
  certified_matter_types?: string[];
  certified_asset_classes?: string[];
  attorney_supervised_matter_types?: string[];
  attorney_supervised_asset_classes?: string[];
  supporting_only_jurisdictions?: string[];
  current_matter_type_certified?: boolean;
  attorney_supervision_required?: boolean;
  evidence_verified?: boolean;
  evidence_verification_status?: string;
  evidence_receipt_dsse?: string;
  evidence_receipt_id?: string;
  evidence_receipt_sha256?: string;
  evidence_pipeline_git_sha?: string;
  evidence_source_tree_sha256?: string;
  evidence_expires_at?: string;
  evidence_issuer_verifier_id?: string;
  evidence_key_id?: string;
  evidence_gate_run_id?: string;
  evidence_benchmark_aggregate_sha256?: string;
  verified_lane_ids?: string[];
  evidence_failures?: string[];
  summary?: string;
}
/**
 * Signed report-level authorization inputs for counsel export workflows.
 */
export interface OpinionReadiness {
  trust_mode?: "explorer" | "counsel" | "monitor";
  attorney_supervision_required?: boolean;
  export_ready?: boolean;
  jurisdictions_blocking_export?: string[];
  gate_failures?: string[];
  summary?: string;
}
/**
 * Decision breakdown for a specific jurisdiction.
 */
export interface JurisdictionDecision {
  jurisdiction: string;
  decision?: ClearanceOutcome1;
  decision_confidence?: number;
  evidence_quality?: number;
  evidence_sufficient_for_clearance?: boolean;
  supports_positive_clearance?: boolean;
  lane_status?: string;
  local_review_required?: boolean;
  authority_grade?: string;
  gate_failures?: string[];
  reviewed_patent_ids?: string[];
  blocking_patent_ids?: string[];
  reasoning?: string[];
}
/**
 * Complete FTO analysis for a single patent.
 *
 * Internal pipeline-state model populated from LLM output (Step 4).
 * LLM output is a governed boundary: surplus fields and malformed nested
 * structures are rejected so schema drift cannot silently change a legal
 * conclusion. ``patent_id`` is inherited from
 * :class:`~praviar_pipeline.models._base.PatentBase`.
 */
export interface PatentAnalysis {
  /**
   * Normalized patent identifier (e.g. US7851188B2, EP1234567A1)
   */
  patent_id: string;
  /**
   * Issuing patent office (US, EP, WO, JP, KR, CN, IN, CA, AU)
   */
  jurisdiction?: string;
  title?: string;
  assignee?: string;
  expiry_date?: string | null;
  claims_analyzed?: ClaimAnalysis[];
  risk_level: RiskLevel;
  /**
   * Executive summary of the risk from this patent
   */
  risk_summary: string;
  design_around_suggestions?: DesignAroundSuggestion[];
  orange_book_info?: OrangeBookInfo | null;
  model_used?: string;
  /**
   * Extended thinking reasoning chain for debugging
   */
  thinking_text?: string;
  input_tokens?: number;
  output_tokens?: number;
  /**
   * Unified runtime profile used for this patent analysis.
   */
  analysis_execution_profile?: string;
  /**
   * Internal adaptive stage that produced the final analysis.
   */
  analysis_stage?: string;
  /**
   * Whether this analysis escalated to agentic research.
   */
  analysis_escalated?: boolean;
  /**
   * Internal audit reasons for agentic escalation.
   */
  analysis_escalation_reasons?: string[];
  /**
   * Internal adaptive execution-plan metadata.
   */
  analysis_execution_plan?: {
    [k: string]: unknown;
  };
  /**
   * Quality gates that failed after claim analysis completed.
   */
  analysis_quality_gate_failures?: string[];
  /**
   * Whether quality gates require human review before clearance.
   */
  analysis_review_required?: boolean;
  /**
   * Deterministic receipt binding this analysis to the exact customer product, act, territory, jurisdiction, and development-stage context.
   */
  analysis_context_sha256?: string;
  perspective_analyses?: PerspectiveAnalysis[];
  multi_perspective_synthesis?: MultiPerspectiveSynthesis | null;
}
/**
 * Analysis of a single patent claim.
 */
export interface ClaimAnalysis {
  claim_number: number;
  /**
   * independent or dependent
   */
  claim_type: "independent" | "dependent";
  /**
   * Parent claim number if dependent
   */
  depends_on?: number | null;
  /**
   * Claim preamble text
   */
  preamble?: string;
  /**
   * comprising, consisting of, consisting essentially of
   */
  transitional_phrase?: string | null;
  /**
   * Jurisdiction-specific construction of whether the preamble limits the claim. Unresolved must never support a positive clearance conclusion.
   */
  preamble_limiting?: "limiting" | "nonlimiting" | "unresolved";
  /**
   * Grounded reasoning for the preamble-limitation construction.
   */
  preamble_limitation_reasoning?: string;
  /**
   * Specification, prosecution, or controlling-law evidence.
   */
  preamble_limitation_evidence?: string;
  elements?: ClaimElement[];
  /**
   * Overall reasoning for the claim analysis
   */
  reasoning?: string;
  overall_status: ElementStatus1;
  overall_confidence?: number;
  /**
   * Optional free-text note capturing genuine claim-level ambiguity (e.g. an unresolved claim term that affects several elements). Empty when the claim assessment is unambiguous.
   */
  uncertainty_note?: string;
  [k: string]: unknown;
}
/**
 * Element-by-element analysis of a single claim limitation.
 */
export interface ClaimElement {
  element_number: number;
  /**
   * The claim limitation text
   */
  element_text: string;
  status: ElementStatus;
  /**
   * Why this element is/isn't met
   */
  reasoning: string;
  confidence?: number;
  /**
   * Specific evidence supporting the assessment
   */
  evidence?: string;
  /**
   * Optional free-text note capturing genuine ambiguity in this element's assessment (e.g. an unresolved claim term or thin evidence). Empty when the assessment is unambiguous.
   */
  uncertainty_note?: string;
  /**
   * Optional specification reference (column/line or paragraph, e.g. 'col. 5, lines 10-22' or 'para. 0042') for where a construed claim term is defined. Empty when no specification definition was relied on.
   */
  spec_citation?: string;
  [k: string]: unknown;
}
/**
 * A suggested modification to avoid infringement.
 */
export interface DesignAroundSuggestion {
  /**
   * Which claim element this avoids
   */
  element_avoided: number;
  suggestion: string;
  /**
   * Assessment of whether this modification is chemically viable
   */
  feasibility?: string;
  /**
   * Proposed modified structure as a SMILES string
   */
  smiles?: string | null;
  /**
   * Tanimoto similarity (Morgan fingerprints, r=2) to the original compound
   */
  tanimoto_to_original?: number | null;
  /**
   * Whether RDKit successfully parsed the proposed SMILES
   */
  rdkit_valid?: boolean | null;
  /**
   * Heuristic flag: True when Tanimoto is in a defensible mid-range band suggesting structural similarity without identity (see design_around_validation)
   */
  pharmacophore_preserved?: boolean | null;
}
/**
 * FDA Orange Book regulatory-listing data for a patent.
 *
 * A listing is a regulatory linkage signal.  It is not, by itself, evidence
 * that a target product practices any claim.
 */
export interface OrangeBookInfo {
  is_listed?: boolean;
  nda_numbers?: string[];
  product_names?: string[];
  active_ingredients?: string[];
  dosage_forms_routes?: string[];
  reference_listed_drug?: boolean;
  reference_standard?: boolean;
  drug_substance_patent?: boolean;
  drug_product_patent?: boolean;
  patent_use_codes?: string[];
  exclusivities?: OrangeBookExclusivity[];
  exclusivity_codes?: string[];
  exclusivity_expiration_dates?: string[];
  pediatric_exclusivity?: boolean;
  delist_requested?: boolean;
  regulatory_linkage_only?: boolean;
}
/**
 * One FDA Orange Book exclusivity code/date record.
 */
export interface OrangeBookExclusivity {
  code: string;
  expiration_date: string;
}
/**
 * Analysis from a single expert perspective.
 */
export interface PerspectiveAnalysis {
  perspective: PerspectiveType;
  key_findings?: string[];
  risk_assessment?: string;
  confidence?: number;
  recommended_risk_level?: RiskLevel | null;
  evidence_cited?: string[];
  [k: string]: unknown;
}
/**
 * Synthesized output from all expert perspectives.
 */
export interface MultiPerspectiveSynthesis {
  perspectives?: PerspectiveAnalysis[];
  synthesized_risk?: RiskLevel | null;
  disagreements?: string[];
  synthesis_reasoning?: string;
  [k: string]: unknown;
}
/**
 * Doctrine of equivalents assessment for a NOT_MET element.
 */
export interface DoEAssessment {
  patent_id: string;
  claim_number: number;
  element_number: number;
  element_text?: string;
  estoppel?: EstoppelResult;
  /**
   * None if estoppel bars DoE analysis
   */
  fwr?: FWRAssessment | null;
  /**
   * True only when FWR is affirmative and estoppel is affirmatively resolved not to bar the theory; null means the legal result is unresolved.
   */
  overall_equivalent?: boolean | null;
  confidence?: number;
  confidence_band?: "HIGH" | "MODERATE" | "LOW";
  reasoning?: string;
}
/**
 * Prosecution history estoppel check.
 */
export interface EstoppelResult {
  /**
   * Narrowing amendments identified in file wrapper
   */
  amendments_found?: string[];
  /**
   * True when the complete record establishes an unrebutted surrender, false when the complete record establishes no bar, and null when the file wrapper, nexus, scope, or Festo rebuttal record is unresolved.
   */
  estoppel_applies?: boolean | null;
  /**
   * Description of subject matter surrendered during prosecution
   */
  surrendered_scope?: string;
  /**
   * Whether the file wrapper was successfully retrieved
   */
  file_wrapper_available?: boolean;
  /**
   * Rejection types found in prosecution history
   */
  rejections_found?: string[];
  prosecution_narrowing_count?: number;
}
/**
 * Function-Way-Result test for a single claim element.
 */
export interface FWRAssessment {
  /**
   * True, false, or null when the function evidence is unresolved.
   */
  same_function: boolean | null;
  function_reasoning: string;
  /**
   * True, false, or null when the way evidence is unresolved.
   */
  same_way: boolean | null;
  way_reasoning: string;
  /**
   * True, false, or null when the result evidence is unresolved.
   */
  same_result: boolean | null;
  result_reasoning: string;
  /**
   * True only when all three prongs are affirmatively met; false when any prong is affirmatively not met; null when no prong is false but at least one is unresolved.
   */
  equivalent: boolean | null;
  chemical_context?: ChemicalEquivalenceContext | null;
}
/**
 * Chemical structural relationship context for DoE analysis.
 */
export interface ChemicalEquivalenceContext {
  structural_relationship?:
    | "bioisostere"
    | "homolog"
    | "stereoisomer"
    | "salt_form"
    | "polymorph"
    | "prodrug"
    | "metabolic_equivalent"
    | "none"
    | "other";
  relationship_reasoning?: string;
  known_interchangeability?: boolean;
  interchangeability_evidence?: string;
}
/**
 * Complete invalidity assessment for a blocking patent.
 */
export interface InvalidityAssessment {
  patent_id: string;
  /**
   * Which claims are being assessed for invalidity
   */
  claim_numbers?: number[];
  ptab?: PTABResult;
  prior_art?: PriorArtReference[];
  /**
   * Ground-specific screening arguments retained from the model response.
   */
  arguments?: InvalidityArgument[];
  written_description_issues?: string[];
  claim_charts?: ClaimChart[];
  graham_factors?: GrahamFactors | null;
  enablement_screening?: EnablementScreening | null;
  /**
   * Every proposed IPR ground is limited to §102/103 patents or printed publications.
   */
  ipr_prior_art_scope_verified?: boolean;
  ipr_timing_verified?: boolean;
  ipr_estoppel_and_rpi_verified?: boolean;
  ipr_discretionary_denial_reviewed?: boolean;
  ipr_eligibility_reasoning?: string;
  /**
   * weak, moderate, strong — how likely these claims are invalid
   */
  overall_invalidity_strength?: string;
  reasoning?: string;
  confidence?: number;
  confidence_band?: "HIGH" | "MODERATE" | "LOW";
  screening_disclaimer?: string;
}
/**
 * Aggregated PTAB history for a patent.
 */
export interface PTABResult {
  has_been_challenged?: boolean;
  proceedings?: PTABProceeding[];
  /**
   * Union of claims with an independently supported effective cancellation record; provider-reported cancellation alone is excluded.
   */
  all_claims_cancelled?: number[];
}
/**
 * A PTAB proceeding (IPR/PGR/CBM) against the patent.
 */
export interface PTABProceeding {
  /**
   * e.g. IPR2019-00123
   */
  proceeding_number: string;
  /**
   * IPR, PGR, or CBM
   */
  type: "IPR" | "PGR" | "CBM";
  /**
   * Instituted, Final Written Decision, Settled, etc.
   */
  status: string;
  filing_date?: string | null;
  decision_date?: string | null;
  claims_challenged?: number[];
  /**
   * Provider-reported cancellations before independent finality verification.
   */
  claims_reported_cancelled?: number[];
  /**
   * Claims with an independently supported effective cancellation record.
   */
  claims_cancelled?: number[];
  claims_survived?: number[];
  outcome_summary?: string;
  final_written_decision_verified?: boolean;
  cancellation_certificate_verified?: boolean;
  review_and_appeal_posture?: string;
}
/**
 * A prior art reference that may invalidate blocking claims.
 */
export interface PriorArtReference {
  /**
   * Patent number or publication ID
   */
  reference_id: string;
  title?: string;
  publication_date?: string | null;
  /**
   * How this reference relates to blocking claims
   */
  relevance?: string;
  /**
   * Likelihood this reference anticipates (102) the blocking claim
   */
  anticipation_score?: number;
  /**
   * Likelihood this reference renders obvious (103) the blocking claim
   */
  obviousness_score?: number;
  /**
   * patent, journal_article, conference_paper, preprint
   */
  reference_type?: "patent" | "journal_article" | "conference_paper" | "preprint";
  authors?: string[];
  journal?: string;
  doi?: string;
  url?: string;
  abstract?: string;
  /**
   * Where this reference was found
   */
  source_database?: "semantic_scholar" | "openalex" | "lens" | "bigquery" | "pubmed" | "";
  /**
   * True only when counsel-verified evidence establishes a patent or printed publication usable under 35 U.S.C. § 311(b).
   */
  ipr_eligible_printed_publication?: boolean;
  ipr_eligibility_basis?: string;
}
/**
 * A single invalidity argument identified by the LLM.
 */
export interface InvalidityArgument {
  /**
   * anticipation, obviousness, enablement, written_description, or obviousness-type double patenting
   */
  type: "anticipation" | "obviousness" | "enablement" | "written_description" | "odp";
  /**
   * e.g. 35 U.S.C. § 102
   */
  statute?: string;
  /**
   * weak, moderate, or strong
   */
  strength: string;
  /**
   * Specific references or facts supporting this argument
   */
  key_evidence: string[];
  /**
   * How the patent holder might respond
   */
  counterarguments?: string[];
  /**
   * Detailed reasoning for the strength assessment
   */
  reasoning: string;
}
/**
 * Complete claim chart mapping one claim against one prior art reference.
 */
export interface ClaimChart {
  patent_id: string;
  claim_number: number;
  prior_art_reference_id: string;
  entries?: ClaimChartEntry[];
  all_elements_disclosed?: boolean;
  chart_summary?: string;
}
/**
 * Maps a single claim element to a prior art disclosure.
 */
export interface ClaimChartEntry {
  element_number: number;
  element_text: string;
  prior_art_reference_id: string;
  prior_art_disclosure: string;
  citation_location?: string;
  disclosed: "yes" | "no" | "partial";
  notes?: string;
}
/**
 * Graham v. John Deere four-factor obviousness analysis.
 */
export interface GrahamFactors {
  scope_and_content: string;
  differences_from_prior_art: string;
  level_of_ordinary_skill: string;
  commercial_success?: string;
  long_felt_need?: string;
  failure_of_others?: string;
  unexpected_results?: string;
  overall_obviousness_assessment: string;
}
/**
 * 35 USC 112 enablement screening, including Amgen v. Sanofi genus claim analysis.
 */
export interface EnablementScreening {
  genus_claim_detected?: boolean;
  genus_indicators?: string[];
  specification_enables_full_scope?: "yes" | "no" | "unclear";
  amgen_v_sanofi_flags?: string[];
  reasoning?: string;
}
/**
 * Complete verification output — all deterministic checks against source data.
 */
export interface VerificationResult {
  checks?: VerificationCheck[];
  /**
   * Every patent_id cited in analysis exists in search results
   */
  all_citations_valid?: boolean;
  /**
   * Quoted claim text matches source documents
   */
  all_claims_grounded?: boolean;
  /**
   * Every SMILES string in output parses in RDKit
   */
  all_entities_valid?: boolean;
  /**
   * Expiry dates are filing_date + 20 years (within PTA tolerance)
   */
  dates_consistent?: boolean;
  /**
   * HIGH risk requires at least one BLOCKS claim
   */
  risk_levels_justified?: boolean;
  issues?: string[];
}
/**
 * A single verification check result.
 */
export interface VerificationCheck {
  check_name: string;
  passed: boolean;
  /**
   * pass=check passed, warning=vacuous pass or advisory, fail=check failed
   */
  severity?: "pass" | "warning" | "fail";
  /**
   * What was checked and what was found
   */
  details?: string;
}
/**
 * Structured prosecution and file-wrapper signals for a material patent.
 */
export interface ProsecutionFinding {
  patent_id: string;
  jurisdiction?: string;
  application_number?: string;
  prosecution_history_available?: boolean;
  transaction_count?: number;
  amendment_event_count?: number;
  office_action_count?: number;
  continuity_entry_count?: number;
  narrowing_signal?: boolean;
  terminal_disclaimer?: boolean;
  terminal_disclaimer_linked_patent?: string;
  ptab_challenged?: boolean;
  ptab_proceeding_count?: number;
  pending_family_signal?: boolean;
  pending_family_member_count?: number;
  ep_register_status?: string;
  ep_opposition_event_count?: number;
  ep_limitation_event_count?: number;
  ep_revocation_event_count?: number;
  ep_lapse_event_count?: number;
  office_action_types?: string[];
  amendment_types?: string[];
  continuity_types?: string[];
  rejected_claim_numbers?: number[];
  narrowing_claim_numbers?: number[];
  rejection_bases?: string[];
  estoppel_risk_flags?: string[];
  continuation_parent_count?: number;
  continuation_child_count?: number;
  divisional_parent_count?: number;
  divisional_child_count?: number;
  cip_parent_count?: number;
  cip_child_count?: number;
  response_after_final_count?: number;
  rce_count?: number;
  interview_event_count?: number;
  appeal_event_count?: number;
  record_basis?: string[];
  summary?: string;
}
/**
 * Structured prosecution dossier captured during Step 4 enrichment.
 */
export interface ProsecutionDossier {
  patent_id: string;
  jurisdiction?: string;
  application_number?: string;
  source_name?: string;
  sections_available?: string[];
  office_actions_summary?: string;
  continuity_summary?: string;
  amendments_summary?: string;
  office_action_events?: ProsecutionOfficeActionEvent[];
  continuity_entries?: ProsecutionContinuityEntry[];
  amendment_events?: ProsecutionAmendmentEvent[];
  office_action_count?: number;
  continuity_entry_count?: number;
  amendment_entry_count?: number;
  office_action_types?: string[];
  amendment_types?: string[];
  continuity_types?: string[];
  rejected_claim_numbers?: number[];
  narrowing_claim_numbers?: number[];
  rejection_bases?: string[];
  estoppel_risk_flags?: string[];
  continuation_parent_count?: number;
  continuation_child_count?: number;
  divisional_parent_count?: number;
  divisional_child_count?: number;
  cip_parent_count?: number;
  cip_child_count?: number;
  response_after_final_count?: number;
  rce_count?: number;
  interview_event_count?: number;
  appeal_event_count?: number;
  narrowing_signal?: boolean;
  terminal_disclaimer?: boolean;
  terminal_disclaimer_linked_patent?: string;
  ptab_challenged?: boolean;
  pending_family_signal?: boolean;
  record_basis?: string[];
  summary?: string;
}
/**
 * Normalized office-action event extracted from a prosecution dossier.
 */
export interface ProsecutionOfficeActionEvent {
  document_code?: string;
  description?: string;
  event_date?: string;
  office_action_type?: string;
  claims_rejected?: number[];
  rejection_bases?: string[];
}
/**
 * Normalized continuity-chain entry extracted from prosecution data.
 */
export interface ProsecutionContinuityEntry {
  relationship?: string;
  relationship_type?: string;
  application_number?: string;
  related_application_number?: string;
  continuity_type?: string;
  filing_date?: string;
  status?: string;
  jurisdiction?: string;
}
/**
 * Normalized amendment/response event extracted from prosecution data.
 */
export interface ProsecutionAmendmentEvent {
  transaction_code?: string;
  description?: string;
  event_date?: string;
  event_type?: string;
  claim_numbers?: number[];
}
/**
 * Matter-level record of claim construction standards used in the report.
 */
export interface ClaimConstructionRecord {
  standard?: string;
  jurisdictions?: string[];
  assumptions?: string[];
  disputed_terms?: string[];
  summary?: string;
}
/**
 * Forward-looking risk item not captured by current issued-claim exposure alone.
 */
export interface FutureRiskFinding {
  patent_id: string;
  jurisdiction?: string;
  risk_type?: string;
  severity?: string;
  monitoring_required?: boolean;
  related_patent_ids?: string[];
  record_basis?: string[];
  summary?: string;
}
/**
 * Commercial impact framing for launch-at-risk scenarios.
 */
export interface CommercialExposure {
  damages_injunction_risk?: string;
  business_severity?: string;
  blocking_patent_ids?: string[];
  rationale?: string[];
  summary?: string;
}
/**
 * Claim-scoped decision object used to synthesize the top-line outcome.
 *
 * Internal pipeline-state model. Uses ``extra="forbid"`` (inherited
 * from :class:`PatentBase`). ``patent_id`` and ``jurisdiction`` are
 * inherited.
 */
export interface ClaimProgramDecision {
  /**
   * Normalized patent identifier (e.g. US7851188B2, EP1234567A1)
   */
  patent_id: string;
  /**
   * Issuing patent office (US, EP, WO, JP, KR, CN, IN, CA, AU)
   */
  jurisdiction?: string;
  claim_number: number;
  literal_outcome?: string;
  literal_risk?: string;
  doe_risk?: string;
  invalidity_strength?: string;
  prosecution_risk_flags?: string[];
  prosecution_risk_level?: string;
  post_grant_risk_level?: string;
  scope_constrained?: boolean;
  future_risk_flags?: string[];
  legal_status?: string;
  legal_status_provenance_verified?: boolean;
  /**
   * active, inactive, pending, conflicting, or unresolved based only on trusted current legal-status evidence
   */
  prospective_enforceability?: string;
  accused_acts?: string[];
  accused_acts_verified?: boolean;
  past_acts_in_scope?: boolean;
  commercial_severity?: string;
  evidence_sufficient?: boolean;
  missing_components?: string[];
  record_basis?: string[];
  rationale?: string[];
}
/**
 * Typed evidence unit emitted by the runtime evidence fabric.
 */
export interface EvidenceArtifact {
  artifact_id: string;
  artifact_type: EvidenceArtifactType;
  source_name?: string;
  authority_tier?: EvidenceAuthorityTier;
  jurisdiction?: string;
  patent_id?: string;
  family_id?: string;
  claim_number?: number | null;
  summary?: string;
  record_basis?: string[];
  linked_node_ids?: string[];
}
/**
 * Standardized result shape for an evidence adapter invocation.
 */
export interface EvidenceAdapterResult {
  adapter_name: string;
  adapter_kind?: EvidenceAdapterKind;
  authority_tier?: EvidenceAuthorityTier1;
  status?: SourceStatus;
  collection_state?: EvidenceCollectionState;
  required_before_clear?: boolean;
  target_patent_ids?: string[];
  covered_patent_ids?: string[];
  missing_patent_ids?: string[];
  artifacts?: EvidenceArtifact[];
  warnings?: string[];
  rate_limit_remaining?: number | null;
  retry_after_seconds?: number | null;
  freshness_note?: string;
  artifact_count?: number;
  covered_components?: string[];
  expected_components?: string[];
  missing_components?: string[];
  supports_authoritative_findings?: boolean;
}
/**
 * First-class runtime state for one collector over the current matter.
 */
export interface EvidenceCollectorRun {
  definition: EvidenceCollectorDefinition;
  collection_state?: EvidenceCollectionState1;
  required_before_clear?: boolean;
  target_patent_ids?: string[];
  covered_patent_ids?: string[];
  missing_patent_ids?: string[];
  expected_components?: string[];
  covered_components?: string[];
  missing_components?: string[];
  retry_budget_remaining?: number;
  freshness_note?: string;
  triggered_directive_ids?: string[];
  collection_targets?: CollectionTarget[];
  attempts?: CollectionAttempt[];
}
/**
 * Static collector metadata used by the runtime collection ledger.
 */
export interface EvidenceCollectorDefinition {
  collector_name: string;
  adapter_kind?: EvidenceAdapterKind1;
  authority_tier?: EvidenceAuthorityTier2;
  supports_authoritative_findings?: boolean;
  expected_components?: string[];
}
/**
 * Patent-scoped collection target tracked by a runtime collector.
 */
export interface CollectionTarget {
  patent_id: string;
  jurisdiction?: string;
  required_components?: string[];
  covered_components?: string[];
  missing_components?: string[];
  required_before_clear?: boolean;
}
/**
 * One deterministic collector attempt captured in the runtime ledger.
 */
export interface CollectionAttempt {
  attempt_number?: number;
  status?: SourceStatus1;
  collection_state?: EvidenceCollectionState2;
  artifact_count?: number;
  warnings?: string[];
  rate_limit_remaining?: number | null;
  retry_after_seconds?: number | null;
  summary?: string;
}
/**
 * Actionable evidence-collection directive required to close record gaps.
 */
export interface EvidenceCollectionDirective {
  directive_id: string;
  directive_type: string;
  priority?: EvidenceDirectivePriority;
  required_before_clear?: boolean;
  target_patent_ids?: string[];
  target_claim_ids?: string[];
  target_jurisdictions?: string[];
  recommended_adapters?: string[];
  summary?: string;
  rationale?: string;
}
/**
 * A specific gap identified in search coverage.
 */
export interface CoverageGap {
  gap_type?: string;
  description?: string;
  suggested_action?: string;
  [k: string]: unknown;
}
/**
 * Canonical graph of patents, families, claims, and record links.
 */
export interface MatterGraph {
  nodes?: MatterNode[];
  edges?: MatterEdge[];
}
/**
 * A node in the per-run matter graph.
 */
export interface MatterNode {
  node_id: string;
  node_type: MatterNodeType;
  label: string;
  jurisdiction?: string;
  patent_id?: string;
  family_id?: string;
  application_number?: string;
}
/**
 * A directional link in the per-run matter graph.
 */
export interface MatterEdge {
  edge_type: MatterEdgeType;
  from_node_id: string;
  to_node_id: string;
  summary?: string;
}
/**
 * Compact summary of the runtime matter graph.
 */
export interface MatterGraphSummary {
  root_compound?: string;
  node_count?: number;
  edge_count?: number;
  node_counts_by_type?: {
    [k: string]: number;
  };
  edge_counts_by_type?: {
    [k: string]: number;
  };
  patent_node_ids?: string[];
  family_node_ids?: string[];
}
/**
 * Persistent per-run evidence substrate shared across runtime stages.
 */
export interface MatterStore {
  matter_graph?: MatterGraph;
  matter_graph_summary?: MatterGraphSummary;
  matter_evidence_index?: MatterEvidenceIndex;
  prosecution_dossiers?: ProsecutionDossier[];
  claim_program_decisions?: ClaimProgramDecision[];
  evidence_artifacts?: EvidenceArtifact[];
  evidence_adapter_results?: EvidenceAdapterResult[];
  collector_runs?: EvidenceCollectorRun[];
  evidence_collection_plan?: EvidenceCollectionDirective[];
  coverage_gaps?: MatterStoreCoverageGap[];
  authority_coverage?: AuthorityCoverage;
  record_completeness?: RecordCompleteness;
  run_observability?: RunObservability;
  record_contradictions?: RecordContradiction[];
}
/**
 * Canonical per-matter evidence inventory derived from the final record.
 */
export interface MatterEvidenceIndex {
  source_names?: string[];
  authoritative_source_names?: string[];
  supporting_source_names?: string[];
  material_patent_count?: number;
  family_count?: number;
  analysis_failure_patent_ids?: string[];
  critic_flagged_patent_ids?: string[];
  clearance_grade_ready_patent_ids?: string[];
  incomplete_patent_ids?: string[];
  clearance_grade_ready_family_ids?: string[];
  incomplete_family_ids?: string[];
  patent_records?: PatentEvidenceRecord[];
  family_records?: FamilyEvidenceRecord[];
}
/**
 * Canonical evidence inventory for one material patent in the matter.
 *
 * External-boundary model: assembled from authoritative source records
 * consumed by report generation. Uses ``extra="forbid"`` (inherited
 * from :class:`PatentBase`) — schema drift here would silently weaken
 * the audit trail. ``patent_id`` and ``jurisdiction`` are inherited.
 */
export interface PatentEvidenceRecord {
  /**
   * Normalized patent identifier (e.g. US7851188B2, EP1234567A1)
   */
  patent_id: string;
  /**
   * Issuing patent office (US, EP, WO, JP, KR, CN, IN, CA, AU)
   */
  jurisdiction?: string;
  title?: string;
  legal_status?: string;
  is_granted?: boolean;
  source_names?: string[];
  authoritative_source_names?: string[];
  supporting_source_names?: string[];
  assignees?: string[];
  family_id?: string;
  family_member_count?: number;
  family_jurisdictions?: string[];
  family_broadest?: boolean;
  application_number?: string;
  has_claims_text?: boolean;
  has_family_context?: boolean;
  has_us_prosecution_context?: boolean;
  has_us_file_wrapper_dossier?: boolean;
  prosecution_dossier_sections?: string[];
  has_ep_register_context?: boolean;
  has_assignments?: boolean;
  has_priority_claims?: boolean;
  has_ptab_proceedings?: boolean;
  has_orange_book_listing?: boolean;
  has_opposition_events?: boolean;
  authoritative_record_categories?: string[];
  component_statuses?: RecordComponentStatus[];
  analysis_completed?: boolean;
  analysis_failed?: boolean;
  claims_analyzed_count?: number;
  risk_level?: string;
  doe_assessed?: boolean;
  invalidity_assessed?: boolean;
  clearance_grade_ready?: boolean;
  gate_failures?: string[];
  critic_issue_count?: number;
  critic_issue_severities?: string[];
  prosecution_signals?: string[];
  future_risk_signals?: string[];
}
/**
 * Per-component collection ledger entry for a patent or family record.
 */
export interface RecordComponentStatus {
  component: string;
  status?: RecordComponentStatusValue;
  source_name?: string;
  authority_expected?: boolean;
  required_before_clear?: boolean;
  note?: string;
}
/**
 * Canonical family-level evidence summary for material patents.
 */
export interface FamilyEvidenceRecord {
  family_id: string;
  material_patent_ids?: string[];
  jurisdictions?: string[];
  broadest_patent_id?: string;
  member_count?: number;
  pending_member_count?: number;
  blocking_patent_ids?: string[];
  orange_book_listed_patent_ids?: string[];
  authoritative_record_categories?: string[];
  component_statuses?: RecordComponentStatus[];
  clearance_grade_ready?: boolean;
  gate_failures?: string[];
  clearance_grade_ready_patent_ids?: string[];
  incomplete_patent_ids?: string[];
}
/**
 * Coverage-gap record persisted in the matter store.
 */
export interface MatterStoreCoverageGap {
  gap_type?: string;
  description?: string;
  suggested_action?: string;
}
/**
 * Authority and provenance coverage for the final matter record.
 */
export interface AuthorityCoverage {
  policy?: string;
  authoritative_source_names?: string[];
  supporting_source_names?: string[];
  authoritative_categories_covered?: string[];
  authoritative_categories_missing?: string[];
  patents_with_authoritative_records?: number;
  patents_without_authoritative_records?: number;
  clearance_grade_ready_patents?: number;
}
/**
 * Record-completeness policy evaluation for the final matter.
 */
export interface RecordCompleteness {
  profile?: string;
  matter_type?: string;
  jurisdictions?: string[];
  required_components?: string[];
  missing_components?: string[];
  blocking_gaps?: string[];
  clearance_grade_ready?: boolean;
}
/**
 * Run-level observability metrics and false-clear risk signals.
 */
export interface RunObservability {
  authoritative_source_hit_rate?: number;
  claims_text_coverage?: number;
  family_context_coverage?: number;
  us_file_wrapper_dossier_coverage?: number;
  ep_register_coverage?: number;
  failed_adapter_names?: string[];
  false_clear_risk_flags?: string[];
  unresolved_contradictions?: string[];
}
/**
 * Typed contradiction record persisted inside the matter store.
 */
export interface RecordContradiction {
  contradiction_id: string;
  category?: string;
  summary?: string;
  severity?: RecordContradictionSeverity;
  affected_patent_ids?: string[];
  affected_claim_ids?: string[];
  source_names?: string[];
}
/**
 * Deterministic support ledger mapping customer-visible claim assertions to source span IDs and unsupported/review-needed counts.
 */
export interface ClaimSourceSpanMap {
  generated_from?: string;
  entries?: ClaimAssertionSupport[];
  spans?: {
    [k: string]: SourceSpanReference;
  };
  unsupported_customer_visible_claim_count?: number;
  needs_review_count?: number;
}
/**
 * Support status for one customer-visible claim assertion.
 */
export interface ClaimAssertionSupport {
  assertion_id: string;
  patent_id?: string;
  claim_number?: number | null;
  element_number?: number | null;
  report_section: string;
  assertion_text: string;
  source_span_ids?: string[];
  support_status?: "supported" | "unsupported" | "needs_review";
  customer_visible?: boolean;
  review_required?: boolean;
}
/**
 * Stable reference to a report/source span used to support an assertion.
 */
export interface SourceSpanReference {
  span_id: string;
  source_type: "claim_text" | "verified_claim_text" | "element_evidence" | "specification_citation" | "claim_reasoning";
  patent_id?: string;
  claim_number?: number | null;
  element_number?: number | null;
  citation?: string;
  excerpt?: string;
  source_document_id?: string;
  source_name?: string;
  source_text_sha256?: string;
  source_retrieved_at?: string;
  source_artifact_locator?: string;
  collector_identity?: string;
  collector_version?: string;
  provenance_schema_version?: string;
  claim_numbers?: number[];
  independent_claim_numbers?: number[];
  retrieval_complete?: boolean;
  provenance_cassette_sha256?: string;
  evidence_attestation_schema_version?: string;
  evidence_attestation_algorithm?: string;
  evidence_attestation_key_id?: string;
  evidence_attestation_subject_id?: string;
  evidence_attestation_hmac_sha256?: string;
}
/**
 * Portfolio-level review of all patent analyses.
 */
export interface CriticReport {
  findings?: CriticFinding[];
  patents_reviewed?: number;
  patents_flagged_for_revision?: string[];
  overall_quality_score?: number;
  portfolio_level_observations?: string[];
  input_tokens?: number;
  output_tokens?: number;
}
/**
 * A single issue identified by the critic agent.
 */
export interface CriticFinding {
  issue_type: CriticIssueType;
  patent_id: string;
  severity: CriticIssueSeverity;
  description: string;
  suggested_correction?: string;
  claim_numbers?: number[];
  related_patent_ids?: string[];
}
/**
 * Aggregated health of all search sources used in a pipeline run.
 */
export interface SourceHealth {
  entries?: SourceHealthEntry[];
}
/**
 * Health record for one data source.
 */
export interface SourceHealthEntry {
  source: string;
  status: SourceStatus2;
  patent_count?: number;
  attempted_count?: number;
  covered_count?: number;
  error_message?: string;
}
/**
 * Record of a patent that failed during analysis (Step 4/5/6).
 */
export interface AnalysisFailure {
  patent_id: string;
  /**
   * Pipeline step where failure occurred
   */
  step: string;
  /**
   * Exception class name
   */
  error_type: string;
  error_message: string;
  /**
   * Whether the failure was due to a transient error
   */
  recoverable?: boolean;
}
/**
 * A known limitation in the pipeline's data coverage.
 */
export interface DataLimitation {
  /**
   * e.g. source_unavailable, enrichment_gap
   */
  category: string;
  description: string;
  /**
   * How this affects the report's reliability
   */
  impact: string;
}
/**
 * Governed audit trail for a pipeline run.
 *
 * Captures row-level discovery → filtering → ranking → triage → analysis
 * provenance, aggregate counts, plus timing data for each step. Rank-cut and
 * hard-filtered SDQ candidates retain content-addressed decision receipts.
 * The ``prompt_hashes`` field pins the exact prompt-file revisions used
 * so the run can be reproduced and audited against EU AI Act
 * record-keeping obligations (Workstream 3).
 */
export interface PipelineAuditTrail {
  search_funnel?: SearchFunnelEntry[];
  query_plan?: SearchQueryPlan | null;
  triage_audit?: TriageAuditEntry[];
  analysis_audit?: AnalysisAuditEntry[];
  timing_data?: StepTiming[];
  total_patents_discovered?: number;
  patents_after_hard_filter?: number;
  patents_after_ranking?: number;
  patents_after_triage?: number;
  patents_analyzed?: number;
  /**
   * Map of prompt filename -> SHA-256 hex of file contents at load time. Populated from the process-wide PromptHasher singleton at finalisation.
   */
  prompt_hashes?: {
    [k: string]: string;
  };
  [k: string]: unknown;
}
/**
 * Tracks the row-level disposition of one retrieval candidate.
 */
export interface SearchFunnelEntry {
  patent_id: string;
  candidate_index?: number | null;
  sources_found_in?: string[];
  disposition?:
    | "legacy"
    | "included_in_triage"
    | "hard_filter_rejected"
    | "composite_pool_cut"
    | "final_rank_cut"
    | "supplementary_included";
  exclusion_stage?: "" | "hard_filter" | "composite_pool" | "final_rank";
  passed_hard_filter?: boolean;
  filter_reason?: string;
  composite_score?: number | null;
  bm25_score?: number | null;
  bm25_normalized_score?: number | null;
  embedding_score?: number | null;
  embedding_normalized_score?: number | null;
  final_blend_score?: number | null;
  composite_rank?: number | null;
  bm25_rank?: number | null;
  embedding_rank?: number | null;
  pre_cut_rank?: number | null;
  final_rank?: number | null;
  included_in_triage?: boolean;
  input_row_sha256?: string | null;
  audit_entry_sha256?: string | null;
  [k: string]: unknown;
}
/**
 * Reproducible query/source plan retained with the report audit trail.
 */
export interface SearchQueryPlan {
  schema_version?: "search-query-plan-v2";
  compound_name?: string;
  compound_type?: "small_molecule" | "biologic" | "peptide";
  canonical_smiles?: string;
  inchi_key?: string;
  pubchem_cid?: number | null;
  synonyms?: string[];
  cas_numbers?: string[];
  target_jurisdictions?: string[];
  iterations?: SearchQueryIteration[];
  sources?: SearchSourcePlanEntry[];
  ranking_signals?: string[];
  ranking_configuration: SearchRankingConfiguration;
  execution_configuration: SearchExecutionConfiguration;
  sequence_queries?: SearchSequenceQueryReceipt[];
  genus_queries?: SearchGenusQueryReceipt[];
  true_markush_coverage_status?: ("verified_manual" | "not_run" | "incomplete" | "unavailable") | "not_applicable";
  markush_evidence?: MarkushEvidenceReceipt | null;
  known_retrieval_limitations?: string[];
  plan_sha256: string;
}
/**
 * The exact structured query set executed for one retrieval iteration.
 */
export interface SearchQueryIteration {
  iteration_number: number;
  queries: ExpandedSearchQueries;
}
/**
 * Search terms plus system-owned provenance consumed by Step 2.
 *
 * Provenance is deliberately excluded from :class:`ExpandedSearchQueryTerms`
 * so an LLM cannot author or corrupt the record of how its terms were
 * obtained.
 */
export interface ExpandedSearchQueries {
  /**
   * Broad patent synonyms (e.g. 'C4 dicarboxylic acid', 'amber acid')
   */
  patent_synonyms?: string[];
  /**
   * Predicted CPC classification codes (e.g. 'C12P7/46', 'C07C55/10')
   */
  cpc_codes?: string[];
  /**
   * Companies known to patent in this compound's production space
   */
  key_assignees?: string[];
  /**
   * Production method terms (e.g. 'fermentation', 'biosynthesis')
   */
  process_keywords?: string[];
  /**
   * Genus-level chemical descriptions (e.g. 'dicarboxylic acid')
   */
  compound_class_terms?: string[];
  provenance?: QueryExpansionProvenance;
  [k: string]: unknown;
}
/**
 * Origin and live-source evidence for this exact query expansion.
 */
export interface QueryExpansionProvenance {
  origin?:
    | "unknown"
    | "web_grounded_agent"
    | "model_without_live_grounding"
    | "coverage_assessment_agent"
    | "evidence_directive";
  grounded?: boolean;
  model_name?: string;
  /**
   * @maxItems 20
   */
  grounding_queries?:
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ];
  /**
   * @maxItems 100
   */
  source_urls?: string[];
}
/**
 * One source's role and final execution disposition in the query plan.
 */
export interface SearchSourcePlanEntry {
  source: string;
  roles?: string[];
  criticality?: "core" | "optional";
  query_categories?: string[];
  execution_status:
    | "ok"
    | "failed"
    | "skipped"
    | "not_configured"
    | "not_requested"
    | "not_applicable"
    | "missing_audit";
  result_count?: number;
  reason?: string;
}
/**
 * Exact ranking cutoffs and weights used by the retrieval funnel.
 */
export interface SearchRankingConfiguration {
  score_model_version?: "composite-bm25-embedding-v1";
  max_sdq_patents: number;
  max_ranked_results: number;
  include_expired: boolean;
  expired_grace_years: number;
  bm25_pool_size: number;
  embedding_enabled: boolean;
  hybrid_retrieval_enabled: boolean;
  composite_cpc_weight: number;
  composite_compound_count_weight: number;
  composite_recency_weight: number;
  composite_title_weight: number;
  composite_multi_source_weight: number;
  blend_composite_2way: number;
  blend_bm25_2way: number;
  blend_composite_3way: number;
  blend_bm25_3way: number;
  blend_embedding_3way: number;
}
/**
 * Exact structure, graph, and iterative-search controls used.
 */
export interface SearchExecutionConfiguration {
  source_failure_policy: "coverage_aware" | "fail_fast" | "best_effort";
  tanimoto_threshold: number;
  surechembl_substructure_enabled: boolean;
  citation_traversal_enabled: boolean;
  citation_max_depth: number;
  citation_max_per_level: number;
  continuation_expansion_enabled: boolean;
  continuation_max_depth: number;
  continuation_max_patents: number;
  search_loop_enabled: boolean;
  search_loop_max_iterations: number;
  search_loop_coverage_threshold: number;
  ncbi_patent_sequence_enabled: boolean;
  ncbi_patent_sequence_max_hits: number;
  ncbi_patent_sequence_min_identity: number;
  ncbi_patent_sequence_min_query_coverage: number;
  pubchem_genus_enabled: boolean;
  pubchem_genus_max_compounds: number;
  pubchem_genus_max_patents: number;
  pubchem_genus_max_seconds: number;
}
/**
 * Non-secret receipt for an exact public sequence submitted to BLAST.
 */
export interface SearchSequenceQueryReceipt {
  subunit_index: number;
  sequence_sha256: string;
  sequence_length: number;
  identity_source?: "fda_gsrs_public";
}
/**
 * Non-secret receipt for one PubChem developed-structure genus query.
 */
export interface SearchGenusQueryReceipt {
  query_sha256: string;
  query_role: "murcko_scaffold" | "canonical_fallback" | "canonical_refinement_after_scaffold_cap";
  search_type?: "pubchem_fastsubstructure";
}
/**
 * Content-addressed evidence for one supervised PATENTSCOPE Markush search.
 *
 * PATENTSCOPE does not document a stable chemical-search Excel schema or a
 * supported automation API. The original export therefore remains the
 * evidence artifact while this receipt records the supervised query context
 * separately. ``markush_enabled`` is explicit because it cannot be inferred
 * from a general-results workbook row.
 */
export interface MarkushEvidenceReceipt {
  schema_version?: "patentscope-markush-evidence-v3";
  source?: "wipo_patentscope_manual";
  source_url?: "https://patentscope.wipo.int/search/en/structure.jsf";
  status: "verified_manual" | "not_run" | "incomplete" | "unavailable";
  organization_id: string;
  target_structure_sha256: string;
  query_structure_sha256: string;
  query_role: "target_compound" | "murcko_scaffold";
  chemical_search_mode: "exact" | "substructure" | "scaffold";
  markush_enabled?: true;
  markush_method: "enumeration" | "formula_matching";
  markush_match_mode: "exact" | "substructure" | "fuzzy";
  wipo_query_field?: "ENUM" | null;
  family_grouping_enabled: boolean;
  executed_at?: string | null;
  server_imported_at?: string | null;
  analyst_identity?: string | null;
  reviewer_identity?: string | null;
  artifact_filename?: string | null;
  artifact_media_type?: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" | null;
  imported_artifact_sha256?: string | null;
  imported_artifact_size_bytes?: number | null;
  controls_artifact_filename?: string | null;
  controls_artifact_media_type?: "image/png" | null;
  controls_artifact_sha256?: string | null;
  controls_artifact_size_bytes?: number | null;
  result_count?: number | null;
  /**
   * @maxItems 10000
   */
  selected_publication_ids?: string[];
  selected_publication_ids_sha256: string;
  /**
   * @minItems 1
   * @maxItems 50
   */
  limitations: [string, ...string[]];
  attestation_key_id?: string | null;
  attestation_hmac_sha256?: string | null;
  receipt_sha256: string;
}
/**
 * Tracks triage decisions for a single patent.
 */
export interface TriageAuditEntry {
  patent_id: string;
  relevance: string;
  reason: string;
  confidence?: number;
  passed_triage?: boolean;
  [k: string]: unknown;
}
/**
 * Tracks which patents were selected for claim analysis and why.
 */
export interface AnalysisAuditEntry {
  patent_id: string;
  selected_for_analysis: boolean;
  selection_reason?: string;
  risk_level?: string | null;
  selected_for_doe?: boolean;
  selected_for_invalidity?: boolean;
  [k: string]: unknown;
}
/**
 * Execution timing for a single pipeline step.
 */
export interface StepTiming {
  step_name: string;
  started_at: string;
  completed_at: string;
  duration_seconds: number;
  items_processed?: number;
  items_output?: number;
  [k: string]: unknown;
}
/**
 * Complete drawing analysis for a single patent.
 *
 * External-boundary model written by Step 2.75 (drawing pipeline).
 * Uses ``extra="forbid"`` (inherited from :class:`PatentBase`).
 * ``patent_id`` is inherited.
 */
export interface PatentDrawingAnalysis {
  /**
   * Normalized patent identifier (e.g. US7851188B2, EP1234567A1)
   */
  patent_id: string;
  /**
   * Issuing patent office (US, EP, WO, JP, KR, CN, IN, CA, AU)
   */
  jurisdiction?: string;
  pages_fetched?: number;
  pages_with_structures?: number;
  structures_found?: number;
  structures_valid?: number;
  structures_pubchem_confirmed?: number;
  structures_llm_verified?: number;
  structures_flagged_for_review?: number;
  structures?: DrawingStructure[];
  governance_provenance?: DrawingGovernanceProvenance | null;
  highest_risk_signal?: DrawingRiskLevel1;
  highest_tanimoto?: number;
  drawing_summary?: string;
  figure_reference_gaps?: string[];
  fetch_time_s?: number;
  segmentation_time_s?: number;
  ocsr_time_s?: number;
  verification_time_s?: number;
  total_time_s?: number;
  llm_verification_cost_usd?: number;
}
/**
 * A chemical structure extracted from a patent drawing page.
 */
export interface DrawingStructure {
  patent_id: string;
  page_number: number;
  structure_index: number;
  raw_smiles?: string;
  canonical_smiles?: string;
  inchi_key?: string;
  confidence?: number;
  extraction_tool?: string;
  input_image_sha256?: string;
  source_page_image_sha256?: string;
  preprocessing_applied?: string[];
  postprocessing_applied?: string[];
  rdkit_valid?: boolean;
  pubchem_match?: boolean;
  pubchem_cid?: number | null;
  llm_verified?: boolean | null;
  llm_verification_model?: string;
  llm_match_confidence?: number;
  tanimoto_to_target?: number;
  is_substructure_of_target?: boolean;
  target_is_substructure?: boolean;
  drawing_risk_signal?: DrawingRiskLevel;
  is_markush?: boolean;
  markush_cxsmiles?: string;
  markush_r_groups?: string[];
  markush_target_in_scope?: boolean | null;
  markush_scope_verdict?: MarkushScopeVerdict | null;
  stereo_flag?: string;
  stereo_cip_count?: number;
  stereo_ez_count?: number;
  stereo_target_cip_count?: number;
  stereo_target_ez_count?: number;
  stereo_claim_mentions?: boolean;
  stereo_details?: string;
  bbox?: [unknown, unknown, unknown, unknown] | null;
  original_page_image?: string;
  cropped_structure_image?: string;
  rendered_comparison_image?: string;
}
/**
 * Agent verdict for whether a target falls inside a Markush structure.
 */
export interface MarkushScopeVerdict {
  verdict?: "in_scope" | "out_of_scope" | "ambiguous";
  reasoning?: string;
  enumerated_hits?: string[];
  confidence?: number;
  abstained_reason?: string;
  tool_calls?: number;
  agent_model?: string;
}
/**
 * Release identities governing customer-visible drawing evidence.
 */
export interface DrawingGovernanceProvenance {
  schema_version?: "praviar.drawing-governance.v1";
  rollout_state: "internal" | "shadow" | "beta" | "production";
  influence_permitted: boolean;
  evidence_gate_passed: boolean;
  runtime_roster_sha256?: string;
  ml_bom_sha256?: string;
  calibration_artifact_id?: string;
  calibration_artifact_revision?: number;
  calibration_artifact_sha256?: string;
  worker_image_digest?: string;
  jurisdictions?: string[];
  verified_at?: string | null;
}
/**
 * Complete result of the agentic search loop.
 */
export interface SearchLoopResult {
  iterations_completed?: number;
  iteration_logs?: SearchIterationLog[];
  final_assessment?: CoverageAssessment | null;
  pending_collection_directives?: EvidenceCollectionDirective[];
  termination_reason?: string;
  total_input_tokens?: number;
  total_output_tokens?: number;
}
/**
 * Log entry for a single search iteration.
 */
export interface SearchIterationLog {
  iteration_number?: number;
  patents_found_new?: number;
  patents_found_total?: number;
  triage_relevant_new?: number;
  queries_used?: ExpandedSearchQueries | null;
  assessment?: CoverageAssessment | null;
  input_tokens?: number;
  output_tokens?: number;
}
/**
 * Assessment of search coverage adequacy.
 */
export interface CoverageAssessment {
  coverage_adequate?: boolean;
  confidence?: number;
  gaps_identified?: CoverageGap[];
  evidence_collection_directives?: EvidenceCollectionDirective[];
  suggested_queries?: ExpandedSearchQueries | null;
  iteration_summary?: string;
  assignee_distribution?: {
    [k: string]: number;
  };
  cpc_distribution?: {
    [k: string]: number;
  };
  [k: string]: unknown;
}
/**
 * Regulatory exclusivity data assembled from pharma regulatory sources.
 */
export interface RegulatoryExclusivity {
  /**
   * Matched Purple Book entry for biologic products
   */
  purple_book_entry?: PurpleBookEntry | null;
  /**
   * BPCIA 12-year reference product exclusivity expiry derived from Purple Book
   */
  bpcia_exclusivity_expiry?: string | null;
  /**
   * USPTO PTE certificates associated with this drug's patents
   */
  pte_extensions?: PTEEntry[];
  /**
   * Authoritative USPTO issued-certificate workbook used for PTE coverage
   */
  pte_source_url?: string;
  /**
   * Explicit population covered by the queried PTE dataset
   */
  pte_source_scope?: string;
  /**
   * Publisher limitations on the PTE dataset's legal and temporal coverage
   */
  pte_source_coverage_note?: string;
  /**
   * UTC instant at which the PTE dataset was retrieved
   */
  pte_source_retrieved_at?: string | null;
  /**
   * Publisher Last-Modified response header when supplied
   */
  pte_source_publisher_last_modified?: string;
  /**
   * Active Paragraph IV ANDA certifications for this product
   */
  paragraph_iv_challenges?: ParagraphIVEntry[];
  /**
   * Names of regulatory sources that were actually queried
   */
  data_sources_queried?: string[];
  /**
   * Per-source regulatory enrichment status so empty result sets cannot hide source failures or non-configuration.
   */
  source_statuses?: SourceHealthEntry[];
}
/**
 * Purple Book biologic product entry used in report regulatory data.
 */
export interface PurpleBookEntry {
  /**
   * BLA application number
   */
  bla_number: string;
  /**
   * Brand name (e.g. Humira)
   */
  proprietary_name?: string;
  /**
   * INN / proper name (e.g. adalimumab)
   */
  proper_name?: string;
  applicant?: string;
  /**
   * 351(a) for reference products, 351(k) for biosimilars
   */
  bla_type?: string;
  strength?: string;
  dosage_form?: string;
  route?: string;
  product_presentation?: string;
  marketing_status?: string;
  licensure?: string;
  approval_date?: string;
  ref_product_proper_name?: string;
  ref_product_proprietary_name?: string;
  /**
   * Reference Product Exclusivity Expiry Date (BPCIA 12-year exclusivity)
   */
  ref_product_exclusivity_expiry?: string;
  date_of_first_licensure?: string;
  /**
   * General exclusivity expiration date
   */
  exclusivity_expiration?: string;
  orphan_exclusivity_expiration?: string;
  /**
   * Whether the product has a biosimilar designation
   */
  biosimilar_designation?: string;
  /**
   * Whether the product has an interchangeable designation
   */
  interchangeable_designation?: string;
}
/**
 * A single USPTO Patent Term Extension certificate record.
 */
export interface PTEEntry {
  patent_number: string;
  product_name?: string;
  nda_bla_number?: string;
  extension_days?: string;
  status?: string;
}
/**
 * A single row from the FDA Paragraph IV certifications list.
 */
export interface ParagraphIVEntry {
  drug_name: string;
  dosage_form?: string | null;
  strength?: string | null;
  nda_number?: string | null;
  /**
   * Number of ANDAs carrying a Paragraph IV certification for this product.
   */
  submission_count?: number | null;
  first_filing_date?: string | null;
  patent_expiry_date?: string | null;
  has_180_day_exclusivity?: boolean;
  [k: string]: unknown;
}
/**
 * A recommended next step derived from analysis results.
 */
export interface ActionItem {
  action_type: ActionType;
  priority: ActionPriority;
  description: string;
  patent_ids?: string[];
  reasoning?: string;
  estimated_timeline?: string;
}
/**
 * Token usage for a single pipeline step, with model role for cost attribution.
 */
export interface StepTokenUsage {
  step_name: string;
  /**
   * triage, analysis, or deep
   */
  model_role: string;
  /**
   * Actual model identifier used (e.g. claude-haiku-4-5-20251001)
   */
  model_name?: string;
  input_tokens?: number;
  output_tokens?: number;
  [k: string]: unknown;
}
/**
 * Provenance manifest emitted alongside every FTO report.
 *
 * Immutable (``frozen=True``) and strict (``extra="forbid"``) so we can
 * diff manifests across runs without ambiguity.
 */
export interface ReportManifest {
  /**
   * Praviar pipeline git SHA at runtime.
   */
  pipeline_version: string;
  /**
   * Source checkout state: clean, dirty, build, or unknown.
   */
  source_tree_state?: string;
  /**
   * Digest binding the exact source tree, including local changes.
   */
  source_tree_digest?: string;
  /**
   * UTC timestamp the manifest was built.
   */
  generated_at: string;
  /**
   * Raw user input for this run.
   */
  compound_query: string;
  /**
   * Map of prompt filename -> SHA256 hex of file contents at load time.
   */
  prompt_hashes?: {
    [k: string]: string;
  };
  /**
   * Map of pipeline role (triage/analysis/deep) -> model ID.
   */
  model_versions?: {
    [k: string]: string;
  };
  /**
   * Per-role sampling parameters, e.g. {'triage': {'temperature': 0}}.
   */
  sampling?: {
    [k: string]: {
      [k: string]: unknown;
    };
  };
  /**
   * Map of source name -> immutable replayable snapshot identifier.
   */
  source_snapshots?: {
    [k: string]: string;
  };
  /**
   * Map of live source name -> non-replayable observation metadata.
   */
  source_observations?: {
    [k: string]: string;
  };
  /**
   * Map of allowed tool name -> SHA256 hex of its tool schema.
   */
  tool_definition_hashes?: {
    [k: string]: string;
  };
  /**
   * SHA256 hex of the deterministic tool-call summary log.
   */
  tool_trace_digest: string;
  /**
   * Non-secret key ID used for domain-separated tool-argument HMACs.
   */
  tool_trace_key_id?: string;
  /**
   * Number of sanitized tool calls included in tool_trace_digest.
   */
  tool_call_count?: number;
  /**
   * Owner-only relative reference to retained exact source responses.
   */
  response_cache_reference?: string;
  /**
   * Digest binding the complete retained response cache.
   */
  response_cache_digest?: string;
  /**
   * HMAC authenticating response_cache_digest.
   */
  response_cache_hmac_sha256?: string;
  /**
   * Non-secret audit key ID used to authenticate the response cache.
   */
  response_cache_key_id?: string;
  /**
   * Number of retained exact external response entries.
   */
  response_cache_entry_count?: number;
  /**
   * Per-role LLM cost aggregates for the run, keyed by role (triage/analysis/deep/report/verification/critic/doe/invalidity/unknown). Each value contains input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, estimated_usd, call_count, and models (map of model-id -> call count).
   */
  cost_breakdown?: {
    [k: string]: {
      [k: string]: unknown;
    };
  };
  /**
   * Sum of estimated_usd across all roles for this run.
   */
  total_cost_usd?: number;
}
/**
 * Keep every generated contract reachable from one explicit root.
 */
export interface SharedRuntimeContracts {
  report: FTOReport;
  claimed_use_match_receipt: ClaimedUseMatchReceipt;
}
