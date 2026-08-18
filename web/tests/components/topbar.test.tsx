import { beforeEach, describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { authScopedQueryKey } from "@/lib/query-keys";
import {
  PRAVIAR_MARK_ID,
  PRAVIAR_MARK_TILE_PATH,
} from "@/components/icons/praviar-mark";
import { useUIStore } from "@/stores/ui-store";

// Track the current pathname for per-test control
let currentPathname = "/dashboard";
let mockToken: string | null = null;
const principalState = vi.hoisted(() => ({
  capabilities: {
    role: "admin",
    can_create_analysis: true,
    can_view_review_queue: true,
  } as {
    role: "admin" | "attorney" | "scientist" | "client";
    can_create_analysis: boolean;
    can_view_review_queue: boolean;
  } | null,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => currentPathname,
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => mockToken,
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  usePrincipalCapabilities: () => ({
    data: principalState.capabilities ?? undefined,
  }),
}));

import { Topbar } from "@/components/layout/topbar";

function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function renderWithQueryClient(
  ui: React.ReactElement,
  queryClient = createQueryClient(),
) {
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

function jwt(claims: Record<string, unknown>) {
  const payload = btoa(JSON.stringify(claims))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
  return `header.${payload}.signature`;
}

describe("Topbar", () => {
  beforeEach(() => {
    currentPathname = "/dashboard";
    mockToken = null;
    principalState.capabilities = {
      role: "admin",
      can_create_analysis: true,
      can_view_review_queue: true,
    };
    useUIStore.setState({ mobileSidebarOpen: false });
  });

  describe("breadcrumb rendering", () => {
    it("renders breadcrumb for /dashboard", () => {
      currentPathname = "/dashboard";
      renderWithQueryClient(<Topbar />);
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
      expect(
        screen.getByRole("navigation", { name: "Breadcrumb" }),
      ).toBeInTheDocument();
    });

    it("renders breadcrumbs for retired /analyses/quick path", () => {
      currentPathname = "/analyses/quick";
      renderWithQueryClient(<Topbar />);
      expect(screen.getByText("Analyses")).toBeInTheDocument();
      expect(screen.getByText("Adaptive Launch")).toBeInTheDocument();
      expect(screen.queryByText("Quick Check")).not.toBeInTheDocument();
    });

    it("renders breadcrumbs for /compounds with correct label", () => {
      currentPathname = "/compounds";
      renderWithQueryClient(<Topbar />);
      expect(screen.getByText("Compounds")).toBeInTheDocument();
    });

    it("renders breadcrumbs for /config", () => {
      currentPathname = "/config";
      renderWithQueryClient(<Topbar />);
      expect(screen.getByText("Configuration")).toBeInTheDocument();
    });

    it("renders breadcrumbs for /help", () => {
      currentPathname = "/help";
      renderWithQueryClient(<Topbar />);
      expect(screen.getByText("Help & Docs")).toBeInTheDocument();
    });

    it("does not send member notification settings users to admin settings", () => {
      currentPathname = "/settings/notifications";
      renderWithQueryClient(<Topbar />);

      expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute(
        "href",
        "/dashboard",
      );
      expect(screen.getByTitle("Notification settings")).toHaveAttribute(
        "aria-current",
        "page",
      );
      expect(
        screen.queryByRole("link", { name: "Settings" }),
      ).not.toBeInTheDocument();
    });

    it("uses the product name for the workflow atlas route", () => {
      currentPathname = "/capabilities";
      renderWithQueryClient(<Topbar />);
      expect(screen.getByText("Workflow Atlas")).toBeInTheDocument();
      expect(screen.queryByText("capabilities...")).not.toBeInTheDocument();
    });

    it("uses canonical administration labels across nested routes", () => {
      currentPathname = "/admin/analytics";
      renderWithQueryClient(<Topbar />);

      expect(
        screen.getByRole("link", { name: "Platform Admin" }),
      ).toHaveAttribute("href", "/admin");
      expect(screen.getByTitle("Cost & Usage")).toHaveAttribute(
        "aria-current",
        "page",
      );
    });

    it("renders decorative icon separators between breadcrumb segments", () => {
      currentPathname = "/analyses/quick";
      const { container } = renderWithQueryClient(<Topbar />);
      const separators = container.querySelectorAll(
        "[data-praviar-breadcrumb-separator]",
      );
      expect(separators.length).toBeGreaterThan(0);
      separators.forEach((separator) => {
        expect(separator).toHaveAttribute("aria-hidden", "true");
      });
    });

    it("uses the premium workbench topbar treatment", () => {
      currentPathname = "/analyses/quick";
      const { container } = renderWithQueryClient(<Topbar />);
      expect(
        container.querySelector("[data-praviar-topbar-workbench]"),
      ).toBeInTheDocument();
      expect(screen.getByTitle("Adaptive Launch")).toHaveClass("rounded-md");
    });

    it("makes the last breadcrumb segment non-clickable", () => {
      currentPathname = "/compounds/compare";
      renderWithQueryClient(<Topbar />);
      const lastSegment = screen.getByTitle("Compare");
      // The last segment should be a span, not wrapped in a link
      expect(lastSegment.tagName).toBe("SPAN");
      expect(lastSegment.closest("a")).toBeNull();
      expect(lastSegment).toHaveAttribute("aria-current", "page");
    });

    it("makes intermediate breadcrumb segments clickable links", () => {
      currentPathname = "/analyses/quick";
      renderWithQueryClient(<Topbar />);
      const analysesLink = screen.getByText("Analyses");
      expect(analysesLink.closest("a")).toHaveAttribute("href", "/analyses");
    });

    it("resolves analysis names for nested report route breadcrumbs", () => {
      const analysisId = "analysis-123456789";
      const currentToken = jwt({ sub: "user_1", org_id: "org_current" });
      const queryClient = createQueryClient();

      currentPathname = `/analyses/${analysisId}/report`;
      mockToken = currentToken;
      queryClient.setQueryData(
        authScopedQueryKey(["analyses", analysisId] as const, currentToken),
        { id: analysisId, compound_name: "Succinic acid" },
      );

      renderWithQueryClient(<Topbar />, queryClient);

      expect(screen.getByText("Analyses")).toBeInTheDocument();
      expect(screen.getByText("Succinic acid")).toBeInTheDocument();
      expect(screen.getByText("Report")).toBeInTheDocument();
      expect(screen.queryByText("analysis-123...")).not.toBeInTheDocument();
    });

    it("ellipsizes a long current analysis label inside the topbar chip", () => {
      const analysisId = "analysis-123456789";
      const longLabel = "Example Molecule Alpha — retrieval replay";
      const currentToken = jwt({ sub: "user_1", org_id: "org_current" });
      const queryClient = createQueryClient();

      currentPathname = `/analyses/${analysisId}`;
      mockToken = currentToken;
      queryClient.setQueryData(
        authScopedQueryKey(["analyses", analysisId] as const, currentToken),
        { id: analysisId, compound_name: longLabel },
      );

      renderWithQueryClient(<Topbar />, queryClient);

      const current = screen.getByTitle(longLabel);
      const visibleLabel = within(current).getByText(longLabel);

      expect(current).toHaveAttribute("aria-current", "page");
      expect(current).toHaveAttribute("title", longLabel);
      expect(current).toHaveTextContent(longLabel);
      expect(current).toHaveClass("min-w-0", "overflow-hidden");
      expect(visibleLabel).toHaveClass("min-w-0", "flex-1", "truncate");
    });

    it("truncates long ID-like segments", () => {
      currentPathname = "/analyses/abc123-def456-ghi789";
      renderWithQueryClient(<Topbar />);
      // Should truncate the long segment
      expect(screen.getByTitle("abc123-def45...")).toHaveAttribute(
        "title",
        "abc123-def45...",
      );
    });

    it("resolves analysis names only from the current auth scope", () => {
      const analysisId = "analysis-123456789";
      const oldToken = jwt({ sub: "user_1", org_id: "org_old" });
      const currentToken = jwt({ sub: "user_1", org_id: "org_current" });
      const queryClient = createQueryClient();

      currentPathname = `/analyses/${analysisId}`;
      mockToken = currentToken;
      queryClient.setQueryData(
        authScopedQueryKey(
          ["analyses", 1, 20, undefined, undefined] as const,
          oldToken,
        ),
        {
          items: [{ id: analysisId, compound_name: "Old Scope Compound" }],
        },
      );
      queryClient.setQueryData(
        authScopedQueryKey(
          ["analyses", 1, 20, undefined, undefined] as const,
          currentToken,
        ),
        {
          items: [{ id: analysisId, compound_name: "Current Scope Compound" }],
        },
      );

      renderWithQueryClient(<Topbar />, queryClient);

      expect(screen.getByText("Current Scope Compound")).toBeInTheDocument();
      expect(screen.queryByText("Old Scope Compound")).not.toBeInTheDocument();
    });

    it("does not use previous-scope cache entries for analysis breadcrumbs", () => {
      const analysisId = "analysis-123456789";
      const oldToken = jwt({ sub: "user_1", org_id: "org_old" });
      const currentToken = jwt({ sub: "user_1", org_id: "org_current" });
      const queryClient = createQueryClient();

      currentPathname = `/analyses/${analysisId}`;
      mockToken = currentToken;
      queryClient.setQueryData(
        authScopedQueryKey(["analyses", analysisId] as const, oldToken),
        { id: analysisId, compound_name: "Old Scope Detail" },
      );

      renderWithQueryClient(<Topbar />, queryClient);

      expect(screen.queryByText("Old Scope Detail")).not.toBeInTheDocument();
      expect(screen.getByText("analysis-123...")).toBeInTheDocument();
    });
  });

  describe("quick action buttons", () => {
    it("renders Review Queue button", () => {
      currentPathname = "/dashboard";
      renderWithQueryClient(<Topbar />);
      expect(screen.getByText("Review Queue")).toBeInTheDocument();
    });

    it("renders New Analysis button", () => {
      currentPathname = "/dashboard";
      renderWithQueryClient(<Topbar />);
      expect(screen.getByText("New Analysis")).toBeInTheDocument();
    });

    it("keeps client quick actions read-only", () => {
      principalState.capabilities = {
        role: "client",
        can_create_analysis: false,
        can_view_review_queue: false,
      };

      renderWithQueryClient(<Topbar />);

      expect(screen.queryByText("Review Queue")).not.toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: "New Analysis" }),
      ).not.toBeInTheDocument();
    });

    it("fails closed while capabilities are unavailable", () => {
      principalState.capabilities = null;

      renderWithQueryClient(<Topbar />);

      expect(screen.queryByText("Review Queue")).not.toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: "New Analysis" }),
      ).not.toBeInTheDocument();
    });

    it("keeps Praviar branding visible in the mobile topbar", () => {
      currentPathname = "/dashboard";
      renderWithQueryClient(<Topbar />);
      const brandLink = screen.getByLabelText("Praviar dashboard");

      expect(brandLink).toHaveAttribute("href", "/dashboard");
      expect(brandLink).toHaveClass("h-12");
    });

    it("keeps mobile topbar quick actions at practical touch size", () => {
      currentPathname = "/dashboard";
      renderWithQueryClient(<Topbar />);

      expect(screen.getByLabelText("New Analysis")).toHaveClass("min-h-11");
      expect(screen.getByLabelText("New Analysis")).toHaveClass("min-w-11");
      expect(screen.getByLabelText("New Analysis")).toHaveClass("w-11");
      expect(screen.getByLabelText("New Analysis")).toHaveClass("sm:w-auto");
    });

    it("uses the canonical supplied mark in the mobile topbar lockup", () => {
      currentPathname = "/dashboard";
      renderWithQueryClient(<Topbar />);

      const brandLink = screen.getByLabelText("Praviar dashboard");
      const mark = brandLink.querySelector(
        `svg[data-praviar-mark="${PRAVIAR_MARK_ID}"]`,
      );

      expect(mark).toBeInTheDocument();
      expect(mark?.querySelector("path")).toHaveAttribute(
        "d",
        PRAVIAR_MARK_TILE_PATH,
      );
      expect(brandLink.querySelector("circle")).not.toBeInTheDocument();
      expect(brandLink.querySelector("line")).not.toBeInTheDocument();
    });

    it("Review Queue links to /reviews", () => {
      currentPathname = "/dashboard";
      renderWithQueryClient(<Topbar />);
      const reviewQueueLink = screen.getByText("Review Queue").closest("a");
      expect(reviewQueueLink).toHaveAttribute("href", "/reviews");
    });

    it("New Analysis links to /analyses/new", () => {
      currentPathname = "/dashboard";
      renderWithQueryClient(<Topbar />);
      const newAnalysisLink = screen.getByText("New Analysis").closest("a");
      expect(newAnalysisLink).toHaveAttribute("href", "/analyses/new");
    });
  });

  describe("header element", () => {
    it("renders as a header element", () => {
      currentPathname = "/dashboard";
      const { container } = renderWithQueryClient(<Topbar />);
      const header = container.querySelector("header");
      expect(header).toBeInTheDocument();
    });

    it("is sticky positioned", () => {
      currentPathname = "/dashboard";
      const { container } = renderWithQueryClient(<Topbar />);
      const header = container.querySelector("header")!;
      expect(header.className).toContain("sticky");
      expect(header.className).toContain("top-0");
    });

    it("announces mobile navigation drawer state", () => {
      currentPathname = "/dashboard";
      renderWithQueryClient(<Topbar />);

      const menuButton = screen.getByRole("button", {
        name: "Open navigation menu",
      });
      expect(menuButton).toHaveAttribute("aria-controls", "dashboard-sidebar");
      expect(menuButton).toHaveAttribute("aria-expanded", "false");
      expect(menuButton).toHaveAttribute("data-praviar-mobile-menu-button");

      fireEvent.click(menuButton);

      expect(menuButton).toHaveAttribute("aria-expanded", "true");
    });
  });
});
