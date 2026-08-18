import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  ONBOARDING_TOUR_STORAGE_KEY,
  WELCOME_MODAL_STORAGE_KEY,
} from "@/components/shared/welcome-modal-constants";
import {
  onboardingStorageKeys,
  TEST_ONBOARDING_IDENTITY,
} from "@/lib/onboarding-storage";

const TEST_STORAGE_KEYS = onboardingStorageKeys(TEST_ONBOARDING_IDENTITY);

if (!TEST_STORAGE_KEYS) {
  throw new Error("Test onboarding identity must produce scoped keys");
}

const navigationState = vi.hoisted(() => ({
  pathname: "/",
  push: vi.fn(),
}));
const principalState = vi.hoisted(() => ({
  canCreateAnalysis: true,
}));

vi.mock("next/navigation", () => ({
  usePathname: () => navigationState.pathname,
  useRouter: () => ({
    push: navigationState.push,
  }),
}));

vi.mock("motion/react", () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
  motion: {
    div: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
      <div {...props}>{children}</div>
    ),
  },
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "token",
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  usePrincipalCapabilities: () => ({
    data: {
      can_create_analysis: principalState.canCreateAnalysis,
    },
  }),
}));

import { WelcomeModal } from "@/components/shared/welcome-modal";

describe("WelcomeModal", () => {
  beforeEach(() => {
    navigationState.pathname = "/";
    navigationState.push.mockClear();
    principalState.canCreateAnalysis = true;
    localStorage.clear();
  });

  it("opens automatically when the welcome flag is missing", async () => {
    render(<WelcomeModal />);

    expect(await screen.findByText("Step 1 of 3")).toBeInTheDocument();
    expect(document.querySelector("[data-praviar-mark-frame]")).toBeTruthy();
    expect(
      screen.getByRole("heading", {
        level: 3,
        name: "Welcome to Praviar",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Praviar first-run briefing")).toBeInTheDocument();
    expect(screen.getByTestId("welcome-packet-preview")).toHaveTextContent(
      "Sample FTO packet",
    );
    expect(screen.getByTestId("welcome-packet-preview")).toHaveTextContent(
      "Not a legal opinion",
    );
    expect(screen.getByTestId("welcome-packet-preview")).toHaveTextContent(
      "Example Molecule Alpha",
    );
    expect(screen.queryByText(/succinic acid/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/US0000000001A1/i)).not.toBeInTheDocument();
  });

  it("uses the explicit skip action instead of the generic dialog close control", async () => {
    render(<WelcomeModal forceOpen />);

    expect(await screen.findByText("Step 1 of 3")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Skip tour" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Close first-run briefing" }),
    ).toHaveClass("h-11", "w-11");
    expect(screen.getByRole("button", { name: "Go to step 1" })).toHaveClass(
      "h-11",
      "w-11",
    );
    expect(screen.getByRole("dialog")).toHaveClass("[&>button]:hidden");
  });

  it("stays closed after the welcome flag is set", () => {
    localStorage.setItem(TEST_STORAGE_KEYS.welcome, "true");

    render(<WelcomeModal />);

    expect(screen.queryByText("Step 1 of 3")).not.toBeInTheDocument();
  });

  it("does not let an unscoped legacy flag suppress scoped onboarding", async () => {
    localStorage.setItem(WELCOME_MODAL_STORAGE_KEY, "true");

    render(<WelcomeModal />);

    expect(await screen.findByText("Step 1 of 3")).toBeInTheDocument();
    expect(localStorage.getItem(WELCOME_MODAL_STORAGE_KEY)).toBeNull();
  });

  it("stays closed on report routes when suppression is enabled", () => {
    navigationState.pathname = "/analyses/demo/report";

    render(<WelcomeModal suppressReportRoutes />);

    expect(screen.queryByText("Step 1 of 3")).not.toBeInTheDocument();
    expect(localStorage.getItem(WELCOME_MODAL_STORAGE_KEY)).toBeNull();
  });

  it("stays closed on billing routes when suppression is enabled", () => {
    navigationState.pathname = "/billing";

    render(<WelcomeModal suppressBillingRoutes />);

    expect(screen.queryByText("Step 1 of 3")).not.toBeInTheDocument();
    expect(localStorage.getItem(WELCOME_MODAL_STORAGE_KEY)).toBeNull();
  });

  it("does not interrupt the analysis launch route", () => {
    navigationState.pathname = "/analyses/new";

    render(<WelcomeModal />);

    expect(screen.queryByText("Step 1 of 3")).not.toBeInTheDocument();
    expect(localStorage.getItem(WELCOME_MODAL_STORAGE_KEY)).toBeNull();
  });

  it("stays closed when the principal cannot create analyses", () => {
    principalState.canCreateAnalysis = false;

    render(<WelcomeModal forceOpen />);

    expect(screen.queryByText("Step 1 of 3")).not.toBeInTheDocument();
    expect(navigationState.push).not.toHaveBeenCalled();
  });

  it("stays closed on control-plane routes when suppression is enabled", () => {
    navigationState.pathname = "/admin/analytics";

    render(<WelcomeModal suppressControlPlaneRoutes />);

    expect(screen.queryByText("Step 1 of 3")).not.toBeInTheDocument();
    expect(localStorage.getItem(WELCOME_MODAL_STORAGE_KEY)).toBeNull();
  });

  it("stays closed on showcase routes when suppression is enabled", () => {
    navigationState.pathname = "/capabilities";

    render(<WelcomeModal suppressShowcaseRoutes />);

    expect(screen.queryByText("Step 1 of 3")).not.toBeInTheDocument();
    expect(localStorage.getItem(WELCOME_MODAL_STORAGE_KEY)).toBeNull();
  });

  it("navigates between steps and supports direct step clicks", async () => {
    render(<WelcomeModal forceOpen />);

    expect(await screen.findByText("Step 1 of 3")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Step 2 of 3")).toBeInTheDocument();
    expect(screen.getByText("Run Your First Analysis")).toBeInTheDocument();
    expect(screen.getByTestId("welcome-launch-preview")).toContainHTML(
      "data-praviar-mark-frame",
    );
    expect(screen.getByTestId("welcome-launch-preview")).toHaveTextContent(
      "Evidence path prepared",
    );

    fireEvent.click(screen.getByRole("button", { name: "Go to step 3" }));
    expect(await screen.findByText("Step 3 of 3")).toBeInTheDocument();
    expect(screen.getByText("Explore Your Report")).toBeInTheDocument();
    expect(screen.getByTestId("welcome-report-preview")).toHaveTextContent(
      "Review context",
    );

    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(await screen.findByText("Step 2 of 3")).toBeInTheDocument();
  });

  it("persists the welcome flag when the user skips the tour", async () => {
    render(<WelcomeModal forceOpen />);

    // Skipping is an explicit dismissal: the flag is persisted directly,
    // with no separate "don't show again" checkbox.
    fireEvent.click(await screen.findByRole("button", { name: "Skip tour" }));

    await waitFor(() => {
      expect(screen.queryByText("Step 1 of 3")).not.toBeInTheDocument();
      expect(localStorage.getItem(TEST_STORAGE_KEYS.welcome)).toBe("true");
      expect(localStorage.getItem(TEST_STORAGE_KEYS.tour)).toBe("true");
      expect(localStorage.getItem(WELCOME_MODAL_STORAGE_KEY)).toBeNull();
      expect(localStorage.getItem(ONBOARDING_TOUR_STORAGE_KEY)).toBeNull();
    });
  });

  it("always persists the welcome flag when the user finishes onboarding", async () => {
    render(<WelcomeModal forceOpen />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Go to step 3" }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Start analysis" }),
    );

    await waitFor(() => {
      expect(screen.queryByText("Step 3 of 3")).not.toBeInTheDocument();
      expect(localStorage.getItem(TEST_STORAGE_KEYS.welcome)).toBe("true");
      expect(localStorage.getItem(TEST_STORAGE_KEYS.tour)).toBe("true");
      expect(navigationState.push).toHaveBeenCalledWith("/analyses/new");
    });
  });
});
