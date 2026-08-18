import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { usePipelineStream } from "@/hooks/use-pipeline-stream";
import {
  PIPELINE_FAILED_MESSAGE,
  PIPELINE_STREAM_ERROR_MESSAGE,
} from "@/hooks/report-interaction-copy";
import { acceptAuthToken, emitAuthBoundaryChanged } from "@/lib/auth-events";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});
const wrapper = ({ children }: { children: React.ReactNode }) =>
  React.createElement(QueryClientProvider, { client: queryClient }, children);

// Mock sse-client
const mockCleanup = vi.fn();
const mockCreatePipelineStream = vi.fn(() => mockCleanup);

vi.mock("@/lib/sse-client", () => ({
  createPipelineStream: (...args: unknown[]) =>
    mockCreatePipelineStream(...args),
}));

// Mock pipeline-store
const mockStore = {
  setStepStatus: vi.fn(),
  setStepProgress: vi.fn(),
  setComplete: vi.fn(),
  setError: vi.fn(),
  setCheckpoint: vi.fn(),
  initSteps: vi.fn(),
};

vi.mock("@/stores/pipeline-store", () => ({
  usePipelineStore: () => mockStore,
}));

describe("usePipelineStream", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    acceptAuthToken("token-123");
  });

  it("does nothing when analysisId is null", () => {
    renderHook(() => usePipelineStream(null, "token-123"), { wrapper });
    expect(mockCreatePipelineStream).not.toHaveBeenCalled();
  });

  it("does nothing when token is null", () => {
    renderHook(() => usePipelineStream("analysis-1", null), { wrapper });
    expect(mockCreatePipelineStream).not.toHaveBeenCalled();
  });

  it("creates stream when both params provided", () => {
    renderHook(() => usePipelineStream("analysis-1", "token-123"), { wrapper });
    expect(mockStore.initSteps).toHaveBeenCalled();
    expect(mockCreatePipelineStream).toHaveBeenCalledWith(
      "analysis-1",
      expect.any(Function),
      expect.any(Function),
      expect.any(Function),
    );
  });

  it("provides the latest accepted token without recreating the stream", () => {
    const { rerender } = renderHook(
      ({ token }) => usePipelineStream("analysis-1", token),
      {
        initialProps: { token: "token-123" },
        wrapper,
      },
    );
    const tokenProvider = mockCreatePipelineStream.mock.calls[0][1] as () =>
      | string
      | null;

    expect(tokenProvider()).toBe("token-123");

    acceptAuthToken("token-456");
    rerender({ token: "token-456" });

    expect(tokenProvider()).toBe("token-456");
    expect(mockCreatePipelineStream).toHaveBeenCalledTimes(1);
  });

  it("cleans up on unmount", () => {
    const { unmount } = renderHook(
      () => usePipelineStream("analysis-1", "token-123"),
      { wrapper },
    );
    unmount();
    expect(mockCleanup).toHaveBeenCalled();
  });

  it("handles 'started' events", () => {
    renderHook(() => usePipelineStream("analysis-1", "token-123"), { wrapper });
    const onEvent = mockCreatePipelineStream.mock.calls[0][2];

    act(() => {
      onEvent({
        type: "started",
        step: 1,
        payload: { description: "Resolving compound" },
      });
    });

    expect(mockStore.setStepStatus).toHaveBeenCalledWith(1, "running", {
      description: "Resolving compound",
    });
  });

  it("marks previous step completed on 'started' for step > 1", () => {
    renderHook(() => usePipelineStream("analysis-1", "token-123"), { wrapper });
    const onEvent = mockCreatePipelineStream.mock.calls[0][2];

    act(() => {
      onEvent({ type: "started", step: 3, payload: { description: "Triage" } });
    });

    expect(mockStore.setStepStatus).toHaveBeenCalledWith(2, "completed");
    expect(mockStore.setStepStatus).toHaveBeenCalledWith(3, "running", {
      description: "Triage",
    });
  });

  it("handles 'progress' events", () => {
    renderHook(() => usePipelineStream("analysis-1", "token-123"), { wrapper });
    const onEvent = mockCreatePipelineStream.mock.calls[0][2];

    act(() => {
      onEvent({ type: "progress", step: 2, payload: { patents_found: 42 } });
    });

    expect(mockStore.setStepProgress).toHaveBeenCalledWith(2, {
      patents_found: 42,
    });
  });

  it("handles 'completed' events with overall_risk", () => {
    renderHook(() => usePipelineStream("analysis-1", "token-123"), { wrapper });
    const onEvent = mockCreatePipelineStream.mock.calls[0][2];

    act(() => {
      onEvent({
        type: "completed",
        step: 8,
        payload: { overall_risk: "medium" },
      });
    });

    expect(mockStore.setStepStatus).toHaveBeenCalledWith(8, "completed");
    expect(mockStore.setComplete).toHaveBeenCalledWith("medium");
  });

  it("handles 'failed' events with safe user-facing copy", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    renderHook(() => usePipelineStream("analysis-1", "token-123"), { wrapper });
    const onEvent = mockCreatePipelineStream.mock.calls[0][2];

    act(() => {
      onEvent({
        type: "failed",
        step: 4,
        payload: { error: "UNPUBLISHED_ASSET_PRV_142 pipeline timeout" },
      });
    });

    expect(mockStore.setStepStatus).toHaveBeenCalledWith(4, "failed");
    expect(mockStore.setError).toHaveBeenCalledWith(PIPELINE_FAILED_MESSAGE);
    expect(mockStore.setError).not.toHaveBeenCalledWith(
      expect.stringContaining("UNPUBLISHED_ASSET_PRV_142"),
    );
    expect(JSON.stringify(consoleSpy.mock.calls)).not.toContain(
      "UNPUBLISHED_ASSET_PRV_142",
    );
  });

  it("handles 'review_required' events as blocking checkpoints", () => {
    renderHook(() => usePipelineStream("analysis-1", "token-123"), { wrapper });
    const onEvent = mockCreatePipelineStream.mock.calls[0][2];

    act(() => {
      onEvent({
        type: "review_required",
        step: 4,
        step_name: "analysis_review",
        payload: {
          checkpoint_id: "analysis-1:analysis_review",
          checkpoint_type: "analysis_review",
          requires_response: true,
          timeout_minutes: 60,
          elapsed_seconds: 3600,
        },
        timestamp: "2026-06-06T00:00:00Z",
      });
    });

    expect(mockStore.setCheckpoint).toHaveBeenCalledWith(
      expect.objectContaining({
        checkpoint_id: "analysis-1:analysis_review",
        checkpoint_type: "analysis_review",
        requires_response: true,
      }),
    );
    expect(mockStore.setError).not.toHaveBeenCalled();
  });

  it("handles error callback from stream with safe user-facing copy", () => {
    renderHook(() => usePipelineStream("analysis-1", "token-123"), { wrapper });
    const onError = mockCreatePipelineStream.mock.calls[0][3];

    act(() => {
      onError(new Error("postgres://secret connection lost"));
    });

    expect(mockStore.setError).toHaveBeenCalledWith(
      PIPELINE_STREAM_ERROR_MESSAGE,
    );
    expect(mockStore.setError).not.toHaveBeenCalledWith(
      expect.stringContaining("postgres://secret"),
    );
  });

  it("drops late stream events after an auth boundary change", () => {
    renderHook(() => usePipelineStream("analysis-1", "token-123"), { wrapper });
    const onEvent = mockCreatePipelineStream.mock.calls[0][2];

    act(() => {
      emitAuthBoundaryChanged({ refreshToken: false });
    });

    act(() => {
      onEvent({
        type: "started",
        step: 1,
        payload: { description: "Stale private stream event" },
      });
    });

    expect(mockStore.setStepStatus).not.toHaveBeenCalled();
  });
});
