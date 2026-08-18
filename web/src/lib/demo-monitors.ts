/**
 * In-memory monitor and alert fixtures for demo mode.
 *
 * Mirrors the API response shapes from `/monitors` so demo flows can render
 * the full monitors UI without contacting the API.
 */

import type {
  MonitorAlertResponse,
  MonitorConclusionReassessmentResponse,
  MonitorResponse,
  ReassessMonitorConclusionInput,
} from "@/hooks/use-monitors";
import {
  SHOWCASE_FIXTURE_RECEIPT,
  SHOWCASE_PAYLOAD,
} from "@/lib/showcase-report";

const DEMO_MONITOR_ID = `monitor-${SHOWCASE_PAYLOAD.analysis.id}`;
const PRIMARY_PUBLICATION =
  SHOWCASE_PAYLOAD.analysis.families[0].publications[0];
const SECONDARY_PUBLICATION =
  SHOWCASE_PAYLOAD.analysis.families[1].publications[0];

const INITIAL_MONITORS: MonitorResponse[] = [
  {
    id: DEMO_MONITOR_ID,
    compound_smiles: "",
    compound_name: `${SHOWCASE_PAYLOAD.compound.display_name} watch`,
    source_analysis_id: "ana_demo_001",
    source_report_id: `rpt_${SHOWCASE_PAYLOAD.analysis.id}`,
    source_trust_mode: "explorer",
    schedule: "weekly",
    is_active: true,
    jurisdiction_bundle: "fictional_showcase",
    target_jurisdictions: [...SHOWCASE_PAYLOAD.compound.jurisdictions],
    strategy_version: SHOWCASE_FIXTURE_RECEIPT.fixtureVersion,
    monitoring_strategy: { posture: "conclusion_aware_event_first" },
    watch_targets: [],
    last_run_at: SHOWCASE_PAYLOAD.clock,
    last_full_refresh_at: SHOWCASE_PAYLOAD.analysis.completed_at,
    last_run_mode: "diff_only",
    last_run_status: "review_required",
    last_run_summary: SHOWCASE_PAYLOAD.failure_states[0].message,
    last_patent_count: SHOWCASE_PAYLOAD.analysis.families.length,
    conclusion_status: "review_required",
    stale_conclusion_count: 2,
    stale_conclusions: [
      {
        conclusion_id: "clearance:global",
        conclusion_type: "clearance_decision",
        label: "Overall FTO clearance",
        previous_outcome: "unclear",
        status: "review_required",
        source_report_id: `rpt_${SHOWCASE_PAYLOAD.analysis.id}`,
        dependency_fingerprint: "a".repeat(64),
        invalidated_at: SHOWCASE_PAYLOAD.clock,
        latest_observed_at: SHOWCASE_PAYLOAD.clock,
        reason_codes: ["new_patent_candidate"],
        trigger_patent_ids: [PRIMARY_PUBLICATION],
        trigger_event_ids: [],
        jurisdictions: [PRIMARY_PUBLICATION.slice(0, 2)],
        reassessment_id: "11111111-1111-4111-8111-111111111111",
        alert_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        evidence_digest: "c".repeat(64),
        evidence_version: SHOWCASE_FIXTURE_RECEIPT.fixtureVersion,
        evidence_observed_at: SHOWCASE_PAYLOAD.clock,
      },
      {
        conclusion_id: "clearance:US",
        conclusion_type: "jurisdiction_clearance",
        label: "Fictional-jurisdiction screening posture",
        previous_outcome: "unclear",
        status: "review_required",
        source_report_id: `rpt_${SHOWCASE_PAYLOAD.analysis.id}`,
        dependency_fingerprint: "b".repeat(64),
        invalidated_at: SHOWCASE_PAYLOAD.clock,
        latest_observed_at: SHOWCASE_PAYLOAD.clock,
        reason_codes: ["new_patent_candidate"],
        trigger_patent_ids: [PRIMARY_PUBLICATION],
        trigger_event_ids: [],
        jurisdictions: [PRIMARY_PUBLICATION.slice(0, 2)],
        reassessment_id: "22222222-2222-4222-8222-222222222222",
        alert_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        evidence_digest: "d".repeat(64),
        evidence_version: SHOWCASE_FIXTURE_RECEIPT.fixtureVersion,
        evidence_observed_at: SHOWCASE_PAYLOAD.clock,
      },
    ],
    created_at: SHOWCASE_PAYLOAD.analysis.started_at,
  },
];

const monitors = new Map<string, MonitorResponse>(
  INITIAL_MONITORS.map((monitor) => [monitor.id, monitor]),
);

const INITIAL_ALERTS: Record<string, MonitorAlertResponse[]> = {
  [DEMO_MONITOR_ID]: [
    {
      id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      monitor_id: DEMO_MONITOR_ID,
      new_patent_ids: [PRIMARY_PUBLICATION],
      new_patent_count: 1,
      run_at: SHOWCASE_PAYLOAD.clock,
      dismissed: false,
      created_at: SHOWCASE_PAYLOAD.clock,
      summary: SHOWCASE_PAYLOAD.failure_states[0].message,
      stale_conclusion_count: 2,
      affected_conclusions: INITIAL_MONITORS[0].stale_conclusions,
    },
    {
      id: "alert-demo-002",
      monitor_id: DEMO_MONITOR_ID,
      new_patent_ids: [SECONDARY_PUBLICATION],
      new_patent_count: 1,
      run_at: SHOWCASE_PAYLOAD.analysis.completed_at,
      dismissed: false,
      created_at: SHOWCASE_PAYLOAD.analysis.completed_at,
      summary: SHOWCASE_PAYLOAD.analysis.limitations[3],
    },
  ],
};

const alerts = new Map<string, MonitorAlertResponse[]>(
  Object.entries(INITIAL_ALERTS),
);

export function listDemoMonitors(): MonitorResponse[] {
  return Array.from(monitors.values()).sort(
    (a, b) =>
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
}

export function getDemoMonitorAlerts(
  monitorId: string,
): MonitorAlertResponse[] {
  return [...(alerts.get(monitorId) ?? [])].sort(
    (a, b) =>
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
}

export function createDemoMonitor(input: {
  analysis_id?: string;
  compound_smiles?: string;
  compound_name?: string;
  schedule?: string;
}): MonitorResponse {
  const now = new Date().toISOString();
  const id = `monitor-demo-${monitors.size + 1}-${Math.random().toString(36).slice(2, 6)}`;
  const monitor: MonitorResponse = {
    id,
    compound_smiles: input.compound_smiles ?? "",
    compound_name: input.compound_name ?? "Demo monitor",
    source_analysis_id: input.analysis_id ?? null,
    source_report_id: input.analysis_id ?? "",
    source_trust_mode: "monitor",
    schedule: input.schedule ?? "weekly",
    is_active: true,
    jurisdiction_bundle: "major_markets",
    target_jurisdictions: ["US", "EP", "UK", "JP", "CN"],
    strategy_version: "2026-07-monitor-v2",
    monitoring_strategy: { posture: "conclusion_aware_event_first" },
    watch_targets: [],
    last_run_at: null,
    last_full_refresh_at: null,
    last_run_mode: "pending",
    last_run_status: "pending",
    last_run_summary: "Awaiting first run.",
    last_patent_count: 0,
    conclusion_status: input.analysis_id ? "fresh" : "unbound",
    stale_conclusions: [],
    stale_conclusion_count: 0,
    created_at: now,
  };

  monitors.set(monitor.id, monitor);
  alerts.set(monitor.id, []);
  return monitor;
}

export function updateDemoMonitor(
  monitorId: string,
  data: { schedule?: string; is_active?: boolean; compound_name?: string },
): MonitorResponse {
  const current = monitors.get(monitorId);
  if (!current) {
    throw new Error("Demo monitor not found");
  }

  const updated: MonitorResponse = {
    ...current,
    ...data,
  };
  monitors.set(monitorId, updated);
  return updated;
}

export function deleteDemoMonitor(monitorId: string): void {
  monitors.delete(monitorId);
  alerts.delete(monitorId);
}

export function dismissDemoAlert(monitorId: string, alertId: string): void {
  const currentAlerts = alerts.get(monitorId) ?? [];
  alerts.set(
    monitorId,
    currentAlerts.map((alert) =>
      alert.id === alertId ? { ...alert, dismissed: true } : alert,
    ),
  );
}

export function reassessDemoMonitorConclusion(
  monitorId: string,
  conclusionId: string,
  data: ReassessMonitorConclusionInput["data"],
): MonitorConclusionReassessmentResponse {
  const current = monitors.get(monitorId);
  if (!current) {
    throw new Error("Demo monitor not found");
  }
  const impact = current.stale_conclusions.find(
    (item) => item.conclusion_id === conclusionId,
  );
  if (!impact) {
    throw new Error("Demo conclusion has no open reassessment");
  }
  const now = new Date().toISOString();
  const remaining = current.stale_conclusions.filter(
    (item) => item.conclusion_id !== conclusionId,
  );
  monitors.set(monitorId, {
    ...current,
    stale_conclusions: remaining,
    stale_conclusion_count: remaining.length,
    conclusion_status: remaining.length > 0 ? "review_required" : "reassessed",
    last_run_status: remaining.length > 0 ? "review_required" : "reassessed",
  });
  return {
    id: `demo-reassessment-${conclusionId}`,
    monitor_id: monitorId,
    source_analysis_id: current.source_analysis_id ?? "demo-source-analysis",
    source_report_id: impact.source_report_id,
    conclusion_id: impact.conclusion_id,
    conclusion_type: impact.conclusion_type,
    conclusion_label: impact.label,
    previous_outcome: impact.previous_outcome,
    dependency_fingerprint: impact.dependency_fingerprint,
    status: data.resolution,
    trigger_evidence: { ...impact },
    invalidated_at: impact.invalidated_at,
    latest_observed_at: impact.latest_observed_at,
    resolved_at: now,
    reviewer_role: "attorney",
    reviewer_name: "Demo counsel",
    reviewer_email: "counsel@example.com",
    resolution_note: data.resolution_note,
    attestation_version: "2026-07-counsel-reassessment-v1",
    attestation_statement:
      "I attest that I reviewed the cited monitoring changes and affected source-report conclusion.",
    attestation_accepted: true,
    replacement_analysis_id: data.replacement_analysis_id ?? null,
    created_at: impact.invalidated_at,
    updated_at: now,
  };
}
