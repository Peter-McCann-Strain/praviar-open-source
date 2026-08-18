import { StrictMode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ShareDialog } from "@/components/collaboration/share-dialog";

const apiClientMock = vi.fn();
const addToast = vi.fn();
const scrollIntoViewMock = vi.fn();
let authToken: string | null = "jwt";
let authBoundaryKey: string | null = "boundary-user-a-org-a";
let authBoundaryError = false;

Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
  configurable: true,
  value: scrollIntoViewMock,
});

vi.mock("@/hooks/use-auth-token", () => ({ useAuthToken: () => authToken }));
vi.mock("@/lib/auth-events", () => ({
  getCurrentAuthBoundaryKey: () => authBoundaryKey,
}));
vi.mock("@/stores/toast-store", () => ({
  useToastStore: () => ({ addToast }),
}));
vi.mock("@/lib/api-client", () => ({
  apiClient: (...args: unknown[]) => apiClientMock(...args),
  isAuthBoundaryError: () => authBoundaryError,
}));
vi.mock("@/components/collaboration/share-dialog-backdrop", () => ({
  ShareDialogBackdrop: () => <div data-testid="backdrop" />,
}));
vi.mock("@/components/collaboration/share-dialog-header", () => ({
  ShareDialogHeader: () => <h2 id="share-dialog-title">Share report</h2>,
}));
vi.mock("@/components/collaboration/use-export-dialog-focus-trap", () => ({
  useExportDialogFocusTrap: () => undefined,
}));
vi.mock("@/components/shared/risk-badge", () => ({
  RiskBadge: () => null,
}));

const ACTIVE_GRANT = {
  id: "grant-1",
  recipient_email: "named.counsel@example.com",
  recipient_domain: "example.com",
  invitation_sent_at: "2026-07-13T12:00:00.000Z",
  expires_at: "2026-07-20T12:00:00.000Z",
  revoked_at: null,
  max_views: 25,
  view_count: 2,
  download_allowed: false,
  last_accessed_at: "2026-07-13T12:05:00.000Z",
  status: "active",
};

const VALIDATED_GRANT = {
  ...ACTIVE_GRANT,
  id: "123e4567-e89b-42d3-a456-426614174000",
  max_downloads: 0,
  download_count: 0,
};

describe("ShareDialog recipient grants", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authToken = "jwt";
    authBoundaryKey = "boundary-user-a-org-a";
    authBoundaryError = false;
    apiClientMock.mockResolvedValue({ items: [ACTIVE_GRANT] });
  });

  it("shows sender-only named access history and no password controls", async () => {
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    const recipient = await screen.findByText("named.counsel@example.com");
    expect(recipient).toHaveClass(
      "block",
      "max-w-full",
      "overflow-hidden",
      "text-ellipsis",
      "whitespace-nowrap",
      "text-[13px]",
      "sm:whitespace-normal",
    );
    const ledgerHeading = screen.getByText("Named access history");
    expect(ledgerHeading.closest("section")).toHaveClass(
      "order-1",
      "lg:order-2",
    );
    expect(
      screen.getByText("Invite one intended recipient").closest("section"),
    ).toHaveClass("order-2", "lg:order-1");
    expect(screen.getByText(/2 of 25 views/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Revoke recipient" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/password/i)).not.toBeInTheDocument();
    expect(screen.getByTestId("share-dialog-sticky-header")).toHaveClass(
      "sticky",
      "top-0",
      "z-20",
    );
  });

  it("refreshes the authoritative recipient ledger on demand", async () => {
    const onShareStateRefresh = vi.fn();
    apiClientMock
      .mockResolvedValueOnce({ items: [ACTIVE_GRANT] })
      .mockResolvedValueOnce({ items: [ACTIVE_GRANT] });
    render(
      <ShareDialog
        reportId="report-1"
        open
        onClose={vi.fn()}
        onShareStateRefresh={onShareStateRefresh}
      />,
    );

    await screen.findByText("named.counsel@example.com");
    fireEvent.click(
      screen.getByRole("button", { name: "Refresh recipient ledger" }),
    );

    await waitFor(() => expect(apiClientMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(scrollIntoViewMock).toHaveBeenCalledOnce(), {
      // The component deliberately schedules the scroll after the refreshed
      // ledger has committed. Under the full 3k-test run that zero-delay task
      // can sit behind other jsdom work for longer than Testing Library's
      // one-second default even though the behavior is correct.
      timeout: 3_000,
    });
    expect(screen.getByTestId("share-recipient-ledger")).toHaveClass(
      "order-1",
      "scroll-mt-28",
      "lg:order-2",
    );
    expect(onShareStateRefresh).toHaveBeenCalledTimes(1);
    expect(apiClientMock).toHaveBeenLastCalledWith(
      "/reports/report-1/share",
      expect.objectContaining({
        token: "jwt",
        signal: expect.any(AbortSignal),
      }),
    );
  });

  it("wraps long report and compound identity values in the handoff header", async () => {
    const longReportId =
      "rpt-US20260345678A1-WO2026123456A1-very-long-governed-share-reference";
    const longCompound =
      "N-(4-((7-chloro-6-(longsubstituentchainwithnoobviousbreakpoints)quinazolin-4-yl)oxy)phenyl)-3-hydroxypropanamide";

    apiClientMock.mockResolvedValueOnce({ items: [] });
    render(
      <ShareDialog
        reportId="report-1"
        report={
          {
            report_id: longReportId,
            compound: { name: longCompound },
            risk_summary: { overall_risk: "medium" },
          } as any
        }
        open
        onClose={vi.fn()}
      />,
    );

    expect(await screen.findByText(longReportId)).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText(longCompound)).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
  });

  it("expands an immutable non-secret activity timeline for one exact grant", async () => {
    apiClientMock
      .mockResolvedValueOnce({ items: [ACTIVE_GRANT] })
      .mockResolvedValueOnce({
        items: [
          {
            id: "event-1",
            event: "invitation_sent",
            occurred_at: "2026-07-13T12:00:00.000Z",
            view_number: null,
            ip_address: "203.0.113.12",
            access_secret: "must-stay-hidden",
          },
          {
            id: "event-2",
            event: "report_viewed",
            occurred_at: "2026-07-13T12:05:00.000Z",
            view_number: 2,
          },
        ],
      });
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Show activity for named.counsel@example.com",
      }),
    );

    expect(
      await screen.findByText("Invitation accepted for delivery"),
    ).toBeInTheDocument();
    expect(screen.getByText("Report view 2")).toBeInTheDocument();
    expect(screen.getByText("2026-07-13T12:00:00Z UTC")).toBeInTheDocument();
    expect(screen.getByText("2026-07-13T12:05:00Z UTC")).toBeInTheDocument();
    expect(apiClientMock).toHaveBeenLastCalledWith(
      "/reports/report-1/share/grant-1/activity",
      expect.objectContaining({
        token: "jwt",
        signal: expect.any(AbortSignal),
      }),
    );
    expect(
      screen.queryByText(/203\.0\.113\.12|must-stay-hidden/),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("list", {
        name: "Immutable activity for named.counsel@example.com",
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("list").parentElement).toHaveClass("scroll-mt-32");
    await waitFor(() =>
      expect(scrollIntoViewMock).toHaveBeenCalledWith({
        behavior: "auto",
        block: "start",
      }),
    );
  });

  it("explains policy, expiry, retention, and reconciliation delivery events", async () => {
    apiClientMock
      .mockResolvedValueOnce({ items: [ACTIVE_GRANT] })
      .mockResolvedValueOnce({
        items: [
          {
            id: "event-policy",
            event: "delivery_cancelled_by_policy",
            occurred_at: "2026-07-13T12:01:00.000Z",
            view_number: null,
          },
          {
            id: "event-expiry",
            event: "delivery_cancelled_expired",
            occurred_at: "2026-07-13T12:02:00.000Z",
            view_number: null,
          },
          {
            id: "event-retention",
            event: "delivery_cancelled_retention_expired",
            occurred_at: "2026-07-13T12:03:00.000Z",
            view_number: null,
          },
          {
            id: "event-alert",
            event: "delivery_reconciliation_alert",
            occurred_at: "2026-07-13T12:04:00.000Z",
            view_number: null,
          },
        ],
      });
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Show activity for named.counsel@example.com",
      }),
    );

    expect(
      await screen.findByText(
        "Invitation cancelled after workspace policy changed",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Invitation cancelled after its access window expired"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Invitation cancelled when provider lookup retention ended",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Delivery reconciliation requires operator review"),
    ).toBeInTheDocument();
  });

  it("keeps activity failure distinct from an authenticated empty timeline and retries", async () => {
    apiClientMock
      .mockResolvedValueOnce({ items: [ACTIVE_GRANT] })
      .mockRejectedValueOnce(new Error("audit store unavailable"))
      .mockResolvedValueOnce({ items: [] });
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Show activity for named.counsel@example.com",
      }),
    );
    expect(
      await screen.findByText("Grant activity unavailable"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("No recorded recipient activity yet."),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry activity" }));
    expect(
      await screen.findByText("No recorded recipient activity yet."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Grant activity unavailable"),
    ).not.toBeInTheDocument();
  });

  it("fails closed when activity violates its runtime contract", async () => {
    apiClientMock
      .mockResolvedValueOnce({ items: [ACTIVE_GRANT] })
      .mockImplementationOnce(
        (_path: string, options: { validate: (data: unknown) => unknown }) =>
          Promise.resolve(
            options.validate({
              items: [
                {
                  id: "123e4567-e89b-42d3-a456-426614174001",
                  event: "recipient_probably_viewed",
                  occurred_at: "2026-07-25T10:05:00Z",
                  view_number: 1,
                },
              ],
            }),
          ),
      );
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Show activity for named.counsel@example.com",
      }),
    );

    expect(
      await screen.findByText("Grant activity unavailable"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/recipient probably viewed/i),
    ).not.toBeInTheDocument();
  });

  it("hides the cached recipient ledger when activity authorization is revoked", async () => {
    apiClientMock
      .mockResolvedValueOnce({ items: [ACTIVE_GRANT] })
      .mockRejectedValueOnce(new Error("forbidden"));
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    await screen.findByText("named.counsel@example.com");
    authBoundaryError = true;
    fireEvent.click(
      screen.getByRole("button", {
        name: "Show activity for named.counsel@example.com",
      }),
    );

    expect(
      await screen.findByText("Share access restricted"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("named.counsel@example.com"),
    ).not.toBeInTheDocument();
  });

  it("creates a mailbox-bound grant and shows the link once", async () => {
    const onShareStateRefresh = vi.fn();
    apiClientMock
      .mockResolvedValueOnce({ items: [] })
      .mockResolvedValueOnce({
        ...ACTIVE_GRANT,
        id: "grant-new",
        recipient_email: "new.counsel@example.com",
        share_token: "T".repeat(43),
        invitation_status: "provider_accepted",
      })
      .mockResolvedValueOnce({
        items: [
          {
            ...ACTIVE_GRANT,
            id: "grant-new",
            recipient_email: "new.counsel@example.com",
          },
        ],
      });
    render(
      <ShareDialog
        reportId="report-1"
        open
        onClose={vi.fn()}
        onShareStateRefresh={onShareStateRefresh}
      />,
    );

    fireEvent.change(screen.getByLabelText("Recipient email"), {
      target: { value: "new.counsel@example.com" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Send verification invitation" }),
    );

    await waitFor(() => {
      expect(apiClientMock).toHaveBeenCalledWith(
        "/reports/report-1/share",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            recipient_email: "new.counsel@example.com",
            expires_in_days: 7,
            max_views: 25,
          }),
        }),
      );
    });
    expect(
      await screen.findByText(
        /Invitation accepted for delivery to new.counsel@example.com/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveClass(
      "scroll-mt-32",
      "border-success/30",
    );
    await waitFor(() =>
      expect(scrollIntoViewMock).toHaveBeenCalledWith({
        behavior: "auto",
        block: "start",
      }),
    );
    expect(
      screen.getByRole("button", { name: "Copy recipient link" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("textbox", { name: "Recipient link (read only)" }),
    ).toHaveTextContent(`/share/${"T".repeat(43)}`);
    expect(onShareStateRefresh).toHaveBeenCalledTimes(1);
  });

  it("keeps create requests live after the Strict Mode mount probe", async () => {
    const createdGrant = {
      ...ACTIVE_GRANT,
      id: "grant-strict-mode",
      recipient_email: "strict.counsel@example.com",
      share_token: "S".repeat(43),
      invitation_status: "provider_accepted",
    };
    apiClientMock.mockImplementation(
      (_path: string, options?: { method?: string; signal?: AbortSignal }) => {
        if (options?.method === "POST") {
          expect(options.signal?.aborted).toBe(false);
          return Promise.resolve(createdGrant);
        }
        return Promise.resolve({ items: [] });
      },
    );

    render(
      <StrictMode>
        <ShareDialog reportId="report-1" open onClose={vi.fn()} />
      </StrictMode>,
    );

    fireEvent.change(screen.getByLabelText("Recipient email"), {
      target: { value: "strict.counsel@example.com" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Send verification invitation" }),
    );

    expect(
      await screen.findByText(
        /Invitation accepted for delivery to strict.counsel@example.com/,
      ),
    ).toBeInTheDocument();
    const getListCalls = () =>
      apiClientMock.mock.calls.filter(
        ([path, options]) =>
          path === "/reports/report-1/share" &&
          (options as { method?: string } | undefined)?.method !== "POST",
      );
    await waitFor(() => expect(getListCalls()).toHaveLength(2));
    const listCalls = getListCalls();
    for (const [, options] of listCalls) {
      expect((options as { signal: AbortSignal }).signal.aborted).toBe(false);
    }
    expect(
      screen.getByRole("textbox", { name: "Recipient link (read only)" }),
    ).toHaveTextContent(`/share/${"S".repeat(43)}`);
  });

  it("refreshes the authoritative ledger and never leaves a reissued mailbox active twice", async () => {
    const oldGrant = {
      ...ACTIVE_GRANT,
      id: "grant-old",
    };
    const newGrant = {
      ...ACTIVE_GRANT,
      id: "grant-new",
      share_token: "N".repeat(43),
      invitation_status: "provider_accepted",
    };
    apiClientMock
      .mockResolvedValueOnce({ items: [oldGrant] })
      .mockResolvedValueOnce(newGrant)
      .mockResolvedValueOnce({
        items: [
          newGrant,
          {
            ...oldGrant,
            revoked_at: "2026-07-14T01:00:00.000Z",
            status: "revoked",
          },
        ],
      });
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    await screen.findByText("named.counsel@example.com");
    fireEvent.change(screen.getByLabelText("Recipient email"), {
      target: { value: "named.counsel@example.com" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Send verification invitation" }),
    );

    await waitFor(() => expect(apiClientMock).toHaveBeenCalledTimes(3));
    expect(screen.getAllByText("named.counsel@example.com")).toHaveLength(2);
    expect(
      screen.getAllByRole("button", { name: "Revoke recipient" }),
    ).toHaveLength(1);
    expect(screen.getByText("Revoked · 2 of 25 views")).toBeInTheDocument();
  });

  it("keeps a failed ledger load distinct from an empty recipient ledger", async () => {
    apiClientMock.mockRejectedValueOnce(new Error("service unavailable"));
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    expect(
      await screen.findByText("Recipient ledger unavailable"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("No recipient grants yet."),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("fails closed when the recipient ledger violates its runtime contract", async () => {
    apiClientMock.mockImplementationOnce(
      (_path: string, options: { validate: (data: unknown) => unknown }) =>
        Promise.resolve(
          options.validate({
            items: [{ ...VALIDATED_GRANT, status: "probably_active" }],
          }),
        ),
    );
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    expect(
      await screen.findByText("Recipient ledger unavailable"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(VALIDATED_GRANT.recipient_email),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("No recipient grants yet."),
    ).not.toBeInTheDocument();
  });

  it("retries a failed ledger load and replaces the error with authenticated data", async () => {
    apiClientMock
      .mockRejectedValueOnce(new Error("service unavailable"))
      .mockResolvedValueOnce({ items: [ACTIVE_GRANT] });
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));

    expect(
      await screen.findByText("named.counsel@example.com"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Recipient ledger unavailable"),
    ).not.toBeInTheDocument();
    expect(apiClientMock).toHaveBeenCalledTimes(2);
  });

  it("waits for authentication before loading and recovers on token arrival", async () => {
    authToken = null;
    const { rerender } = render(
      <ShareDialog reportId="report-1" open onClose={vi.fn()} />,
    );

    expect(apiClientMock).not.toHaveBeenCalled();
    expect(screen.getByText("Loading recipient ledger…")).toBeInTheDocument();
    expect(
      screen.getByText("Preparing your authenticated sharing session…"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Recipient email")).toBeDisabled();
    expect(screen.getByLabelText("Expires after")).toBeDisabled();
    expect(screen.getByLabelText("Maximum views")).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Send verification invitation" }),
    ).toBeDisabled();

    authToken = "fresh-jwt";
    rerender(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    expect(
      await screen.findByText("named.counsel@example.com"),
    ).toBeInTheDocument();
    expect(apiClientMock).toHaveBeenCalledTimes(1);
    expect(apiClientMock).toHaveBeenCalledWith(
      "/reports/report-1/share",
      expect.objectContaining({
        token: "fresh-jwt",
        signal: expect.any(AbortSignal),
        validate: expect.any(Function),
      }),
    );
    expect(
      screen.queryByText("Share access restricted"),
    ).not.toBeInTheDocument();
  });

  it("clears a stale restriction after a later authenticated load succeeds", async () => {
    authBoundaryError = true;
    apiClientMock.mockRejectedValueOnce(new Error("unauthorized"));
    const { rerender } = render(
      <ShareDialog reportId="report-1" open onClose={vi.fn()} />,
    );

    expect(
      await screen.findByText("Share access restricted"),
    ).toBeInTheDocument();

    authBoundaryError = false;
    authToken = "renewed-jwt";
    rerender(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    expect(
      await screen.findByText("named.counsel@example.com"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Share access restricted"),
    ).not.toBeInTheDocument();
  });

  it("preserves draft and one-time URL across a token refresh in one auth boundary", async () => {
    let resolveRefresh!: (value: { items: (typeof ACTIVE_GRANT)[] }) => void;
    const refreshLoad = new Promise<{ items: (typeof ACTIVE_GRANT)[] }>(
      (resolve) => {
        resolveRefresh = resolve;
      },
    );
    const created = {
      ...ACTIVE_GRANT,
      id: "grant-new",
      recipient_email: "fresh.counsel@example.com",
      share_token: "R".repeat(43),
      invitation_status: "provider_accepted",
    };
    apiClientMock
      .mockResolvedValueOnce({ items: [] })
      .mockResolvedValueOnce(created)
      .mockResolvedValueOnce({ items: [created] });
    const { rerender } = render(
      <ShareDialog reportId="report-1" open onClose={vi.fn()} />,
    );
    fireEvent.change(screen.getByLabelText("Recipient email"), {
      target: { value: "fresh.counsel@example.com" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Send verification invitation" }),
    );
    await screen.findByRole("textbox", { name: "Recipient link (read only)" });
    await waitFor(() => expect(apiClientMock).toHaveBeenCalledTimes(3));
    fireEvent.change(screen.getByLabelText("Recipient email"), {
      target: { value: "next-recipient@example.com" },
    });

    apiClientMock.mockImplementationOnce(() => refreshLoad);
    authToken = "refreshed-jwt-for-same-user-org";
    rerender(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    expect(screen.getByLabelText("Recipient email")).toHaveValue(
      "next-recipient@example.com",
    );
    expect(
      screen.getByRole("textbox", { name: "Recipient link (read only)" }),
    ).toHaveTextContent(`/share/${"R".repeat(43)}`);
    resolveRefresh({ items: [created] });
    expect(
      await screen.findByText("fresh.counsel@example.com"),
    ).toBeInTheDocument();
  });

  it("clears the prior auth boundary before the replacement ledger resolves", async () => {
    let resolveReplacement!: (value: { items: never[] }) => void;
    const replacementLoad = new Promise<{ items: never[] }>((resolve) => {
      resolveReplacement = resolve;
    });
    const created = {
      ...ACTIVE_GRANT,
      id: "grant-new",
      recipient_email: "fresh.counsel@example.com",
      share_token: "S".repeat(43),
      invitation_status: "provider_accepted",
    };
    apiClientMock
      .mockResolvedValueOnce({ items: [] })
      .mockResolvedValueOnce(created)
      .mockResolvedValueOnce({ items: [created] });
    const { rerender } = render(
      <ShareDialog reportId="report-1" open onClose={vi.fn()} />,
    );

    fireEvent.change(screen.getByLabelText("Recipient email"), {
      target: { value: "fresh.counsel@example.com" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Send verification invitation" }),
    );
    await screen.findByRole("textbox", { name: "Recipient link (read only)" });
    await waitFor(() => expect(apiClientMock).toHaveBeenCalledTimes(3));

    apiClientMock.mockImplementationOnce(() => replacementLoad);
    authToken = "jwt-for-another-user";
    authBoundaryKey = "boundary-user-b-org-b";
    rerender(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    expect(
      screen.queryByRole("textbox", { name: "Recipient link (read only)" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("fresh.counsel@example.com"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Loading recipient ledger…")).toBeInTheDocument();
    expect(apiClientMock).toHaveBeenLastCalledWith(
      "/reports/report-1/share",
      expect.objectContaining({
        token: "jwt-for-another-user",
        signal: expect.any(AbortSignal),
        validate: expect.any(Function),
      }),
    );

    resolveReplacement({ items: [] });
    expect(
      await screen.findByText("No recipient grants yet."),
    ).toBeInTheDocument();
  });

  it("clears the prior report ledger before the next report resolves", async () => {
    let resolveReplacement!: (value: { items: never[] }) => void;
    const replacementLoad = new Promise<{ items: never[] }>((resolve) => {
      resolveReplacement = resolve;
    });
    apiClientMock.mockResolvedValueOnce({ items: [ACTIVE_GRANT] });
    const { rerender } = render(
      <ShareDialog reportId="report-1" open onClose={vi.fn()} />,
    );
    await screen.findByText("named.counsel@example.com");

    apiClientMock.mockImplementationOnce(() => replacementLoad);
    rerender(<ShareDialog reportId="report-2" open onClose={vi.fn()} />);

    expect(
      screen.queryByText("named.counsel@example.com"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Loading recipient ledger…")).toBeInTheDocument();
    expect(apiClientMock).toHaveBeenLastCalledWith(
      "/reports/report-2/share",
      expect.objectContaining({
        token: "jwt",
        signal: expect.any(AbortSignal),
        validate: expect.any(Function),
      }),
    );

    resolveReplacement({ items: [] });
    expect(
      await screen.findByText("No recipient grants yet."),
    ).toBeInTheDocument();
  });

  it("revokes only the selected recipient grant", async () => {
    const onShareStateRefresh = vi.fn();
    apiClientMock
      .mockResolvedValueOnce({ items: [ACTIVE_GRANT] })
      .mockResolvedValueOnce({ status: "revoked" });
    render(
      <ShareDialog
        reportId="report-1"
        open
        onClose={vi.fn()}
        onShareStateRefresh={onShareStateRefresh}
      />,
    );

    fireEvent.click(
      await screen.findByRole("button", { name: "Revoke recipient" }),
    );
    await waitFor(() =>
      expect(scrollIntoViewMock).toHaveBeenCalledWith({
        behavior: "auto",
        block: "center",
      }),
    );
    expect(
      screen.getByRole("button", { name: "Keep recipient access" }),
    ).toHaveFocus();
    expect(screen.getByText(`${ACTIVE_GRANT.recipient_email}.`)).toHaveClass(
      "break-all",
      "[overflow-wrap:anywhere]",
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Keep recipient access" }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Revoke recipient" }),
      ).toHaveFocus(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Revoke recipient" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm revocation" }));
    await waitFor(() => {
      expect(apiClientMock).toHaveBeenCalledWith(
        "/reports/report-1/share/grant-1",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
    expect(
      screen.queryByRole("button", { name: "Revoke recipient" }),
    ).not.toBeInTheDocument();
    expect(onShareStateRefresh).toHaveBeenCalledTimes(1);
  });

  it("reloads authoritative state when invitation outcome is unconfirmed", async () => {
    apiClientMock
      .mockResolvedValueOnce({ items: [ACTIVE_GRANT] })
      .mockRejectedValueOnce(new Error("provider secret: raw failure"));
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);
    await screen.findByText("named.counsel@example.com");
    fireEvent.change(screen.getByLabelText("Recipient email"), {
      target: { value: "new.counsel@example.com" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Send verification invitation" }),
    );

    await waitFor(() => {
      expect(addToast).toHaveBeenCalledWith(
        "Invitation outcome could not be confirmed. The authoritative recipient ledger is being reloaded.",
        "error",
      );
    });
    expect(
      await screen.findByText("named.counsel@example.com"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("new.counsel@example.com"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("textbox", { name: "Recipient link (read only)" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/provider secret|raw failure/i),
    ).not.toBeInTheDocument();
  });

  it("reuses one idempotency key after an unconfirmed create outcome", async () => {
    const created = {
      ...ACTIVE_GRANT,
      id: "grant-recovered",
      recipient_email: "retry.counsel@example.com",
      share_token: "I".repeat(43),
      invitation_status: "provider_accepted",
      replayed: true,
    };
    apiClientMock
      .mockResolvedValueOnce({ items: [ACTIVE_GRANT] })
      .mockRejectedValueOnce(new Error("network outcome unknown"))
      .mockResolvedValueOnce({ items: [ACTIVE_GRANT] })
      .mockResolvedValueOnce(created)
      .mockResolvedValueOnce({ items: [created, ACTIVE_GRANT] });
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);
    await screen.findByText("named.counsel@example.com");
    fireEvent.change(screen.getByLabelText("Recipient email"), {
      target: { value: "retry.counsel@example.com" },
    });

    fireEvent.click(
      screen.getByRole("button", { name: "Send verification invitation" }),
    );
    await waitFor(() => expect(apiClientMock).toHaveBeenCalledTimes(3));
    fireEvent.click(
      screen.getByRole("button", { name: "Send verification invitation" }),
    );
    await waitFor(() => expect(apiClientMock).toHaveBeenCalledTimes(5));

    const postCalls = apiClientMock.mock.calls.filter(
      (call) => call[1]?.method === "POST",
    );
    expect(postCalls).toHaveLength(2);
    expect(postCalls[0][1].headers["Idempotency-Key"]).toBe(
      postCalls[1][1].headers["Idempotency-Key"],
    );
  });

  it("does not fabricate a copyable link for an already-active replay", async () => {
    apiClientMock
      .mockResolvedValueOnce({ items: [] })
      .mockResolvedValueOnce({
        ...ACTIVE_GRANT,
        share_token: null,
        invitation_status: "provider_accepted",
        replayed: true,
      })
      .mockResolvedValueOnce({ items: [ACTIVE_GRANT] });
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Recipient email"), {
      target: { value: ACTIVE_GRANT.recipient_email },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Send verification invitation" }),
    );

    await waitFor(() => {
      expect(addToast).toHaveBeenCalledWith(
        "This invitation was already accepted for delivery",
        "success",
      );
    });
    expect(
      screen.queryByRole("button", { name: "Copy recipient link" }),
    ).not.toBeInTheDocument();
  });

  it("never exposes a malformed one-time share token", async () => {
    apiClientMock
      .mockResolvedValueOnce({ items: [] })
      .mockImplementationOnce(
        (_path: string, options: { validate: (data: unknown) => unknown }) =>
          Promise.resolve(
            options.validate({
              ...VALIDATED_GRANT,
              recipient_email: "new.counsel@example.com",
              share_token: "../recipient/token",
              invitation_status: "provider_accepted",
              replayed: false,
            }),
          ),
      )
      .mockResolvedValueOnce({ items: [] });
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Recipient email"), {
      target: { value: "new.counsel@example.com" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Send verification invitation" }),
    );

    await waitFor(() => expect(apiClientMock).toHaveBeenCalledTimes(3));
    expect(
      screen.queryByRole("textbox", { name: "Recipient link (read only)" }),
    ).not.toBeInTheDocument();
    expect(addToast).toHaveBeenCalledWith(
      "Invitation outcome could not be confirmed. The authoritative recipient ledger is being reloaded.",
      "error",
    );
  });

  it("reloads authoritative state when revocation outcome is unconfirmed", async () => {
    apiClientMock
      .mockResolvedValueOnce({ items: [ACTIVE_GRANT] })
      .mockRejectedValueOnce(new Error("database detail must stay hidden"));
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Revoke recipient" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Confirm revocation" }));

    await waitFor(() => {
      expect(addToast).toHaveBeenCalledWith(
        "Revocation outcome could not be confirmed. The authoritative recipient ledger is being reloaded.",
        "error",
      );
    });
    expect(
      await screen.findByText("named.counsel@example.com"),
    ).toBeInTheDocument();
    expect(screen.getByText(/2 of 25 views/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Revoke recipient" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/database detail/i)).not.toBeInTheDocument();
  });

  it("does not claim revocation when the acknowledgement contract drifts", async () => {
    apiClientMock
      .mockResolvedValueOnce({ items: [ACTIVE_GRANT] })
      .mockImplementationOnce(
        (_path: string, options: { validate: (data: unknown) => unknown }) =>
          Promise.resolve(options.validate({ status: "ok" })),
      )
      .mockResolvedValueOnce({ items: [ACTIVE_GRANT] });
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Revoke recipient" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Confirm revocation" }));

    await waitFor(() => expect(apiClientMock).toHaveBeenCalledTimes(3));
    expect(
      screen.getByRole("button", { name: "Revoke recipient" }),
    ).toBeInTheDocument();
    expect(addToast).toHaveBeenCalledWith(
      "Revocation outcome could not be confirmed. The authoritative recipient ledger is being reloaded.",
      "error",
    );
  });

  it("allows a delivery-pending invitation to be revoked", async () => {
    const pendingGrant = {
      ...ACTIVE_GRANT,
      invitation_sent_at: null,
      status: "delivery_pending",
    };
    apiClientMock
      .mockResolvedValueOnce({ items: [pendingGrant] })
      .mockResolvedValueOnce({ status: "revoked" });
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Revoke recipient" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Confirm revocation" }));
    await waitFor(() => {
      expect(apiClientMock).toHaveBeenCalledWith(
        "/reports/report-1/share/grant-1",
        expect.objectContaining({ method: "DELETE", token: "jwt" }),
      );
    });
  });

  it("lets the sender cancel an unknown delivery before any late recovery", async () => {
    const ambiguousGrant = {
      ...ACTIVE_GRANT,
      invitation_sent_at: null,
      status: "delivery_outcome_unknown",
    };
    apiClientMock
      .mockResolvedValueOnce({ items: [ambiguousGrant] })
      .mockResolvedValueOnce({ status: "revoked" });
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    const cancelAction = await screen.findByRole("button", {
      name: "Cancel unresolved invitation",
    });
    expect(cancelAction).toHaveClass("order-1");
    expect(
      screen.getByRole("button", {
        name: "Show activity for named.counsel@example.com",
      }),
    ).toHaveClass("order-2");
    fireEvent.click(cancelAction);
    expect(
      screen.getByText(/prevents any later provider recovery from activating/i),
    ).toBeInTheDocument();
    expect(screen.getByText(`${ACTIVE_GRANT.recipient_email}.`)).toHaveClass(
      "break-all",
      "[overflow-wrap:anywhere]",
    );
    expect(
      screen.getByRole("button", { name: "Keep recovery active" }),
    ).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Cancel invitation" }));

    await waitFor(() => {
      expect(apiClientMock).toHaveBeenCalledWith(
        "/reports/report-1/share/grant-1",
        expect.objectContaining({ method: "DELETE", token: "jwt" }),
      );
    });
    expect(
      screen.queryByRole("button", { name: "Cancel unresolved invitation" }),
    ).not.toBeInTheDocument();
  });

  it("renders every authoritative delivery terminal distinctly without revoke controls", async () => {
    apiClientMock.mockResolvedValueOnce({
      items: [
        {
          ...ACTIVE_GRANT,
          id: "grant-policy",
          recipient_email: "policy@example.com",
          status: "delivery_cancelled_by_policy",
        },
        {
          ...ACTIVE_GRANT,
          id: "grant-expiry",
          recipient_email: "expiry@example.com",
          status: "delivery_cancelled_expired",
        },
        {
          ...ACTIVE_GRANT,
          id: "grant-retention",
          recipient_email: "retention@example.com",
          status: "delivery_cancelled_retention_expired",
        },
        {
          ...ACTIVE_GRANT,
          id: "grant-alert",
          recipient_email: "alert@example.com",
          status: "delivery_reconciliation_alert",
        },
      ],
    });
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    expect(await screen.findByText("Cancelled by policy")).toBeInTheDocument();
    expect(screen.getByText("Cancelled after expiry")).toBeInTheDocument();
    expect(screen.getByText("Cancelled after retention")).toBeInTheDocument();
    expect(screen.getByText("Operator review required")).toBeInTheDocument();
    expect(
      screen.getByText("Cancelled after workspace policy changed."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Cancelled after its access window expired."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Cancelled when provider lookup retention ended."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Delivery reconciliation requires operator review."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Revoke recipient" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Cancel unresolved invitation" }),
    ).not.toBeInTheDocument();
  });

  it("starts a genuinely new operation after an authoritative provider rejection", async () => {
    const rejected = {
      ...ACTIVE_GRANT,
      id: "grant-rejected",
      recipient_email: "rejected@example.com",
      invitation_sent_at: null,
      status: "delivery_rejected",
    };
    const created = {
      ...ACTIVE_GRANT,
      id: "grant-new-attempt",
      recipient_email: "rejected@example.com",
      share_token: "J".repeat(43),
      invitation_status: "provider_accepted",
    };
    apiClientMock
      .mockResolvedValueOnce({ items: [] })
      .mockRejectedValueOnce(new Error("provider rejected"))
      .mockResolvedValueOnce({ items: [rejected] })
      .mockResolvedValueOnce(created)
      .mockResolvedValueOnce({ items: [created, rejected] });
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Recipient email"), {
      target: { value: "rejected@example.com" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Send verification invitation" }),
    );
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Start new invitation attempt for rejected@example.com",
      }),
    );
    expect(screen.getByLabelText("Recipient email")).toHaveValue(
      "rejected@example.com",
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Send verification invitation" }),
    );

    await waitFor(() => expect(apiClientMock).toHaveBeenCalledTimes(5));
    const postCalls = apiClientMock.mock.calls.filter(
      (call) => call[1]?.method === "POST",
    );
    expect(postCalls).toHaveLength(2);
    expect(postCalls[0][1].headers["Idempotency-Key"]).not.toBe(
      postCalls[1][1].headers["Idempotency-Key"],
    );
  });

  it("uses a new operation key only after unknown delivery is explicitly cancelled", async () => {
    const unknown = {
      ...ACTIVE_GRANT,
      id: "grant-unknown",
      recipient_email: "unknown@example.com",
      invitation_sent_at: null,
      status: "delivery_outcome_unknown",
    };
    const created = {
      ...ACTIVE_GRANT,
      id: "grant-after-cancel",
      recipient_email: "unknown@example.com",
      share_token: "K".repeat(43),
      invitation_status: "provider_accepted",
    };
    apiClientMock
      .mockResolvedValueOnce({ items: [] })
      .mockRejectedValueOnce(new Error("network outcome unknown"))
      .mockResolvedValueOnce({ items: [unknown] })
      .mockResolvedValueOnce({ status: "revoked" })
      .mockResolvedValueOnce(created)
      .mockResolvedValueOnce({ items: [created, unknown] });
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Recipient email"), {
      target: { value: "unknown@example.com" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Send verification invitation" }),
    );
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Cancel unresolved invitation",
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Cancel invitation" }));
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Start new invitation attempt for unknown@example.com",
      }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Send verification invitation" }),
    );

    await waitFor(() => expect(apiClientMock).toHaveBeenCalledTimes(6));
    const postCalls = apiClientMock.mock.calls.filter(
      (call) => call[1]?.method === "POST",
    );
    expect(postCalls).toHaveLength(2);
    expect(postCalls[0][1].headers["Idempotency-Key"]).not.toBe(
      postCalls[1][1].headers["Idempotency-Key"],
    );
  });

  it("reloads expanded activity when the ledger advances unknown to active", async () => {
    const unknown = {
      ...ACTIVE_GRANT,
      invitation_sent_at: null,
      status: "delivery_outcome_unknown",
    };
    apiClientMock
      .mockResolvedValueOnce({ items: [unknown] })
      .mockResolvedValueOnce({
        items: [
          {
            id: "event-unknown",
            event: "delivery_outcome_unknown",
            occurred_at: "2026-07-13T12:01:00.000Z",
            view_number: null,
          },
        ],
      })
      .mockResolvedValueOnce({ items: [ACTIVE_GRANT] })
      .mockResolvedValueOnce({
        items: [
          {
            id: "event-active",
            event: "invitation_sent",
            occurred_at: "2026-07-13T12:02:00.000Z",
            view_number: null,
          },
        ],
      });
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Show activity for named.counsel@example.com",
      }),
    );
    expect(
      await screen.findByText(
        "Delivery outcome unknown; no resubmission attempted",
      ),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Refresh recipient ledger" }),
    );

    expect(
      await screen.findByText("Invitation accepted for delivery"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Delivery outcome unknown; no resubmission attempted"),
    ).not.toBeInTheDocument();
    expect(apiClientMock).toHaveBeenCalledTimes(4);
  });

  it("refreshes activity even when the ledger status remains operator alert", async () => {
    const alert = {
      ...ACTIVE_GRANT,
      invitation_sent_at: null,
      status: "delivery_reconciliation_alert",
    };
    apiClientMock
      .mockResolvedValueOnce({ items: [alert] })
      .mockResolvedValueOnce({ items: [] })
      .mockResolvedValueOnce({
        items: [
          {
            id: "event-alert",
            event: "delivery_reconciliation_alert",
            occurred_at: "2026-07-13T12:04:00.000Z",
            view_number: null,
          },
        ],
      });
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Show activity for named.counsel@example.com",
      }),
    );
    expect(
      await screen.findByText("No recorded recipient activity yet."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Refresh activity" }));

    expect(
      await screen.findByText(
        "Delivery reconciliation requires operator review",
      ),
    ).toBeInTheDocument();
    expect(apiClientMock).toHaveBeenCalledTimes(3);
  });

  it("rejects empty and non-integer maximum-view values before the API", async () => {
    render(<ShareDialog reportId="report-1" open onClose={vi.fn()} />);
    await screen.findByText("named.counsel@example.com");
    fireEvent.change(screen.getByLabelText("Recipient email"), {
      target: { value: "new.counsel@example.com" },
    });

    const maxViewsInput = screen.getByLabelText("Maximum views");
    fireEvent.change(maxViewsInput, { target: { value: "" } });
    expect(
      screen.getByText("Enter a whole number from 1 to 100."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Send verification invitation" }),
    ).toBeDisabled();
    expect(apiClientMock).toHaveBeenCalledTimes(1);

    fireEvent.change(maxViewsInput, { target: { value: "2.5" } });
    expect(
      screen.getByRole("button", { name: "Send verification invitation" }),
    ).toBeDisabled();
    expect(apiClientMock).toHaveBeenCalledTimes(1);
  });
});
