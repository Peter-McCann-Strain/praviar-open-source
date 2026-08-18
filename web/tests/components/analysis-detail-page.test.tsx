import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  AnalysisDetailContent,
  getRunningElapsedMs,
} from "@/components/analysis-detail/analysis-detail-content";
import { APIError } from "@/lib/api-client";

const mockUseAuthToken = vi.fn();
const mockUseAnalysis = vi.fn();
const mockUsePipelineStream = vi.fn();
const mockRunningAnalysisWorkspace = vi.fn();
let mockActiveCheckpoint: unknown = null;
let mockPipelineError: string | null = null;

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => mockUseAuthToken(),
}));

vi.mock("@/hooks/use-analysis", () => ({
  useAnalysis: (...args: unknown[]) => mockUseAnalysis(...args),
}));

vi.mock("@/hooks/use-pipeline-stream", () => ({
  usePipelineStream: (...args: unknown[]) => mockUsePipelineStream(...args),
}));

vi.mock("@/components/shared/breadcrumb", () => ({
  Breadcrumb: () => <nav data-testid="breadcrumb" />,
}));

vi.mock("@/components/analysis-detail/analysis-header", () => ({
  AnalysisHeader: ({ analysis }: { analysis: { compound_name: string } }) => (
    <h1>{analysis.compound_name}</h1>
  ),
}));

vi.mock("@/components/analysis-detail/compound-summary-card", () => ({
  CompoundSummaryCard: () => <div data-testid="compound-summary" />,
}));

vi.mock("@/components/analysis-detail/pipeline-progress-card", () => ({
  PipelineProgressCard: () => <div data-testid="pipeline-progress" />,
}));

vi.mock("@/components/analysis-detail/analysis-status-cards", () => ({
  CancelledAnalysisCard: () => <div data-testid="cancelled-analysis" />,
  PipelineErrorCard: () => <div data-testid="pipeline-error" />,
  ReviewPauseCard: () => <div data-testid="review-pause" />,
  FailedAnalysisCard: () => <div data-testid="failed-analysis" />,
  AnalysisCompleteCard: ({
    reviewStatus,
  }: {
    reviewStatus?: { status?: string; reviewer_name?: string | null } | null;
  }) => (
    <div data-testid="analysis-complete">
      {reviewStatus?.status ? <span>{reviewStatus.status}</span> : null}
      {reviewStatus?.reviewer_name ? (
        <span>{reviewStatus.reviewer_name}</span>
      ) : null}
    </div>
  ),
}));

vi.mock("@/components/analysis-detail/checkpoint-overlay", () => ({
  CheckpointOverlay: () => <div data-testid="checkpoint-overlay" />,
}));

vi.mock("@/components/analysis-detail/running-analysis-workspace", () => ({
  RunningAnalysisWorkspace: (props: unknown) => {
    mockRunningAnalysisWorkspace(props);
    return <div data-testid="running-workspace" />;
  },
}));

vi.mock("@/stores/pipeline-store", () => ({
  useActiveCheckpoint: () => mockActiveCheckpoint,
  useCurrentStep: () => 0,
  useIsComplete: () => false,
  useOverallRisk: () => null,
  usePipelineError: () => mockPipelineError,
  usePipelineSteps: () => [],
  useProgressPayloads: () => ({}),
  usePipelineStore: Object.assign(
    (selector: (state: { clearCheckpoint: () => void }) => unknown) =>
      selector({ clearCheckpoint: vi.fn() }),
    { getState: () => ({ reset: vi.fn() }) },
  ),
}));

function renderAnalysisDetail() {
  return render(<AnalysisDetailContent id="ana-route-1" />);
}

const completedAnalysis = {
  id: "ana-route-1",
  compound_input: "succinic acid",
  compound_name: "Succinic acid",
  compound_smiles: "OC(=O)CCC(O)=O",
  status: "completed",
  current_step: 8,
  progress_pct: 100,
  overall_risk: "high",
  blocking_patents_count: 3,
  total_patents_found: 2417,
  executive_summary: "Review required.",
  estimated_cost_usd: 4.82,
  pipeline_duration_seconds: 842,
  flagged_for_review: true,
  created_at: "2026-04-08T14:22:13.100Z",
  updated_at: "2026-04-08T14:36:15.000Z",
};

describe("AnalysisDetailPage states", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockActiveCheckpoint = null;
    mockPipelineError = null;
    mockUseAuthToken.mockReturnValue("test-token");
    mockUseAnalysis.mockReturnValue({
      data: completedAnalysis,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
  });

  it("shows access checking while token-gated analysis query is idle", async () => {
    mockUseAuthToken.mockReturnValue(null);
    mockUseAnalysis.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderAnalysisDetail();

    expect(
      await screen.findByRole("heading", { name: "Checking analysis access" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/not found/i)).not.toBeInTheDocument();
  });

  it.each([403, 404])(
    "shows a neutral unavailable state for status %s",
    async (status) => {
      mockUseAnalysis.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: new APIError(status, "Backend detail should stay hidden"),
        refetch: vi.fn(),
      });

      renderAnalysisDetail();

      expect(
        await screen.findByRole("heading", {
          name: "Analysis unavailable in this workspace",
        }),
      ).toBeInTheDocument();
      expect(
        screen.queryByText("Backend detail should stay hidden"),
      ).not.toBeInTheDocument();
    },
  );

  it("shows retryable temporary state for service failures", async () => {
    const refetch = vi.fn();
    mockUseAnalysis.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new APIError(500, "API error: 500"),
      refetch,
    });

    renderAnalysisDetail();

    expect(
      await screen.findByRole("heading", {
        name: "Analysis temporarily unavailable",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText("API error: 500")).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Retry analysis load" }),
    );

    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("keeps the normal analysis detail shell on successful data", async () => {
    renderAnalysisDetail();

    expect(
      await screen.findByRole("heading", { name: "Succinic acid" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("compound-summary")).toBeInTheDocument();
    expect(screen.getByTestId("pipeline-progress")).toBeInTheDocument();
  });

  it("passes completed legal review metadata to the complete card", async () => {
    mockUseAnalysis.mockReturnValue({
      data: {
        ...completedAnalysis,
        review_status: {
          status: "approved",
          is_persisted: true,
          reviewer_name: "Ada Lovelace",
          updated_at: "2026-04-08T14:36:15.000Z",
        },
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderAnalysisDetail();

    expect(await screen.findByText("approved")).toBeInTheDocument();
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
  });

  it("renders human review pauses without showing the pipeline error card", async () => {
    mockActiveCheckpoint = {
      checkpoint_type: "analysis_review",
      context: {},
      requires_response: true,
      timeout_minutes: 60,
      step: 4,
      step_name: "analysis_review",
      timestamp: "2026-06-06T00:00:00Z",
    };
    mockPipelineError =
      "Human review is required before the pipeline can continue.";
    mockUseAnalysis.mockReturnValue({
      data: { ...completedAnalysis, status: "running", current_step: 4 },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderAnalysisDetail();

    expect(await screen.findByTestId("running-workspace")).toBeInTheDocument();
    expect(screen.getByTestId("review-pause")).toBeInTheDocument();
    expect(screen.queryByTestId("pipeline-error")).not.toBeInTheDocument();
  });

  it("passes pipeline issue state into the running workspace when an error is visible", async () => {
    mockPipelineError = "Stream reconnect failed.";
    mockUseAnalysis.mockReturnValue({
      data: {
        ...completedAnalysis,
        current_step: 4,
        progress_pct: 37.5,
        status: "running",
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderAnalysisDetail();

    expect(await screen.findByTestId("running-workspace")).toBeInTheDocument();
    expect(screen.getByTestId("pipeline-error")).toBeInTheDocument();
    expect(mockRunningAnalysisWorkspace).toHaveBeenLastCalledWith(
      expect.objectContaining({
        hasCheckpoint: false,
        hasPipelineIssue: true,
        progressPct: 37.5,
      }),
    );
  });

  it("renders a seeded in-progress record as a static fixture, not a live worker run", async () => {
    mockUseAnalysis.mockReturnValue({
      data: {
        ...completedAnalysis,
        current_step: 4,
        development_fixture: true,
        pipeline_duration_seconds: null,
        progress_pct: 50,
        status: "running",
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderAnalysisDetail();

    expect(
      await screen.findByText("Static in-progress preview"),
    ).toBeInTheDocument();
    expect(screen.getByText(/no task was dispatched/i)).toBeInTheDocument();
    expect(screen.getByText("Not a worker health signal")).toBeInTheDocument();
    expect(screen.queryByTestId("pipeline-progress")).not.toBeInTheDocument();
    expect(screen.queryByTestId("running-workspace")).not.toBeInTheDocument();
  });
});

describe("getRunningElapsedMs", () => {
  it("uses a believable fixed elapsed window for stale running demo analyses", () => {
    expect(
      getRunningElapsedMs({
        createdAt: "2026-04-10T09:15:00.000Z",
        isDemoMode: true,
        isRunning: true,
        nowMs: new Date("2026-07-01T18:00:00.000Z").getTime(),
      }),
    ).toBe(360_000);
  });

  it("uses real created_at elapsed time outside demo mode", () => {
    expect(
      getRunningElapsedMs({
        createdAt: "2026-07-01T17:54:00.000Z",
        isDemoMode: false,
        isRunning: true,
        nowMs: new Date("2026-07-01T18:00:00.000Z").getTime(),
      }),
    ).toBe(360_000);
  });

  it("returns zero for invalid, missing, or non-running analyses", () => {
    expect(
      getRunningElapsedMs({
        createdAt: "not-a-date",
        isDemoMode: false,
        isRunning: true,
        nowMs: Date.now(),
      }),
    ).toBe(0);
    expect(
      getRunningElapsedMs({
        createdAt: "2026-07-01T18:00:00.000Z",
        isDemoMode: false,
        isRunning: false,
        nowMs: Date.now(),
      }),
    ).toBe(0);
  });
});
