import type { RiskLevel } from "@praviar/shared-types";

export interface KeyPatent {
  patent_number: string;
  risk_level?: RiskLevel;
  assignee?: string;
  expiry?: string;
  patent_url?: string;
  source_reference?: string;
}

export interface SharedReport {
  report_id?: string;
  share_id?: string;
  packet_version?: string;
  source_snapshot_at?: string;
  pipeline_version?: string;
  model_version?: string;
  integrity_digest?: string;
  compound_name: string;
  overall_risk: RiskLevel;
  blocking_patents_count: number;
  total_patents_found: number;
  executive_summary: string;
  key_findings: string[];
  generated_at: string;
  key_patents?: KeyPatent[];
  source_coverage?: string[];
  jurisdiction_scope?: string[];
  evidence_limitations?: string[];
  integrity_summary?: SharedReportIntegritySummary;
  total_material_patents?: number;
  omitted_key_patents_count?: number;
  omitted_limitations_count?: number;
  standard_limitations?: string[];
  intended_use?: string;
  ai_system_notice?: string;
  reliance_boundary?: string;
  review_status?: string;
  share_expires_at?: string;
  verified_recipient_email: string;
  attributable_view_number: number;
  verified_session_expires_at: string;
}

export interface SharedReportIntegritySummary {
  affected_patents_count?: number;
  recoverable_failures_count?: number;
  needs_review_count?: number;
  data_limitations_count?: number;
  source_caveats_count?: number;
  evidence_sufficient_for_clearance?: boolean;
  metadata_inconsistent?: boolean;
}

export type SharedReportResult =
  | { status: "ok"; report: SharedReport }
  | { status: "not-found" }
  | { status: "expired" }
  | { status: "verification-required"; invalid: boolean }
  | { status: "error" };
