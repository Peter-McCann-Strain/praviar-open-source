/**
 * API response types for the Praviar backend.
 *
 * These mirror the Pydantic response schemas in api/src/api/schemas/.
 * Single source of truth for all API response shapes used in hooks.
 */

import type {
  ClaimedUseMatchReceipt,
  MarkushEvidenceReceipt,
  RiskLevel,
} from "@praviar/shared-types";

export interface ClaimedUseEligibleUse {
  accused_act_index: number;
  jurisdiction: string;
  actor: string;
  start_date: string;
  regulatory_path:
    | "none"
    | "anda"
    | "nda_505_b_1"
    | "nda_505_b_2"
    | "bla_351_a"
    | "abla"
    | "biosimilar_351_k"
    | "unknown";
  target_product_identity: string;
  proposed_indication: string;
  proposed_label_use: string;
  label_carve_out_state: "none" | "partial" | "complete" | "unknown";
}

export interface ClaimedUseReceiptIssueRequest {
  expected_report_id: string;
  expected_report_fingerprint: string;
  patent_id: string;
  claim_number: number;
  accused_act_index: number;
  claimed_use_match: true;
  product_identity_match: true;
}

export interface ClaimedUseReceiptRevokeRequest {
  reason: string;
}

export interface ClaimedUseReceipt {
  id: string;
  analysis_id: string;
  report_id: string;
  report_fingerprint: string;
  patent_id: string;
  claim_number: number;
  accused_act_index: number;
  accused_act_sha256: string;
  receipt: ClaimedUseMatchReceipt;
  issuer_user_id: string;
  reviewer_role: "attorney";
  attestation_statement_version: "claimed-use-counsel-affirmation-v1";
  issued_at: string;
  revoked_at: string | null;
  revoked_by_user_id: string | null;
  revocation_reason: string;
  governs_current_report: boolean;
  can_revoke: boolean;
}

export interface ClaimedUseReceiptListResponse {
  current_report_id: string;
  current_report_fingerprint: string;
  eligible_uses: ClaimedUseEligibleUse[];
  items: ClaimedUseReceipt[];
}

export interface MarkushEvidenceImportRequest {
  query_structure: string;
  target_structure: string;
  query_role: "target_compound" | "murcko_scaffold";
  chemical_search_mode: "exact" | "substructure" | "scaffold";
  markush_method: "enumeration" | "formula_matching";
  markush_match_mode: "exact" | "substructure" | "fuzzy";
  wipo_query_field?: "ENUM" | null;
  family_grouping_enabled: boolean;
  executed_at: string;
  artifact_base64: string;
  artifact_filename: string;
  artifact_media_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  controls_artifact_base64: string;
  controls_artifact_filename: string;
  controls_artifact_media_type: "image/png";
  result_count: number;
  selected_publication_ids: string[];
  limitations: string[];
}

export interface MarkushEvidenceVerifyRequest {
  draft_receipt: MarkushEvidenceReceipt;
  query_structure: string;
  target_structure: string;
  query_role: "target_compound" | "murcko_scaffold";
  chemical_search_mode: "exact" | "substructure" | "scaffold";
  markush_method: "enumeration" | "formula_matching";
  markush_match_mode: "exact" | "substructure" | "fuzzy";
  wipo_query_field?: "ENUM" | null;
  family_grouping_enabled: boolean;
  executed_at: string;
  artifact_base64: string;
  artifact_filename: string;
  artifact_media_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  controls_artifact_base64: string;
  controls_artifact_filename: string;
  controls_artifact_media_type: "image/png";
  result_count: number;
  selected_publication_ids: string[];
}

// ── Analysis ────────────────────────────────────────────────

export interface AnalysisListItem {
  id: string;
  compound_input: string;
  compound_name: string;
  compound_smiles: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  current_step: number;
  progress_pct: number;
  development_fixture?: boolean;
  invalidity_assessments_count?: number | null;
  overall_risk: RiskLevel | null;
  blocking_patents_count: number | null;
  total_patents_found: number;
  executive_summary: string;
  risk_ratings_restricted?: boolean;
  estimated_cost_usd: number;
  pipeline_duration_seconds: number | null;
  flagged_for_review: boolean;
  review_status?: AnalysisReviewStatusSummary | null;
  launch_context?: AnalysisLaunchContextSummary | null;
  current_user_role?: string | null;
  share_active?: boolean;
  share_recipient_bound?: boolean;
  share_view_count?: number;
  share_last_viewed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AnalysisProductContext {
  product_name?: string;
  dosage_form?: string;
  route_of_administration?: string;
  strength?: string;
  release_profile?: string;
  salt_polymorph_form?: string;
  key_excipients?: string[];
  indication?: string;
  patient_population?: string;
  combination_assets?: string[];
  reference_product?: string;
  manufacturing_route?: string;
  commercial_action?: string;
  decision_deadline?: string;
  commercial_territories?: string[];
  accused_acts?: Array<{
    act:
      | "manufacture"
      | "import"
      | "offer_for_sale"
      | "sale"
      | "use"
      | "regulatory_submission";
    jurisdiction: string;
    start_date: string;
    end_date?: string | null;
    actor: string;
    status: "planned" | "actual" | "denied" | "hypothetical";
    purpose:
      | "commercial"
      | "regulatory_approval"
      | "clinical_research"
      | "experimental"
      | "internal_research"
      | "other"
      | "unknown";
    regulatory_path:
      | "none"
      | "anda"
      | "nda_505_b_1"
      | "nda_505_b_2"
      | "bla_351_a"
      | "abla"
      | "biosimilar_351_k"
      | "unknown";
    instrumentality: string;
    liability_theory:
      | "direct"
      | "induced"
      | "contributory"
      | "artificial_infringement"
      | "unknown";
    performs_all_claim_steps?: boolean | null;
    direct_infringer?: string | null;
    knowledge_of_patent?: boolean | null;
    affirmative_encouragement?: boolean | null;
    manufacturing_jurisdiction?: string | null;
    process_used?: string | null;
    process_use_verified?: boolean | null;
    materially_changed_after_process?: boolean | null;
    trivial_component_after_process?: boolean | null;
    target_product_identity?: string | null;
    proposed_indication?: string | null;
    proposed_label_use?: string | null;
    label_carve_out_state?: "none" | "partial" | "complete" | "unknown" | null;
    claimed_use_match_receipts?: ClaimedUseMatchReceipt[];
  }>;
  known_patents_or_assignees?: string[];
  owned_or_licensed_ip?: string;
}

export interface AnalysisLaunchContextSummary {
  trust_mode?: string | null;
  jurisdiction_bundle?: string | null;
  target_jurisdictions: string[];
  development_stage?: string | null;
  asset_type_hint?: string | null;
  matter_type?: string | null;
  intended_actions: string[];
  product_context: AnalysisProductContext;
}

export type AnalysisReviewStatusValue =
  | "pending"
  | "under_review"
  | "approved"
  | "changes_requested";

export interface AnalysisReviewStatusSummary {
  status: AnalysisReviewStatusValue;
  is_persisted: boolean;
  note?: string | null;
  reviewer_name?: string | null;
  reviewer_email?: string | null;
  reviewed_at?: string | null;
  updated_at?: string | null;
}

export interface AnalysisListResponse {
  items: AnalysisListItem[];
  total: number;
  page: number;
  per_page: number;
  status_counts: Record<string, number>;
}
