import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { APIError } from "@/lib/api-client";
import type { FTOReport } from "@praviar/shared-types";

const mocks = vi.hoisted(() => ({
  logError: vi.fn(),
  refetchMonitor: vi.fn(),
  existingMonitor: undefined as
    | {
        id: string;
        is_active?: boolean;
        schedule: string;
        source_analysis_id: string;
      }
    | undefined,
  createMonitor: { mutate: vi.fn(), isPending: false },
  updateMonitor: { mutate: vi.fn(), isPending: false },
  deleteMonitor: { mutate: vi.fn(), isPending: false },
}));

vi.mock("@/hooks/use-monitors", () => ({
  useMonitorForAnalysisState: () => ({
    monitor: mocks.existingMonitor,
    refetch: mocks.refetchMonitor,
  }),
  useCreateMonitor: () => mocks.createMonitor,
  useUpdateMonitor: () => mocks.updateMonitor,
  useDeleteMonitor: () => mocks.deleteMonitor,
}));

vi.mock("@/lib/error-logger", () => ({
  logError: (...args: unknown[]) => mocks.logError(...args),
}));

import {
  ReportWatchControlProvider,
  useReportWatchControl,
  useSharedReportWatchControl,
} from "@/components/report-page/use-report-watch-control";

const report = {
  compound: {
    canonical_smiles: "CC(=O)OC1=CC=CC=C1C(=O)O",
    name: "Aspirin",
  },
} as FTOReport;

describe("useReportWatchControl", () => {
  beforeEach(() => {
    mocks.logError.mockReset();
    mocks.refetchMonitor.mockReset();
    mocks.refetchMonitor.mockResolvedValue({ error: null });
    mocks.createMonitor.mutate.mockReset();
    mocks.updateMonitor.mutate.mockReset();
    mocks.deleteMonitor.mutate.mockReset();
    mocks.existingMonitor = undefined;
  });

  it("pauses a newly created monitor before monitor refetch catches up", () => {
    mocks.createMonitor.mutate.mockImplementation((input, options) => {
      options?.onSuccess?.({
        id: "monitor-created",
        is_active: true,
        schedule: input.schedule,
      });
    });

    const { result } = renderHook(() =>
      useReportWatchControl({ analysisId: "analysis-1", report }),
    );

    act(() => {
      result.current.handleWatchToggle(true, "weekly");
    });

    expect(result.current.watchEnabled).toBe(true);

    act(() => {
      result.current.handleWatchToggle(false, "weekly");
    });

    expect(mocks.deleteMonitor.mutate).not.toHaveBeenCalled();
    expect(mocks.updateMonitor.mutate).toHaveBeenCalledWith(
      {
        monitorId: "monitor-created",
        data: { schedule: "weekly", is_active: false },
      },
      expect.any(Object),
    );
  });

  it("updates an existing monitor when frequency changes", () => {
    mocks.existingMonitor = {
      id: "monitor-1",
      is_active: true,
      schedule: "weekly",
      source_analysis_id: "analysis-1",
    };
    mocks.updateMonitor.mutate.mockImplementation((_input, options) => {
      options?.onSuccess?.({
        id: "monitor-1",
        is_active: true,
        schedule: "daily",
      });
    });

    const { result } = renderHook(() =>
      useReportWatchControl({ analysisId: "analysis-1", report }),
    );

    act(() => {
      result.current.handleWatchToggle(true, "daily");
    });

    expect(mocks.updateMonitor.mutate).toHaveBeenCalledWith(
      {
        monitorId: "monitor-1",
        data: { schedule: "daily", is_active: true },
      },
      expect.any(Object),
    );
    expect(result.current.watchSchedule).toBe("daily");
  });

  it("normalizes unsupported monitor cadences before saving", () => {
    mocks.existingMonitor = {
      id: "monitor-1",
      is_active: true,
      schedule: "biweekly",
      source_analysis_id: "analysis-1",
    };
    mocks.updateMonitor.mutate.mockImplementation((input, options) => {
      options?.onSuccess?.({
        id: "monitor-1",
        is_active: true,
        schedule: input.data.schedule,
      });
    });

    const { result } = renderHook(() =>
      useReportWatchControl({ analysisId: "analysis-1", report }),
    );

    expect(result.current.watchSchedule).toBe("weekly");

    act(() => {
      result.current.handleWatchToggle(true, "biweekly");
    });

    expect(mocks.updateMonitor.mutate).toHaveBeenCalledWith(
      {
        monitorId: "monitor-1",
        data: { schedule: "weekly", is_active: true },
      },
      expect.any(Object),
    );
    expect(result.current.watchSchedule).toBe("weekly");
  });

  it("re-enables a paused existing monitor after disabling watch", () => {
    mocks.existingMonitor = {
      id: "monitor-stale",
      is_active: true,
      schedule: "weekly",
      source_analysis_id: "analysis-1",
    };
    mocks.updateMonitor.mutate.mockImplementation((input, options) => {
      options?.onSuccess?.({
        id: input.monitorId,
        is_active: input.data.is_active,
        schedule: input.data.schedule,
      });
    });

    const { result } = renderHook(() =>
      useReportWatchControl({ analysisId: "analysis-1", report }),
    );

    act(() => {
      result.current.handleWatchToggle(false, "weekly");
    });

    expect(result.current.watchEnabled).toBe(false);

    act(() => {
      result.current.handleWatchToggle(true, "daily");
    });

    expect(mocks.deleteMonitor.mutate).not.toHaveBeenCalled();
    expect(mocks.createMonitor.mutate).not.toHaveBeenCalled();
    expect(mocks.updateMonitor.mutate).toHaveBeenLastCalledWith(
      {
        monitorId: "monitor-stale",
        data: { schedule: "daily", is_active: true },
      },
      expect.any(Object),
    );

    act(() => {
      result.current.handleWatchToggle(true, "monthly");
    });

    expect(mocks.updateMonitor.mutate).toHaveBeenLastCalledWith(
      {
        monitorId: "monitor-stale",
        data: { schedule: "monthly", is_active: true },
      },
      expect.any(Object),
    );
  });

  it("treats inactive existing monitors as paused and re-enables them with PATCH", () => {
    mocks.existingMonitor = {
      id: "monitor-paused",
      is_active: false,
      schedule: "monthly",
      source_analysis_id: "analysis-1",
    };
    mocks.updateMonitor.mutate.mockImplementation((_input, options) => {
      options?.onSuccess?.({
        id: "monitor-paused",
        is_active: true,
        schedule: "weekly",
      });
    });

    const { result } = renderHook(() =>
      useReportWatchControl({ analysisId: "analysis-1", report }),
    );

    expect(result.current.watchEnabled).toBe(false);
    expect(result.current.watchSchedule).toBe("monthly");

    act(() => {
      result.current.handleWatchToggle(true, "weekly");
    });

    expect(mocks.createMonitor.mutate).not.toHaveBeenCalled();
    expect(mocks.updateMonitor.mutate).toHaveBeenCalledWith(
      {
        monitorId: "monitor-paused",
        data: { schedule: "weekly", is_active: true },
      },
      expect.any(Object),
    );
    expect(result.current.watchEnabled).toBe(true);
    expect(result.current.watchSchedule).toBe("weekly");
  });

  it("refreshes monitor state after an unknown start outcome without creating a second watch", async () => {
    mocks.createMonitor.mutate.mockImplementation((_input, options) => {
      options?.onError?.(
        new Error("postgres://secret-token monitor backend exploded"),
      );
    });

    const { result } = renderHook(() =>
      useReportWatchControl({ analysisId: "analysis-1", report }),
    );

    act(() => {
      result.current.handleWatchToggle(true, "weekly");
    });

    expect(result.current.watchRecovery).toEqual({
      mode: "outcome-unknown",
      variables: {
        kind: "start",
        variables: {
          analysis_id: "analysis-1",
          compound_name: "Aspirin",
          compound_smiles: "CC(=O)OC1=CC=CC=C1C(=O)O",
          schedule: "weekly",
        },
      },
    });
    expect(result.current.watchControlsLocked).toBe(true);

    await act(async () => {
      await result.current.handleWatchRecoveryAction();
    });

    expect(mocks.refetchMonitor).toHaveBeenCalledTimes(1);
    expect(mocks.createMonitor.mutate).toHaveBeenCalledTimes(1);
    expect(result.current.watchRecovery).toBeNull();
  });

  it("returns a definitive start failure to the plan without retrying or refreshing", async () => {
    mocks.createMonitor.mutate.mockImplementation((_input, options) => {
      options?.onError?.(
        new APIError(422, "postgres://secret-token invalid monitor"),
      );
    });

    const { result } = renderHook(() =>
      useReportWatchControl({ analysisId: "analysis-1", report }),
    );

    act(() => {
      result.current.handleWatchToggle(true, "weekly");
    });
    expect(result.current.watchRecovery?.mode).toBe("failed");

    await act(async () => {
      await result.current.handleWatchRecoveryAction();
    });

    expect(mocks.createMonitor.mutate).toHaveBeenCalledTimes(1);
    expect(mocks.refetchMonitor).not.toHaveBeenCalled();
    expect(result.current.watchRecovery).toBeNull();
  });

  it("replays the exact frequency update after an unknown outcome", () => {
    mocks.existingMonitor = {
      id: "monitor-1",
      is_active: true,
      schedule: "weekly",
      source_analysis_id: "analysis-1",
    };
    mocks.updateMonitor.mutate
      .mockImplementationOnce((_input, options) => {
        options?.onError?.(
          new Error("postgres://secret-token update backend exploded"),
        );
      })
      .mockImplementationOnce((input, options) => {
        options?.onSuccess?.({
          id: input.monitorId,
          is_active: input.data.is_active,
          schedule: input.data.schedule,
        });
      });

    const { result } = renderHook(() =>
      useReportWatchControl({ analysisId: "analysis-1", report }),
    );

    act(() => {
      result.current.handleWatchToggle(true, "daily");
    });

    expect(result.current.watchRecovery?.mode).toBe("outcome-unknown");

    act(() => {
      void result.current.handleWatchRecoveryAction();
    });

    expect(mocks.updateMonitor.mutate).toHaveBeenCalledTimes(2);
    expect(mocks.updateMonitor.mutate).toHaveBeenNthCalledWith(
      1,
      {
        monitorId: "monitor-1",
        data: { schedule: "daily", is_active: true },
      },
      expect.any(Object),
    );
    expect(mocks.updateMonitor.mutate).toHaveBeenNthCalledWith(
      2,
      {
        monitorId: "monitor-1",
        data: { schedule: "daily", is_active: true },
      },
      expect.any(Object),
    );
    expect(result.current.watchRecovery).toBeNull();
  });

  it("replays the exact stopped state after an unknown outcome", () => {
    mocks.existingMonitor = {
      id: "monitor-1",
      is_active: true,
      schedule: "monthly",
      source_analysis_id: "analysis-1",
    };
    mocks.updateMonitor.mutate
      .mockImplementationOnce((_input, options) => {
        options?.onError?.(new Error("stop outcome unknown"));
      })
      .mockImplementationOnce((input, options) => {
        options?.onSuccess?.({
          id: input.monitorId,
          is_active: input.data.is_active,
          schedule: input.data.schedule,
        });
      });

    const { result } = renderHook(() =>
      useReportWatchControl({ analysisId: "analysis-1", report }),
    );

    act(() => {
      result.current.handleWatchToggle(false, "monthly");
    });
    act(() => {
      void result.current.handleWatchRecoveryAction();
    });

    expect(mocks.updateMonitor.mutate).toHaveBeenCalledTimes(2);
    expect(mocks.updateMonitor.mutate).toHaveBeenNthCalledWith(
      2,
      {
        monitorId: "monitor-1",
        data: { schedule: "monthly", is_active: false },
      },
      expect.any(Object),
    );
    expect(result.current.watchEnabled).toBe(false);
  });

  it("shares one unknown-start lock across every report watch consumer", () => {
    mocks.createMonitor.mutate.mockImplementation((_input, options) => {
      options?.onError?.(new Error("start outcome unknown"));
    });

    function Consumer({ label }: { label: string }) {
      const control = useSharedReportWatchControl();
      return (
        <div>
          <span data-testid={`${label}-lock`}>
            {control.watchControlsLocked ? "locked" : "ready"}
          </span>
          <button
            type="button"
            onClick={() => control.handleWatchToggle(true, "weekly")}
          >
            Start {label}
          </button>
        </div>
      );
    }

    render(
      <ReportWatchControlProvider analysisId="analysis-1" report={report}>
        <Consumer label="desktop" />
        <Consumer label="mobile" />
        <Consumer label="dialog" />
      </ReportWatchControlProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Start desktop" }));

    expect(screen.getByTestId("desktop-lock")).toHaveTextContent("locked");
    expect(screen.getByTestId("mobile-lock")).toHaveTextContent("locked");
    expect(screen.getByTestId("dialog-lock")).toHaveTextContent("locked");
    expect(mocks.createMonitor.mutate).toHaveBeenCalledTimes(1);
  });
});
