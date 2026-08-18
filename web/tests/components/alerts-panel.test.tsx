import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { APIError } from "@/lib/api-client";

const mockUseMonitorAlerts = vi.hoisted(() => vi.fn());
const mockDismissMutate = vi.hoisted(() => vi.fn());
const mockReassessMutate = vi.hoisted(() => vi.fn());

vi.mock("@/hooks/use-monitors", () => ({
  useMonitorAlerts: (...args: unknown[]) => mockUseMonitorAlerts(...args),
  useDismissAlert: () => ({
    mutate: mockDismissMutate,
    isPending: false,
  }),
  useReassessMonitorConclusion: () => ({
    mutate: mockReassessMutate,
    isPending: false,
    error: null,
    reset: vi.fn(),
  }),
}));

import { AlertsPanel } from "@/components/monitors/alerts-panel";

describe("AlertsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseMonitorAlerts.mockReturnValue({
      data: { items: [], total: 0 },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });
  });

  it("moves focus into the alert rail when it opens", () => {
    render(
      <AlertsPanel
        monitorId="monitor-1"
        monitorName="succinic acid"
        onClose={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("button", { name: "Close alerts panel" }),
    ).toHaveFocus();
  });

  it("renders an alert-load recovery state instead of a false empty state", () => {
    const refetch = vi.fn();
    mockUseMonitorAlerts.mockReturnValue({
      data: undefined,
      error: new Error("401 unauthorized"),
      isLoading: false,
      refetch,
    });

    render(
      <AlertsPanel
        monitorId="monitor-1"
        monitorName="succinic acid"
        onClose={vi.fn()}
      />,
    );

    expect(
      screen.getByText("Alert history temporarily unavailable"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("No monitored changes detected"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/401 unauthorized/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry alert load" }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("prefers the alert-load recovery state over empty cached data after an error", () => {
    mockUseMonitorAlerts.mockReturnValue({
      data: { items: [], total: 0, page: 1, per_page: 20 },
      error: new Error("session expired"),
      isLoading: false,
      refetch: vi.fn(),
    });

    render(
      <AlertsPanel
        monitorId="monitor-1"
        monitorName="succinic acid"
        onClose={vi.fn()}
      />,
    );

    expect(
      screen.getByText("Alert history temporarily unavailable"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("No monitored changes detected"),
    ).not.toBeInTheDocument();
  });

  it("labels a populated alert rail as stale when refresh fails", () => {
    mockUseMonitorAlerts.mockReturnValue({
      data: {
        items: [
          {
            id: "alert-stale",
            monitor_id: "monitor-1",
            new_patent_ids: ["US123"],
            new_patent_count: 1,
            run_at: "2026-06-01T10:00:00.000Z",
            dismissed: false,
            created_at: "2026-06-01T10:05:00.000Z",
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
      },
      error: new Error("backend unavailable"),
      isLoading: false,
      refetch: vi.fn(),
    });

    render(
      <AlertsPanel
        monitorId="monitor-1"
        monitorName="succinic acid"
        onClose={vi.fn()}
      />,
    );

    expect(
      screen.getByText(
        /Alert refresh failed. Showing the last loaded alert history/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("1 new patent found")).toBeInTheDocument();
  });

  it("hides cached alert rows when alert history access is revoked", () => {
    mockUseMonitorAlerts.mockReturnValue({
      data: {
        items: [
          {
            id: "alert-private",
            monitor_id: "monitor-1",
            new_patent_ids: ["US123"],
            new_patent_count: 1,
            run_at: "2026-06-01T10:00:00.000Z",
            dismissed: false,
            created_at: "2026-06-01T10:05:00.000Z",
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
      },
      error: new APIError(403, "Forbidden"),
      isLoading: false,
      refetch: vi.fn(),
    });

    render(
      <AlertsPanel
        monitorId="monitor-1"
        monitorName="succinic acid"
        onClose={vi.fn()}
      />,
    );

    expect(
      screen.getByText("Alert history access restricted"),
    ).toBeInTheDocument();
    expect(screen.queryByText("1 new patent found")).not.toBeInTheDocument();
    expect(screen.queryByText(/Alert refresh failed/i)).not.toBeInTheDocument();
  });

  it("renders empty alert pages as a refresh state, not verified absence", () => {
    mockUseMonitorAlerts.mockReturnValue({
      data: { items: [], total: 25, page: 2, per_page: 20 },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });

    render(
      <AlertsPanel
        monitorId="monitor-1"
        monitorName="succinic acid"
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("Refreshing alert page")).toBeInTheDocument();
    expect(
      screen.queryByText("No monitored changes detected"),
    ).not.toBeInTheDocument();
  });

  it("retries the exact alert acknowledgement after an unknown outcome", () => {
    mockDismissMutate.mockImplementation((_variables, options) => {
      options.onError(new Error("postgres timeout"));
    });
    mockUseMonitorAlerts.mockReturnValue({
      data: {
        items: [
          {
            id: "alert-1",
            monitor_id: "monitor-1",
            new_patent_ids: ["US123"],
            new_patent_count: 1,
            run_at: "2026-06-01T10:00:00.000Z",
            dismissed: false,
            created_at: "2026-06-01T10:05:00.000Z",
          },
        ],
        total: 1,
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });

    render(
      <AlertsPanel
        monitorId="monitor-1"
        monitorName="succinic acid"
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Acknowledge alert alert-1 for succinic acid",
      }),
    );

    const recovery = screen.getByTestId("monitor-alert-dismiss-recovery");
    expect(recovery).toHaveAttribute(
      "data-mutation-recovery-mode",
      "outcome-unknown",
    );
    expect(recovery).not.toHaveTextContent("postgres timeout");
    expect(
      screen.getByRole("button", {
        name: "Acknowledge alert alert-1 for succinic acid",
      }),
    ).toBeDisabled();

    fireEvent.click(
      screen.getByTestId("monitor-alert-dismiss-recovery-action"),
    );

    expect(mockDismissMutate).toHaveBeenCalledTimes(2);
    expect(mockDismissMutate).toHaveBeenNthCalledWith(
      2,
      { monitorId: "monitor-1", alertId: "alert-1" },
      expect.any(Object),
    );
  });

  it("renders alert metadata with UTC run dates and reviewer-safe action copy", () => {
    mockUseMonitorAlerts.mockReturnValue({
      data: {
        items: [
          {
            id: "alert-2",
            monitor_id: "monitor-1",
            new_patent_ids: ["US123", "EP456", "JP789", "CN000"],
            new_patent_count: 4,
            run_at: "2026-06-01T00:30:00.000Z",
            dismissed: false,
            created_at: "2026-06-01T10:05:00.000Z",
            summary: "Four new family events surfaced.",
            severity: "material",
            alert_type: "family_continuation",
            strategy_mode: "full_refresh",
            jurisdiction_deltas: { US: 2 },
          },
        ],
        total: 1,
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });

    render(
      <AlertsPanel
        monitorId="monitor-1"
        monitorName="succinic acid"
        onClose={vi.fn()}
      />,
    );

    expect(
      screen.getByText("Four new family events surfaced."),
    ).toBeInTheDocument();
    expect(screen.getByText("Material")).toBeInTheDocument();
    expect(screen.getByText("Family Continuation")).toBeInTheDocument();
    expect(screen.getByText("Full refresh")).toBeInTheDocument();
    expect(screen.getByText("Run Jun 1, 2026")).toBeInTheDocument();
    expect(
      screen.getByText(/US123, EP456, JP789 \+1 more/),
    ).toBeInTheDocument();
    expect(screen.getByText("Jurisdiction deltas: US +2")).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Acknowledge alert alert-2 for succinic acid",
      }),
    ).toHaveClass("min-h-11");
  });

  it("leads with stale conclusions and keeps acknowledgement distinct from reassessment", () => {
    mockUseMonitorAlerts.mockReturnValue({
      data: {
        items: [
          {
            id: "alert-conclusion",
            monitor_id: "monitor-1",
            new_patent_ids: ["US999"],
            new_patent_count: 1,
            run_at: "2026-07-26T10:00:00.000Z",
            dismissed: false,
            created_at: "2026-07-26T10:00:01.000Z",
            affected_conclusions: [
              {
                conclusion_id: "clearance:global",
                conclusion_type: "clearance_decision",
                label: "Overall FTO clearance",
                previous_outcome: "clear",
                status: "review_required",
                source_report_id: "report-1",
                dependency_fingerprint: "a".repeat(64),
                invalidated_at: "2026-07-26T10:00:00.000Z",
                latest_observed_at: "2026-07-26T10:00:00.000Z",
                reason_codes: ["new_patent_candidate"],
                trigger_patent_ids: ["US999"],
                trigger_event_ids: [],
                jurisdictions: ["US"],
              },
            ],
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });

    render(
      <AlertsPanel
        monitorId="monitor-1"
        monitorName="succinic acid"
        onClose={vi.fn()}
      />,
    );

    expect(
      screen.getByText("1 report conclusion requires attorney reassessment"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("note", {
        name: "Conclusions requiring attorney reassessment",
      }),
    ).toHaveTextContent("Overall FTO clearance · previously Clear · US");
    expect(
      screen.getByText(
        "Acknowledging this notification does not restore conclusion currency.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Acknowledge alert alert-conclusion for succinic acid",
      }),
    ).toBeInTheDocument();
  });

  it("lets counsel reveal and act on every affected conclusion", () => {
    const alertId = "11111111-1111-4111-8111-111111111111";
    const affectedConclusions = Array.from({ length: 4 }, (_, index) => ({
      conclusion_id: `clearance:${index + 1}`,
      conclusion_type: "jurisdiction_clearance",
      label: `Conclusion ${index + 1}`,
      previous_outcome: "clear",
      status: "review_required" as const,
      source_report_id: "report-1",
      dependency_fingerprint: String(index + 1).repeat(64),
      invalidated_at: "2026-07-26T10:00:00.000Z",
      latest_observed_at: "2026-07-26T10:00:00.000Z",
      reason_codes: ["new_patent_candidate"],
      trigger_patent_ids: [`US99${index}`],
      trigger_event_ids: [],
      jurisdictions: ["US"],
      reassessment_id: `22222222-2222-4222-8222-22222222222${index}`,
      alert_id: alertId,
      evidence_digest: String(index + 5).repeat(64),
      evidence_version: "monitor-evidence-v1",
      evidence_observed_at: "2026-07-26T10:00:00.000Z",
    }));
    mockUseMonitorAlerts.mockReturnValue({
      data: {
        items: [
          {
            id: alertId,
            monitor_id: "monitor-1",
            new_patent_ids: ["US999"],
            new_patent_count: 1,
            run_at: "2026-07-26T10:00:00.000Z",
            dismissed: false,
            created_at: "2026-07-26T10:00:01.000Z",
            affected_conclusions: affectedConclusions,
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });

    render(
      <AlertsPanel
        monitorId="monitor-1"
        monitorName="succinic acid"
        openConclusionIds={affectedConclusions.map(
          (impact) => impact.conclusion_id,
        )}
        canReassessConclusions
        onClose={vi.fn()}
      />,
    );

    expect(screen.queryByText("Conclusion 4")).not.toBeInTheDocument();
    const showAll = screen.getByRole("button", {
      name: "Show 1 more conclusion",
    });
    expect(showAll).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(showAll);

    expect(screen.getByText("Conclusion 4")).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "Record counsel reassessment" }),
    ).toHaveLength(4);
    const showFewer = screen.getByRole("button", {
      name: "Show fewer conclusions",
    });
    expect(showFewer).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(showFewer);
    expect(screen.queryByText("Conclusion 4")).not.toBeInTheDocument();
  });

  it("requires an attorney attestation before recording a conclusion disposition", () => {
    const alertId = "33333333-3333-4333-8333-333333333333";
    const reassessmentId = "44444444-4444-4444-8444-444444444444";
    const dependencyFingerprint = "a".repeat(64);
    const evidenceDigest = "b".repeat(64);
    const evidenceObservedAt = "2026-07-26T10:00:00.000Z";
    mockUseMonitorAlerts.mockReturnValue({
      data: {
        items: [
          {
            id: alertId,
            monitor_id: "monitor-1",
            new_patent_ids: ["US999"],
            new_patent_count: 1,
            run_at: "2026-07-26T10:00:00.000Z",
            dismissed: false,
            created_at: "2026-07-26T10:00:01.000Z",
            affected_conclusions: [
              {
                conclusion_id: "clearance:global",
                conclusion_type: "clearance_decision",
                label: "Overall FTO clearance",
                previous_outcome: "clear",
                status: "review_required",
                source_report_id: "report-1",
                dependency_fingerprint: dependencyFingerprint,
                invalidated_at: "2026-07-26T10:00:00.000Z",
                latest_observed_at: "2026-07-26T10:00:00.000Z",
                reason_codes: ["new_patent_candidate"],
                trigger_patent_ids: ["US999"],
                trigger_event_ids: [],
                jurisdictions: ["US"],
                reassessment_id: reassessmentId,
                alert_id: alertId,
                evidence_digest: evidenceDigest,
                evidence_version: "monitor-evidence-v1",
                evidence_observed_at: evidenceObservedAt,
              },
            ],
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });

    render(
      <AlertsPanel
        monitorId="monitor-1"
        monitorName="succinic acid"
        openConclusionIds={["clearance:global"]}
        canReassessConclusions
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Record counsel reassessment" }),
    );
    const submit = screen.getByRole("button", { name: "Attest and record" });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Reassessment rationale"), {
      target: {
        value:
          "Reviewed the continuation claims and confirmed the prior conclusion remains appropriate.",
      },
    });
    fireEvent.click(
      screen.getByLabelText(
        /I attest that I reviewed the cited monitoring changes/i,
      ),
    );
    expect(submit).toBeEnabled();
    fireEvent.click(submit);

    expect(mockReassessMutate).toHaveBeenCalledWith(
      {
        monitorId: "monitor-1",
        conclusionId: "clearance:global",
        data: {
          reassessment_id: reassessmentId,
          alert_id: alertId,
          dependency_fingerprint: dependencyFingerprint,
          evidence_digest: evidenceDigest,
          evidence_version: "monitor-evidence-v1",
          evidence_observed_at: evidenceObservedAt,
          resolution: "reaffirmed",
          resolution_note:
            "Reviewed the continuation claims and confirmed the prior conclusion remains appropriate.",
          attestation_accepted: true,
        },
      },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("keeps alert pagination copy tied to rendered alert data", async () => {
    mockUseMonitorAlerts.mockImplementation(
      (_monitorId: string, page: number) => ({
        data: {
          items: [
            {
              id: "alert-3",
              monitor_id: "monitor-1",
              new_patent_ids: ["US123"],
              new_patent_count: 1,
              run_at: "2026-06-01T00:30:00.000Z",
              dismissed: false,
              created_at: "2026-06-01T10:05:00.000Z",
            },
          ],
          total: 40,
          page: 1,
          per_page: 20,
        },
        error: null,
        isLoading: false,
        isFetching: page === 2,
        isPlaceholderData: page === 2,
        refetch: vi.fn(),
      }),
    );

    render(
      <AlertsPanel
        monitorId="monitor-1"
        monitorName="succinic acid"
        onClose={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("button", {
        name: "Previous alert page for succinic acid",
      }),
    ).toHaveClass("min-h-11", "min-w-11");
    expect(
      screen.getByRole("button", {
        name: "Next alert page for succinic acid",
      }),
    ).toHaveClass("min-h-11", "min-w-11");

    fireEvent.click(
      screen.getByRole("button", {
        name: "Next alert page for succinic acid",
      }),
    );

    await waitFor(() => {
      expect(mockUseMonitorAlerts).toHaveBeenLastCalledWith("monitor-1", 2, 20);
    });
    expect(
      screen.getByText("Page 1 of 2 · updating page 2"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Next alert page for succinic acid",
      }),
    ).toBeDisabled();
  });

  it("renders unknown strategy modes without coercing them to diff watch", () => {
    mockUseMonitorAlerts.mockReturnValue({
      data: {
        items: [
          {
            id: "alert-4",
            monitor_id: "monitor-1",
            new_patent_ids: [],
            new_patent_count: 1,
            run_at: "2026-06-01T00:30:00.000Z",
            dismissed: false,
            created_at: "2026-06-01T10:05:00.000Z",
            strategy_mode: "experimental_review_sweep",
            jurisdiction_deltas: { ep: -1, jp: "watchlist changed" },
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });

    render(
      <AlertsPanel
        monitorId="monitor-1"
        monitorName="succinic acid"
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("Experimental Review Sweep")).toBeInTheDocument();
    expect(screen.queryByText("Diff watch")).not.toBeInTheDocument();
    expect(
      screen.getByText("Jurisdiction deltas: EP -1 · JP watchlist changed"),
    ).toBeInTheDocument();
  });

  it("renders event-only deltas without claiming zero new patents", () => {
    mockUseMonitorAlerts.mockReturnValue({
      data: {
        items: [
          {
            id: "alert-event-only",
            monitor_id: "monitor-1",
            new_patent_ids: [],
            new_patent_count: 0,
            new_event_ids: [
              "evt-US123-status",
              "evt-EP456-opposition",
              "evt-WO789-family",
              "evt-JP000-term",
            ],
            run_at: "2026-06-01T00:30:00.000Z",
            dismissed: false,
            created_at: "2026-06-01T10:05:00.000Z",
            alert_type: "monitor_event_delta",
            summary: "Material prosecution and legal-status changes surfaced.",
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });

    render(
      <AlertsPanel
        monitorId="monitor-1"
        monitorName="succinic acid"
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("4 monitored events detected")).toBeInTheDocument();
    expect(screen.queryByText(/0 new patents?/i)).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "Event references: evt-US123-status, evt-EP456-opposition, evt-WO789-family +1 more",
      ),
    ).toBeInTheDocument();
  });
});
