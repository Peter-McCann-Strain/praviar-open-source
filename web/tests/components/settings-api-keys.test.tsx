import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiKeysTable } from "@/components/settings/api-keys-table";
import {
  CreateApiKeyForm,
  findReconciledAPIKey,
} from "@/components/settings/create-api-key-form";
import {
  apiKeyRotationLabel,
  apiKeyPrefixLabel,
  apiKeyUsageLabel,
  relativeTime,
} from "@/components/settings/helpers";
import { NewApiKeyDisplay } from "@/components/settings/new-api-key-display";
import { SettingsAccessPostureStrip } from "@/components/settings/settings-access-posture-strip";
import { SettingsGovernanceRail } from "@/components/settings/settings-governance-rail";
import { SettingsPageHeader } from "@/components/settings/settings-page-header";
import { SettingsSummaryCards } from "@/components/settings/settings-summary-cards";
import { SSOSettings } from "@/components/settings/sso-settings";
import type { APIKeyResponse, CreateAPIKeyPayload } from "@/hooks/use-api-keys";
import { APIError } from "@/lib/api-client";

const mockCreateMutate = vi.hoisted(() => vi.fn());
const mockAddToast = vi.hoisted(() => vi.fn());
const mockUseSSOStatus = vi.hoisted(() => vi.fn());
const mockConfigureSSOMutate = vi.hoisted(() => vi.fn());
const principalState = vi.hoisted(() => ({
  exportScopeAvailable: false,
}));

vi.mock("@/hooks/use-api-keys", () => ({
  useCreateAPIKey: () => ({
    mutate: mockCreateMutate,
    isPending: false,
  }),
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "test-token",
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  usePrincipalCapabilities: () => ({
    data: {
      api_key_report_export_scope_available:
        principalState.exportScopeAvailable,
    },
  }),
}));

vi.mock("@/stores/toast-store", () => ({
  useToastStore: () => ({ addToast: mockAddToast }),
}));

vi.mock("@/hooks/use-sso", () => ({
  useSSOStatus: () => mockUseSSOStatus(),
  useConfigureSSO: () => ({
    mutate: mockConfigureSSOMutate,
    isPending: false,
  }),
}));

vi.mock("@/components/shared/animated-counter", () => ({
  AnimatedCounter: ({ value }: { value: number }) => <span>{value}</span>,
}));

const activeKey: APIKeyResponse = {
  id: "key-1",
  name: "Production API",
  key_prefix: "sg_live_prod",
  scopes: ["analyses:read", "reports:read"],
  expires_at: "2026-09-01T08:30:00.000Z",
  last_used_at: "2026-05-26T08:30:00.000Z",
  revoked: false,
  created_at: "2026-05-20T08:30:00.000Z",
};

const revokedKey: APIKeyResponse = {
  id: "key-2",
  name: "Old CI Key",
  key_prefix: "sg_old_ci",
  scopes: ["analyses:read"],
  expires_at: "2026-05-20T08:30:00.000Z",
  last_used_at: null,
  revoked: true,
  created_at: "2026-05-01T08:30:00.000Z",
};

describe("settings API key helpers", () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.setSystemTime(new Date("2026-05-26T09:30:00.000Z"));
    principalState.exportScopeAvailable = false;
    mockCreateMutate.mockReset();
    mockAddToast.mockReset();
    mockConfigureSSOMutate.mockReset();
    mockUseSSOStatus.mockReturnValue({
      data: {
        sso_enabled: false,
        provider: null,
        domains: [],
        status: "inactive",
        clerk_dashboard_url: null,
        sso_status_available: true,
        sso_last_synced_at: "2026-05-26T09:30:00.000Z",
        sso_status_stale: false,
        sso_unavailable_reason: null,
      },
      isLoading: false,
      error: null,
    });
  });

  it("formats relative API key timestamps across common ranges", () => {
    expect(relativeTime("2026-05-26T09:29:45.000Z")).toBe("just now");
    expect(relativeTime("2026-05-26T09:00:00.000Z")).toBe("30m ago");
    expect(relativeTime("2026-05-26T06:30:00.000Z")).toBe("3h ago");
    expect(relativeTime("2026-05-24T09:30:00.000Z")).toBe("2d ago");
    expect(relativeTime("not-a-date")).toBe("Unknown");
    expect(apiKeyUsageLabel(null)).toBe("Never used");
    expect(apiKeyRotationLabel("2026-02-01T09:30:00.000Z")).toBe("Review now");
    expect(apiKeyPrefixLabel("sg_live")).toBe("sg_live...");
    expect(apiKeyPrefixLabel("sg_live...")).toBe("sg_live...");
  });
});

describe("ApiKeysTable", () => {
  it("renders the empty state when no API keys exist", () => {
    render(
      <ApiKeysTable
        items={[]}
        confirmRevoke={null}
        onStartRevoke={vi.fn()}
        onCancelRevoke={vi.fn()}
        onConfirmRevoke={vi.fn()}
        revokePending={false}
      />,
    );

    expect(screen.getByText("No API keys")).toBeInTheDocument();
    expect(screen.getByLabelText("No API keys")).not.toHaveClass(
      "praviar-report-decision-field",
    );
    expect(
      screen.getByText(
        "Use New API Key to integrate Praviar with approved tools, CI jobs, and internal workflow automation.",
      ),
    ).toBeInTheDocument();
  });

  it("shows active and revoked key rows and routes revoke confirmation actions", () => {
    const onStartRevoke = vi.fn();
    const onCancelRevoke = vi.fn();
    const onConfirmRevoke = vi.fn();
    const { rerender } = render(
      <ApiKeysTable
        items={[activeKey, revokedKey]}
        confirmRevoke={null}
        onStartRevoke={onStartRevoke}
        onCancelRevoke={onCancelRevoke}
        onConfirmRevoke={onConfirmRevoke}
        revokePending={false}
      />,
    );

    const activeRow = screen.getByText("Production API").closest("tr");
    expect(activeRow).not.toBeNull();
    expect(screen.getByText("Production API")).toHaveClass(
      "[overflow-wrap:anywhere]",
    );
    expect(within(activeRow!).getByText("sg_live_prod...")).toBeInTheDocument();
    expect(within(activeRow!).getByText("Read analyses")).toBeInTheDocument();
    expect(within(activeRow!).getByText("Read reports")).toBeInTheDocument();
    expect(within(activeRow!).getByText("Active")).toBeInTheDocument();
    expect(within(activeRow!).getByText("1h ago")).toBeInTheDocument();
    expect(within(activeRow!).getByText("Sep 1, 2026")).toBeInTheDocument();
    const startRevoke = within(activeRow!).getByRole("button", {
      name: "Start revoke for Production API",
    });
    expect(screen.getByRole("region", { name: "API key ledger" })).toHaveClass(
      "overflow-x-auto",
    );
    expect(
      screen.getByText(
        /API key ledger with credential scope, status, usage, expiry/i,
      ),
    ).toBeInTheDocument();
    expect(startRevoke).toHaveClass("min-h-11");
    expect(startRevoke).not.toHaveClass("md:min-h-8");
    fireEvent.click(startRevoke);
    expect(onStartRevoke).toHaveBeenCalledWith("key-1");

    const revokedRow = screen.getByText("Old CI Key").closest("tr");
    expect(revokedRow).not.toBeNull();
    expect(within(revokedRow!).getAllByText("Revoked")).toHaveLength(2);
    expect(within(revokedRow!).getByText("Never used")).toBeInTheDocument();
    expect(within(revokedRow!).getByText("Closed")).toBeInTheDocument();

    for (const header of screen.getAllByRole("columnheader")) {
      expect(header).toHaveAttribute("scope", "col");
    }

    rerender(
      <ApiKeysTable
        items={[activeKey]}
        confirmRevoke="key-1"
        onStartRevoke={onStartRevoke}
        onCancelRevoke={onCancelRevoke}
        onConfirmRevoke={onConfirmRevoke}
        revokePending={false}
      />,
    );
    const confirmRevoke = screen.getByRole("button", {
      name: "Confirm revoke for Production API",
    });
    const cancelRevoke = screen.getByRole("button", {
      name: "Cancel revoke for Production API",
    });
    expect(confirmRevoke).toHaveClass("min-h-11");
    expect(cancelRevoke).toHaveClass("min-h-11");
    expect(confirmRevoke).not.toHaveClass("md:min-h-8");
    expect(cancelRevoke).not.toHaveClass("md:min-h-8");
    fireEvent.click(confirmRevoke);
    expect(onConfirmRevoke).toHaveBeenCalledWith("key-1");
    fireEvent.click(cancelRevoke);
    expect(onCancelRevoke).toHaveBeenCalledTimes(1);
  });

  it("keeps revoke actions locked while a revoke is pending", () => {
    render(
      <ApiKeysTable
        items={[activeKey]}
        confirmRevoke="key-1"
        pendingRevokeId="key-1"
        onStartRevoke={vi.fn()}
        onCancelRevoke={vi.fn()}
        onConfirmRevoke={vi.fn()}
        revokePending={true}
      />,
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

  it("flags unrevoked keys that are expired or expiring soon", () => {
    const expiredKey: APIKeyResponse = {
      ...activeKey,
      id: "key-expired",
      name: "Expired automation",
      expires_at: "2026-05-25T08:30:00.000Z",
    };
    const expiringKey: APIKeyResponse = {
      ...activeKey,
      id: "key-expiring",
      name: "Rotating automation",
      expires_at: "2026-06-03T08:30:00.000Z",
    };

    render(
      <ApiKeysTable
        items={[expiredKey, expiringKey]}
        confirmRevoke={null}
        onStartRevoke={vi.fn()}
        onCancelRevoke={vi.fn()}
        onConfirmRevoke={vi.fn()}
        revokePending={false}
      />,
    );

    const expiredRow = screen.getByText("Expired automation").closest("tr");
    expect(expiredRow).not.toBeNull();
    expect(
      within(expiredRow!).getAllByText("Expired").length,
    ).toBeGreaterThanOrEqual(1);

    const expiringRow = screen.getByText("Rotating automation").closest("tr");
    expect(expiringRow).not.toBeNull();
    expect(within(expiringRow!).getByText("Expiring")).toBeInTheDocument();
    expect(within(expiringRow!).getByText("8d left")).toBeInTheDocument();
    expect(within(expiringRow!).getByText("Rotate soon")).toBeInTheDocument();
  });
});

describe("CreateApiKeyForm", () => {
  beforeEach(() => {
    mockCreateMutate.mockReset();
    mockAddToast.mockReset();
  });

  it("keeps submission disabled until the key name is non-empty", () => {
    render(
      <CreateApiKeyForm
        existingKeyIds={[]}
        onClose={vi.fn()}
        onCreated={vi.fn()}
        onReconciledCreation={vi.fn()}
        onRefreshKeys={vi.fn().mockResolvedValue([])}
      />,
    );

    expect(
      screen.getByRole("button", { name: /Generate Key/i }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: /Generate Key/i })).toHaveClass(
      "min-h-11",
    );
    expect(screen.getByRole("button", { name: /Cancel/i })).toHaveClass(
      "min-h-11",
    );
    expect(screen.getByPlaceholderText(/Production API/i)).toHaveClass("h-11");
    fireEvent.change(screen.getByPlaceholderText(/Production API/i), {
      target: { value: "  CI pipeline  " },
    });
    expect(
      screen.getByRole("button", { name: /Generate Key/i }),
    ).not.toBeDisabled();
    expect(screen.getByLabelText("Toggle Read analyses scope")).toBeChecked();
    expect(screen.getByLabelText("Toggle Read reports scope")).toBeChecked();
  });

  it("does not treat a matching pre-attempt key as the unknown creation", () => {
    expect(
      findReconciledAPIKey(
        [activeKey],
        {
          name: activeKey.name,
          scopes: activeKey.scopes,
          expires_at: activeKey.expires_at,
        },
        new Set([activeKey.id]),
      ),
    ).toBeNull();
  });

  it("locks close and cancel controls while creation is pending", () => {
    mockCreateMutate.mockImplementation(() => undefined);
    const onClose = vi.fn();
    render(
      <CreateApiKeyForm
        existingKeyIds={[]}
        onClose={onClose}
        onCreated={vi.fn()}
        onReconciledCreation={vi.fn()}
        onRefreshKeys={vi.fn().mockResolvedValue([])}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText(/Production API/i), {
      target: { value: "Production reports" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Generate Key/i }));

    expect(screen.getByLabelText("Close create API key form")).toBeDisabled();
    expect(screen.getByRole("button", { name: /Cancel/i })).toBeDisabled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("trims the key name, sends scope and expiry, and passes the created secret", () => {
    principalState.exportScopeAvailable = true;
    const onCreated = vi.fn();
    mockCreateMutate.mockImplementation((_payload, options) => {
      options.onSuccess({ secret_key: "sg_secret_created" });
    });
    render(
      <CreateApiKeyForm
        existingKeyIds={[]}
        onClose={vi.fn()}
        onCreated={onCreated}
        onReconciledCreation={vi.fn()}
        onRefreshKeys={vi.fn().mockResolvedValue([])}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText(/Production API/i), {
      target: { value: "  Production reports  " },
    });
    fireEvent.change(screen.getByLabelText("Expiry"), {
      target: { value: "180" },
    });
    fireEvent.click(screen.getByLabelText("Toggle Export reports scope"));
    fireEvent.click(screen.getByRole("button", { name: /Generate Key/i }));

    expect(mockCreateMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Production reports",
        scopes: ["analyses:read", "reports:read", "reports:export"],
        expires_at: expect.any(String),
      }),
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
    expect(onCreated).toHaveBeenCalledWith("sg_secret_created");
  });

  it("refreshes the ledger instead of retrying an unknown API-key creation", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const onRefreshKeys = vi.fn().mockResolvedValue([]);
    mockCreateMutate.mockImplementation((_payload, options) => {
      options.onError(new Error("secret backend stack"));
      options.onSettled();
    });

    render(
      <CreateApiKeyForm
        existingKeyIds={[]}
        onClose={vi.fn()}
        onCreated={vi.fn()}
        onReconciledCreation={vi.fn()}
        onRefreshKeys={onRefreshKeys}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText(/Production API/i), {
      target: { value: "Production reports" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Generate Key/i }));

    const recovery = screen.getByTestId("api-key-create-recovery");
    expect(recovery).toHaveAttribute(
      "data-mutation-recovery-mode",
      "outcome-unknown",
    );
    expect(recovery).not.toHaveTextContent("secret backend stack");
    expect(recovery).toHaveTextContent(
      "the one-time secret cannot be recovered",
    );
    expect(mockCreateMutate).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId("api-key-create-recovery-action"));

    await waitFor(() => expect(onRefreshKeys).toHaveBeenCalledOnce());
    expect(mockCreateMutate).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(
        screen.queryByTestId("api-key-create-recovery"),
      ).not.toBeInTheDocument(),
    );
    expect(consoleError).toHaveBeenCalledWith(
      "[CreateApiKeyForm] Failed to create API key",
    );
    expect(consoleError).not.toHaveBeenCalledWith(
      expect.any(String),
      expect.any(Error),
    );
    consoleError.mockRestore();
  });

  it("reports a matching post-attempt ledger key instead of unlocking replacement creation", async () => {
    const onReconciledCreation = vi.fn();
    let submittedPayload: CreateAPIKeyPayload | null = null;
    mockCreateMutate.mockImplementation((payload, options) => {
      submittedPayload = payload;
      options.onError(new Error("creation outcome unknown"));
      options.onSettled();
    });
    const onRefreshKeys = vi.fn().mockImplementation(async () => {
      if (!submittedPayload) return [];
      const key: APIKeyResponse = {
        id: "key-reconciled",
        name: submittedPayload.name,
        key_prefix: "sg_reconciled",
        scopes: submittedPayload.scopes,
        expires_at: submittedPayload.expires_at,
        last_used_at: null,
        revoked: false,
        created_at: new Date().toISOString(),
      };
      return [key];
    });

    render(
      <CreateApiKeyForm
        existingKeyIds={[]}
        onClose={vi.fn()}
        onCreated={vi.fn()}
        onReconciledCreation={onReconciledCreation}
        onRefreshKeys={onRefreshKeys}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText(/Production API/i), {
      target: { value: "Reconciled automation" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Generate Key/i }));
    fireEvent.click(screen.getByTestId("api-key-create-recovery-action"));

    await waitFor(() =>
      expect(onReconciledCreation).toHaveBeenCalledWith(
        expect.objectContaining({
          id: "key-reconciled",
          name: "Reconciled automation",
        }),
      ),
    );
    expect(mockCreateMutate).toHaveBeenCalledTimes(1);
  });

  it("preserves API-key form inputs after a definitive rejected request", () => {
    principalState.exportScopeAvailable = true;
    mockCreateMutate.mockImplementation((_payload, options) => {
      options.onError(new APIError(422, "Invalid"));
      options.onSettled();
    });

    render(
      <CreateApiKeyForm
        existingKeyIds={[]}
        onClose={vi.fn()}
        onCreated={vi.fn()}
        onReconciledCreation={vi.fn()}
        onRefreshKeys={vi.fn().mockResolvedValue([])}
      />,
    );

    const nameInput = screen.getByPlaceholderText(/Production API/i);
    fireEvent.change(nameInput, {
      target: { value: "Preserved pipeline key" },
    });
    fireEvent.click(screen.getByLabelText("Toggle Export reports scope"));
    fireEvent.click(screen.getByRole("button", { name: /Generate Key/i }));

    expect(screen.getByTestId("api-key-create-recovery")).toHaveAttribute(
      "data-mutation-recovery-mode",
      "failed",
    );
    expect(nameInput).toHaveValue("Preserved pipeline key");
    expect(screen.getByLabelText("Toggle Export reports scope")).toBeChecked();

    fireEvent.click(screen.getByTestId("api-key-create-recovery-action"));

    expect(
      screen.queryByTestId("api-key-create-recovery"),
    ).not.toBeInTheDocument();
    expect(nameInput).toHaveValue("Preserved pipeline key");
    expect(mockCreateMutate).toHaveBeenCalledTimes(1);
  });
});

describe("NewApiKeyDisplay", () => {
  it("copies the new secret and supports dismissing the one-time panel", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    const onDismiss = vi.fn();
    render(
      <NewApiKeyDisplay apiKey="sg_live_secret_once" onDismiss={onDismiss} />,
    );

    const secret = screen.getByLabelText("New API key secret");
    expect(secret).toHaveTextContent("sg_live_secret_once");
    expect(secret).toHaveClass(
      "overflow-x-auto",
      "whitespace-nowrap",
      "select-all",
    );
    expect(secret).not.toHaveClass("break-all");
    expect(secret).toHaveAttribute("tabindex", "0");
    expect(
      screen.getByText(
        /Shown once\. Anyone with this key can access organization data/i,
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByTitle("Copy to clipboard"));
    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith("sg_live_secret_once");
    });
    expect(screen.getByText("API key copied to clipboard")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Dismiss new API key panel"));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});

describe("settings page chrome", () => {
  it("renders summary cards and the create-key entry point", () => {
    const onToggleCreate = vi.fn();
    render(
      <>
        <SettingsPageHeader onToggleCreate={onToggleCreate} />
        <SettingsSummaryCards
          total={3}
          activeCount={2}
          revokedCount={1}
          expiringSoonCount={1}
        />
      </>,
    );

    fireEvent.click(screen.getByRole("button", { name: /New API Key/i }));
    expect(onToggleCreate).toHaveBeenCalledTimes(1);
    const header = screen.getByTestId("settings-app-surface-header");

    expect(header).toBeInTheDocument();
    expect(header).toHaveAttribute(
      "data-praviar-app-surface-density",
      "compact",
    );
    expect(header).toHaveClass("py-4");
    expect(screen.getByText("Access control plane")).toBeInTheDocument();
    expect(screen.getByText("Organization")).toBeInTheDocument();
    expect(screen.getByText("90-day review")).toBeInTheDocument();
    expect(screen.getByText("Audit retained")).toBeInTheDocument();
    expect(screen.getByText("Issued keys")).toBeInTheDocument();
    expect(screen.getByText("Active access")).toBeInTheDocument();
    expect(screen.getByText("Expiring soon")).toBeInTheDocument();
    expect(screen.getByText("Revoked audit")).toBeInTheDocument();
  });

  it("renders the governance rail as an audit-oriented review path", () => {
    render(
      <SettingsGovernanceRail
        activeCount={2}
        neverUsedCount={1}
        revokePending={false}
        createOpen={false}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Access governance" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Review")).toBeInTheDocument();
    expect(screen.getByText("2 active API keys")).toBeInTheDocument();
    expect(screen.getByText("No expiring keys")).toBeInTheDocument();
    expect(screen.getByText("1 key never used")).toBeInTheDocument();
    expect(screen.getByText("Bounded credential lifetime")).toBeInTheDocument();
    expect(screen.getByText("Admin review path")).toBeInTheDocument();
    expect(
      screen.getByText(/close unused paths with retained audit context/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("complementary", { hidden: true })).toHaveClass(
      "lg:self-start",
    );
    expect(
      screen.getByRole("complementary", { name: "Access governance" }),
    ).toBeInTheDocument();
  });

  it("renders a scan-friendly access posture strip", () => {
    const { rerender } = render(
      <SettingsAccessPostureStrip
        total={3}
        activeCount={2}
        neverUsedCount={1}
        revokePending={false}
        createOpen={false}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Access posture" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Review needed");
    expect(screen.getByText("Review needed")).toBeInTheDocument();
    expect(
      screen.getByText(/Review never-used keys before they become forgotten/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/API key posture only/i)).toBeInTheDocument();
    expect(screen.getByText("Issued ledger")).toBeInTheDocument();
    expect(screen.getByText("3 total")).toBeInTheDocument();
    expect(screen.getByText("2 active")).toBeInTheDocument();
    expect(screen.getByText("1 flagged")).toBeInTheDocument();

    rerender(
      <SettingsAccessPostureStrip
        total={2}
        activeCount={2}
        neverUsedCount={0}
        revokePending={true}
        createOpen={false}
      />,
    );

    expect(screen.getByText("Revocation pending")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Revocation pending");
    expect(
      screen.getByText(/locked until the revocation request settles/i),
    ).toBeInTheDocument();
  });

  it("labels pending SSO as a continuation, not a fresh setup", () => {
    mockUseSSOStatus.mockReturnValue({
      data: {
        sso_enabled: true,
        provider: "Okta",
        domains: ["acme.example"],
        status: "pending",
        clerk_dashboard_url: "https://dashboard.clerk.com/example",
        sso_status_available: true,
        sso_last_synced_at: "2026-05-26T09:30:00.000Z",
        sso_status_stale: false,
        sso_unavailable_reason: null,
      },
      isLoading: false,
      error: null,
    });

    render(<SSOSettings />);

    fireEvent.click(screen.getByRole("button", { name: "Manage" }));

    expect(
      screen.getByRole("button", { name: "Continue SSO setup" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Start SSO setup" }),
    ).not.toBeInTheDocument();
  });
});
