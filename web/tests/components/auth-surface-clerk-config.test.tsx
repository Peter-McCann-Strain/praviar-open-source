import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DEFAULT_AUTH_RETURN_PATH,
  resolveExplicitAuthReturnPath,
  resolveAuthReturnPath,
} from "@/components/auth/auth-redirects";
import { resolveAuthCheckoutIntent } from "@/components/auth/auth-checkout-intent";

const clerkPublishableKey = (mode: "test" | "live", payload: string) =>
  ["pk", mode, payload].join("_");

const VALID_TEST_CLERK_KEY = clerkPublishableKey(
  "test",
  [
    "Zm9v",
    "LWJh",
    "ci0x",
    "My5j",
    "bGVy",
    "ay5h",
    "Y2Nv",
    "dW50",
    "cy5k",
    "ZXYk",
  ].join(""),
);

const authNavigation = vi.hoisted(() => ({
  searchParams: "",
}));

const clerkRuntime = vi.hoisted(() => ({
  state: "loaded" as "loading" | "loaded" | "degraded" | "failed",
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useSearchParams: () => new URLSearchParams(authNavigation.searchParams),
}));

function mockClerk(orgRole = "org:admin") {
  vi.doMock("@clerk/nextjs", () => ({
    ClerkLoading: ({ children }: { children: React.ReactNode }) =>
      clerkRuntime.state === "loading" ? children : null,
    ClerkLoaded: ({ children }: { children: React.ReactNode }) =>
      clerkRuntime.state === "loaded" || clerkRuntime.state === "degraded"
        ? children
        : null,
    ClerkDegraded: ({ children }: { children: React.ReactNode }) =>
      clerkRuntime.state === "degraded" ? children : null,
    ClerkFailed: ({ children }: { children: React.ReactNode }) =>
      clerkRuntime.state === "failed" ? children : null,
    useAuth: () => ({
      isLoaded: true,
      orgRole,
    }),
    SignIn: () => <div data-testid="clerk-sign-in" />,
    SignUp: () => <div data-testid="clerk-sign-up" />,
    AuthenticateWithRedirectCallback: () => (
      <div data-testid="clerk-sso-callback" />
    ),
    UserButton: () => <div data-testid="clerk-user-button" />,
  }));
}

function mockSidebarApplicationRole(
  role: "admin" | "attorney" | "scientist" | "client",
) {
  vi.doMock("@/hooks/use-auth-token", () => ({
    useAuthToken: () => "test-token",
  }));
  vi.doMock("@/hooks/use-principal-capabilities", () => ({
    usePrincipalCapabilities: () => ({
      data: { role },
      isLoading: false,
      isError: false,
    }),
  }));
}

function mockDynamic() {
  const dynamicSpy = vi.fn();
  vi.doMock("next/dynamic", () => ({
    default: (loader: unknown, options: unknown) => {
      dynamicSpy(loader, options);
      return function DynamicClerkMock(props: {
        appearance?: { elements?: Record<string, string> };
        fallbackRedirectUrl?: string;
        forceRedirectUrl?: string;
        signInFallbackRedirectUrl?: string;
        signInForceRedirectUrl?: string;
        signUpFallbackRedirectUrl?: string;
        signUpForceRedirectUrl?: string;
        hidePersonal?: boolean;
        afterSelectOrganizationUrl?: string;
      }) {
        const elements = props.appearance?.elements ?? {};

        return (
          <div
            data-testid="clerk-widget"
            data-fallback-redirect-url={props.fallbackRedirectUrl ?? ""}
            data-force-redirect-url={props.forceRedirectUrl ?? ""}
            data-sign-in-fallback-redirect-url={
              props.signInFallbackRedirectUrl ?? ""
            }
            data-sign-in-force-redirect-url={props.signInForceRedirectUrl ?? ""}
            data-sign-up-fallback-redirect-url={
              props.signUpFallbackRedirectUrl ?? ""
            }
            data-sign-up-force-redirect-url={props.signUpForceRedirectUrl ?? ""}
            data-hide-personal={String(props.hidePersonal ?? false)}
            data-after-select-organization-url={
              props.afterSelectOrganizationUrl ?? ""
            }
            data-form-button-primary={elements.formButtonPrimary ?? ""}
            data-form-field-input={elements.formFieldInput ?? ""}
            data-social-buttons-block-button={
              elements.socialButtonsBlockButton ?? ""
            }
          />
        );
      };
    },
  }));
  return dynamicSpy;
}

async function loadAuthPage(route: "sign-in" | "sign-up") {
  if (route === "sign-in") {
    return (await import("@/app/(auth)/sign-in/page")).default;
  }
  return (await import("@/app/(auth)/sign-up/page")).default;
}

async function loadAuthCallback(route: "sign-in" | "sign-up") {
  if (route === "sign-in") {
    return (await import("@/app/(auth)/sign-in/sso-callback/page")).default;
  }
  return (await import("@/app/(auth)/sign-up/sso-callback/page")).default;
}

afterEach(() => {
  authNavigation.searchParams = "";
  clerkRuntime.state = "loaded";
  vi.unstubAllEnvs();
  vi.doUnmock("next/dynamic");
  vi.doUnmock("@clerk/nextjs");
  vi.doUnmock("@/hooks/use-auth-token");
  vi.doUnmock("@/hooks/use-principal-capabilities");
  vi.resetModules();
});

describe("auth redirect targets", () => {
  it("keeps auth return targets local and stable", () => {
    expect(
      resolveAuthReturnPath("/billing?intent=credits&pack=portfolio_5"),
    ).toBe("/billing?intent=credits&pack=portfolio_5");
    expect(
      resolveAuthReturnPath("/analyses/new?compound=succinic%20acid"),
    ).toBe("/analyses/new");
    expect(resolveAuthReturnPath("/analyses/new#compound=secret")).toBe(
      "/analyses/new",
    );
    expect(
      resolveAuthReturnPath(
        "/sign-in?return_to=%2Fanalyses%2Fnew%3Fcompound%3Dsecret",
      ),
    ).toBe("/sign-in");
    expect(
      resolveAuthReturnPath(
        "/sign-in?return_to=%252Fanalyses%252Fnew%253Fcompound%253Dsecret",
      ),
    ).toBe("/sign-in");
    expect(
      resolveAuthReturnPath(
        "/sign-in?return_to=%2Fanalyses%2Fnew%23%2Fanalyses%2Fnew%3Fcompound%3Dsecret",
      ),
    ).toBe("/sign-in");
    expect(resolveAuthReturnPath("/methodology#scope")).toBe(
      "/methodology#scope",
    );
    expect(resolveAuthReturnPath(`/${"a".repeat(2048)}`)).toBe(
      DEFAULT_AUTH_RETURN_PATH,
    );
    expect(
      resolveExplicitAuthReturnPath("/billing?intent=credits&pack=portfolio_5"),
    ).toBe("/billing?intent=credits&pack=portfolio_5");
    expect(resolveExplicitAuthReturnPath(null)).toBeNull();
    expect(resolveAuthReturnPath("https://example.com/billing")).toBe(
      DEFAULT_AUTH_RETURN_PATH,
    );
    expect(resolveAuthReturnPath("//example.com/billing")).toBe(
      DEFAULT_AUTH_RETURN_PATH,
    );
    expect(resolveAuthReturnPath(null)).toBe(DEFAULT_AUTH_RETURN_PATH);
  });

  it("derives checkout context only from sanitized billing credit-pack return targets", () => {
    const intent = resolveAuthCheckoutIntent(
      "/billing?intent=credits&needed_reports=5&pack=portfolio_5",
    );

    expect(intent).toMatchObject({
      kind: "credit_pack",
      returnPath: "/billing?intent=credits&needed_reports=5&pack=portfolio_5",
      packId: "portfolio_5",
      packLabel: "Portfolio Pack",
      reportCredits: "5 Report Credits",
      totalPrice: "$1,145",
      effectiveRate: "$229 / request",
      savingsLabel: "Save 8%",
      contractCopy:
        "1 Report Credit = 1 first-pass FTO report request for 1 compound",
    });
    expect(resolveAuthCheckoutIntent("/billing?intent=credits")).toBeNull();
    expect(
      resolveAuthCheckoutIntent(
        "/billing?intent=credits&pack=https://evil.example",
      ),
    ).toBeNull();
    expect(
      resolveAuthCheckoutIntent("/analyses/new?compound=succinic%20acid"),
    ).toBeNull();
    expect(
      resolveAuthCheckoutIntent("https://evil.example/billing"),
    ).toBeNull();
  });
});

describe.each([
  ["sign-in", "Sign In"],
  ["sign-up", "Sign Up"],
] as const)("Clerk auth surface config for %s", (route, heading) => {
  it("does not load Clerk widgets for malformed publishable keys", async () => {
    vi.resetModules();
    const dynamicSpy = mockDynamic();
    mockClerk();
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "pk_test_abc");

    const AuthPage = await loadAuthPage(route);
    render(<AuthPage />);

    expect(screen.queryByRole("main")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Praviar access" })).toHaveClass(
      "praviar-auth-field",
    );
    expect(screen.getByTestId("auth-mobile-proof")).toHaveTextContent(
      "Compound evidence, patent citations",
    );
    expect(screen.getByTestId("auth-mobile-proof")).toHaveTextContent(
      "Provider required",
    );
    expect(screen.getByTestId("auth-identity-readiness")).toHaveTextContent(
      "Identity methods",
    );
    expect(screen.getByTestId("auth-identity-readiness")).toHaveTextContent(
      "Provider controlled",
    );
    expect(screen.getByTestId("auth-identity-readiness")).toHaveTextContent(
      "Tenant scoped",
    );
    expect(screen.getByTestId("auth-identity-readiness")).toHaveTextContent(
      "Attached after sign-in",
    );
    expect(screen.queryByText("Praviar access")).not.toBeInTheDocument();
    expect(screen.getByTestId("auth-unavailable-state")).toBeInTheDocument();
    expect(dynamicSpy).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    expect(
      screen.getByText(/Authentication check is unavailable/),
    ).toBeInTheDocument();
    expect(screen.getByTestId("auth-unavailable-state")).toHaveAttribute(
      "data-auth-unavailable-context",
      "entry",
    );
    expect(
      screen.getByRole("button", { name: "Try again" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Authentication trust ledger" }),
    ).toHaveClass("hidden", "sm:block");
    expect(
      screen.queryByRole("region", { name: "Authentication trust summary" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Evidence remains sealed")).toBeInTheDocument();
    expect(
      screen.getAllByText("Identity provider required").length,
    ).toBeGreaterThan(0);
    expect(
      screen.queryByText("Succinic acid review packet"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("HIGH")).not.toBeInTheDocument();
    expect(screen.queryByText("blockers")).not.toBeInTheDocument();
    expect(screen.queryByText("searched")).not.toBeInTheDocument();
    expect(screen.queryByText("reviewed")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toHaveClass(
      "min-h-11",
    );
    expect(
      screen.getByRole("link", { name: /Review deployment setup/ }),
    ).toHaveClass("min-h-11");
    expect(
      screen.getByRole("link", { name: /Review deployment setup/ }),
    ).toHaveAttribute("href", "/trust#assurance-heading");
    expect(screen.queryByTestId("clerk-widget")).not.toBeInTheDocument();
  });

  it("loads Clerk widgets only for validator-approved publishable keys", async () => {
    vi.resetModules();
    const dynamicSpy = mockDynamic();
    mockClerk();
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", VALID_TEST_CLERK_KEY);

    const AuthPage = await loadAuthPage(route);
    render(<AuthPage />);

    expect(dynamicSpy).toHaveBeenCalledOnce();
    expect(screen.queryByRole("main")).not.toBeInTheDocument();
    expect(screen.getByTestId("auth-mobile-proof")).toHaveTextContent(
      "Compound evidence, patent citations",
    );
    const clerkWidget = screen.getByTestId("clerk-widget");
    expect(clerkWidget).toBeInTheDocument();
    expect(screen.getByTestId("auth-identity-readiness")).toHaveTextContent(
      "SSO, email-code, and passkey policies",
    );
    expect(screen.getByTestId("auth-identity-readiness")).toHaveTextContent(
      "Return paths stay local",
    );
    expect(clerkWidget.dataset.fallbackRedirectUrl).toBe(
      DEFAULT_AUTH_RETURN_PATH,
    );
    expect(clerkWidget.dataset.forceRedirectUrl).toBe("");
    if (route === "sign-in") {
      expect(clerkWidget.dataset.signUpFallbackRedirectUrl).toBe(
        DEFAULT_AUTH_RETURN_PATH,
      );
      expect(clerkWidget.dataset.signUpForceRedirectUrl).toBe("");
    } else {
      expect(clerkWidget.dataset.signInFallbackRedirectUrl).toBe(
        DEFAULT_AUTH_RETURN_PATH,
      );
      expect(clerkWidget.dataset.signInForceRedirectUrl).toBe("");
    }
    expect(clerkWidget.dataset.formButtonPrimary).toContain("min-h-11");
    expect(clerkWidget.dataset.formButtonPrimary).toContain(
      "focus-visible:ring-2",
    );
    expect(clerkWidget.dataset.formFieldInput).toContain("min-h-11");
    expect(clerkWidget.dataset.formFieldInput).toContain(
      "focus-visible:ring-2",
    );
    expect(clerkWidget.dataset.socialButtonsBlockButton).toContain("min-h-11");
    expect(
      screen.queryByRole("heading", { name: heading }),
    ).not.toBeInTheDocument();
  });

  it("renders a fail-closed recovery surface when the Clerk runtime fails", async () => {
    vi.resetModules();
    mockDynamic();
    mockClerk();
    clerkRuntime.state = "failed";
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", VALID_TEST_CLERK_KEY);

    const AuthPage = await loadAuthPage(route);
    render(<AuthPage />);

    expect(screen.getByTestId("auth-unavailable-state")).toHaveAttribute(
      "data-auth-unavailable-context",
      "entry",
    );
    expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Try again" }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("clerk-widget")).not.toBeInTheDocument();
  });

  it("shows explicit loading and degraded runtime states", async () => {
    vi.resetModules();
    mockDynamic();
    mockClerk();
    clerkRuntime.state = "loading";
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", VALID_TEST_CLERK_KEY);

    const LoadingPage = await loadAuthPage(route);
    const { unmount } = render(<LoadingPage />);

    expect(screen.getByRole("status")).toHaveAttribute(
      "data-praviar-app-state",
      "loading",
    );
    expect(screen.queryByTestId("clerk-widget")).not.toBeInTheDocument();
    unmount();

    vi.resetModules();
    mockDynamic();
    mockClerk();
    clerkRuntime.state = "degraded";
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", VALID_TEST_CLERK_KEY);

    const DegradedPage = await loadAuthPage(route);
    render(<DegradedPage />);

    expect(screen.getByTestId("auth-provider-degraded")).toHaveTextContent(
      "Identity provider operating in recovery mode",
    );
    expect(screen.getByTestId("clerk-widget")).toBeInTheDocument();
  });

  it("preserves sanitized local return targets for checkout handoff", async () => {
    vi.resetModules();
    authNavigation.searchParams =
      "return_to=%2Fbilling%3Fintent%3Dcredits%26pack%3Dportfolio_5";
    mockDynamic();
    mockClerk();
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", VALID_TEST_CLERK_KEY);

    const AuthPage = await loadAuthPage(route);
    render(<AuthPage />);

    const clerkWidget = screen.getByTestId("clerk-widget");
    expect(clerkWidget.dataset.fallbackRedirectUrl).toBe(
      "/billing?intent=credits&pack=portfolio_5",
    );
    expect(clerkWidget.dataset.forceRedirectUrl).toBe(
      "/billing?intent=credits&pack=portfolio_5",
    );
    if (route === "sign-in") {
      expect(clerkWidget.dataset.signUpFallbackRedirectUrl).toBe(
        "/billing?intent=credits&pack=portfolio_5",
      );
      expect(clerkWidget.dataset.signUpForceRedirectUrl).toBe(
        "/billing?intent=credits&pack=portfolio_5",
      );
    } else {
      expect(clerkWidget.dataset.signInFallbackRedirectUrl).toBe(
        "/billing?intent=credits&pack=portfolio_5",
      );
      expect(clerkWidget.dataset.signInForceRedirectUrl).toBe(
        "/billing?intent=credits&pack=portfolio_5",
      );
    }
    const checkoutIntent = screen.getByTestId("auth-checkout-intent");
    expect(checkoutIntent).toHaveAttribute("data-pack-id", "portfolio_5");
    expect(checkoutIntent).toHaveTextContent("Selected before sign-in");
    expect(checkoutIntent).toHaveTextContent("Portfolio Pack");
    expect(checkoutIntent).toHaveTextContent("$1,145");
    expect(checkoutIntent).toHaveTextContent("$229 / request");
    expect(checkoutIntent).toHaveTextContent(
      "Included Report Credits are checked first after sign-in.",
    );
    expect(checkoutIntent).toHaveTextContent(
      "Stripe checkout opens only if extra prepaid capacity is needed.",
    );
  });

  it("makes explicit checkout return_to authoritative over competing Clerk redirect_url", async () => {
    vi.resetModules();
    authNavigation.searchParams =
      "return_to=%2Fbilling%3Fintent%3Dcredits%26needed_reports%3D5%26pack%3Dportfolio_5&redirect_url=%2Fdashboard";
    mockDynamic();
    mockClerk();
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", VALID_TEST_CLERK_KEY);

    const AuthPage = await loadAuthPage(route);
    render(<AuthPage />);

    const clerkWidget = screen.getByTestId("clerk-widget");
    expect(clerkWidget.dataset.fallbackRedirectUrl).toBe(
      "/billing?intent=credits&needed_reports=5&pack=portfolio_5",
    );
    expect(clerkWidget.dataset.forceRedirectUrl).toBe(
      "/billing?intent=credits&needed_reports=5&pack=portfolio_5",
    );
    if (route === "sign-in") {
      expect(clerkWidget.dataset.signUpForceRedirectUrl).toBe(
        "/billing?intent=credits&needed_reports=5&pack=portfolio_5",
      );
    } else {
      expect(clerkWidget.dataset.signInForceRedirectUrl).toBe(
        "/billing?intent=credits&needed_reports=5&pack=portfolio_5",
      );
    }
    expect(screen.getByTestId("auth-checkout-intent")).toHaveTextContent(
      "Portfolio Pack",
    );
  });
});

describe("local demo sign-in boundary", () => {
  it("offers a deterministic synthetic workspace path without loading Clerk", async () => {
    vi.resetModules();
    const dynamicSpy = mockDynamic();
    mockClerk();
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "true");
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "pk_test_abc");
    authNavigation.searchParams =
      "return_to=%2Fanalyses%2Fana_demo_001%2Freport";

    const AuthPage = await loadAuthPage("sign-in");
    render(<AuthPage />);

    expect(dynamicSpy).not.toHaveBeenCalled();
    expect(screen.getByTestId("demo-sign-in-state")).toHaveTextContent(
      "Demo data only",
    );
    expect(screen.getByTestId("demo-sign-in-state")).toHaveTextContent(
      "not legal advice or a clearance opinion",
    );
    expect(
      screen.getByRole("link", { name: "Enter demo workspace" }),
    ).toHaveAttribute("href", "/analyses/ana_demo_001/report");
    expect(
      screen.getByText(/This demo path cannot authenticate into one\./),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("clerk-widget")).not.toBeInTheDocument();
  });

  it("never exposes the demo sign-in path in a production runtime", async () => {
    vi.resetModules();
    mockDynamic();
    mockClerk();
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "true");
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "pk_test_abc");

    const AuthPage = await loadAuthPage("sign-in");
    render(<AuthPage />);

    expect(screen.queryByTestId("demo-sign-in-state")).not.toBeInTheDocument();
    expect(
      screen.getByText(/Authentication check is unavailable/),
    ).toBeInTheDocument();
  });
});

describe.each([
  ["sign-in", "Sign In"],
  ["sign-up", "Sign Up"],
] as const)("Clerk SSO callback config for %s", (route, heading) => {
  it("does not load Clerk callbacks for malformed publishable keys", async () => {
    vi.resetModules();
    const dynamicSpy = mockDynamic();
    mockClerk();
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "pk_test_abc");

    const AuthCallback = await loadAuthCallback(route);
    render(<AuthCallback />);

    expect(screen.getByRole("region", { name: "Praviar access" })).toHaveClass(
      "praviar-auth-field",
    );
    expect(dynamicSpy).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    expect(
      screen.getByText(/identity-provider return cannot finish/),
    ).toBeInTheDocument();
    expect(screen.getByTestId("auth-unavailable-state")).toHaveAttribute(
      "data-auth-unavailable-context",
      "sso-callback",
    );
    expect(
      screen.getByRole("button", { name: "Retry callback" }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("clerk-widget")).not.toBeInTheDocument();
    expect(screen.queryByTestId("clerk-sso-callback")).not.toBeInTheDocument();
  });

  it("loads Clerk callbacks only for validator-approved publishable keys", async () => {
    vi.resetModules();
    const dynamicSpy = mockDynamic();
    mockClerk();
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", VALID_TEST_CLERK_KEY);

    const AuthCallback = await loadAuthCallback(route);
    render(<AuthCallback />);

    expect(dynamicSpy).toHaveBeenCalledOnce();
    expect(screen.getByTestId("clerk-widget")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: heading }),
    ).not.toBeInTheDocument();
  });

  it("fails closed when the Clerk runtime drops during an SSO return", async () => {
    vi.resetModules();
    mockDynamic();
    mockClerk();
    clerkRuntime.state = "failed";
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", VALID_TEST_CLERK_KEY);

    const AuthCallback = await loadAuthCallback(route);
    render(<AuthCallback />);

    expect(screen.getByTestId("auth-unavailable-state")).toHaveAttribute(
      "data-auth-unavailable-context",
      "sso-callback",
    );
    expect(
      screen.getByRole("button", { name: "Retry callback" }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("clerk-widget")).not.toBeInTheDocument();
  });

  it("preserves sanitized local return targets through SSO callbacks", async () => {
    vi.resetModules();
    authNavigation.searchParams =
      "return_to=%2Fbilling%3Fintent%3Dcredits%26pack%3Dportfolio_5";
    mockDynamic();
    mockClerk();
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", VALID_TEST_CLERK_KEY);

    const AuthCallback = await loadAuthCallback(route);
    render(<AuthCallback />);

    const clerkWidget = screen.getByTestId("clerk-widget");
    expect(clerkWidget).toHaveAttribute(
      "data-sign-in-fallback-redirect-url",
      "/billing?intent=credits&pack=portfolio_5",
    );
    expect(clerkWidget).toHaveAttribute(
      "data-sign-in-force-redirect-url",
      "/billing?intent=credits&pack=portfolio_5",
    );
    expect(clerkWidget).toHaveAttribute(
      "data-sign-up-fallback-redirect-url",
      "/billing?intent=credits&pack=portfolio_5",
    );
    expect(clerkWidget).toHaveAttribute(
      "data-sign-up-force-redirect-url",
      "/billing?intent=credits&pack=portfolio_5",
    );
    expect(screen.getByTestId("auth-checkout-intent")).toHaveTextContent(
      "Portfolio Pack",
    );
  });

  it("makes checkout return_to authoritative over competing redirect_url through SSO callbacks", async () => {
    vi.resetModules();
    authNavigation.searchParams =
      "return_to=%2Fbilling%3Fintent%3Dcredits%26needed_reports%3D5%26pack%3Dportfolio_5&redirect_url=%2Fdashboard";
    mockDynamic();
    mockClerk();
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", VALID_TEST_CLERK_KEY);

    const AuthCallback = await loadAuthCallback(route);
    render(<AuthCallback />);

    const clerkWidget = screen.getByTestId("clerk-widget");
    expect(clerkWidget).toHaveAttribute(
      "data-sign-in-force-redirect-url",
      "/billing?intent=credits&needed_reports=5&pack=portfolio_5",
    );
    expect(clerkWidget).toHaveAttribute(
      "data-sign-up-force-redirect-url",
      "/billing?intent=credits&needed_reports=5&pack=portfolio_5",
    );
    expect(screen.getByTestId("auth-checkout-intent")).toHaveTextContent(
      "Portfolio Pack",
    );
  });
});

describe("Sidebar Clerk config", () => {
  it("keeps dashboard Clerk widgets disabled for malformed publishable keys", async () => {
    vi.resetModules();
    mockClerk();
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "pk_test_abc");

    const { hasClerk } = await import("@/components/layout/sidebar-constants");

    expect(hasClerk).toBe(false);
  });

  it("enables dashboard Clerk widgets only for validator-approved publishable keys", async () => {
    vi.resetModules();
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", VALID_TEST_CLERK_KEY);

    const { hasClerk } = await import("@/components/layout/sidebar-constants");

    expect(hasClerk).toBe(true);
  });

  it("does not render sidebar Clerk widgets for malformed publishable keys", async () => {
    vi.resetModules();
    mockDynamic();
    mockClerk();
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "pk_test_abc");

    const { Sidebar } = await import("@/components/layout/sidebar");
    const { useUIStore } = await import("@/stores/ui-store");
    useUIStore.setState({ sidebarOpen: true, mobileSidebarOpen: false });
    render(<Sidebar />);

    expect(screen.queryByTestId("clerk-widget")).not.toBeInTheDocument();
  });

  it("shows both the Clerk organization selector and user control", async () => {
    vi.resetModules();
    const dynamicSpy = mockDynamic();
    mockClerk("org:admin");
    mockSidebarApplicationRole("admin");
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", VALID_TEST_CLERK_KEY);

    const { Sidebar } = await import("@/components/layout/sidebar");
    const { useUIStore } = await import("@/stores/ui-store");
    useUIStore.setState({ sidebarOpen: true, mobileSidebarOpen: false });
    render(<Sidebar />);

    expect(dynamicSpy).toHaveBeenCalledTimes(2);
    expect(screen.getAllByTestId("clerk-widget")).toHaveLength(2);
    expect(
      screen
        .getAllByTestId("clerk-widget")
        .some(
          (widget) =>
            widget.dataset.hidePersonal === "true" &&
            widget.dataset.afterSelectOrganizationUrl === "/dashboard",
        ),
    ).toBe(true);
  });

  it("hides admin-only sidebar links for non-admin Clerk roles", async () => {
    vi.resetModules();
    mockDynamic();
    mockClerk("org:member");
    mockSidebarApplicationRole("scientist");
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", VALID_TEST_CLERK_KEY);

    const { Sidebar } = await import("@/components/layout/sidebar");
    const { useUIStore } = await import("@/stores/ui-store");
    useUIStore.setState({ sidebarOpen: true, mobileSidebarOpen: false });
    render(<Sidebar />);

    expect(screen.getByText("Credits & Billing")).toBeInTheDocument();
    expect(screen.queryByText("Settings")).not.toBeInTheDocument();
    expect(screen.queryByText("Admin")).not.toBeInTheDocument();
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Analyses")).toBeInTheDocument();
  });
});
