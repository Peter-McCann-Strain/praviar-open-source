import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SSOSettings } from "@/components/settings/sso-settings";
import { APIError } from "@/lib/api-client";

const mockUseSSOStatus = vi.hoisted(() => vi.fn());
const mockConfigureMutate = vi.hoisted(() => vi.fn());
const mockAddToast = vi.hoisted(() => vi.fn());
const mockRefetchSSOStatus = vi.hoisted(() => vi.fn());

const availableStatusMetadata = {
  sso_status_available: true,
  sso_last_synced_at: new Date().toISOString(),
  sso_status_stale: false,
  sso_unavailable_reason: null,
} as const;

vi.mock("@/hooks/use-sso", () => ({
  useSSOStatus: () => mockUseSSOStatus(),
  useConfigureSSO: () => ({
    mutate: mockConfigureMutate,
    isPending: false,
  }),
}));

vi.mock("@/stores/toast-store", () => ({
  useToastStore: () => ({ addToast: mockAddToast }),
}));

describe("SSOSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    const inactiveStatus = {
      ...availableStatusMetadata,
      sso_enabled: false,
      provider: null,
      domains: [],
      status: "inactive",
      clerk_dashboard_url: null,
    };
    mockUseSSOStatus.mockReturnValue({
      data: inactiveStatus,
      error: null,
      isLoading: false,
      refetch: mockRefetchSSOStatus,
    });
    mockRefetchSSOStatus.mockResolvedValue({
      data: inactiveStatus,
      error: null,
    });
  });

  it("shows recovery instead of setup actions when SSO status fails to load", () => {
    mockUseSSOStatus.mockReturnValue({
      data: undefined,
      error: new Error("clerk outage"),
      isLoading: false,
      refetch: mockRefetchSSOStatus,
    });

    render(<SSOSettings />);

    expect(
      screen.getByText("SSO status temporarily unavailable"),
    ).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Manage" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Start SSO setup" }),
    ).not.toBeInTheDocument();
    const retryButton = screen.getByRole("button", {
      name: "Retry SSO status",
    });
    expect(retryButton).toHaveClass("min-h-11");
    fireEvent.click(retryButton);
    expect(mockRefetchSSOStatus).toHaveBeenCalledOnce();
    expect(screen.queryByText(/clerk outage/i)).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Retry SSO status" }),
    ).toHaveClass("min-h-11");
    expect(mockConfigureMutate).not.toHaveBeenCalled();
  });

  it("announces SSO status loading to assistive technology", () => {
    mockUseSSOStatus.mockReturnValue({
      data: undefined,
      error: null,
      isLoading: true,
      refetch: mockRefetchSSOStatus,
    });

    render(<SSOSettings />);

    expect(
      screen.getByRole("status", { name: "Loading SSO status" }),
    ).toBeInTheDocument();
  });

  it("routes inactive SSO configuration through the Clerk setup action", () => {
    render(<SSOSettings />);

    fireEvent.click(screen.getByRole("button", { name: "Manage" }));
    const configureButton = screen.getByRole("button", {
      name: "Start SSO setup",
    });
    expect(configureButton).toHaveClass("min-h-11");
    fireEvent.click(configureButton);

    expect(mockConfigureMutate).toHaveBeenCalledWith(
      true,
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
  });

  it("requires authoritative status reconciliation before retrying an unconfirmed SSO change", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    render(<SSOSettings />);

    fireEvent.click(screen.getByRole("button", { name: "Manage" }));
    fireEvent.click(screen.getByRole("button", { name: "Start SSO setup" }));
    const options = mockConfigureMutate.mock.calls[0]?.[1] as {
      onError: () => void;
    };
    act(() => options.onError());

    expect(mockAddToast).toHaveBeenCalledWith(
      "SSO change outcome is unconfirmed. Check current SSO status before retrying.",
      "warning",
    );
    const inlineError = screen.getByTestId("sso-configuration-error");
    expect(inlineError).toHaveTextContent("SSO change outcome unknown");
    expect(inlineError).toHaveTextContent(
      "The server may have applied this change.",
    );
    const checkStatus = screen.getByRole("button", {
      name: "Check SSO status",
    });
    expect(checkStatus).toHaveClass("min-h-11");
    fireEvent.click(checkStatus);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Retry SSO change" }),
      ).toBeInTheDocument();
    });
    expect(inlineError).toHaveTextContent(
      "Current SSO status does not show the requested change.",
    );
    expect(screen.getByText("SSO not yet configured")).toBeInTheDocument();
    expect(consoleError).toHaveBeenCalledWith(
      "[SSOSettings] Failed to update SSO configuration",
    );
    consoleError.mockRestore();
  });

  it("closes recovery when refreshed SSO status confirms the response-lost change", async () => {
    const pendingStatus = {
      ...availableStatusMetadata,
      sso_enabled: false,
      provider: "Okta",
      domains: ["praviar.example"],
      status: "pending",
      clerk_dashboard_url:
        "https://dashboard.clerk.com/organizations/org_demo/sso-connections",
    } as const;
    mockRefetchSSOStatus.mockResolvedValue({
      data: pendingStatus,
      error: null,
    });
    render(<SSOSettings />);

    fireEvent.click(screen.getByRole("button", { name: "Manage" }));
    fireEvent.click(screen.getByRole("button", { name: "Start SSO setup" }));
    const options = mockConfigureMutate.mock.calls[0]?.[1] as {
      onError: () => void;
    };
    act(() => options.onError());

    fireEvent.click(screen.getByRole("button", { name: "Check SSO status" }));
    await waitFor(() => {
      expect(
        screen.queryByTestId("sso-configuration-error"),
      ).not.toBeInTheDocument();
    });
    expect(mockAddToast).toHaveBeenLastCalledWith(
      "SSO setup request confirmed in current status.",
      "success",
    );
    expect(mockConfigureMutate).toHaveBeenCalledTimes(1);
  });

  it("removes instructions from a previous action before a new request fails", () => {
    const activeStatus = {
      ...availableStatusMetadata,
      sso_enabled: true,
      provider: "Okta",
      domains: ["praviar.example"],
      status: "active",
      clerk_dashboard_url:
        "https://dashboard.clerk.com/organizations/org_demo/sso-connections",
    } as const;
    const { rerender } = render(<SSOSettings />);

    fireEvent.click(screen.getByRole("button", { name: "Manage" }));
    fireEvent.click(screen.getByRole("button", { name: "Start SSO setup" }));
    const setupOptions = mockConfigureMutate.mock.calls[0]?.[1] as {
      onSuccess: (result: {
        status: "pending";
        message: string;
        next_steps: string[];
        clerk_dashboard_url: string;
      }) => void;
    };
    act(() => {
      setupOptions.onSuccess({
        status: "pending",
        message: "Complete the existing setup workflow.",
        next_steps: ["Connect the identity provider."],
        clerk_dashboard_url:
          "https://dashboard.clerk.com/organizations/org_demo/sso-connections",
      });
    });
    expect(
      screen.getByText("Complete the existing setup workflow."),
    ).toBeInTheDocument();

    mockUseSSOStatus.mockReturnValue({
      data: activeStatus,
      error: null,
      isLoading: false,
      refetch: mockRefetchSSOStatus,
    });
    rerender(<SSOSettings />);
    fireEvent.click(
      screen.getByRole("button", { name: "Start disable request" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm disable request" }),
    );

    expect(
      screen.queryByText("Complete the existing setup workflow."),
    ).not.toBeInTheDocument();
    const disableOptions = mockConfigureMutate.mock.calls[1]?.[1] as {
      onError: () => void;
    };
    act(() => disableOptions.onError());
    expect(
      screen.queryByText("Complete the existing setup workflow."),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/SSO is still active — follow the steps below/),
    ).not.toBeInTheDocument();
  });

  it("requires confirmation before starting the active SSO disable workflow", () => {
    mockUseSSOStatus.mockReturnValue({
      data: {
        ...availableStatusMetadata,
        sso_enabled: true,
        provider: "Okta",
        domains: ["praviar.example"],
        status: "active",
        clerk_dashboard_url:
          "https://dashboard.clerk.com/organizations/org_demo/sso-connections",
      },
      error: null,
      isLoading: false,
      refetch: mockRefetchSSOStatus,
    });

    render(<SSOSettings />);

    fireEvent.click(screen.getByRole("button", { name: "Manage" }));
    const disableButton = screen.getByRole("button", {
      name: "Start disable request",
    });
    expect(disableButton).toHaveClass("min-h-11");
    expect(
      screen.getByRole("link", { name: /Open Clerk Dashboard/i }),
    ).toHaveClass("min-h-11");
    fireEvent.click(disableButton);

    expect(mockConfigureMutate).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Confirm SSO disable request",
    );
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveClass(
      "min-h-11",
    );
    const confirmButton = screen.getByRole("button", {
      name: "Confirm disable request",
    });
    expect(confirmButton).toHaveClass("min-h-11");

    fireEvent.click(confirmButton);

    expect(mockConfigureMutate).toHaveBeenCalledWith(
      false,
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
  });

  it("cancels an active SSO disable confirmation without calling Clerk", () => {
    mockUseSSOStatus.mockReturnValue({
      data: {
        ...availableStatusMetadata,
        sso_enabled: true,
        provider: "Okta",
        domains: ["praviar.example"],
        status: "active",
        clerk_dashboard_url:
          "https://dashboard.clerk.com/organizations/org_demo/sso-connections",
      },
      error: null,
      isLoading: false,
      refetch: mockRefetchSSOStatus,
    });

    render(<SSOSettings />);

    fireEvent.click(screen.getByRole("button", { name: "Manage" }));
    fireEvent.click(
      screen.getByRole("button", {
        name: "Start disable request",
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(
      screen.queryByText("Confirm SSO disable request"),
    ).not.toBeInTheDocument();
    expect(mockConfigureMutate).not.toHaveBeenCalled();
  });

  it("locks SSO changes when stale status data is paired with a refresh error", () => {
    mockUseSSOStatus.mockReturnValue({
      data: {
        ...availableStatusMetadata,
        sso_enabled: true,
        provider: "Okta",
        domains: ["praviar.example"],
        status: "active",
        clerk_dashboard_url:
          "https://dashboard.clerk.com/organizations/org_demo/sso-connections",
      },
      error: new Error("clerk status refresh failed"),
      isLoading: false,
      refetch: mockRefetchSSOStatus,
    });

    render(<SSOSettings />);

    expect(
      screen.getByText("SSO status temporarily unavailable"),
    ).toBeInTheDocument();
    expect(screen.getByText("Okta")).toBeInTheDocument();
    expect(screen.getByText("praviar.example")).toBeInTheDocument();
    const disableButton = screen.getByRole("button", {
      name: "Start disable request",
    });
    expect(disableButton).toBeDisabled();
    expect(
      screen.queryByRole("link", { name: /Open Clerk Dashboard/i }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry SSO status" }));
    expect(mockRefetchSSOStatus).toHaveBeenCalledOnce();

    fireEvent.click(disableButton);
    expect(mockConfigureMutate).not.toHaveBeenCalled();
  });

  it("hides cached SSO details when status access is revoked", () => {
    mockUseSSOStatus.mockReturnValue({
      data: {
        ...availableStatusMetadata,
        sso_enabled: true,
        provider: "Okta",
        domains: ["praviar.example"],
        status: "active",
        clerk_dashboard_url:
          "https://dashboard.clerk.com/organizations/org_demo/sso-connections",
      },
      error: new APIError(403, "Forbidden"),
      isLoading: false,
      refetch: mockRefetchSSOStatus,
    });

    render(<SSOSettings />);

    expect(screen.getByText("SSO access restricted")).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Okta")).not.toBeInTheDocument();
    expect(screen.queryByText("praviar.example")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Start disable request" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Open Clerk Dashboard/i }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry SSO status" }));
    expect(mockRefetchSSOStatus).toHaveBeenCalledOnce();
    expect(mockConfigureMutate).not.toHaveBeenCalled();
  });

  it("wraps long enterprise SSO domains inside the settings card", () => {
    const longDomain =
      "very-long-enterprise-identity-provider-domain-with-many-subdelegations.research-and-legal-operations.praviar.example";
    mockUseSSOStatus.mockReturnValue({
      data: {
        ...availableStatusMetadata,
        sso_enabled: true,
        provider: "Okta",
        domains: [longDomain],
        status: "active",
        clerk_dashboard_url:
          "https://dashboard.clerk.com/organizations/org_demo/sso-connections",
      },
      error: null,
      isLoading: false,
      refetch: mockRefetchSSOStatus,
    });

    render(<SSOSettings />);

    fireEvent.click(screen.getByRole("button", { name: "Manage" }));

    const domainChip = screen.getByText(longDomain);
    expect(domainChip).toHaveAttribute("title", longDomain);
    expect(domainChip).toHaveClass(
      "max-w-full",
      "min-w-0",
      "break-all",
      "[overflow-wrap:anywhere]",
    );
  });

  it("rejects an API-provided non-Clerk status destination", () => {
    mockUseSSOStatus.mockReturnValue({
      data: {
        ...availableStatusMetadata,
        sso_enabled: true,
        provider: "Okta",
        domains: ["praviar.example"],
        status: "active",
        clerk_dashboard_url: "https://evil.example/fake-clerk-dashboard",
      },
      error: null,
      isLoading: false,
      refetch: mockRefetchSSOStatus,
    });

    render(<SSOSettings />);
    fireEvent.click(screen.getByRole("button", { name: "Manage" }));

    expect(
      screen.queryByRole("link", { name: /Open Clerk Dashboard/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "did not match Praviar's trusted Clerk destination",
    );
  });

  it("rejects a non-Clerk destination returned by the configure action", () => {
    render(<SSOSettings />);
    fireEvent.click(screen.getByRole("button", { name: "Manage" }));
    fireEvent.click(screen.getByRole("button", { name: "Start SSO setup" }));

    const configureOptions = mockConfigureMutate.mock.calls[0]?.[1] as {
      onSuccess: (result: {
        status: string;
        message: string;
        next_steps: string[];
        clerk_dashboard_url: string;
      }) => void;
    };
    act(() => {
      configureOptions.onSuccess({
        status: "pending",
        message: "Continue setup.",
        next_steps: ["Open the provider dashboard."],
        clerk_dashboard_url: "https://evil.example/fake-clerk-dashboard",
      });
    });

    expect(
      screen.queryByRole("link", { name: /Open Clerk Dashboard/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "did not match Praviar's trusted Clerk destination",
    );
  });

  it("shows cached details as stale and locks actions when the API marks SSO unavailable", () => {
    mockUseSSOStatus.mockReturnValue({
      data: {
        sso_enabled: true,
        provider: "Okta",
        domains: ["cached.example"],
        status: "active",
        clerk_dashboard_url:
          "https://dashboard.clerk.com/organizations/org_demo/sso-connections",
        sso_status_available: false,
        sso_last_synced_at: "2026-07-13T10:00:00Z",
        sso_status_stale: true,
        sso_unavailable_reason: "transport_error",
      },
      error: null,
      isLoading: false,
      refetch: mockRefetchSSOStatus,
    });

    render(<SSOSettings />);
    expect(screen.getByText("Unavailable")).toBeInTheDocument();

    expect(
      screen.getByText("SSO status temporarily unavailable"),
    ).toBeInTheDocument();
    expect(screen.getByText(/may be stale/i)).toBeInTheDocument();
    expect(screen.getByText("Okta")).toBeInTheDocument();
    expect(screen.getByText("cached.example")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Start disable request" }),
    ).toBeDisabled();
    expect(
      screen.queryByRole("link", { name: /Open Clerk Dashboard/i }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry SSO status" }));
    expect(mockRefetchSSOStatus).toHaveBeenCalledOnce();
    expect(mockConfigureMutate).not.toHaveBeenCalled();
  });

  it("does not trust an old timestamp when the API availability flag remains true", () => {
    mockUseSSOStatus.mockReturnValue({
      data: {
        sso_enabled: true,
        provider: "Okta",
        domains: ["expired.example"],
        status: "active",
        clerk_dashboard_url:
          "https://dashboard.clerk.com/organizations/org_demo/sso-connections",
        sso_status_available: true,
        sso_last_synced_at: "2026-07-13T10:00:00Z",
        sso_status_stale: false,
        sso_unavailable_reason: null,
      },
      error: null,
      isLoading: false,
      refetch: mockRefetchSSOStatus,
    });

    render(<SSOSettings />);
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Start disable request" }),
    ).toBeDisabled();
    expect(screen.getByText(/may be stale/i)).toBeInTheDocument();
    expect(mockConfigureMutate).not.toHaveBeenCalled();
  });
});
