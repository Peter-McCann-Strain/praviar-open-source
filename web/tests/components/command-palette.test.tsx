import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Track router.push calls
const mockPush = vi.fn();
const authTokenState = vi.hoisted(() => ({
  token: "test-token" as string | null,
}));
const principalState = vi.hoisted(() => ({
  role: "admin" as "admin" | "attorney" | "scientist" | "client",
  riskRatingsRestricted: false,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/",
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => authTokenState.token,
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  usePrincipalCapabilities: () => ({
    data: {
      role: principalState.role,
      can_create_analysis: principalState.role !== "client",
      risk_ratings_restricted: principalState.riskRatingsRestricted,
    },
    isLoading: false,
    isError: false,
  }),
}));

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ isLoaded: true, orgRole: "org:admin" }),
}));

const mockAnalysesData = {
  items: [
    {
      id: "a1",
      compound_name: "Aspirin",
      status: "completed",
      overall_risk: "high",
    },
    {
      id: "a2",
      compound_name: "Ibuprofen",
      status: "running",
      overall_risk: "low",
    },
  ],
  total: 2,
};

vi.mock("@/hooks/use-analysis", () => ({
  useAnalyses: () => ({
    data: mockAnalysesData,
    isLoading: false,
    isSuccess: true,
  }),
}));

// Mock the Command UI components to be simpler for testing
vi.mock("@/components/ui/command", () => ({
  CommandDialog: ({ children, open, onOpenChange }: any) => {
    if (!open) return null;
    return (
      <div data-testid="command-dialog" role="dialog">
        <button data-testid="close-dialog" onClick={() => onOpenChange(false)}>
          Close
        </button>
        {children}
      </div>
    );
  },
  CommandInput: ({ placeholder }: any) => (
    <input data-testid="command-input" placeholder={placeholder} />
  ),
  CommandList: ({ children }: any) => (
    <div data-testid="command-list">{children}</div>
  ),
  CommandEmpty: ({ children }: any) => (
    <div data-testid="command-empty">{children}</div>
  ),
  CommandGroup: ({ heading, children }: any) => (
    <div
      data-testid={`command-group-${heading?.toLowerCase().replace(/\s/g, "-")}`}
    >
      <span>{heading}</span>
      {children}
    </div>
  ),
  CommandItem: ({ children, onSelect, value, keywords }: any) => {
    return (
      <div
        data-value={value}
        data-keywords={keywords?.join(" ")}
        role="option"
        aria-selected={false}
        onClick={() => onSelect?.()}
      >
        {children}
      </div>
    );
  },
  CommandSeparator: () => <hr />,
}));

// Mock lucide-react icons
vi.mock("lucide-react", () => {
  const IconStub = ({ children, className }: any) => (
    <svg className={className}>{children}</svg>
  );
  return {
    LayoutDashboard: IconStub,
    FileSearch: IconStub,
    HelpCircle: IconStub,
    SlidersHorizontal: IconStub,
    BarChart3: IconStub,
    CreditCard: IconStub,
    Key: IconStub,
    Layers: IconStub,
    LibraryBig: IconStub,
    Radar: IconStub,
    ScrollText: IconStub,
    Shield: IconStub,
    Plus: IconStub,
    ClipboardCheck: IconStub,
    Compass: IconStub,
    Clock: IconStub,
  };
});

import {
  CommandPalette,
  CommandPaletteContent,
} from "@/components/shared/command-palette";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children,
    );
  };
}

describe("CommandPalette", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authTokenState.token = "test-token";
    principalState.role = "admin";
    principalState.riskRatingsRestricted = false;
  });

  it("does not render dialog initially (closed state)", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <CommandPalette />
      </Wrapper>,
    );

    expect(screen.queryByTestId("command-dialog")).not.toBeInTheDocument();
  });

  it("opens dialog on Cmd+K keyboard shortcut", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <CommandPalette />
      </Wrapper>,
    );

    fireEvent.keyDown(document, { key: "k", metaKey: true });

    expect(screen.getByTestId("command-dialog")).toBeInTheDocument();
  });

  it("opens dialog on Ctrl+K keyboard shortcut", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <CommandPalette />
      </Wrapper>,
    );

    fireEvent.keyDown(document, { key: "k", ctrlKey: true });

    expect(screen.getByTestId("command-dialog")).toBeInTheDocument();
  });

  it("toggles dialog closed on second Cmd+K press", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <CommandPalette />
      </Wrapper>,
    );

    // Open
    fireEvent.keyDown(document, { key: "k", metaKey: true });
    expect(screen.getByTestId("command-dialog")).toBeInTheDocument();

    // Close
    fireEvent.keyDown(document, { key: "k", metaKey: true });
    expect(screen.queryByTestId("command-dialog")).not.toBeInTheDocument();
  });

  it("does not open on just 'k' without meta/ctrl key", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <CommandPalette />
      </Wrapper>,
    );

    fireEvent.keyDown(document, { key: "k" });

    expect(screen.queryByTestId("command-dialog")).not.toBeInTheDocument();
  });

  it("renders navigation items when open", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <CommandPalette />
      </Wrapper>,
    );

    fireEvent.keyDown(document, { key: "k", metaKey: true });

    expect(screen.getByText("Workspace")).toBeInTheDocument();
    expect(screen.getByText("Decisions")).toBeInTheDocument();
    expect(screen.getByText("Operations")).toBeInTheDocument();
    expect(screen.getByText("Administration")).toBeInTheDocument();
    expect(screen.getByText("Support")).toBeInTheDocument();
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Analyses")).toBeInTheDocument();
    expect(screen.getByText("Compounds")).toBeInTheDocument();
    expect(screen.getByText("Patents")).toBeInTheDocument();
    expect(screen.getByText("Configuration")).toBeInTheDocument();
    expect(screen.getByText("Cost & Usage")).toBeInTheDocument();
    expect(screen.getByText("Help")).toBeInTheDocument();
  });

  it("shows read-only billing but not privileged administration destinations to members", () => {
    principalState.role = "scientist";
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <CommandPaletteContent orgRole="org:member" />
      </Wrapper>,
    );

    fireEvent.keyDown(document, { key: "k", metaKey: true });

    expect(screen.getByText("Credits & Billing")).toBeInTheDocument();
    expect(screen.queryByText("Settings")).not.toBeInTheDocument();
    expect(screen.queryByText("Platform Admin")).not.toBeInTheDocument();
    expect(screen.queryByText("Cost & Usage")).not.toBeInTheDocument();
    expect(screen.getByText("Compounds")).toBeInTheDocument();
    expect(screen.getByText("Patents")).toBeInTheDocument();
    expect(screen.getByText("Review Queue")).toBeInTheDocument();
    expect(screen.queryByText("Configuration")).not.toBeInTheDocument();
  });

  it("keeps client navigation and actions read-only", () => {
    principalState.role = "client";
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <CommandPaletteContent orgRole="org:member" />
      </Wrapper>,
    );

    fireEvent.keyDown(document, { key: "k", metaKey: true });

    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Analyses")).toBeInTheDocument();
    expect(screen.getByText("Compounds")).toBeInTheDocument();
    expect(screen.getByText("Workflow Atlas")).toBeInTheDocument();
    expect(screen.getByText("Help")).toBeInTheDocument();
    expect(screen.queryByText("Patents")).not.toBeInTheDocument();
    expect(screen.queryByText("Review Queue")).not.toBeInTheDocument();
    expect(screen.queryByText("New FTO Analysis")).not.toBeInTheDocument();
  });

  it("renders recent analyses section with compound names", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <CommandPalette />
      </Wrapper>,
    );

    fireEvent.keyDown(document, { key: "k", metaKey: true });

    expect(screen.getByText("Recent Analyses")).toBeInTheDocument();
    expect(screen.getByText("Aspirin")).toBeInTheDocument();
    expect(screen.getByText("Ibuprofen")).toBeInTheDocument();
  });

  it("does not render cached recent analyses when auth is missing", () => {
    authTokenState.token = null;
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <CommandPalette />
      </Wrapper>,
    );

    fireEvent.keyDown(document, { key: "k", metaKey: true });

    expect(screen.queryByText("Recent Analyses")).not.toBeInTheDocument();
    expect(screen.queryByText("Aspirin")).not.toBeInTheDocument();
    expect(screen.queryByText("Ibuprofen")).not.toBeInTheDocument();
  });

  it("renders actions section with New FTO Analysis and Review Queue", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <CommandPalette />
      </Wrapper>,
    );

    fireEvent.keyDown(document, { key: "k", metaKey: true });

    expect(screen.getByText("Actions")).toBeInTheDocument();
    expect(screen.getByText("New FTO Analysis")).toBeInTheDocument();
    expect(screen.getByText("Review Queue")).toBeInTheDocument();
    expect(screen.getByText("Workflow Atlas")).toBeInTheDocument();
    expect(screen.queryByText("Quick Check")).not.toBeInTheDocument();
  });

  it("navigates to /dashboard when Dashboard is selected", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <CommandPalette />
      </Wrapper>,
    );

    fireEvent.keyDown(document, { key: "k", metaKey: true });
    fireEvent.click(screen.getByText("Dashboard").closest('[role="option"]')!);

    expect(mockPush).toHaveBeenCalledWith("/dashboard");
  });

  it("navigates to analysis detail when a recent analysis is selected", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <CommandPalette />
      </Wrapper>,
    );

    fireEvent.keyDown(document, { key: "k", metaKey: true });

    fireEvent.click(screen.getByText("Aspirin").closest('[role="option"]')!);

    expect(mockPush).toHaveBeenCalledWith("/analyses/a1");
  });

  it("navigates to /analyses/new when New FTO Analysis is selected", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <CommandPalette />
      </Wrapper>,
    );

    fireEvent.keyDown(document, { key: "k", metaKey: true });
    fireEvent.click(
      screen.getByText("New FTO Analysis").closest('[role="option"]')!,
    );

    expect(mockPush).toHaveBeenCalledWith("/analyses/new");
  });

  it("navigates to /reviews when Review Queue is selected", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <CommandPalette />
      </Wrapper>,
    );

    fireEvent.keyDown(document, { key: "k", metaKey: true });
    fireEvent.click(
      screen.getByText("Review Queue").closest('[role="option"]')!,
    );

    expect(mockPush).toHaveBeenCalledWith("/reviews");
  });

  it("closes dialog after navigation command is executed", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <CommandPalette />
      </Wrapper>,
    );

    fireEvent.keyDown(document, { key: "k", metaKey: true });
    expect(screen.getByTestId("command-dialog")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Dashboard").closest('[role="option"]')!);

    // Dialog should close after command execution
    expect(screen.queryByTestId("command-dialog")).not.toBeInTheDocument();
  });

  it("renders risk level labels for recent analyses", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <CommandPalette />
      </Wrapper>,
    );

    fireEvent.keyDown(document, { key: "k", metaKey: true });

    // Risk levels shown as uppercase text
    expect(screen.getByText("high")).toBeInTheDocument();
    expect(screen.getByText("low")).toBeInTheDocument();
  });

  it("labels governed risk as counsel only instead of missing or zero", () => {
    principalState.role = "client";
    principalState.riskRatingsRestricted = true;
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <CommandPaletteContent orgRole="org:member" />
      </Wrapper>,
    );

    fireEvent.keyDown(document, { key: "k", metaKey: true });

    const governedLabels = screen.getAllByText("Counsel only");
    expect(governedLabels).toHaveLength(2);
    for (const label of governedLabels) {
      expect(label).toHaveClass("text-warning");
      expect(label).not.toHaveClass("text-error");
    }
    expect(screen.queryByText("high")).not.toBeInTheDocument();
    expect(screen.queryByText("low")).not.toBeInTheDocument();
    expect(screen.queryByText("N/A")).not.toBeInTheDocument();
  });

  it("renders status labels for recent analyses", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <CommandPalette />
      </Wrapper>,
    );

    fireEvent.keyDown(document, { key: "k", metaKey: true });

    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.getByText("Running")).toBeInTheDocument();
  });

  it("cleans up keydown listener on unmount", () => {
    const Wrapper = createWrapper();
    const removeEventListenerSpy = vi.spyOn(document, "removeEventListener");

    const { unmount } = render(
      <Wrapper>
        <CommandPalette />
      </Wrapper>,
    );

    unmount();

    expect(removeEventListenerSpy).toHaveBeenCalledWith(
      "keydown",
      expect.any(Function),
    );
    removeEventListenerSpy.mockRestore();
  });
});
