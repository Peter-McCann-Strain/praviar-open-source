import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StrictMode, type RefObject } from "react";
import { APIError } from "@/lib/api-client";

const mockUseMonitors = vi.fn();
const mockUseUpdateMonitor = vi.fn();
const mockUseDeleteMonitor = vi.fn();
const mockUseAuthToken = vi.fn();
const mockUsePrincipalCapabilities = vi.fn();

vi.mock("@/hooks/use-monitors", () => ({
  useMonitors: (...args: unknown[]) => mockUseMonitors(...args),
  useUpdateMonitor: () => mockUseUpdateMonitor(),
  useDeleteMonitor: () => mockUseDeleteMonitor(),
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => mockUseAuthToken(),
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  usePrincipalCapabilities: (...args: unknown[]) =>
    mockUsePrincipalCapabilities(...args),
}));

vi.mock("@/components/monitors/page-header", () => ({
  MonitorsPageHeader: ({
    actionsDisabled,
    createButtonRef,
    onCreateClick,
  }: {
    actionsDisabled?: boolean;
    createButtonRef?: RefObject<HTMLButtonElement | null>;
    onCreateClick: () => void;
  }) => (
    <button
      ref={createButtonRef}
      type="button"
      disabled={actionsDisabled}
      onClick={onCreateClick}
    >
      New Monitor
    </button>
  ),
}));

vi.mock("@/components/monitors/create-monitor-form", () => ({
  CreateMonitorForm: ({ onClose }: { onClose: () => void }) => (
    <div data-testid="create-monitor-form">
      <button type="button" onClick={onClose}>
        Close create monitor form
      </button>
    </div>
  ),
}));

vi.mock("@/components/monitors/monitors-table", () => ({
  MonitorsTable: ({
    monitors,
    pendingMonitorId,
    actionsDisabled,
    isUpdating,
    onDelete,
    onAlertButtonFocus,
    onToggleActive,
    onViewAlerts,
  }: {
    monitors: Array<{ id: string; is_active: boolean; compound_name?: string }>;
    pendingMonitorId?: string | null;
    actionsDisabled?: boolean;
    isUpdating?: boolean;
    onDelete: (monitorId: string) => void;
    onAlertButtonFocus?: (element: HTMLButtonElement) => void;
    onToggleActive: (monitor: { id: string; is_active: boolean }) => void;
    onViewAlerts: (monitor: {
      id: string;
      is_active: boolean;
      compound_name?: string;
    }) => void;
  }) => {
    const mutatingActionsLocked =
      Boolean(actionsDisabled) ||
      Boolean(pendingMonitorId) ||
      Boolean(isUpdating);

    return (
      <div data-testid="monitors-table">
        {monitors.map((monitor) => (
          <div key={monitor.id}>
            <button
              type="button"
              onClick={(event) => {
                onAlertButtonFocus?.(event.currentTarget);
                onViewAlerts(monitor);
              }}
            >
              Alerts {monitor.id}
            </button>
            <button
              type="button"
              disabled={mutatingActionsLocked}
              onClick={() => onToggleActive(monitor)}
            >
              Toggle {monitor.id}
            </button>
            <button
              type="button"
              disabled={mutatingActionsLocked}
              onClick={() => onDelete(monitor.id)}
            >
              Delete {monitor.id}
            </button>
          </div>
        ))}
      </div>
    );
  },
}));

vi.mock("@/components/monitors/summary-cards", () => ({
  MonitorSummaryCards: () => <div data-testid="monitor-summary-cards" />,
}));

vi.mock("@/components/monitors/alerts-panel", () => ({
  AlertsPanel: ({
    monitorName,
    onClose,
  }: {
    monitorName: string;
    onClose: () => void;
  }) => (
    <div data-testid="alerts-panel">
      Alerts for {monitorName}
      <button type="button" onClick={onClose}>
        Close alerts panel
      </button>
    </div>
  ),
}));

import MonitorsPage from "@/app/(dashboard)/monitors/page";

describe("MonitorsPage", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuthToken.mockReturnValue("test-token");
    mockUsePrincipalCapabilities.mockReturnValue({
      data: { role: "attorney" },
    });
    mockUseUpdateMonitor.mockReturnValue({ mutate: vi.fn() });
    mockUseDeleteMonitor.mockReturnValue({ mutate: vi.fn() });
    mockUseMonitors.mockReturnValue({
      data: { items: [], total: 0 },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
  });

  it("renders the monitor table when monitor data is available", () => {
    render(<MonitorsPage />);

    expect(screen.getByTestId("monitors-table")).toBeInTheDocument();
  });

  it("renders a recovery state and retries when monitors fail to load", () => {
    const refetch = vi.fn();
    const consoleErrorSpy = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mockUseMonitors.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Failed to fetch"),
      refetch,
    });

    render(
      <StrictMode>
        <MonitorsPage />
      </StrictMode>,
    );

    expect(
      screen.getByText("Patent monitoring temporarily unavailable"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Detail:|Failed to fetch/i),
    ).not.toBeInTheDocument();
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      "[MonitorsPage] Failed to load monitor workspace",
    );
    expect(consoleErrorSpy).toHaveBeenCalledTimes(1);
    expect(consoleErrorSpy).not.toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ message: expect.stringMatching(/Failed/) }),
    );
    expect(screen.getByRole("button", { name: "New Monitor" })).toBeDisabled();

    fireEvent.click(
      screen.getByRole("button", { name: "Retry workspace load" }),
    );

    expect(refetch).toHaveBeenCalledTimes(1);
    consoleErrorSpy.mockRestore();
  });

  it("shows access preparation when monitor queries are disabled", () => {
    mockUseMonitors.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<MonitorsPage />);

    expect(
      screen.getByText("Checking patent monitoring workspace access"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New Monitor" })).toBeDisabled();
  });

  it("fails closed when the auth token disappears with cached monitor data present", () => {
    mockUseAuthToken.mockReturnValue(null);
    mockUseMonitors.mockReturnValue({
      data: {
        items: [
          {
            id: "monitor-1",
            is_active: true,
            compound_name: "Private compound",
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<MonitorsPage />);

    expect(
      screen.getByText("Checking patent monitoring workspace access"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("monitors-table")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New Monitor" })).toBeDisabled();
  });

  it("preserves stale monitor data when a background refetch errors", () => {
    mockUseMonitors.mockReturnValue({
      data: {
        items: [
          {
            id: "monitor-1",
            is_active: true,
          },
        ],
        total: 1,
      },
      isLoading: false,
      error: new Error("background fetch failed"),
      refetch: vi.fn(),
    });

    render(<MonitorsPage />);

    expect(screen.getByTestId("monitors-table")).toBeInTheDocument();
    expect(
      screen.queryByText("Patent monitoring temporarily unavailable"),
    ).not.toBeInTheDocument();
  });

  it("hides cached monitor data when monitor access is revoked", () => {
    const refetch = vi.fn();
    mockUseMonitors.mockReturnValue({
      data: {
        items: [
          {
            id: "monitor-1",
            is_active: true,
            compound_name: "Private compound",
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
      },
      isLoading: false,
      error: new APIError(403, "Forbidden"),
      refetch,
    });

    render(<MonitorsPage />);

    expect(
      screen.getByText("Patent monitoring workspace access restricted"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("monitor-summary-cards"),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("monitors-table")).not.toBeInTheDocument();
    expect(screen.queryByTestId("alerts-panel")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New Monitor" })).toBeDisabled();

    fireEvent.click(
      screen.getByRole("button", { name: "Retry workspace load" }),
    );
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("clamps out-of-range monitor pages after totals shrink", async () => {
    vi.useFakeTimers();
    mockUseMonitors.mockReturnValue({
      data: {
        items: [
          {
            id: "monitor-1",
            is_active: true,
          },
        ],
        total: 40,
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    const view = render(<MonitorsPage />);

    fireEvent.click(screen.getByRole("button", { name: "Next monitors page" }));
    expect(mockUseMonitors).toHaveBeenLastCalledWith(2, undefined, 20);

    mockUseMonitors.mockReturnValue({
      data: {
        items: [],
        total: 1,
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    view.rerender(<MonitorsPage />);

    act(() => {
      vi.runOnlyPendingTimers();
    });

    expect(mockUseMonitors).toHaveBeenLastCalledWith(1, undefined, 20);
  });

  it("keeps pagination copy tied to the rendered monitor page", async () => {
    mockUseMonitors.mockImplementation((requestedPage: number) => ({
      data: {
        items: [
          {
            id: "monitor-1",
            is_active: true,
          },
        ],
        total: 40,
        page: 1,
        per_page: 20,
      },
      isLoading: false,
      isFetching: requestedPage === 2,
      isPlaceholderData: requestedPage === 2,
      error: null,
      refetch: vi.fn(),
    }));

    render(<MonitorsPage />);

    fireEvent.click(screen.getByRole("button", { name: "Next monitors page" }));

    await waitFor(() => {
      expect(mockUseMonitors).toHaveBeenLastCalledWith(2, undefined, 20);
    });
    expect(screen.getByText("Showing 1-1 of 40 monitors")).toBeInTheDocument();
    expect(screen.getByText("Updating page 2")).toBeInTheDocument();
    expect(
      screen.queryByText("Showing 21-21 of 40 monitors"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Next monitors page" }),
    ).toBeDisabled();
  });

  it("renders an out-of-range monitor page as a refresh state", async () => {
    mockUseMonitors.mockImplementation((requestedPage: number) => ({
      data:
        requestedPage === 2
          ? {
              items: [],
              total: 25,
              page: 2,
              per_page: 20,
            }
          : {
              items: [
                {
                  id: "monitor-1",
                  is_active: true,
                },
              ],
              total: 40,
              page: 1,
              per_page: 20,
            },
      isLoading: false,
      isFetching: false,
      isPlaceholderData: false,
      error: null,
      refetch: vi.fn(),
    }));

    render(<MonitorsPage />);

    fireEvent.click(screen.getByRole("button", { name: "Next monitors page" }));

    await waitFor(() => {
      expect(mockUseMonitors).toHaveBeenLastCalledWith(2, undefined, 20);
    });
    expect(screen.getAllByText("Showing 0 of 25 monitors")).toHaveLength(2);
    expect(
      screen.queryByText("Showing 21-20 of 25 monitors"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Next monitors page" }),
    ).toBeDisabled();
  });

  it("hides previous-filter rows while the selected monitor filter refreshes", () => {
    mockUseMonitors.mockImplementation((_page: number, isActive?: boolean) => ({
      data: {
        items: [
          {
            id: "monitor-1",
            is_active: true,
            compound_name: "Active placeholder row",
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
        is_active: undefined,
      },
      isLoading: false,
      isFetching: isActive === false,
      isPlaceholderData: isActive === false,
      error: null,
      refetch: vi.fn(),
    }));

    render(<MonitorsPage />);

    expect(screen.getByTestId("monitor-summary-cards")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Paused" }));

    expect(
      screen.getByText(
        "Refreshing the selected watch posture before showing matching monitors.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("monitor-summary-cards"),
    ).not.toBeInTheDocument();
  });

  it("passes active-state filters to the monitor query", () => {
    mockUseMonitors.mockReturnValue({
      data: {
        items: [
          {
            id: "monitor-1",
            is_active: true,
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
      },
      isLoading: false,
      isFetching: false,
      isPlaceholderData: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<MonitorsPage />);

    const pausedFilter = screen.getByRole("button", { name: "Paused" });
    expect(pausedFilter).toHaveClass("min-h-11");
    fireEvent.click(pausedFilter);

    expect(mockUseMonitors).toHaveBeenLastCalledWith(1, false, 20);
    expect(screen.getByRole("button", { name: "Paused" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    fireEvent.click(screen.getByRole("button", { name: "Active" }));
    expect(mockUseMonitors).toHaveBeenLastCalledWith(1, true, 20);
  });

  it("locks monitor filters and sibling mutating actions during a pending watch update", async () => {
    const updateMutate = vi.fn();
    mockUseUpdateMonitor.mockReturnValue({ mutate: updateMutate });
    mockUseMonitors.mockReturnValue({
      data: {
        items: [
          {
            id: "monitor-1",
            is_active: true,
          },
          {
            id: "monitor-2",
            is_active: false,
          },
        ],
        total: 2,
        page: 1,
        per_page: 20,
      },
      isLoading: false,
      isFetching: false,
      isPlaceholderData: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<MonitorsPage />);

    fireEvent.click(screen.getByRole("button", { name: "Toggle monitor-1" }));

    expect(updateMutate).toHaveBeenCalledWith(
      {
        monitorId: "monitor-1",
        data: { is_active: false },
      },
      expect.objectContaining({
        onError: expect.any(Function),
        onSettled: expect.any(Function),
      }),
    );
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Paused" })).toBeDisabled();
    });
    expect(
      screen.getByText("Applying a watch update before changing filters."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Delete monitor-2" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Alerts monitor-2" }),
    ).not.toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Paused" }));
    expect(mockUseMonitors).toHaveBeenLastCalledWith(1, undefined, 20);
  });

  it("closes the alert rail when the selected monitor disappears", () => {
    vi.useFakeTimers();
    mockUseMonitors.mockReturnValue({
      data: {
        items: [
          {
            id: "monitor-1",
            is_active: true,
            compound_name: "Succinic acid",
          },
        ],
        total: 1,
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    const view = render(<MonitorsPage />);

    fireEvent.click(screen.getByRole("button", { name: "Alerts monitor-1" }));
    expect(screen.getByTestId("alerts-panel")).toHaveTextContent(
      "Alerts for Succinic acid",
    );

    mockUseMonitors.mockReturnValue({
      data: {
        items: [],
        total: 0,
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    view.rerender(<MonitorsPage />);

    act(() => {
      vi.runOnlyPendingTimers();
    });

    view.rerender(<MonitorsPage />);
    expect(screen.queryByTestId("alerts-panel")).not.toBeInTheDocument();
  });

  it("returns focus after closing create and alert panels", () => {
    vi.useFakeTimers();
    mockUseMonitors.mockReturnValue({
      data: {
        items: [
          {
            id: "monitor-1",
            is_active: true,
            compound_name: "Succinic acid",
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
      },
      isLoading: false,
      isFetching: false,
      isPlaceholderData: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<MonitorsPage />);

    const newMonitorButton = screen.getByRole("button", {
      name: "New Monitor",
    });
    newMonitorButton.focus();
    fireEvent.click(newMonitorButton);
    fireEvent.click(
      screen.getByRole("button", { name: "Close create monitor form" }),
    );

    act(() => {
      vi.runOnlyPendingTimers();
    });
    expect(newMonitorButton).toHaveFocus();

    const alertsButton = screen.getByRole("button", {
      name: "Alerts monitor-1",
    });
    alertsButton.focus();
    fireEvent.click(alertsButton);
    fireEvent.click(screen.getByRole("button", { name: "Close alerts panel" }));

    act(() => {
      vi.runOnlyPendingTimers();
    });
    expect(alertsButton).toHaveFocus();
  });

  it("reapplies the exact monitor posture after an unknown update outcome", () => {
    const updateMutate = vi.fn((_variables, options) => {
      options.onError(new Error("database timeout"));
      options.onSettled();
    });
    mockUseUpdateMonitor.mockReturnValue({ mutate: updateMutate });
    mockUseMonitors.mockReturnValue({
      data: {
        items: [
          {
            id: "monitor-1",
            is_active: true,
          },
        ],
        total: 1,
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<MonitorsPage />);

    fireEvent.click(screen.getByRole("button", { name: "Toggle monitor-1" }));

    const recovery = screen.getByTestId("monitor-update-recovery");
    expect(recovery).toHaveAttribute(
      "data-mutation-recovery-mode",
      "outcome-unknown",
    );
    expect(recovery).not.toHaveTextContent("database timeout");
    expect(
      screen.getByRole("button", { name: "Delete monitor-1" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "New Monitor" })).toBeDisabled();

    fireEvent.click(screen.getByTestId("monitor-update-recovery-action"));

    expect(updateMutate).toHaveBeenCalledTimes(2);
    expect(updateMutate).toHaveBeenNthCalledWith(
      2,
      {
        monitorId: "monitor-1",
        data: { is_active: false },
      },
      expect.any(Object),
    );
  });

  it("preserves the exact resume posture in recovery", () => {
    const updateMutate = vi.fn((_variables, options) => {
      options.onError(new Error("network timeout"));
      options.onSettled();
    });
    mockUseUpdateMonitor.mockReturnValue({ mutate: updateMutate });
    mockUseMonitors.mockReturnValue({
      data: {
        items: [{ id: "monitor-paused", is_active: false }],
        total: 1,
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<MonitorsPage />);

    fireEvent.click(
      screen.getByRole("button", { name: "Toggle monitor-paused" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Reapply resume" }));

    expect(updateMutate).toHaveBeenNthCalledWith(
      2,
      {
        monitorId: "monitor-paused",
        data: { is_active: true },
      },
      expect.any(Object),
    );
  });

  it("refreshes authoritative monitor state after an unknown delete outcome", async () => {
    const refetch = vi.fn().mockResolvedValue({ error: null });
    const deleteMutate = vi.fn((_monitorId, options) => {
      options.onError(new Error("network connection lost"));
      options.onSettled();
    });
    mockUseDeleteMonitor.mockReturnValue({ mutate: deleteMutate });
    mockUseMonitors.mockReturnValue({
      data: {
        items: [{ id: "monitor-1", is_active: true }],
        total: 1,
      },
      isLoading: false,
      error: null,
      refetch,
    });

    render(<MonitorsPage />);

    fireEvent.click(screen.getByRole("button", { name: "Delete monitor-1" }));

    expect(screen.getByTestId("monitor-delete-recovery")).toHaveAttribute(
      "data-mutation-recovery-mode",
      "outcome-unknown",
    );
    fireEvent.click(screen.getByTestId("monitor-delete-recovery-action"));

    await waitFor(() => expect(refetch).toHaveBeenCalledOnce());
    expect(deleteMutate).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(
        screen.queryByTestId("monitor-delete-recovery"),
      ).not.toBeInTheDocument(),
    );
  });
});
