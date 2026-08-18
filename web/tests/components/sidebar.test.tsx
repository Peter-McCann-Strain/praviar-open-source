import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// Track the current pathname for per-test control
let currentPathname = "/dashboard";

// Override the global next/navigation mock from setup.tsx to allow per-test pathname
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

// Mock next/dynamic to render nothing for Clerk components
vi.mock("next/dynamic", () => ({
  default: () => {
    const Component = () => null;
    Component.displayName = "DynamicMock";
    return Component;
  },
}));

// Mock @clerk/nextjs
vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ isLoaded: true, orgRole: "org:admin" }),
  UserButton: () => <div data-testid="clerk-user-button" />,
}));

import { Sidebar } from "@/components/layout/sidebar";
import { SidebarNav } from "@/components/layout/sidebar-nav";
import {
  PRAVIAR_MARK_BAND_PATHS,
  PRAVIAR_MARK_ID,
  PRAVIAR_MARK_INK_PATH,
  PRAVIAR_MARK_ON_DARK_FILLS,
  PRAVIAR_MARK_TILE_PATH,
} from "@/components/icons/praviar-mark";
import { useUIStore } from "@/stores/ui-store";

function mockMobileViewport(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

beforeEach(() => {
  currentPathname = "/dashboard";
  mockMobileViewport(false);
  // Reset store to open sidebar on the locked premium light shell.
  document.documentElement.className = "light";
  useUIStore.setState({
    sidebarOpen: true,
    mobileSidebarOpen: false,
  });
});

describe("Sidebar", () => {
  describe("nav items rendering", () => {
    it("renders grouped navigation when the sidebar is open", () => {
      render(<Sidebar />);
      expect(
        screen.getByRole("heading", { name: "Workspace" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("heading", { name: "Decisions" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("heading", { name: "Operations" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("heading", { name: "Administration" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("heading", { name: "Support" }),
      ).toBeInTheDocument();
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
      expect(screen.getByText("Analyses")).toBeInTheDocument();
      expect(screen.getByText("Configuration")).toBeInTheDocument();
      expect(screen.getByText("Help")).toBeInTheDocument();
    });

    it("renders nav items as links with correct hrefs", () => {
      render(<Sidebar />);
      const dashboardLink = screen.getByText("Dashboard").closest("a");
      expect(dashboardLink).toHaveAttribute("href", "/dashboard");

      const analysesLink = screen.getByText("Analyses").closest("a");
      expect(analysesLink).toHaveAttribute("href", "/analyses");

      const configLink = screen.getByText("Configuration").closest("a");
      expect(configLink).toHaveAttribute("href", "/config");

      const helpLink = screen.getByText("Help").closest("a");
      expect(helpLink).toHaveAttribute("href", "/help");

      expect(
        screen.getByRole("link", { name: "Review Queue" }),
      ).toHaveAttribute("href", "/reviews");
      expect(
        screen.getByRole("link", { name: "Workflow Atlas" }),
      ).toHaveAttribute("href", "/capabilities");
      expect(
        screen.getByRole("link", { name: "Cost & Usage" }),
      ).toHaveAttribute("href", "/admin/analytics");
    });

    it("renders the Praviar brand name when sidebar is open", () => {
      render(<Sidebar />);
      expect(screen.getByText("Praviar")).toBeInTheDocument();
    });

    it("keeps the workspace brand link inside the dashboard app", () => {
      render(<Sidebar />);

      const brandLink = screen.getByLabelText("Praviar dashboard");
      expect(brandLink).toHaveAttribute("href", "/dashboard");
    });

    it("renders the supplied Praviar evidence mark beside the wordmark", () => {
      render(<Sidebar />);

      const brandLink = screen.getByLabelText("Praviar dashboard");
      const mark = brandLink.querySelector(
        `svg[data-praviar-mark="${PRAVIAR_MARK_ID}"]`,
      );
      const paths = mark?.querySelectorAll("path") ?? [];

      expect(mark).toBeInTheDocument();
      expect(mark).toHaveAttribute("viewBox", "0 0 230 230");
      expect(Array.from(paths).map((path) => path.getAttribute("d"))).toEqual([
        PRAVIAR_MARK_TILE_PATH,
        PRAVIAR_MARK_INK_PATH,
        ...PRAVIAR_MARK_BAND_PATHS,
      ]);
      expect(
        Array.from(paths).map((path) => path.getAttribute("fill")),
      ).toEqual([
        PRAVIAR_MARK_ON_DARK_FILLS.paper,
        PRAVIAR_MARK_ON_DARK_FILLS.ink,
        PRAVIAR_MARK_ON_DARK_FILLS.mint,
        PRAVIAR_MARK_ON_DARK_FILLS.teal,
        PRAVIAR_MARK_ON_DARK_FILLS.copper,
        PRAVIAR_MARK_ON_DARK_FILLS.softMint,
      ]);
      expect(brandLink.querySelector("circle")).not.toBeInTheDocument();
      expect(brandLink.querySelector("line")).not.toBeInTheDocument();
      expect(brandLink.querySelector("polygon")).not.toBeInTheDocument();
      expect(brandLink.querySelector("polyline")).not.toBeInTheDocument();
    });

    it("hides admin-only nav items for non-admin organization roles", () => {
      render(
        <SidebarNav
          pathname="/dashboard"
          sidebarOpen
          onNavigate={vi.fn()}
          orgRole="org:member"
          applicationRole="attorney"
        />,
      );

      expect(screen.getByText("Credits & Billing")).toBeInTheDocument();
      expect(screen.queryByText("Settings")).not.toBeInTheDocument();
      expect(screen.queryByText("Platform Admin")).not.toBeInTheDocument();
      expect(screen.queryByText("Cost & Usage")).not.toBeInTheDocument();
      expect(screen.getByText("Review Queue")).toBeInTheDocument();
      expect(screen.getByText("Workflow Atlas")).toBeInTheDocument();
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
      expect(screen.getByText("Analyses")).toBeInTheDocument();
    });

    it("shows admin-only nav items for admin organization roles", () => {
      render(
        <SidebarNav
          pathname="/dashboard"
          sidebarOpen
          onNavigate={vi.fn()}
          orgRole="org:admin"
          applicationRole="admin"
        />,
      );

      expect(screen.getByText("Credits & Billing")).toBeInTheDocument();
      expect(screen.getByText("Settings")).toBeInTheDocument();
      expect(screen.getByText("Platform Admin")).toBeInTheDocument();
      expect(screen.getByText("Cost & Usage")).toBeInTheDocument();
    });
  });

  describe("active state", () => {
    it("applies active styling for the current route", () => {
      currentPathname = "/analyses";
      render(<Sidebar />);
      const analysesLink = screen.getByText("Analyses").closest("a")!;
      expect(analysesLink.className).toContain("font-semibold");
      expect(analysesLink.className).toContain("brand-primary");
      expect(analysesLink.className).toContain("surface-inverted-fg");
    });

    it("applies active styling for nested routes", () => {
      currentPathname = "/analyses/123/report";
      render(<Sidebar />);
      const analysesLink = screen.getByText("Analyses").closest("a")!;
      expect(analysesLink.className).toContain("brand-primary");
    });

    it("selects the most specific persistent destination", () => {
      render(
        <SidebarNav
          pathname="/admin/analytics"
          sidebarOpen
          onNavigate={vi.fn()}
          orgRole="org:admin"
          applicationRole="admin"
        />,
      );

      expect(screen.getByText("Cost & Usage").closest("a")).toHaveAttribute(
        "aria-current",
        "page",
      );
      expect(
        screen.getByRole("link", { name: "Platform Admin" }),
      ).not.toHaveAttribute("aria-current");
    });

    it("applies inactive styling for non-matching routes", () => {
      currentPathname = "/dashboard";
      render(<Sidebar />);
      const helpLink = screen.getByText("Help").closest("a")!;
      expect(helpLink.className).toContain("surface-inverted-fg-muted");
      expect(helpLink.className).not.toContain("font-semibold");
    });

    it("renders active indicator bar for current route", () => {
      currentPathname = "/config";
      render(<Sidebar />);
      const configLink = screen.getByText("Configuration").closest("a")!;
      const indicator = configLink.querySelector('div[class*="brand-mint"]');
      expect(indicator).toBeInTheDocument();
    });

    it("does not render active indicator for inactive routes", () => {
      currentPathname = "/dashboard";
      render(<Sidebar />);
      const helpLink = screen.getByText("Help").closest("a")!;
      const indicator = helpLink.querySelector('div[class*="brand-mint"]');
      expect(indicator).toBeNull();
    });
  });

  describe("collapsed state", () => {
    it("hides inline nav item labels when sidebar is collapsed (tooltip spans still in DOM)", () => {
      useUIStore.setState({ sidebarOpen: false });
      render(<Sidebar />);
      // Inline label spans are removed; tooltip spans exist but are opacity-0
      const dashboardEls = screen.queryAllByText("Dashboard");
      // Each label only appears once (as floating tooltip), not as inline span
      dashboardEls.forEach((el) => {
        expect(el.className).toContain("opacity-0");
      });
    });

    it("hides Praviar brand name when sidebar is collapsed", () => {
      useUIStore.setState({ sidebarOpen: false });
      render(<Sidebar />);
      expect(screen.queryByText("Praviar")).not.toBeInTheDocument();
    });

    it("applies narrow width when collapsed", () => {
      useUIStore.setState({ sidebarOpen: false });
      const { container } = render(<Sidebar />);
      const aside = container.querySelector("aside")!;
      expect(aside.className).toContain("lg:w-[64px]");
    });

    it("applies wide width when expanded", () => {
      useUIStore.setState({ sidebarOpen: true });
      const { container } = render(<Sidebar />);
      const aside = container.querySelector("aside")!;
      expect(aside.className).toContain("lg:w-[256px]");
    });

    it("shows floating tooltip spans on nav links when collapsed", () => {
      useUIStore.setState({ sidebarOpen: false });
      render(<Sidebar />);
      // Floating tooltip spans contain nav item labels
      const dashboardTooltips = screen.queryAllByText("Dashboard");
      expect(dashboardTooltips.length).toBeGreaterThan(0);
      // Tooltips have pointer-events-none and opacity-0 by default
      dashboardTooltips.forEach((el) => {
        expect(el.className).toContain("pointer-events-none");
      });
    });

    it("keeps the collapsed desktop toggle at a 44px touch target", () => {
      useUIStore.setState({ sidebarOpen: false });
      render(<Sidebar />);

      expect(
        screen.getByRole("button", { name: "Expand sidebar" }),
      ).toHaveClass("h-11", "w-11");
    });

    it("keeps collapsed nav flyouts above the shell and horizontally visible", () => {
      useUIStore.setState({ sidebarOpen: false });
      const { container } = render(<Sidebar />);
      const nav = container.querySelector("[data-praviar-sidebar-nav]")!;
      const dashboardTooltip = screen.getByText("Dashboard");

      expect(nav.className).toContain("overflow-x-visible");
      expect(dashboardTooltip.className).toContain("z-[70]");
    });
  });

  describe("sidebar toggle", () => {
    it("toggles sidebar state when toggle button is clicked", () => {
      render(<Sidebar />);
      expect(useUIStore.getState().sidebarOpen).toBe(true);

      const toggleBtn = screen.getByRole("button", {
        name: "Collapse sidebar",
      });
      fireEvent.click(toggleBtn);

      expect(useUIStore.getState().sidebarOpen).toBe(false);
    });

    it("renders mobile drawer labels even when desktop sidebar is collapsed", () => {
      mockMobileViewport(true);
      useUIStore.setState({ sidebarOpen: false, mobileSidebarOpen: true });

      render(<Sidebar />);

      expect(screen.getByText("Praviar")).toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: "Dashboard" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: "Analyses" }),
      ).toBeInTheDocument();
      expect(screen.getByText("Search")).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Close navigation" }),
      ).toBeInTheDocument();
    });

    it("moves focus into the mobile drawer and restores it after Escape", async () => {
      mockMobileViewport(true);
      const launcher = document.createElement("button");
      launcher.textContent = "Open navigation menu";
      document.body.appendChild(launcher);
      launcher.focus();
      useUIStore.setState({ sidebarOpen: true, mobileSidebarOpen: true });

      const { container } = render(<Sidebar />);
      const aside = container.querySelector("aside")!;
      const closeButton = screen.getByRole("button", {
        name: "Close navigation",
      });

      expect(aside).toHaveAttribute("role", "dialog");
      expect(aside).toHaveAttribute("aria-modal", "true");
      await waitFor(() => expect(closeButton).toHaveFocus());

      fireEvent.keyDown(aside, { key: "Escape" });

      await waitFor(() =>
        expect(useUIStore.getState().mobileSidebarOpen).toBe(false),
      );
      await waitFor(() => expect(launcher).toHaveFocus());
      launcher.remove();
    });

    it("keeps Tab focus cycling inside the mobile drawer", async () => {
      mockMobileViewport(true);
      useUIStore.setState({ sidebarOpen: true, mobileSidebarOpen: true });

      const { container } = render(<Sidebar />);
      const aside = container.querySelector("aside")!;
      const brandLink = screen.getByLabelText("Praviar dashboard");
      const lastNavLink = screen.getByRole("link", { name: "Help" });

      await waitFor(() =>
        expect(
          screen.getByRole("button", { name: "Close navigation" }),
        ).toHaveFocus(),
      );

      brandLink.focus();
      fireEvent.keyDown(aside, { key: "Tab", shiftKey: true });
      expect(lastNavLink).toHaveFocus();

      lastNavLink.focus();
      fireEvent.keyDown(aside, { key: "Tab" });
      expect(brandLink).toHaveFocus();
    });

    it("keeps a stale mobile drawer flag from expanding collapsed desktop labels", () => {
      mockMobileViewport(false);
      useUIStore.setState({ sidebarOpen: false, mobileSidebarOpen: true });

      const { container } = render(<Sidebar />);
      const aside = container.querySelector("aside")!;

      expect(aside.className).toContain("lg:w-[64px]");
      expect(screen.queryByText("Praviar")).not.toBeInTheDocument();
      expect(screen.queryByText("Search")).not.toBeInTheDocument();
      screen.queryAllByText("Dashboard").forEach((el) => {
        expect(el.className).toContain("opacity-0");
      });
    });
  });

  describe("premium light theme contract", () => {
    it("does not render a light or dark mode toggle", () => {
      render(<Sidebar />);

      expect(
        screen.queryByTitle(/Switch to (light|dark) mode/u),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /Switch to/u }),
      ).not.toBeInTheDocument();
    });

    it("keeps the document shell on the premium light class", () => {
      render(<Sidebar />);

      expect(document.documentElement.className).toBe("light");
    });
  });

  describe("keyboard shortcut hint", () => {
    it("shows keyboard shortcut hint when sidebar is open", () => {
      render(<Sidebar />);
      expect(screen.getByText("Search")).toBeInTheDocument();
    });

    it("hides keyboard shortcut hint when sidebar is collapsed", () => {
      useUIStore.setState({ sidebarOpen: false });
      render(<Sidebar />);
      expect(screen.queryByText("Search")).not.toBeInTheDocument();
    });
  });
});
