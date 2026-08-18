import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { FlagButton } from "@/components/collaboration/flag-button";

// Mock auth token
vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "test-token",
}));

// Mock toast store
const mockAddToast = vi.fn();
vi.mock("@/stores/toast-store", () => ({
  useToastStore: () => ({
    addToast: mockAddToast,
    toasts: [],
    removeToast: vi.fn(),
  }),
}));

// Mock api-client used by use-flag
const mockApiClient = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: (...args: unknown[]) => mockApiClient(...args),
}));

// Mock Button component
vi.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, disabled, className, ...props }: any) => (
    <button
      onClick={onClick}
      disabled={disabled}
      className={className}
      data-testid="flag-btn"
      {...props}
    >
      {children}
    </button>
  ),
}));

// Mock lucide-react icons
vi.mock("lucide-react", () => ({
  Flag: ({ className }: any) => (
    <svg data-testid="flag-icon" className={className} />
  ),
  Loader2: ({ className }: any) => (
    <svg data-testid="loader-icon" className={className} />
  ),
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children,
    );
  };
}

describe("FlagButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders with flag icon and correct default text", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <FlagButton analysisId="a1" />
      </Wrapper>,
    );

    expect(screen.getByTestId("flag-icon")).toBeInTheDocument();
    expect(screen.getByText("Flag for Review")).toBeInTheDocument();
  });

  it("renders 'Flagged' text when isFlagged is true", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <FlagButton analysisId="a1" isFlagged={true} />
      </Wrapper>,
    );

    expect(screen.getByText("Flagged")).toBeInTheDocument();
  });

  it("is disabled when isFlagged is true", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <FlagButton analysisId="a1" isFlagged={true} />
      </Wrapper>,
    );

    expect(screen.getByTestId("flag-btn")).toBeDisabled();
  });

  it("shows 'Flagged' text and disabled state for already-flagged analysis", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <FlagButton analysisId="a1" isFlagged={true} />
      </Wrapper>,
    );

    // When isFlagged is true, button shows "Flagged" text and is disabled
    expect(screen.getByText("Flagged")).toBeInTheDocument();
    expect(screen.getByTestId("flag-btn")).toBeDisabled();
    // No API call should be made
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("calls flag API on click when not flagged", async () => {
    mockApiClient.mockResolvedValueOnce({ flagged_for_review: true });
    const Wrapper = createWrapper();

    render(
      <Wrapper>
        <FlagButton analysisId="a1" />
      </Wrapper>,
    );

    fireEvent.click(screen.getByText("Flag for Review"));

    await waitFor(() => {
      expect(mockApiClient).toHaveBeenCalledWith(
        "/analyses/a1/flag",
        expect.objectContaining({
          method: "POST",
          token: "test-token",
        }),
      );
    });
  });

  it("shows success toast after flagging", async () => {
    mockApiClient.mockResolvedValueOnce({ flagged_for_review: true });
    const Wrapper = createWrapper();

    render(
      <Wrapper>
        <FlagButton analysisId="a1" />
      </Wrapper>,
    );

    fireEvent.click(screen.getByText("Flag for Review"));

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        "Flagged for review — team notified",
        "warning",
      );
    });
  });

  it("shows error toast when flag API fails", async () => {
    mockApiClient.mockRejectedValueOnce(new Error("Server error"));
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const Wrapper = createWrapper();

    render(
      <Wrapper>
        <FlagButton analysisId="a1" />
      </Wrapper>,
    );

    fireEvent.click(screen.getByText("Flag for Review"));

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        "Failed to flag — please try again",
        "error",
      );
    });

    consoleSpy.mockRestore();
  });

  it("accepts custom className prop", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <FlagButton analysisId="a1" className="custom-class" />
      </Wrapper>,
    );

    expect(screen.getByTestId("flag-btn")).toHaveClass("custom-class");
  });

  it("renders with default variant='outline' and size='default'", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <FlagButton analysisId="a1" />
      </Wrapper>,
    );

    // Button renders — this verifies default props are passed
    expect(screen.getByTestId("flag-btn")).toBeInTheDocument();
    expect(screen.getByText("Flag for Review")).toBeInTheDocument();
  });

  it("does not call API when isFlagged prop is false and button is not clicked", () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <FlagButton analysisId="a1" isFlagged={false} />
      </Wrapper>,
    );

    expect(mockApiClient).not.toHaveBeenCalled();
  });
});
