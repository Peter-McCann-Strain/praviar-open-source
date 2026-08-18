import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StrictMode } from "react";
import type { NotificationPreferences } from "@/hooks/use-notifications";
import { APIError } from "@/lib/api-client";
import { emitAuthBoundaryChanged } from "@/lib/auth-events";
import NotificationSettingsPage from "@/components/settings/notifications/notification-settings-page";

const mockUseAuthToken = vi.fn();
const mockUseNotificationPreferences = vi.fn();
const mockUpdateMutate = vi.fn();
const mockAddToast = vi.fn();

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => mockUseAuthToken(),
}));

vi.mock("@/hooks/use-notifications", () => ({
  useNotificationPreferences: (...args: unknown[]) =>
    mockUseNotificationPreferences(...args),
  useUpdateNotificationPreferences: () => ({
    mutate: mockUpdateMutate,
    isPending: false,
  }),
}));

vi.mock("@/stores/toast-store", () => ({
  useToastStore: (
    selector: (state: { addToast: typeof mockAddToast }) => unknown,
  ) => selector({ addToast: mockAddToast }),
}));

describe("NotificationSettingsPage", () => {
  const prefs: NotificationPreferences = {
    email_on_analysis_complete: false,
    email_on_monitor_alert: true,
    email_digest_frequency: "weekly",
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuthToken.mockReturnValue("test-token");
    mockUseNotificationPreferences.mockReturnValue({
      data: prefs,
      error: null,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    mockUpdateMutate.mockImplementation(
      (
        _prefs: NotificationPreferences,
        options?: { onSuccess?: () => void; onError?: () => void },
      ) => {
        options?.onSuccess?.();
      },
    );
  });

  it("shows the loading state while preferences resolve", () => {
    mockUseNotificationPreferences.mockReturnValue({
      data: undefined,
      error: null,
      isLoading: true,
      isError: false,
      refetch: vi.fn(),
    });

    render(<NotificationSettingsPage />);

    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(
      screen.getByText("Loading notification preferences"),
    ).toBeInTheDocument();
  });

  it("does not render default preferences while auth is pending", () => {
    mockUseAuthToken.mockReturnValue(null);
    mockUseNotificationPreferences.mockReturnValue({
      data: undefined,
      error: null,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    render(<NotificationSettingsPage />);

    expect(
      screen.getByText("Checking notification preferences access"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Save Preferences" }),
    ).not.toBeInTheDocument();
  });

  it("renders safe retry copy when preference loading fails", () => {
    const refetch = vi.fn();
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mockUseNotificationPreferences.mockReturnValue({
      data: undefined,
      error: new Error("smtp token leaked"),
      isLoading: false,
      isError: true,
      refetch,
    });

    render(
      <StrictMode>
        <NotificationSettingsPage />
      </StrictMode>,
    );

    expect(
      screen.getByText("Notification preferences temporarily unavailable"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/smtp token leaked|Failed to load/i),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry control load" }));
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(consoleError).toHaveBeenCalledWith(
      "[NotificationSettingsPage] Failed to load preferences",
    );
    expect(consoleError).toHaveBeenCalledTimes(1);
    expect(consoleError).not.toHaveBeenCalledWith(
      expect.any(String),
      expect.any(Error),
    );
    consoleError.mockRestore();
  });

  it("fails closed when cached preferences are paired with an auth boundary error", () => {
    const refetch = vi.fn();
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mockUseNotificationPreferences.mockReturnValue({
      data: prefs,
      error: new APIError(403, "Forbidden"),
      isLoading: false,
      isError: true,
      refetch,
    });

    render(<NotificationSettingsPage />);

    expect(
      screen.getByText("Notification preferences restricted"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("notifications-account-control-restricted"),
    ).toHaveAttribute("data-praviar-status-frame");
    expect(
      screen.queryByRole("switch", { name: "Analysis Complete" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Save Preferences" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry control load" }));
    expect(refetch).toHaveBeenCalledTimes(1);
    consoleError.mockRestore();
  });

  it("shows stale refresh warning and locks preference edits on transient errors", () => {
    const refetch = vi.fn();
    mockUseNotificationPreferences.mockReturnValue({
      data: prefs,
      error: new Error("background refresh failed"),
      isLoading: false,
      isError: true,
      refetch,
    });

    render(<NotificationSettingsPage />);

    expect(
      screen.getByText(/Notification preference refresh failed/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/background refresh failed/i),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("switch", { name: "Analysis Complete" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("switch", { name: "Patent Monitor Alerts" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: /Weekly/i })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Save Preferences" }),
    ).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Retry refresh" }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("renders preferences, tracks dirty state, and saves updates", async () => {
    const { container } = render(<NotificationSettingsPage />);

    expect(
      screen.getByRole("heading", { name: "Notification settings" }),
    ).toBeInTheDocument();
    expect(container.querySelector("[data-praviar-mark-frame]")).toBeTruthy();
    expect(screen.getByText("Notification policy")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Choose which workspace events can leave the product by email.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Receive an email when an FTO analysis finishes. Emails may reveal analysis activity; report contents stay behind sign-in.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("switch", { name: "Analysis Complete" }),
    ).toHaveAttribute("aria-checked", "false");
    expect(
      screen.getByRole("switch", { name: "Analysis Complete" }),
    ).toHaveClass("h-11", "w-16");
    expect(
      screen.getByRole("switch", { name: "Patent Monitor Alerts" }),
    ).toHaveAttribute("aria-checked", "true");
    expect(
      screen.getByRole("button", { name: "Save Preferences" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Save Preferences" }),
    ).toHaveClass("min-h-11");
    expect(screen.getByRole("button", { name: /Weekly/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /Weekly/i })).toHaveClass(
      "min-h-16",
      "focus:ring-2",
    );

    fireEvent.click(screen.getByRole("switch", { name: "Analysis Complete" }));

    expect(screen.getByText("You have unsaved changes")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Save Preferences" }),
    ).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Save Preferences" }));

    await waitFor(() => {
      expect(mockUpdateMutate).toHaveBeenCalledWith(
        {
          email_on_analysis_complete: true,
          email_on_monitor_alert: true,
          email_digest_frequency: "weekly",
        },
        expect.objectContaining({
          onSuccess: expect.any(Function),
          onError: expect.any(Function),
        }),
      );
    });

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        "Notification preferences saved",
        "success",
      );
      expect(
        screen.queryByText("You have unsaved changes"),
      ).not.toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Save Preferences" }),
      ).toBeDisabled();
    });
  });

  it("preserves and retries the exact notification payload after a failed save", () => {
    mockUpdateMutate.mockImplementation(
      (
        _prefs: NotificationPreferences,
        options?: { onSuccess?: () => void; onError?: (error: Error) => void },
      ) => {
        options?.onError?.(new APIError(422, "smtp token leaked"));
      },
    );

    render(<NotificationSettingsPage />);

    fireEvent.click(screen.getByRole("switch", { name: "Analysis Complete" }));
    fireEvent.click(screen.getByRole("button", { name: "Save Preferences" }));

    const recovery = screen.getByTestId(
      "notification-preferences-save-recovery",
    );
    expect(recovery).toHaveAttribute("data-mutation-recovery-mode", "failed");
    expect(recovery).not.toHaveTextContent("smtp token leaked");
    expect(
      screen.getByRole("switch", { name: "Analysis Complete" }),
    ).toHaveAttribute("aria-checked", "true");

    fireEvent.click(
      screen.getByTestId("notification-preferences-save-recovery-action"),
    );

    expect(mockUpdateMutate).toHaveBeenCalledTimes(2);
    expect(mockUpdateMutate).toHaveBeenNthCalledWith(
      2,
      {
        email_on_analysis_complete: true,
        email_on_monitor_alert: true,
        email_digest_frequency: "weekly",
      },
      expect.any(Object),
    );
  });

  it("reapplies the exact notification payload after an unknown save outcome", () => {
    mockUpdateMutate.mockImplementation(
      (
        _prefs: NotificationPreferences,
        options?: { onSuccess?: () => void; onError?: (error: Error) => void },
      ) => {
        options?.onError?.(new Error("network response lost"));
      },
    );

    render(<NotificationSettingsPage />);

    fireEvent.click(
      screen.getByRole("switch", { name: "Patent Monitor Alerts" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Save Preferences" }));

    expect(
      screen.getByTestId("notification-preferences-save-recovery"),
    ).toHaveAttribute("data-mutation-recovery-mode", "outcome-unknown");
    fireEvent.click(
      screen.getByTestId("notification-preferences-save-recovery-action"),
    );

    expect(mockUpdateMutate).toHaveBeenCalledTimes(2);
    expect(mockUpdateMutate).toHaveBeenNthCalledWith(
      2,
      {
        email_on_analysis_complete: false,
        email_on_monitor_alert: false,
        email_digest_frequency: "weekly",
      },
      expect.any(Object),
    );
  });

  it("locks controls while a preference save is pending", () => {
    mockUpdateMutate.mockImplementation(() => undefined);

    render(<NotificationSettingsPage />);

    fireEvent.click(screen.getByRole("switch", { name: "Analysis Complete" }));
    fireEvent.click(screen.getByRole("button", { name: "Save Preferences" }));

    expect(
      screen.getByRole("switch", { name: "Analysis Complete" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("switch", { name: "Patent Monitor Alerts" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: /Weekly/i })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Save Preferences" }),
    ).toBeDisabled();
  });

  it("ignores a late old-boundary mutation error after an organization switch", () => {
    let mutationOptions:
      | {
          onError?: (error: Error) => void;
        }
      | undefined;
    mockUpdateMutate.mockImplementation(
      (
        _prefs: NotificationPreferences,
        options?: { onError?: (error: Error) => void },
      ) => {
        mutationOptions = options;
      },
    );

    render(<NotificationSettingsPage />);

    fireEvent.click(screen.getByRole("switch", { name: "Analysis Complete" }));
    fireEvent.click(screen.getByRole("button", { name: "Save Preferences" }));

    act(() => {
      emitAuthBoundaryChanged({ refreshToken: false });
    });
    act(() => {
      mutationOptions?.onError?.(
        new Error("late failure from previous organization"),
      );
    });

    expect(
      screen.queryByTestId("notification-preferences-save-recovery"),
    ).not.toBeInTheDocument();
  });
});
