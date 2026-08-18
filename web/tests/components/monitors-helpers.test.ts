import { afterEach, describe, expect, it, vi } from "vitest";
import {
  formatMonitorDate,
  getMonitorPosture,
  relativeTime,
} from "@/components/monitors/helpers";
import type { MonitorResponse } from "@/hooks/use-monitors";

function makeMonitor(
  overrides: Partial<MonitorResponse> = {},
): MonitorResponse {
  return {
    id: "monitor-1",
    compound_smiles: "CCO",
    compound_name: "Ethanol",
    source_analysis_id: null,
    source_report_id: "",
    source_trust_mode: "monitor",
    schedule: "weekly",
    is_active: true,
    jurisdiction_bundle: "custom",
    target_jurisdictions: ["US", "EP"],
    strategy_version: "2026-04-monitor-v1",
    monitoring_strategy: {},
    watch_targets: [],
    last_run_at: "2026-06-10T12:00:00.000Z",
    last_full_refresh_at: null,
    last_run_mode: "diff_only",
    last_run_status: "ready",
    last_run_summary: "No new events.",
    last_patent_count: 2,
    conclusion_status: "fresh",
    stale_conclusions: [],
    stale_conclusion_count: 0,
    created_at: "2026-06-01T12:00:00.000Z",
    ...overrides,
  };
}

describe("monitor helpers", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("handles invalid and future relative timestamps safely", () => {
    vi.setSystemTime(new Date("2026-06-19T12:00:00.000Z"));

    expect(relativeTime("not-a-date")).toBe("Unknown");
    expect(relativeTime("2026-06-20T12:00:00.000Z")).toBe("Scheduled");
  });

  it("formats monitor dates in UTC", () => {
    expect(formatMonitorDate("2026-06-01T00:30:00.000Z")).toBe("Jun 1, 2026");
  });

  it("separates healthy, stale, pending, and paused posture", () => {
    vi.setSystemTime(new Date("2026-06-19T12:00:00.000Z"));

    expect(getMonitorPosture(makeMonitor()).label).toBe("Healthy");
    expect(
      getMonitorPosture(
        makeMonitor({ last_run_at: "2026-05-01T12:00:00.000Z" }),
      ).label,
    ).toBe("Stale");
    expect(
      getMonitorPosture(
        makeMonitor({ last_run_at: null, last_run_status: "pending" }),
      ).label,
    ).toBe("First run pending");
    expect(getMonitorPosture(makeMonitor({ is_active: false })).label).toBe(
      "Paused",
    );
  });

  it("never labels a monitor healthy while report conclusions are stale", () => {
    const posture = getMonitorPosture(
      makeMonitor({
        conclusion_status: "review_required",
        last_run_status: "review_required",
        stale_conclusion_count: 2,
        stale_conclusions: [],
      }),
    );

    expect(posture).toEqual({
      label: "Attorney review required",
      detail: "2 prior conclusions no longer current",
      tone: "warning",
      needsAttention: true,
    });
  });
});
