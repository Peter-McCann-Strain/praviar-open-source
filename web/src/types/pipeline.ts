/**
 * Typed pipeline SSE event payloads.
 *
 * Replaces `Record<string, unknown>` throughout the SSE → store → UI chain
 * with discriminated unions so TypeScript catches payload mismatches at compile time.
 */

import type { ClaimedUseMatchReceipt, RiskLevel } from "@praviar/shared-types";

// ── Matter scope preflight ──────────────────────────────────

export type DevelopmentStage =
  | "discovery"
  | "lead_optimization"
  | "preclinical"
  | "clinical"
  | "commercial";

export type AssetTypeHint =
  | "small_molecule"
  | "markush_candidate"
  | "biologic_or_sequence"
  | "formulation"
  | "process_or_synthesis"
  | "combination"
  | "unknown";

export type IntendedAction =
  | "manufacture_import"
  | "commercial_launch"
  | "formulation_review"
  | "method_of_use_review"
  | "design_around"
  | "diligence_screen"
  | "monitor_continuations";

export interface MatterScopePreflightValue {
  assetTypeHint: AssetTypeHint;
  developmentStage: DevelopmentStage;
  intendedActions: IntendedAction[];
}

export type AccusedActType =
  | "manufacture"
  | "import"
  | "offer_for_sale"
  | "sale"
  | "use"
  | "regulatory_submission";

export type AccusedActStatus = "planned" | "actual" | "denied" | "hypothetical";

export type AccusedActPurpose =
  | "commercial"
  | "regulatory_approval"
  | "clinical_research"
  | "experimental"
  | "internal_research"
  | "other"
  | "unknown";

export type RegulatorySubmissionPath =
  | "none"
  | "anda"
  | "nda_505_b_1"
  | "nda_505_b_2"
  | "bla_351_a"
  | "abla"
  | "biosimilar_351_k"
  | "unknown";

export type AccusedActLiabilityTheory =
  | "direct"
  | "induced"
  | "contributory"
  | "artificial_infringement"
  | "unknown";

export type LabelCarveOutState = "none" | "partial" | "complete" | "unknown";

export interface AccusedActRecordValue {
  act: AccusedActType;
  jurisdiction: string;
  startDate: string;
  endDate?: string;
  actor: string;
  status: AccusedActStatus;
  purpose: AccusedActPurpose;
  regulatoryPath: RegulatorySubmissionPath;
  instrumentality: string;
  liabilityTheory: AccusedActLiabilityTheory;
  performsAllClaimSteps?: boolean;
  directInfringer?: string;
  knowledgeOfPatent?: boolean;
  affirmativeEncouragement?: boolean;
  manufacturingJurisdiction?: string;
  processUsed?: string;
  processUseVerified?: boolean;
  materiallyChangedAfterProcess?: boolean;
  trivialComponentAfterProcess?: boolean;
  targetProductIdentity?: string;
  proposedIndication?: string;
  proposedLabelUse?: string;
  labelCarveOutState?: LabelCarveOutState;
  claimedUseMatchReceipts?: ClaimedUseMatchReceipt[];
}

export interface ProductContextValue {
  productName?: string;
  dosageForm?: string;
  routeOfAdministration?: string;
  strength?: string;
  releaseProfile?: string;
  saltPolymorphForm?: string;
  keyExcipients?: string[];
  indication?: string;
  patientPopulation?: string;
  combinationAssets?: string[];
  referenceProduct?: string;
  manufacturingRoute?: string;
  commercialAction?: string;
  decisionDeadline?: string;
  commercialTerritories?: string[];
  accusedActs?: AccusedActRecordValue[];
  knownPatentsOrAssignees?: string[];
  ownedOrLicensedIp?: string;
}

// ── Per-step progress payloads ──────────────────────────────

export interface Step1Payload {
  compound_name?: string;
  smiles?: string;
  message?: string;
}

export interface Step2Payload {
  patents_found?: number;
  sources_completed?: string[];
  message?: string;
}

export interface Step3Payload {
  relevant?: number;
  total?: number;
  message?: string;
}

export interface Step4Payload {
  analyzed?: number;
  total?: number;
  current_patent?: string;
  message?: string;
}

export interface Step5Payload {
  assessments?: number;
  message?: string;
}

export interface Step6Payload {
  assessed?: number;
  message?: string;
}

export interface Step7Payload {
  checks_passed?: number;
  message?: string;
}

export interface Step8Payload {
  format?: string;
  message?: string;
}

/** Map from step number to its typed progress payload. */
export interface StepPayloadMap {
  1: Step1Payload;
  2: Step2Payload;
  3: Step3Payload;
  4: Step4Payload;
  5: Step5Payload;
  6: Step6Payload;
  7: Step7Payload;
  8: Step8Payload;
}

export type StepNumber = keyof StepPayloadMap;

/** Union of all step payloads — used where the step number isn't statically known. */
export type AnyStepPayload = StepPayloadMap[StepNumber];

// ── SSE event types ─────────────────────────────────────────

export interface PipelineEventStarted {
  step: number;
  step_name: string;
  type: "started";
  payload: { description?: string };
  timestamp: string;
}

export interface PipelineEventProgress {
  step: number;
  step_name: string;
  type: "progress";
  payload: AnyStepPayload;
  timestamp: string;
}

export interface PipelineEventCompleted {
  step: number;
  step_name: string;
  type: "completed";
  payload: { overall_risk?: RiskLevel };
  timestamp: string;
}

export interface PipelineEventFailed {
  step: number;
  step_name: string;
  type: "failed";
  payload: { error?: string };
  timestamp: string;
}

/**
 * Emitted when a running pipeline is cancelled (e.g. user cancel, batch cancel
 * from another tab). The backend publishes this with step 0 / step_name
 * "cancelled" (see api workers/tasks.py).
 */
export interface PipelineEventCancelled {
  step: number;
  step_name?: string;
  type: "cancelled";
  payload: { message?: string; cancelled?: boolean };
  timestamp?: string;
}

/**
 * Emitted by the SSE endpoint when the live stream exceeds its max duration
 * (see api services/pipeline_stream.py). The pipeline itself may still be
 * running server-side; the client should stop the stale stream and refetch.
 */
export interface PipelineEventTimeout {
  type: "timeout";
  payload: { message?: string };
  step?: number;
  step_name?: string;
  timestamp?: string;
}

/** Discriminated union of all pipeline SSE events. Discriminant: `type`. */
export type PipelineEvent =
  | PipelineEventStarted
  | PipelineEventProgress
  | PipelineEventCompleted
  | PipelineEventFailed
  | PipelineEventReviewRequired
  | PipelineEventCheckpoint
  | PipelineEventCancelled
  | PipelineEventTimeout;

// ── Jurisdiction bundles ─────────────────────────────────────

export type MajorMarketJurisdiction = "US" | "EP" | "UK" | "IN" | "JP" | "CN";

export type JurisdictionBundle =
  | "us_europe"
  | "europe_uk"
  | "major_markets"
  | "custom";

// ── Pipeline config (sent with analysis creation) ───────────

export interface PipelineConfig {
  search_max_ranked_results: number;
  search_tanimoto_threshold: number;
  include_expired: boolean;
  enable_pubchem: boolean;
  enable_bigquery: boolean;
  enable_surechembl: boolean;
  enable_patcid: boolean;
  max_analysis_patents: number;
  max_doe_candidates: number;
  triage_batch_size: number;
  citation_traversal_enabled: boolean;
  citation_max_depth: number;
  analysis_thinking_budget_tokens: number;
  search_expired_grace_years: number;
  search_jurisdictions: string[];
  thinking_effort_analysis: "high" | "medium" | "low";
  thinking_effort_triage: "high" | "medium" | "low";
  thinking_effort_report: "high" | "medium" | "low";
  hitl_enabled: boolean;
  hitl_checkpoints: string[];
  hitl_auto_skip_minutes: number;
}

// ── HITL checkpoint events ───────────────────────────────────

export interface PipelineEventCheckpoint {
  step: number;
  step_name: string;
  type: "checkpoint";
  payload: {
    checkpoint_id?: string;
    checkpoint_type:
      | "identity_review"
      | "search_review"
      | "triage_review"
      | "analysis_review"
      | "report_review";
    context: Record<string, unknown>;
    requires_response: boolean;
    timeout_minutes: number;
  };
  timestamp: string;
}

export interface PipelineEventReviewRequired {
  step: number;
  step_name: string;
  type: "review_required";
  payload: {
    checkpoint_id?: string;
    checkpoint_type:
      | "identity_review"
      | "search_review"
      | "triage_review"
      | "analysis_review"
      | "report_review";
    context?: Record<string, unknown>;
    requires_response: true;
    timeout_minutes: number;
    elapsed_seconds?: number;
  };
  timestamp: string;
}
