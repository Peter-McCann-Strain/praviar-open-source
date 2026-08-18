import { render } from "@testing-library/react";
import { beforeEach, describe, it, expect, vi } from "vitest";
import { ToastContainer } from "@/components/ui/toast";

const { mockUsePathname } = vi.hoisted(() => ({
  mockUsePathname: vi.fn(() => "/dashboard"),
}));

vi.mock("next/navigation", () => ({
  usePathname: mockUsePathname,
}));

vi.mock("@/stores/toast-store", () => ({
  useToastStore: vi.fn(() => ({
    toasts: [
      { id: "1", type: "success", message: "Analysis complete" },
      { id: "2", type: "error", message: "Failed to export" },
    ],
    removeToast: vi.fn(),
  })),
}));

describe("ToastContainer ARIA", () => {
  beforeEach(() => {
    mockUsePathname.mockReturnValue("/dashboard");
  });

  it("has aria-label on container", () => {
    const { container } = render(<ToastContainer />);
    const labeled = container.querySelector('[aria-label="Notifications"]');
    expect(labeled).toBeInTheDocument();
  });

  it("announces successful toasts politely and error toasts assertively", () => {
    const { container } = render(<ToastContainer />);

    const politeStatus = container.querySelector(
      '[role="status"][aria-live="polite"]',
    );
    const assertiveAlert = container.querySelector(
      '[role="alert"][aria-live="assertive"]',
    );

    expect(politeStatus).toHaveTextContent("Analysis complete");
    expect(assertiveAlert).toHaveTextContent("Failed to export");
  });

  it("has aria-atomic on individual toasts", () => {
    const { container } = render(<ToastContainer />);
    const atomicElements = container.querySelectorAll('[aria-atomic="true"]');
    expect(atomicElements.length).toBe(2);
  });

  it("has aria-label on close buttons", () => {
    const { container } = render(<ToastContainer />);
    const closeButtons = container.querySelectorAll(
      '[aria-label="Close notification"]',
    );
    expect(closeButtons.length).toBe(2);
    closeButtons.forEach((button) => {
      expect(button).toHaveClass("min-h-11", "min-w-11");
      expect(button).toHaveAttribute("type", "button");
    });
  });

  it("keeps close buttons outside toast live regions", () => {
    const { container } = render(<ToastContainer />);
    const closeButtons = container.querySelectorAll(
      '[aria-label="Close notification"]',
    );

    closeButtons.forEach((button) => {
      expect(button.closest('[role="status"], [role="alert"]')).toBeNull();
    });
  });

  it("moves mobile report toasts above the report command bar", () => {
    mockUsePathname.mockReturnValue("/analyses/ana_demo_001/report");

    const { container } = render(<ToastContainer />);
    const labeled = container.querySelector('[aria-label="Notifications"]');

    expect(labeled?.className).toContain(
      "bottom-[calc(10.75rem+env(safe-area-inset-bottom))]",
    );
    expect(labeled?.className).toContain("sm:bottom-6");
  });

  it("keeps mobile workspace toasts clear of bottom confirmation actions", () => {
    const { container } = render(<ToastContainer />);
    const labeled = container.querySelector('[aria-label="Notifications"]');

    expect(labeled?.className).toContain(
      "top-[calc(4.75rem+env(safe-area-inset-top))]",
    );
    expect(labeled?.className).toContain("sm:bottom-6");
    expect(labeled?.className).toContain("sm:top-auto");
  });
});
