import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import NewAnalysisPage from "@/app/(dashboard)/analyses/new/page";
import { APIError } from "@/lib/api-client";
import { useConfigStore } from "@/stores/config-store";
import { useToastStore } from "@/stores/toast-store";
import {
  clearMarketingCompoundHandoff,
  consumeMarketingCompoundHandoff,
  storeMarketingCompoundHandoff,
} from "@/lib/marketing-compound-handoff";

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  createAnalysis: {
    isPending: false,
    mutateAsync: vi.fn(),
  },
  createPreset: {
    isPending: false,
    mutateAsync: vi.fn(),
  },
  requestCreditCapacity: {
    isPending: false,
    mutateAsync: vi.fn(),
  },
  billingStatus: {
    data: {
      org_id: "org_test",
      plan: "starter",
      stripe_customer_id: "cus_test",
      stripe_subscription_id: "sub_test",
      subscription_status: "active",
      current_period_start: "2026-06-01T00:00:00.000Z",
      current_period_end: "2026-07-01T00:00:00.000Z",
      analyses_used: 2,
      analyses_limit: 10,
      included_analyses_limit: 10,
      purchased_credits_balance: 1,
      purchased_credits_used: 0,
      cancel_at_period_end: false,
    },
    error: null as unknown,
    isFetching: false,
    isLoading: false,
    refetch: vi.fn(),
  },
  reconciliation: {
    data: {
      status: "pending",
      session_id: "cs_test_pending123",
    } as
      | {
          status: "pending";
          session_id: string;
        }
      | {
          status: "applied";
          session_id: string;
          ledger_entry_id: string;
          credit_pack_id: "single_analysis" | "portfolio_5";
          credits_applied: number;
          current_purchased_credits_balance: number;
          applied_at: string;
        },
    error: null as unknown,
    isFetching: false,
    pollingTimedOut: false,
    refetch: vi.fn(),
  },
  token: "token" as string | null,
  principal: {
    data: {
      can_create_analysis: true,
      can_manage_billing: true,
    } as
      | {
          can_create_analysis: boolean;
          can_manage_config?: boolean;
          can_manage_billing: boolean;
        }
      | undefined,
    isFetching: false,
    isLoading: false,
    refetch: vi.fn(),
  },
  searchParams: new URLSearchParams(),
  scrollIntoView: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push }),
  useSearchParams: () => mocks.searchParams,
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => mocks.token,
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  usePrincipalCapabilities: () => mocks.principal,
}));

vi.mock("@/hooks/use-analysis", () => ({
  useCreateAnalysis: () => mocks.createAnalysis,
}));

vi.mock("@/hooks/use-billing", () => ({
  useBillingStatus: () => mocks.billingStatus,
  useRequestCreditCapacity: () => mocks.requestCreditCapacity,
  useCreditPackCheckoutReconciliation: () => mocks.reconciliation,
  isStripeCheckoutSessionId: (value: string | null | undefined) =>
    Boolean(value && /^cs_(?:test|live)_[A-Za-z0-9]+$/u.test(value)),
}));

vi.mock("@/hooks/use-config", () => ({
  useConfigPresets: () => ({ data: [] }),
  useCreatePreset: () => mocks.createPreset,
}));

async function advancePrefilledFlowToReview() {
  await confirmCurrentIdentity();
  fireEvent.click(
    await screen.findByRole("button", { name: /Next: Configure/i }),
  );
  fireEvent.click(await screen.findByRole("button", { name: /Next: Review/i }));
}

async function confirmCurrentIdentity() {
  fireEvent.click(
    await screen.findByRole("button", { name: "Confirm for resolution" }),
  );
}

describe("NewAnalysisPage", () => {
  beforeEach(() => {
    mocks.scrollIntoView.mockReset();
    Object.defineProperty(window.HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: mocks.scrollIntoView,
    });
    mocks.searchParams = new URLSearchParams();
    mocks.token = "token";
    mocks.principal.data = {
      can_create_analysis: true,
      can_manage_config: true,
      can_manage_billing: true,
    };
    mocks.principal.isFetching = false;
    mocks.principal.isLoading = false;
    mocks.principal.refetch.mockReset();
    mocks.billingStatus.data = {
      org_id: "org_test",
      plan: "starter",
      stripe_customer_id: "cus_test",
      stripe_subscription_id: "sub_test",
      subscription_status: "active",
      current_period_start: "2026-06-01T00:00:00.000Z",
      current_period_end: "2026-07-01T00:00:00.000Z",
      analyses_used: 2,
      analyses_limit: 10,
      included_analyses_limit: 10,
      purchased_credits_balance: 1,
      purchased_credits_used: 0,
      cancel_at_period_end: false,
    };
    mocks.billingStatus.error = null;
    mocks.billingStatus.isFetching = false;
    mocks.billingStatus.isLoading = false;
    mocks.billingStatus.refetch.mockReset();
    mocks.billingStatus.refetch.mockResolvedValue({});
    mocks.reconciliation.data = {
      status: "pending",
      session_id: "cs_test_pending123",
    };
    mocks.reconciliation.error = null;
    mocks.reconciliation.isFetching = false;
    mocks.reconciliation.pollingTimedOut = false;
    mocks.reconciliation.refetch.mockReset();
    mocks.push.mockReset();
    mocks.createAnalysis.mutateAsync.mockReset();
    mocks.createAnalysis.mutateAsync.mockResolvedValue({ id: "ana-new" });
    mocks.requestCreditCapacity.isPending = false;
    mocks.requestCreditCapacity.mutateAsync.mockReset();
    mocks.requestCreditCapacity.mutateAsync.mockResolvedValue({
      notified_admins: 1,
      request_id: "11111111-1111-4111-8111-111111111111",
      requested_at: "2026-07-16T12:00:00.000Z",
      status: "sent",
    });
    mocks.createPreset.mutateAsync.mockReset();
    useConfigStore.getState().reset();
    useToastStore.setState({ toasts: [] });
    window.localStorage.clear();
    window.sessionStorage.clear();
    storeMarketingCompoundHandoff("aspirin");
  });

  it("fails closed before rendering the wizard when creation is not authorized", async () => {
    mocks.principal.data = {
      can_create_analysis: false,
      can_manage_billing: false,
    };

    render(<NewAnalysisPage />);

    expect(
      await screen.findByRole("heading", {
        name: "New analysis access restricted",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("navigation", { name: "New analysis progress" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Report Credit consumed"),
    ).not.toBeInTheDocument();
    expect(consumeMarketingCompoundHandoff()).toBe("");
  });

  it("does not mislabel an unavailable capability snapshot as a role denial", async () => {
    mocks.principal.data = undefined;

    render(<NewAnalysisPage />);

    expect(
      await screen.findByRole("heading", {
        name: "New analysis access check unavailable",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", {
        name: "New analysis access restricted",
      }),
    ).not.toBeInTheDocument();
  });

  it("ignores compound query parameters after consuming the private handoff", async () => {
    const { container, rerender } = render(<NewAnalysisPage />);

    expect((await screen.findAllByText("aspirin")).length).toBeGreaterThan(0);
    expect(
      container.querySelector(".praviar-analysis-launch-field"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("new-analysis-mobile-readiness")).toHaveClass(
      "sm:hidden",
    );
    expect(screen.getByTestId("new-analysis-launch-signals")).toHaveClass(
      "hidden",
      "sm:grid",
    );
    expect(
      screen.getByTestId("new-analysis-hero-evidence-summary"),
    ).toHaveClass("hidden", "sm:grid");
    expect(
      screen.getByRole("navigation", { name: "New analysis progress" }),
    ).toBeInTheDocument();
    const progressList = screen
      .getByRole("navigation", { name: "New analysis progress" })
      .querySelector("ol");
    expect(progressList).not.toBeNull();
    expect(progressList!).toHaveClass("grid", "grid-cols-3", "sm:flex");
    expect(
      screen.getByText("Add molecule").closest("[aria-current='step']"),
    ).toBeInTheDocument();
    expect(screen.getByText("Decision supported")).toBeInTheDocument();
    expect(screen.getAllByText("Diligence Screen").length).toBeGreaterThan(0);
    expect(
      screen.getByText("Readiness, Scope, Capacity, Handoff"),
    ).toBeInTheDocument();

    mocks.searchParams = new URLSearchParams("compound=ibuprofen");
    rerender(<NewAnalysisPage />);

    await waitFor(() => {
      expect(screen.getAllByText("aspirin").length).toBeGreaterThan(0);
    });
    expect(screen.queryAllByText("ibuprofen")).toHaveLength(0);
    expect(screen.getByText("Scope brief")).toBeInTheDocument();
    expect(screen.getByText("Edit scope")).toBeInTheDocument();
  });

  it("preserves identity confirmation when returning to the submitted compound", async () => {
    render(<NewAnalysisPage />);

    expect(
      await screen.findByTestId("compound-identity-confirmation-status"),
    ).toHaveTextContent("Review before continuing");

    await confirmCurrentIdentity();
    fireEvent.click(screen.getByRole("button", { name: /Next: Configure/i }));
    fireEvent.click(screen.getByRole("button", { name: /Add molecule/i }));

    expect(
      screen.getByTestId("compound-identity-confirmation-status"),
    ).toHaveTextContent("Confirmed for resolution");

    fireEvent.change(screen.getByPlaceholderText("Name, SMILES, InChI, CAS"), {
      target: { value: "ibuprofen" },
    });

    expect(
      screen.getByTestId("compound-identity-confirmation-status"),
    ).toHaveTextContent("Review before continuing");
  });

  it("hides preset creation when the authoritative role cannot manage configuration", async () => {
    mocks.principal.data = {
      can_create_analysis: true,
      can_manage_config: false,
      can_manage_billing: true,
    };

    render(<NewAnalysisPage />);

    await confirmCurrentIdentity();
    fireEvent.click(screen.getByRole("button", { name: /Next: Configure/i }));

    expect(
      screen.queryByRole("button", { name: "Save as Preset" }),
    ).not.toBeInTheDocument();
  });

  it("keeps launch controls disabled while the secure session is preparing", async () => {
    mocks.token = null;

    render(<NewAnalysisPage />);

    await advancePrefilledFlowToReview();

    expect(screen.getByRole("status")).toHaveTextContent(
      "Preparing secure session",
    );
    const launchButton = screen.getByRole("button", {
      name: "Start Analysis",
    });
    expect(launchButton).toBeDisabled();

    fireEvent.click(launchButton);

    expect(mocks.createAnalysis.mutateAsync).not.toHaveBeenCalled();
  });

  it("blocks launch when report request capacity is depleted", async () => {
    mocks.billingStatus.data = {
      ...mocks.billingStatus.data,
      analyses_used: 10,
      analyses_limit: 10,
      included_analyses_limit: 10,
      purchased_credits_balance: 0,
    };

    render(<NewAnalysisPage />);

    await advancePrefilledFlowToReview();

    await waitFor(() => {
      expect(mocks.scrollIntoView).toHaveBeenCalledWith({ block: "start" });
    });

    expect(screen.getByRole("status")).toHaveTextContent(
      "No FTO report request capacity remains",
    );
    expect(
      screen.getByRole("link", { name: /Buy 1 Report Credit/i }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("capacity-credit-action")).toContainElement(
      screen.getByRole("link", { name: /Buy 1 Report Credit/i }),
    );
    expect(
      screen.getAllByText("Report Credits required before launch"),
    ).toHaveLength(1);
    expect(
      screen.getByText(
        "Start Analysis remains disabled until report-request capacity is available.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Resolve report capacity"),
    ).not.toBeInTheDocument();
    const creditHref = screen
      .getByRole("link", { name: /Buy 1 Report Credit/i })
      .getAttribute("href");
    expect(creditHref).toBeTruthy();
    const creditUrl = new URL(creditHref!, "http://localhost");
    expect(creditUrl.pathname).toBe("/billing");
    expect(creditUrl.searchParams.get("intent")).toBe("credits");
    expect(creditUrl.searchParams.get("pack")).toBe("single_analysis");
    expect(creditUrl.searchParams.get("source")).toBe("launch");
    const returnTo = creditUrl.searchParams.get("return_to");
    expect(returnTo).toMatch(
      /^\/analyses\/new\?resume=credit_checkout&launch_draft_id=ld_[A-Za-z0-9_-]+$/,
    );
    expect(returnTo).not.toContain("compound=");
    expect(creditHref).not.toContain("aspirin");
    const launchButton = screen.getByRole("button", {
      name: "Start Analysis",
    });
    expect(launchButton).toBeDisabled();

    fireEvent.click(launchButton);

    expect(mocks.createAnalysis.mutateAsync).not.toHaveBeenCalled();
  });

  it("lets non-admin creators request depleted capacity from workspace admins", async () => {
    mocks.principal.data = {
      can_create_analysis: true,
      can_manage_billing: false,
    };
    mocks.billingStatus.data = {
      ...mocks.billingStatus.data,
      analyses_used: 10,
      analyses_limit: 10,
      included_analyses_limit: 10,
      purchased_credits_balance: 0,
    };

    render(<NewAnalysisPage />);

    await advancePrefilledFlowToReview();

    expect(screen.getByRole("status")).toHaveTextContent(
      "Ask a workspace administrator to add Report Credits",
    );
    expect(
      screen.queryByRole("link", { name: /Buy 1 Report Credit/i }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Request Report Credits" }),
    );

    await waitFor(() => {
      expect(mocks.requestCreditCapacity.mutateAsync).toHaveBeenCalledWith({
        requested_reports: 1,
        source: "analysis_launch",
      });
    });
    expect(document.body).not.toHaveTextContent("mailto:");
  });

  it("explains the credit-request cooldown instead of blaming the connection", async () => {
    mocks.principal.data = {
      can_create_analysis: true,
      can_manage_billing: false,
    };
    mocks.billingStatus.data = {
      ...mocks.billingStatus.data,
      analyses_used: 10,
      analyses_limit: 10,
      included_analyses_limit: 10,
      purchased_credits_balance: 0,
    };
    mocks.requestCreditCapacity.mutateAsync.mockRejectedValueOnce(
      new APIError(429, "Rate limit exceeded"),
    );

    render(<NewAnalysisPage />);
    await advancePrefilledFlowToReview();
    fireEvent.click(
      screen.getByRole("button", { name: "Request Report Credits" }),
    );

    await waitFor(() => {
      expect(useToastStore.getState().toasts.at(-1)).toMatchObject({
        message:
          "Report Credit requests are limited to three per hour. Wait for the cooldown before sending another request.",
        type: "error",
      });
    });
  });

  it("allows launch when consumed purchased credits leave effective capacity", async () => {
    mocks.billingStatus.data = {
      ...mocks.billingStatus.data,
      analyses_used: 30,
      analyses_limit: 32,
      included_analyses_limit: 25,
      purchased_credits_balance: 1,
      purchased_credits_used: 6,
    };

    render(<NewAnalysisPage />);

    await advancePrefilledFlowToReview();

    expect(
      screen.getAllByText("2 report requests available").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        "1 included, 1 credit-backed remaining; 1 unused purchased",
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByRole("button", { name: "Start Analysis" }),
    ).toBeEnabled();
    expect(
      screen.queryByText("No FTO report request capacity remains"),
    ).not.toBeInTheDocument();
  });

  it("uses purchased credits as the only runway after a lapsed allowance downgrade", async () => {
    mocks.billingStatus.data = {
      ...mocks.billingStatus.data,
      subscription_status: "past_due",
      analyses_used: 5,
      analyses_limit: 7,
      included_analyses_limit: 3,
      purchased_credits_balance: 2,
      purchased_credits_used: 0,
    };

    render(<NewAnalysisPage />);

    await advancePrefilledFlowToReview();

    expect(
      screen.getAllByText("2 report requests available").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        "0 included, 2 credit-backed remaining; 2 unused purchased",
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByRole("button", { name: "Start Analysis" }),
    ).toBeEnabled();
    expect(
      screen.queryByText("No FTO report request capacity remains"),
    ).not.toBeInTheDocument();
  });

  it("blocks commercial launch scopes until core product context is explicit", async () => {
    render(<NewAnalysisPage />);

    fireEvent.click(await screen.findByText("Edit scope"));
    fireEvent.click(
      screen.getByRole("checkbox", { name: /Commercial launch/i }),
    );

    await advancePrefilledFlowToReview();

    expect(screen.getByRole("status")).toHaveTextContent(
      "commercial launch scopes require core product context",
    );
    expect(screen.getByText("Launch blocked:")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Start Analysis" }),
    ).toBeDisabled();
    expect(mocks.createAnalysis.mutateAsync).not.toHaveBeenCalled();
  });

  it("acknowledges credit checkout resume state on return to launch", async () => {
    mocks.searchParams = new URLSearchParams(
      "resume=credit_checkout&checkout=success&credit_pack=portfolio_5&intent=credits&checkout_session_id=cs_test_pending123",
    );
    clearMarketingCompoundHandoff();

    render(<NewAnalysisPage />);

    expect(
      await screen.findByText("Checkout returned; Report Credits pending"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/return URL alone does not verify payment/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Awaiting input")).toBeInTheDocument();
  });

  it("retries launch-capacity refresh after an applied ledger refetch failure", async () => {
    mocks.billingStatus.data = {
      ...mocks.billingStatus.data,
      analyses_used: 10,
      analyses_limit: 10,
      included_analyses_limit: 10,
      purchased_credits_balance: 0,
    };
    mocks.billingStatus.error = new Error("temporary billing refresh failure");
    mocks.reconciliation.data = {
      status: "applied",
      session_id: "cs_test_applied123",
      ledger_entry_id: "11111111-1111-4111-8111-111111111111",
      credit_pack_id: "single_analysis",
      credits_applied: 1,
      current_purchased_credits_balance: 1,
      applied_at: "2026-07-16T08:00:00.000Z",
    };
    mocks.searchParams = new URLSearchParams(
      "compound=aspirin&resume=credit_checkout&checkout=success" +
        "&intent=credits&checkout_session_id=cs_test_applied123",
    );

    render(<NewAnalysisPage />);

    expect(
      await screen.findByText(
        "Ledger confirmed; launch capacity refresh failed.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Retry launch capacity" }),
    );
    expect(mocks.billingStatus.refetch).toHaveBeenCalledOnce();
  });

  it("does not claim a purchase outcome from a cancelled return URL", async () => {
    mocks.searchParams = new URLSearchParams(
      "compound=aspirin&resume=credit_checkout&checkout=cancelled&intent=credits",
    );

    render(<NewAnalysisPage />);

    expect(
      await screen.findByText("Report Credits checkout flow cancelled"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/No Report Credit purchase is assumed/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("No Report Credits were purchased."),
    ).not.toBeInTheDocument();
  });

  it("restores the reviewed launch packet after credit checkout", async () => {
    mocks.billingStatus.data = {
      ...mocks.billingStatus.data,
      analyses_used: 10,
      analyses_limit: 10,
      included_analyses_limit: 10,
      purchased_credits_balance: 0,
    };

    const { rerender } = render(<NewAnalysisPage />);

    fireEvent.click(await screen.findByText("Edit scope"));
    fireEvent.click(screen.getByRole("radio", { name: "Clinical" }));
    fireEvent.click(
      screen.getByRole("checkbox", { name: /Commercial launch/i }),
    );
    fireEvent.change(screen.getByLabelText("Product or program"), {
      target: { value: "PRV-142 oral tablet" },
    });
    fireEvent.change(screen.getByLabelText("Dosage form"), {
      target: { value: "Film-coated tablet" },
    });
    fireEvent.change(screen.getByLabelText("Route"), {
      target: { value: "Oral" },
    });
    fireEvent.change(screen.getByLabelText("Strength"), {
      target: { value: "200 mg" },
    });
    fireEvent.change(screen.getByLabelText("Indication"), {
      target: { value: "Pain" },
    });
    fireEvent.change(screen.getByLabelText("Commercial action"), {
      target: { value: "US launch diligence before term sheet" },
    });
    fireEvent.change(screen.getByLabelText("Commercial territories"), {
      target: { value: "US, EP" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add act" }));
    fireEvent.change(screen.getByLabelText("Act 1 jurisdiction"), {
      target: { value: "US" },
    });
    fireEvent.change(screen.getByLabelText("Act 1 start date"), {
      target: { value: "2027-08-01" },
    });
    fireEvent.change(screen.getByLabelText("Act 1 actor"), {
      target: { value: "Praviar Therapeutics Ltd" },
    });
    fireEvent.change(screen.getByLabelText("Act 1 instrumentality"), {
      target: { value: "PRV-142 oral tablet" },
    });

    await advancePrefilledFlowToReview();

    const creditHref = screen
      .getByRole("link", { name: /Buy 1 Report Credit/i })
      .getAttribute("href");
    expect(creditHref).toBeTruthy();
    const creditUrl = new URL(creditHref!, "http://localhost");
    const returnTo = creditUrl.searchParams.get("return_to");
    expect(returnTo).toBeTruthy();
    const returnQuery = returnTo!.split("?")[1];
    const returnParams = new URLSearchParams(returnQuery);
    const launchDraftId = returnParams.get("launch_draft_id");

    await waitFor(() => {
      expect(
        window.sessionStorage.getItem(
          `praviar:analysis-launch-draft:${launchDraftId}`,
        ),
      ).toContain("PRV-142 oral tablet");
    });

    mocks.billingStatus.data = {
      ...mocks.billingStatus.data,
      analyses_limit: 11,
      purchased_credits_balance: 1,
    };
    mocks.reconciliation.data = {
      status: "applied",
      session_id: "cs_test_applied123",
      ledger_entry_id: "11111111-1111-4111-8111-111111111111",
      credit_pack_id: "single_analysis",
      credits_applied: 1,
      current_purchased_credits_balance: 1,
      applied_at: "2026-07-16T08:00:00.000Z",
    };
    mocks.searchParams = new URLSearchParams(
      `${returnQuery}&checkout=success&credit_pack=single_analysis&intent=credits&checkout_session_id=cs_test_applied123`,
    );
    rerender(<NewAnalysisPage />);

    expect(
      await screen.findByText("1 Report Credit applied"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/reviewed launch packet remains restored/i),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("Small Molecule; Clinical").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Commercial Launch")).toBeInTheDocument();
    expect(screen.getAllByText("PRV-142 oral tablet").length).toBeGreaterThan(
      0,
    );

    fireEvent.click(screen.getByRole("button", { name: "Start Analysis" }));

    await waitFor(() => {
      expect(mocks.createAnalysis.mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          compound_input: "aspirin",
          development_stage: "clinical",
          intended_actions: ["diligence_screen", "commercial_launch"],
          product_context: expect.objectContaining({
            product_name: "PRV-142 oral tablet",
            commercial_action: "US launch diligence before term sheet",
            commercial_territories: ["US", "EP"],
          }),
        }),
      );
    });
  }, 20_000);

  it("rejects a checkout launch draft after the auth or organization boundary changes", async () => {
    mocks.billingStatus.data = {
      ...mocks.billingStatus.data,
      analyses_used: 10,
      analyses_limit: 10,
      included_analyses_limit: 10,
      purchased_credits_balance: 0,
    };

    const { rerender } = render(<NewAnalysisPage />);
    await advancePrefilledFlowToReview();

    const creditHref = screen
      .getByRole("link", { name: /Buy 1 Report Credit/i })
      .getAttribute("href");
    expect(creditHref).toBeTruthy();
    const creditUrl = new URL(creditHref!, "http://localhost");
    const returnTo = creditUrl.searchParams.get("return_to");
    expect(returnTo).toBeTruthy();
    const returnQuery = returnTo!.split("?")[1];

    await waitFor(() => {
      expect(window.sessionStorage.length).toBeGreaterThan(0);
    });

    mocks.token = "different-organization-token";
    mocks.searchParams = new URLSearchParams(
      `${returnQuery}&checkout=success&credit_pack=single_analysis&intent=credits&checkout_session_id=cs_test_pending123`,
    );
    rerender(<NewAnalysisPage />);

    expect(
      await screen.findByText("Checkout returned; Report Credits pending"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/reviewed launch packet remains restored/i),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Awaiting input")).toBeInTheDocument();
  });

  it("blocks malformed prefilled identifiers before configuration", async () => {
    mocks.searchParams = new URLSearchParams("compound=110-15-7");
    clearMarketingCompoundHandoff();
    storeMarketingCompoundHandoff("110-15-7");

    render(<NewAnalysisPage />);

    expect(
      (await screen.findAllByText("CAS checksum needs review")).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        "The CAS checksum does not match. Check the digits before using a Report Credit.",
      ).length,
    ).toBeGreaterThan(0);

    const nextButton = screen.getByRole("button", {
      name: /Next: Configure/i,
    });
    expect(nextButton).toBeDisabled();

    fireEvent.click(nextButton);

    expect(screen.queryByText("Evidence Plan")).not.toBeInTheDocument();
    expect(mocks.createAnalysis.mutateAsync).not.toHaveBeenCalled();
  });

  it("keeps launch disabled while report request capacity is loading", async () => {
    mocks.billingStatus.data = undefined as never;
    mocks.billingStatus.isLoading = true;

    render(<NewAnalysisPage />);

    await advancePrefilledFlowToReview();

    expect(screen.getByRole("status")).toHaveTextContent(
      "Checking FTO report request capacity",
    );
    const launchButton = screen.getByRole("button", {
      name: "Start Analysis",
    });
    expect(launchButton).toBeDisabled();

    fireEvent.click(launchButton);

    expect(mocks.createAnalysis.mutateAsync).not.toHaveBeenCalled();
  });

  it("blocks launch and hides cached capacity when billing access is revoked", async () => {
    mocks.billingStatus.error = new APIError(403, "Forbidden");
    mocks.billingStatus.data = {
      ...mocks.billingStatus.data,
      analyses_used: 2,
      analyses_limit: 10,
      included_analyses_limit: 10,
      purchased_credits_balance: 1,
    };

    render(<NewAnalysisPage />);

    await advancePrefilledFlowToReview();

    expect(screen.getByRole("status")).toHaveTextContent(
      "FTO report request capacity access is restricted",
    );
    expect(screen.getAllByText("Access restricted").length).toBeGreaterThan(0);
    expect(
      screen.getByText(
        "Report Credit capacity is hidden until billing access is restored.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("8 report requests available"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/1 unused purchased/i)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Buy 1 Report Credit/i }),
    ).not.toBeInTheDocument();

    const launchButton = screen.getByRole("button", {
      name: "Start Analysis",
    });
    expect(launchButton).toBeDisabled();
    fireEvent.click(launchButton);

    expect(mocks.createAnalysis.mutateAsync).not.toHaveBeenCalled();
  });

  it("blocks review until at least one patent source is enabled", async () => {
    useConfigStore.getState().setConfig({
      enablePubchem: false,
      enableBigquery: false,
      enableSurechembl: false,
      enablePatcid: false,
    });

    render(<NewAnalysisPage />);

    expect(
      (await screen.findAllByText("Enable at least one patent source")).length,
    ).toBeGreaterThan(0);

    await confirmCurrentIdentity();
    fireEvent.click(
      await screen.findByRole("button", { name: /Next: Configure/i }),
    );
    const reviewButton = screen.getByRole("button", { name: /Next: Review/i });
    expect(reviewButton).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Enable at least one patent source.",
    );

    fireEvent.click(reviewButton);

    expect(mocks.createAnalysis.mutateAsync).not.toHaveBeenCalled();
    expect(screen.queryByText("Confirm & Launch")).not.toBeInTheDocument();
  });

  it("keeps suggested matter scope synchronized with typed compound context", async () => {
    mocks.searchParams = new URLSearchParams("");

    render(<NewAnalysisPage />);

    fireEvent.change(
      await screen.findByPlaceholderText("Name, SMILES, InChI, CAS"),
      {
        target: { value: "oral dosage formulation with excipient blend" },
      },
    );
    await confirmCurrentIdentity();
    fireEvent.click(screen.getByRole("button", { name: /Next: Configure/i }));
    fireEvent.click(
      await screen.findByRole("button", { name: /Next: Review/i }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Start Analysis" }));

    await waitFor(() => {
      expect(mocks.createAnalysis.mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          compound_input: "oral dosage formulation with excipient blend",
          asset_type_hint: "formulation",
          intended_actions: ["formulation_review", "diligence_screen"],
        }),
      );
    });
  });

  it("preserves explicit matter scope edits when typed context changes", async () => {
    mocks.searchParams = new URLSearchParams("");

    render(<NewAnalysisPage />);

    fireEvent.click(screen.getByText("Edit scope"));
    fireEvent.click(screen.getByRole("radio", { name: /Process\/synthesis/i }));
    fireEvent.change(
      await screen.findByPlaceholderText("Name, SMILES, InChI, CAS"),
      {
        target: { value: "oral dosage formulation with excipient blend" },
      },
    );
    await confirmCurrentIdentity();
    fireEvent.click(screen.getByRole("button", { name: /Next: Configure/i }));
    fireEvent.click(
      await screen.findByRole("button", { name: /Next: Review/i }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Start Analysis" }));

    await waitFor(() => {
      expect(mocks.createAnalysis.mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          compound_input: "oral dosage formulation with excipient blend",
          asset_type_hint: "process_or_synthesis",
          intended_actions: ["diligence_screen"],
        }),
      );
    });
  });

  it("submits confirmed matter scope fields with the launch request", async () => {
    mocks.searchParams = new URLSearchParams("");

    render(<NewAnalysisPage />);

    fireEvent.change(
      await screen.findByPlaceholderText("Name, SMILES, InChI, CAS"),
      {
        target: { value: "oral dosage formulation" },
      },
    );
    fireEvent.click(screen.getByText("Edit scope"));
    fireEvent.click(screen.getByRole("button", { name: "Apply suggestion" }));
    fireEvent.click(screen.getByRole("radio", { name: "Clinical" }));
    fireEvent.click(
      screen.getByRole("checkbox", { name: /Commercial launch/i }),
    );
    fireEvent.change(screen.getByLabelText("Product or program"), {
      target: { value: "PRV-142 oral tablet" },
    });
    fireEvent.change(screen.getByLabelText("Dosage form"), {
      target: { value: "Film-coated tablet" },
    });
    fireEvent.change(screen.getByLabelText("Route"), {
      target: { value: "Oral" },
    });
    fireEvent.change(screen.getByLabelText("Strength"), {
      target: { value: "200 mg" },
    });
    fireEvent.change(screen.getByLabelText("Salt / polymorph"), {
      target: { value: "Unknown" },
    });
    fireEvent.change(screen.getByLabelText("Key excipients"), {
      target: { value: "Lactose, HPMC" },
    });
    fireEvent.change(screen.getByLabelText("Indication"), {
      target: { value: "Pain" },
    });
    fireEvent.change(screen.getByLabelText("Commercial action"), {
      target: { value: "US launch diligence before term sheet" },
    });
    fireEvent.change(screen.getByLabelText("Commercial territories"), {
      target: { value: "US, EP" },
    });
    fireEvent.change(screen.getByLabelText("Known patents / assignees"), {
      target: { value: "US12345678, Fictional Meridian" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add act" }));
    fireEvent.change(screen.getByLabelText("Act 1 jurisdiction"), {
      target: { value: "US" },
    });
    fireEvent.change(screen.getByLabelText("Act 1 start date"), {
      target: { value: "2027-08-01" },
    });
    fireEvent.change(screen.getByLabelText("Act 1 actor"), {
      target: { value: "Praviar Therapeutics Ltd" },
    });
    fireEvent.change(screen.getByLabelText("Act 1 instrumentality"), {
      target: { value: "PRV-142 oral tablet" },
    });
    await confirmCurrentIdentity();
    fireEvent.click(screen.getByRole("button", { name: /Next: Configure/i }));
    fireEvent.click(
      await screen.findByRole("button", { name: /Next: Review/i }),
    );

    expect(screen.getAllByText("Formulation; Clinical").length).toBeGreaterThan(
      0,
    );
    expect(screen.getByText("Commercial Launch")).toBeInTheDocument();
    expect(screen.getByText("Product profile")).toBeInTheDocument();
    expect(screen.getAllByText("PRV-142 oral tablet").length).toBeGreaterThan(
      0,
    );
    expect(screen.getAllByText("Film-coated tablet").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Start Analysis" }));

    await waitFor(() => {
      expect(mocks.createAnalysis.mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          compound_input: "oral dosage formulation",
          asset_type_hint: "formulation",
          development_stage: "clinical",
          intended_actions: [
            "formulation_review",
            "diligence_screen",
            "commercial_launch",
          ],
          product_context: {
            product_name: "PRV-142 oral tablet",
            dosage_form: "Film-coated tablet",
            route_of_administration: "Oral",
            strength: "200 mg",
            salt_polymorph_form: "Unknown",
            key_excipients: ["Lactose", "HPMC"],
            indication: "Pain",
            commercial_action: "US launch diligence before term sheet",
            commercial_territories: ["US", "EP"],
            accused_acts: [
              {
                act: "sale",
                actor: "Praviar Therapeutics Ltd",
                instrumentality: "PRV-142 oral tablet",
                jurisdiction: "US",
                liability_theory: "direct",
                purpose: "commercial",
                regulatory_path: "none",
                start_date: "2027-08-01",
                status: "planned",
              },
            ],
            known_patents_or_assignees: ["US12345678", "Fictional Meridian"],
          },
        }),
      );
    });
    expect(mocks.push).toHaveBeenCalledWith("/analyses/ana-new");
  }, 10_000);

  it("guards against rapid duplicate launches and shows inline launch failures", async () => {
    mocks.createAnalysis.mutateAsync.mockReturnValue(new Promise(() => {}));

    const { unmount } = render(<NewAnalysisPage />);

    await advancePrefilledFlowToReview();
    const launchButton = screen.getByRole("button", {
      name: "Start Analysis",
    });

    fireEvent.click(launchButton);
    fireEvent.click(launchButton);

    expect(mocks.createAnalysis.mutateAsync).toHaveBeenCalledTimes(1);

    mocks.createAnalysis.mutateAsync.mockRejectedValueOnce(
      new Error("postgres://secret-token launch failed"),
    );
    unmount();
    window.localStorage.clear();
    window.sessionStorage.clear();
    storeMarketingCompoundHandoff("metformin");
    render(<NewAnalysisPage />);

    await advancePrefilledFlowToReview();
    fireEvent.click(screen.getByRole("button", { name: "Start Analysis" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Launch outcome could not be confirmed. A Report Credit may have been reserved.",
      );
    });
    expect(
      screen.getByRole("button", { name: "Reconcile exact launch" }),
    ).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("postgres://secret-token");
  });

  it("reuses the durable idempotency key after 30 minutes and tab storage loss", async () => {
    mocks.createAnalysis.mutateAsync
      .mockRejectedValueOnce(new Error("network outcome unknown"))
      .mockResolvedValueOnce({ id: "ana-reconciled" });

    const firstRender = render(<NewAnalysisPage />);

    await advancePrefilledFlowToReview();
    fireEvent.click(screen.getByRole("button", { name: "Start Analysis" }));
    await screen.findByRole("button", { name: "Reconcile exact launch" });

    const firstRequest = mocks.createAnalysis.mutateAsync.mock.calls[0][0];
    expect(firstRequest.client_idempotency_key).toMatch(/^[!-~]{16,128}$/u);

    const draftKey = Array.from(
      { length: window.localStorage.length },
      (_, index) => window.localStorage.key(index),
    ).find(
      (key) =>
        key?.startsWith("praviar:analysis-launch-draft:ld_") &&
        !key.includes(":active:"),
    );
    expect(draftKey).toBeTruthy();
    const durableDraft = JSON.parse(
      window.localStorage.getItem(draftKey!)!,
    ) as Record<string, unknown>;
    durableDraft.createdAt = new Date(
      Date.now() - 31 * 60 * 1000,
    ).toISOString();
    window.localStorage.setItem(draftKey!, JSON.stringify(durableDraft));

    firstRender.unmount();
    window.sessionStorage.clear();
    render(<NewAnalysisPage />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Start Analysis" }),
    );

    await waitFor(() => {
      expect(mocks.createAnalysis.mutateAsync).toHaveBeenCalledTimes(2);
    });
    expect(
      mocks.createAnalysis.mutateAsync.mock.calls[1][0].client_idempotency_key,
    ).toBe(firstRequest.client_idempotency_key);
    expect(mocks.push).toHaveBeenCalledWith("/analyses/ana-reconciled");
  });

  it("keeps the launch draft and sends buyers to credits when server capacity is exhausted", async () => {
    mocks.createAnalysis.mutateAsync.mockRejectedValueOnce(
      new APIError(429, "No report capacity remains for org_test", undefined, {
        typeUri: "https://problems.praviar.invalid/analysis-capacity-exhausted",
      }),
    );

    render(<NewAnalysisPage />);

    await advancePrefilledFlowToReview();
    fireEvent.click(screen.getByRole("button", { name: "Start Analysis" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Launch capacity or request rate changed. Reconcile the analysis library",
      );
    });

    expect(mocks.billingStatus.refetch).toHaveBeenCalledOnce();
    const creditHref = screen
      .getByRole("link", { name: "Review Report Credits" })
      .getAttribute("href");
    expect(creditHref).toBeTruthy();
    const creditUrl = new URL(creditHref!, "http://localhost");
    expect(creditUrl.pathname).toBe("/billing");
    expect(creditUrl.searchParams.get("intent")).toBe("credits");
    expect(creditUrl.searchParams.get("pack")).toBe("single_analysis");
    const returnTo = creditUrl.searchParams.get("return_to");
    expect(returnTo).toMatch(
      /^\/analyses\/new\?resume=credit_checkout&launch_draft_id=ld_[A-Za-z0-9_-]+$/,
    );
    const launchDraftId = new URLSearchParams(returnTo!.split("?")[1]).get(
      "launch_draft_id",
    );
    expect(
      window.sessionStorage.getItem(
        `praviar:analysis-launch-draft:${launchDraftId}`,
      ),
    ).toContain('"compoundInput":"aspirin"');
    expect(mocks.push).not.toHaveBeenCalled();
  });

  it("keeps rate-limit cooldowns out of the Report Credit purchase funnel", async () => {
    mocks.createAnalysis.mutateAsync.mockRejectedValueOnce(
      new APIError(429, "Analysis rate limit exceeded", undefined, {
        typeUri: "https://problems.praviar.invalid/rate-limit-exceeded",
      }),
    );

    render(<NewAnalysisPage />);

    await advancePrefilledFlowToReview();
    fireEvent.click(screen.getByRole("button", { name: "Start Analysis" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "No additional Report Credit is needed",
      );
    });
    expect(
      screen.getByRole("button", { name: "Retry exact launch" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Review Report Credits" }),
    ).not.toBeInTheDocument();
    expect(mocks.requestCreditCapacity.mutateAsync).not.toHaveBeenCalled();
    expect(mocks.billingStatus.refetch).not.toHaveBeenCalled();
  });

  it("requests admin capacity in-app after a non-admin launch race returns 429", async () => {
    mocks.principal.data = {
      can_create_analysis: true,
      can_manage_config: false,
      can_manage_billing: false,
    };
    mocks.createAnalysis.mutateAsync.mockRejectedValueOnce(
      new APIError(429, "No report capacity remains for org_test", undefined, {
        typeUri: "https://problems.praviar.invalid/analysis-capacity-exhausted",
      }),
    );

    render(<NewAnalysisPage />);

    await advancePrefilledFlowToReview();
    fireEvent.click(screen.getByRole("button", { name: "Start Analysis" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "ask a workspace administrator to refresh Report Credit capacity",
      );
    });
    expect(
      screen.queryByRole("link", { name: "Buy 1 Report Credit" }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Request Report Credits" }),
    );
    await waitFor(() => {
      expect(mocks.requestCreditCapacity.mutateAsync).toHaveBeenCalledWith({
        requested_reports: 1,
        source: "launch_retry",
      });
    });
  });

  it("explains dispatch failures without sending buyers to billing", async () => {
    mocks.createAnalysis.mutateAsync.mockRejectedValueOnce(
      new APIError(503, "Dispatch unavailable"),
    );

    render(<NewAnalysisPage />);

    await advancePrefilledFlowToReview();
    fireEvent.click(screen.getByRole("button", { name: "Start Analysis" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Launch outcome could not be confirmed after dispatch handoff.",
      );
    });

    expect(
      screen.queryByRole("link", { name: "Buy 1 Report Credit" }),
    ).not.toBeInTheDocument();
    expect(mocks.billingStatus.refetch).toHaveBeenCalledOnce();
    expect(
      screen.getByRole("button", { name: "Reconcile exact launch" }),
    ).toBeInTheDocument();
    expect(mocks.push).not.toHaveBeenCalled();
  });
});
