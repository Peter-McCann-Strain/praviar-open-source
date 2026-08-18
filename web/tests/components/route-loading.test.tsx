import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import NewLoading from "@/app/(dashboard)/analyses/new/loading";
import QuickLoading from "@/app/(dashboard)/analyses/quick/loading";
import ConfigLoading from "@/app/(dashboard)/config/loading";
import HelpLoading from "@/app/(dashboard)/help/loading";
import PatentsLoading from "@/app/(dashboard)/patents/loading";
import ReportLoading from "@/app/(dashboard)/analyses/[id]/report/loading";
import DashboardLoading from "@/app/(dashboard)/dashboard/loading";

function expectPraviarLoadingFrame(container: HTMLElement) {
  const frame = container.querySelector("[data-praviar-route-loading-frame]");
  expect(frame).toBeTruthy();
  expect(frame).toHaveAttribute("role", "status");
  expect(frame).toHaveAttribute("aria-busy", "true");
  expect(frame).toHaveAttribute("aria-atomic", "true");
  expect(frame).toHaveClass("praviar-operational-field");
  expect(frame).not.toHaveClass("praviar-report-decision-field");
  expect(
    frame?.querySelector('svg[data-praviar-mark="praviar-evidence-mark"]'),
  ).toBeTruthy();
}

function expectWorkspaceLoadingState(container: HTMLElement, selector: string) {
  const frame = container.querySelector(selector);
  expect(frame).toBeTruthy();
  expect(frame).toHaveAttribute("role", "status");
  expect(frame).toHaveAttribute("aria-busy", "true");
  expect(frame).toHaveAttribute("aria-atomic", "true");
  expect(frame).toHaveAttribute("data-praviar-app-state", "loading");
}

// ---------------------------------------------------------------------------
// Detailed tests for the representative skeleton: analyses/new/loading
// ---------------------------------------------------------------------------
describe("NewLoading skeleton", () => {
  it("renders without crashing", () => {
    const { container } = render(<NewLoading />);
    expect(container.firstChild).toBeTruthy();
  });

  it("announces the loading state without relying on raw pulse animation", () => {
    const { container } = render(<NewLoading />);
    const root = container.firstChild as HTMLElement;
    expect(root).toHaveAttribute("role", "status");
    expect(root).toHaveAttribute("aria-busy", "true");
    expect(root.className).not.toContain("animate-pulse");
    expectPraviarLoadingFrame(container);
    expect(screen.getByText("Loading new analysis workspace")).toHaveClass(
      "sr-only",
    );
  });

  it("contains multiple shared shimmer skeleton placeholder elements", () => {
    const { container } = render(<NewLoading />);
    const skeletons = container.querySelectorAll(".skeleton-shimmer");
    // analyses/new has 5 skeleton blocks (title + 3 inputs + button)
    expect(skeletons.length).toBeGreaterThanOrEqual(4);
  });

  it("uses rounded-md for consistent skeleton styling", () => {
    const { container } = render(<NewLoading />);
    const rounded = container.querySelectorAll('[class*="rounded-"]');
    expect(rounded.length).toBeGreaterThan(0);
    // Every skeleton element should have a rounded class
    const skeletons = container.querySelectorAll(".skeleton-shimmer");
    skeletons.forEach((el) => {
      expect(el.className).toMatch(/rounded-/);
    });
  });

  it("keeps loading copy screen-reader only", () => {
    render(<NewLoading />);
    expect(screen.getByText("Loading new analysis workspace")).toHaveClass(
      "sr-only",
    );
  });
});

// ---------------------------------------------------------------------------
// Existence + render tests for all 4 loading files
// ---------------------------------------------------------------------------
describe("All route loading skeletons render", () => {
  it("analyses/new/loading exports a default function and renders", () => {
    expect(typeof NewLoading).toBe("function");
    const { container } = render(<NewLoading />);
    const root = container.firstChild as HTMLElement;
    expect(root).toBeTruthy();
    expect(root).toHaveAttribute("role", "status");
    expect(root).toHaveAttribute("aria-busy", "true");
    expectPraviarLoadingFrame(container);
  });

  it("analyses/quick/loading exports a default function and renders", () => {
    expect(typeof QuickLoading).toBe("function");
    const { container } = render(<QuickLoading />);
    const root = container.firstChild as HTMLElement;
    expect(root).toBeTruthy();
    expect(root).toHaveAttribute("role", "status");
    expect(root).toHaveAttribute("aria-busy", "true");
    expectPraviarLoadingFrame(container);
  });

  it("config/loading exports a default function and renders", () => {
    expect(typeof ConfigLoading).toBe("function");
    const { container } = render(<ConfigLoading />);
    const root = container.firstChild as HTMLElement;
    expect(root).toBeTruthy();
    expect(root).toHaveAttribute("role", "status");
    expect(root).toHaveAttribute("aria-busy", "true");
    expectPraviarLoadingFrame(container);
  });

  it("help/loading exports a default function and renders", () => {
    expect(typeof HelpLoading).toBe("function");
    const { container } = render(<HelpLoading />);
    const root = container.firstChild as HTMLElement;
    expect(root).toBeTruthy();
    expect(root).toHaveAttribute("role", "status");
    expect(root).toHaveAttribute("aria-busy", "true");
    expectPraviarLoadingFrame(container);
  });

  it("analyses/[id]/report/loading mirrors the stable report workspace shell", () => {
    expect(typeof ReportLoading).toBe("function");
    const { container } = render(<ReportLoading />);
    const root = container.firstChild as HTMLElement;
    expect(root).toBeTruthy();
    expectWorkspaceLoadingState(
      container,
      "[data-praviar-report-loading-workspace]",
    );
    expect(root).toHaveClass(
      "praviar-report-workspace",
      "max-w-[90rem]",
      "overflow-x-clip",
    );
    expect(
      container.querySelector("[data-praviar-route-loading-frame]"),
    ).not.toBeInTheDocument();
    expect(
      container.querySelector("[data-praviar-report-loading-identity]"),
    ).toBeInTheDocument();
    expect(
      container.querySelector("[data-praviar-report-loading-section-rail]"),
    ).toHaveClass("sticky", "top-14");
    expect(
      container.querySelector("[data-praviar-report-loading-command-rail]"),
    ).toHaveClass("sticky", "top-[6.25rem]", "sm:top-[6.75rem]", "lg:hidden");
    expect(
      container.querySelector("[data-praviar-report-loading-decision-brief]"),
    ).toBeInTheDocument();
    expect(
      container.querySelector(
        "[data-praviar-report-loading-readiness-disclosure]",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Loading report workspace")).toHaveClass("sr-only");
  });

  it("dashboard/loading mirrors the executive and legal workload composition", () => {
    expect(typeof DashboardLoading).toBe("function");
    const { container } = render(<DashboardLoading />);

    expectWorkspaceLoadingState(
      container,
      "[data-praviar-dashboard-loading-workspace]",
    );
    expect(
      container.querySelector("[data-praviar-route-loading-frame]"),
    ).not.toBeInTheDocument();
    expect(
      container.querySelector("[data-praviar-dashboard-loading-header]"),
    ).toHaveClass("praviar-dashboard-command-deck");
    expect(
      screen.getByTestId("dashboard-loading-today-workbench"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("dashboard-loading-executive-decision-brief"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("dashboard-loading-legal-review-disclosure"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("dashboard-loading-legal-workload"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("dashboard-loading-risk-docket-disclosure"),
    ).toBeInTheDocument();
    expect(screen.getByText("Loading dashboard workspace")).toHaveClass(
      "sr-only",
    );
  });

  it("all loading skeletons contain shared shimmer placeholder elements", () => {
    const components = [
      NewLoading,
      QuickLoading,
      ConfigLoading,
      HelpLoading,
      PatentsLoading,
      ReportLoading,
      DashboardLoading,
    ];
    components.forEach((Component) => {
      const { container } = render(<Component />);
      const skeletons = container.querySelectorAll(".skeleton-shimmer");
      expect(skeletons.length).toBeGreaterThan(0);
    });
  });

  it("all loading skeletons expose a status name for assistive technology", () => {
    render(
      <>
        <NewLoading />
        <QuickLoading />
        <ConfigLoading />
        <HelpLoading />
        <ReportLoading />
        <DashboardLoading />
      </>,
    );

    expect(screen.getByText("Loading new analysis workspace")).toHaveClass(
      "sr-only",
    );
    expect(screen.getByText("Loading quick analysis launcher")).toHaveClass(
      "sr-only",
    );
    expect(screen.getByText("Loading configuration workspace")).toHaveClass(
      "sr-only",
    );
    expect(screen.getByText("Loading help workspace")).toHaveClass("sr-only");
    expect(screen.getByText("Loading report workspace")).toHaveClass("sr-only");
    expect(screen.getByText("Loading dashboard workspace")).toHaveClass(
      "sr-only",
    );
  });

  it("patents loading uses mobile cards plus a desktop table without overflow-prone flex rows", () => {
    const { container } = render(<PatentsLoading />);

    expectPraviarLoadingFrame(container);
    expect(screen.getByText("Loading patent evidence library")).toHaveClass(
      "sr-only",
    );
    expect(
      screen.getByRole("region", { name: "Loading patent records" }),
    ).toBeInTheDocument();
    expect(container.querySelector(".md\\:hidden")).toBeTruthy();
    expect(container.querySelector(".hidden.md\\:block")).toBeTruthy();
  });
});
