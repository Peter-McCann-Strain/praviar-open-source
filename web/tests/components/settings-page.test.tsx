import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StrictMode } from "react";
import { APIError } from "@/lib/api-client";
import { AUTH_BOUNDARY_CHANGED_EVENT } from "@/lib/auth-events";

const mockUseAuthToken = vi.hoisted(() => vi.fn());
const mockUseAPIKeys = vi.hoisted(() => vi.fn());
const mockRevokeMutate = vi.hoisted(() => vi.fn());
const mockSettingsAuth = vi.hoisted(() => ({
  hasClerk: false,
  isLoaded: true,
  orgRole: "org:admin" as string | null,
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => mockUseAuthToken(),
}));

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({
    isLoaded: mockSettingsAuth.isLoaded,
    orgRole: mockSettingsAuth.orgRole,
  }),
}));

vi.mock("@/components/layout/sidebar-constants", () => ({
  get hasClerk() {
    return mockSettingsAuth.hasClerk;
  },
  isAdminOrgRole: (orgRole: string | null | undefined) =>
    orgRole === "org:admin" || orgRole === "admin",
}));

vi.mock("@/hooks/use-api-keys", () => ({
  useAPIKeys: (...args: unknown[]) => mockUseAPIKeys(...args),
  useRevokeAPIKey: () => ({
    mutate: mockRevokeMutate,
    isPending: false,
  }),
}));

vi.mock("@/components/settings/sso-settings", () => ({
  SSOSettings: () => <div data-testid="sso-settings" />,
}));

vi.mock("@/components/settings/create-api-key-form", () => ({
  CreateApiKeyForm: (props: {
    onCreated: (secret: string) => void;
    onReconciledCreation: (key: (typeof apiKeys.items)[number]) => void;
  }) => (
    <>
      <button
        type="button"
        onClick={() => props.onCreated("sk_org_a_one_time_secret")}
      >
        Simulate key creation
      </button>
      <button
        type="button"
        onClick={() => props.onReconciledCreation(apiKeys.items[0])}
      >
        Simulate reconciled creation
      </button>
    </>
  ),
}));

vi.mock("@/components/settings/external-sharing-policy-card", () => ({
  ExternalSharingPolicyCard: () => (
    <div data-testid="external-sharing-policy" />
  ),
}));

vi.mock("@/components/shared/animated-counter", () => ({
  AnimatedCounter: ({ value }: { value: number }) => <span>{value}</span>,
}));

import SettingsPage from "@/app/(dashboard)/settings/page";

const apiKeys = {
  items: [
    {
      id: "key-1",
      name: "Production API",
      key_prefix: "sg_live_prod",
      scopes: ["analyses:read", "reports:read"],
      expires_at: "2026-09-01T10:00:00.000Z",
      last_used_at: null,
      revoked: false,
      created_at: "2026-06-01T10:00:00.000Z",
    },
  ],
  total: 1,
};

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSettingsAuth.hasClerk = false;
    mockSettingsAuth.isLoaded = true;
    mockSettingsAuth.orgRole = "org:admin";
    mockUseAuthToken.mockReturnValue("tok");
    mockUseAPIKeys.mockReturnValue({
      data: apiKeys,
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });
  });

  it("renders a governed loading state and disables API key creation", () => {
    mockUseAPIKeys.mockReturnValue({
      data: undefined,
      error: null,
      isLoading: true,
      refetch: vi.fn(),
    });

    render(<SettingsPage />);

    expect(
      screen.getByTestId("settings-account-control-loading"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New API Key" })).toBeDisabled();
  });

  it("withholds API key controls and queries until Clerk role is loaded", () => {
    mockSettingsAuth.hasClerk = true;
    mockSettingsAuth.isLoaded = false;

    render(<SettingsPage />);

    expect(
      screen.getByText("Checking API key settings access"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New API Key" })).toBeDisabled();
    expect(screen.queryByText("Production API")).not.toBeInTheDocument();
    expect(mockUseAPIKeys).not.toHaveBeenCalled();
  });

  it("restricts API key controls for non-admin workspace roles", () => {
    mockSettingsAuth.hasClerk = true;
    mockSettingsAuth.orgRole = "org:member";

    render(<SettingsPage />);

    expect(screen.getByText("API key settings restricted")).toBeInTheDocument();
    expect(screen.getByText("Admin access required")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New API Key" })).toBeDisabled();
    expect(screen.queryByText("Production API")).not.toBeInTheDocument();
    expect(screen.queryByText("Access & Automation")).not.toBeInTheDocument();
    expect(mockUseAPIKeys).not.toHaveBeenCalled();
  });

  it("does not render empty controls while auth is not ready", () => {
    mockUseAuthToken.mockReturnValue(null);
    mockUseAPIKeys.mockReturnValue({
      data: undefined,
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });

    render(<SettingsPage />);

    expect(
      screen.getByText("Checking API key settings access"),
    ).toBeInTheDocument();
    expect(screen.queryByText("No API keys")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New API Key" })).toBeDisabled();
  });

  it("renders a safe retry state without exposing API diagnostics", () => {
    const refetch = vi.fn();
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mockUseAPIKeys.mockReturnValue({
      data: undefined,
      error: new Error("postgres password failed"),
      isLoading: false,
      refetch,
    });

    render(
      <StrictMode>
        <SettingsPage />
      </StrictMode>,
    );

    expect(
      screen.getByText("API key settings temporarily unavailable"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/postgres password failed/i),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Access & Automation")).toBeInTheDocument();
    expect(screen.getByText("Identity & Sign-On")).toBeInTheDocument();
    expect(screen.getByTestId("sso-settings")).toBeInTheDocument();
    expect(screen.getByText("External Collaboration")).toBeInTheDocument();
    expect(screen.getByTestId("external-sharing-policy")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry control load" }));
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(consoleError).toHaveBeenCalledWith(
      "[SettingsPage] Failed to load API key settings",
    );
    expect(consoleError).toHaveBeenCalledTimes(1);
    expect(consoleError).not.toHaveBeenCalledWith(
      expect.any(String),
      expect.any(Error),
    );
    consoleError.mockRestore();
  });

  it("preserves stale API key data when a background refetch errors", () => {
    mockUseAPIKeys.mockReturnValue({
      data: apiKeys,
      error: new Error("background fetch failed"),
      isLoading: false,
      refetch: vi.fn(),
    });

    render(<SettingsPage />);

    expect(screen.getByText("Production API")).toBeInTheDocument();
    expect(
      screen.queryByText("API key settings temporarily unavailable"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Access posture")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Existing key data is still visible, but the latest refresh needs retry.",
      ),
    ).toBeInTheDocument();
  });

  it("hides cached API key data when settings access is revoked", () => {
    const refetch = vi.fn();
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mockUseAPIKeys.mockReturnValue({
      data: apiKeys,
      error: new APIError(403, "Forbidden"),
      isLoading: false,
      refetch,
    });

    render(<SettingsPage />);

    expect(screen.getByText("API key settings restricted")).toBeInTheDocument();
    expect(
      screen.getByTestId("settings-account-control-restricted"),
    ).toHaveAttribute("data-praviar-status-frame");
    expect(screen.getByRole("button", { name: "New API Key" })).toBeDisabled();
    expect(screen.queryByText("Production API")).not.toBeInTheDocument();
    expect(screen.queryByText("Access & Automation")).not.toBeInTheDocument();
    expect(screen.queryByText("Access posture")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry control load" }));
    expect(refetch).toHaveBeenCalledTimes(1);
    consoleError.mockRestore();
  });

  it("renders the access posture strip before the credential ledger", () => {
    render(<SettingsPage />);

    expect(screen.getByTestId("settings-governance-layout")).toHaveClass(
      "lg:grid-cols-[minmax(0,1fr)_20rem]",
      "lg:items-start",
    );
    expect(screen.getByText("Access posture")).toBeInTheDocument();
    expect(screen.getByText("Review needed")).toBeInTheDocument();
    expect(screen.getByText("Issued ledger")).toBeInTheDocument();
    expect(screen.getByText("1 total")).toBeInTheDocument();
    expect(screen.getByText("1 active")).toBeInTheDocument();
    expect(screen.getByText("1 flagged")).toBeInTheDocument();
    expect(
      screen.getByText(/Review never-used keys before they become forgotten/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/API key posture only/i)).toBeInTheDocument();
    expect(screen.getByText("External Collaboration")).toBeInTheDocument();
    expect(screen.getByTestId("external-sharing-policy")).toBeInTheDocument();
  });

  it("prioritizes identity status until an API key workflow is active", () => {
    render(<SettingsPage />);

    const identityHeading = screen.getByText("Identity & Sign-On");
    const accessHeading = screen.getByText("Access & Automation");
    expect(
      identityHeading.compareDocumentPosition(accessHeading) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Revoke/i }));

    expect(
      accessHeading.compareDocumentPosition(identityHeading) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("keeps revoke controls locked while revocation is pending", () => {
    mockRevokeMutate.mockImplementation(() => undefined);

    render(<SettingsPage />);

    fireEvent.click(screen.getByRole("button", { name: /Revoke/i }));
    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm revoke for Production API",
      }),
    );

    expect(mockRevokeMutate).toHaveBeenCalledWith(
      "key-1",
      expect.objectContaining({
        onError: expect.any(Function),
        onSettled: expect.any(Function),
      }),
    );
    expect(
      screen.getByRole("button", {
        name: "Confirm revoke for Production API",
      }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", {
        name: "Cancel revoke for Production API",
      }),
    ).toBeDisabled();
  });

  it("refreshes the API-key ledger after an unknown revoke outcome", async () => {
    const refetch = vi.fn().mockResolvedValue({ data: apiKeys, error: null });
    mockUseAPIKeys.mockReturnValue({
      data: apiKeys,
      error: null,
      isLoading: false,
      isFetching: false,
      refetch,
    });
    mockRevokeMutate.mockImplementation((_keyId, options) => {
      options.onError(new Error("delete denied"));
      options.onSettled();
    });

    render(<SettingsPage />);

    fireEvent.click(screen.getByRole("button", { name: /Revoke/i }));
    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm revoke for Production API",
      }),
    );

    const recovery = screen.getByTestId("api-key-revoke-recovery");
    expect(recovery).toHaveAttribute(
      "data-mutation-recovery-mode",
      "outcome-unknown",
    );
    expect(recovery).not.toHaveTextContent("delete denied");
    expect(mockRevokeMutate).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "New API Key" })).toBeDisabled();

    fireEvent.click(screen.getByTestId("api-key-revoke-recovery-action"));

    await waitFor(() => expect(refetch).toHaveBeenCalledOnce());
    expect(mockRevokeMutate).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(
        screen.queryByTestId("api-key-revoke-recovery"),
      ).not.toBeInTheDocument(),
    );
  });

  it("blocks replacement creation until a reconciled key is revoked", () => {
    mockRevokeMutate.mockImplementation((_keyId, options) => {
      options.onSuccess();
      options.onSettled();
    });

    render(<SettingsPage />);

    fireEvent.click(screen.getByRole("button", { name: "New API Key" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Simulate reconciled creation" }),
    );

    expect(screen.getByTestId("api-key-create-reconciled")).toHaveTextContent(
      "Matching API key requires review",
    );
    expect(screen.getByRole("button", { name: "New API Key" })).toBeDisabled();

    fireEvent.click(screen.getByTestId("api-key-create-reconciled-action"));
    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm revoke for Production API",
      }),
    );

    expect(mockRevokeMutate).toHaveBeenCalledWith(
      "key-1",
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
    expect(
      screen.queryByTestId("api-key-create-reconciled"),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New API Key" })).toBeEnabled();
  });

  it("clears one-time credentials and private workflow state on organization switches", () => {
    mockRevokeMutate.mockImplementation(() => undefined);

    render(<SettingsPage />);

    fireEvent.click(screen.getByRole("button", { name: "New API Key" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Simulate key creation" }),
    );
    expect(screen.getByText("sk_org_a_one_time_secret")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Revoke/i }));
    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm revoke for Production API",
      }),
    );
    expect(
      screen.getByRole("button", {
        name: "Confirm revoke for Production API",
      }),
    ).toBeDisabled();

    act(() => {
      window.dispatchEvent(new CustomEvent(AUTH_BOUNDARY_CHANGED_EVENT));
    });

    expect(
      screen.queryByText("sk_org_a_one_time_secret"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", {
        name: "Confirm revoke for Production API",
      }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New API Key" })).toBeEnabled();
  });
});
