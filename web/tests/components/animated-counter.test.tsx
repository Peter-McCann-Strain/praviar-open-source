import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { AnimatedCounter } from "@/components/shared/animated-counter";

const mockUseReducedMotion = vi.fn(() => false);

vi.mock("motion/react", () => ({
  useReducedMotion: () => mockUseReducedMotion(),
}));

describe("AnimatedCounter", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockUseReducedMotion.mockReturnValue(false);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe("renders the target value", () => {
    it("displays the target value after animation completes", () => {
      // Mock requestAnimationFrame to run immediately with high elapsed time
      let rafCallback: ((time: number) => void) | null = null;
      const mockRaf = vi
        .spyOn(window, "requestAnimationFrame")
        .mockImplementation((cb) => {
          rafCallback = cb;
          return 1;
        });

      const mockNow = vi.spyOn(performance, "now").mockReturnValue(0);

      render(<AnimatedCounter value={42} duration={1000} />);

      // Simulate animation completion by calling raf with time > duration
      act(() => {
        if (rafCallback) {
          mockNow.mockReturnValue(2000); // Well past duration
          rafCallback(2000);
        }
      });

      expect(screen.getByText("42")).toBeInTheDocument();
      expect(screen.getByText("42")).toHaveAttribute(
        "data-praviar-counter-state",
        "settled",
      );

      mockRaf.mockRestore();
      mockNow.mockRestore();
    });
  });

  describe("renders with prefix and suffix", () => {
    it("displays prefix and suffix around the value", () => {
      let rafCallback: ((time: number) => void) | null = null;
      const mockRaf = vi
        .spyOn(window, "requestAnimationFrame")
        .mockImplementation((cb) => {
          rafCallback = cb;
          return 1;
        });
      const mockNow = vi.spyOn(performance, "now").mockReturnValue(0);

      render(
        <AnimatedCounter value={100} prefix="$" suffix="k" duration={1000} />,
      );

      act(() => {
        if (rafCallback) {
          mockNow.mockReturnValue(2000);
          rafCallback(2000);
        }
      });

      expect(screen.getByText("$100k")).toBeInTheDocument();

      mockRaf.mockRestore();
      mockNow.mockRestore();
    });
  });

  describe("renders with decimals", () => {
    it("displays the value with specified decimal places", () => {
      let rafCallback: ((time: number) => void) | null = null;
      const mockRaf = vi
        .spyOn(window, "requestAnimationFrame")
        .mockImplementation((cb) => {
          rafCallback = cb;
          return 1;
        });
      const mockNow = vi.spyOn(performance, "now").mockReturnValue(0);

      render(<AnimatedCounter value={3.14} decimals={2} duration={1000} />);

      act(() => {
        if (rafCallback) {
          mockNow.mockReturnValue(2000);
          rafCallback(2000);
        }
      });

      expect(screen.getByText("3.14")).toBeInTheDocument();

      mockRaf.mockRestore();
      mockNow.mockRestore();
    });
  });

  describe("starts from 0", () => {
    it("initially renders 0 before animation", () => {
      // Don't call requestAnimationFrame callbacks — capture initial state
      vi.spyOn(window, "requestAnimationFrame").mockImplementation(() => 1);

      render(<AnimatedCounter value={100} duration={1000} />);

      // Initially the display state is 0 (Math.round(0) = 0)
      expect(screen.getByText("0")).toBeInTheDocument();

      vi.mocked(window.requestAnimationFrame).mockRestore();
    });
  });

  describe("element attributes", () => {
    it("renders a span element", () => {
      vi.spyOn(window, "requestAnimationFrame").mockImplementation(() => 1);

      const { container } = render(
        <AnimatedCounter value={50} duration={1000} />,
      );

      const span = container.querySelector("span");
      expect(span).toBeInTheDocument();
      expect(span).toHaveAttribute("data-praviar-counter-target", "50");

      vi.mocked(window.requestAnimationFrame).mockRestore();
    });

    it("applies animate-count-up class when motion is allowed", () => {
      vi.spyOn(window, "requestAnimationFrame").mockImplementation(() => 1);

      const { container } = render(
        <AnimatedCounter value={50} duration={1000} />,
      );

      const span = container.querySelector("span");
      expect(span?.className).toContain("animate-count-up");

      vi.mocked(window.requestAnimationFrame).mockRestore();
    });

    it("renders the target immediately without animation when reduced motion is preferred", () => {
      mockUseReducedMotion.mockReturnValue(true);
      const mockRaf = vi.spyOn(window, "requestAnimationFrame");

      const { container } = render(
        <AnimatedCounter value={50} duration={1000} />,
      );

      expect(screen.getByText("50")).toBeInTheDocument();
      expect(container.querySelector("span")).not.toHaveClass(
        "animate-count-up",
      );
      expect(container.querySelector("span")).toHaveAttribute(
        "data-praviar-counter-state",
        "settled",
      );
      expect(mockRaf).not.toHaveBeenCalled();

      mockRaf.mockRestore();
    });

    it("settles immediately when animation duration is disabled", () => {
      const mockRaf = vi.spyOn(window, "requestAnimationFrame");

      render(<AnimatedCounter value={73} duration={0} suffix="%" />);

      expect(screen.getByText("73%")).toHaveAttribute(
        "data-praviar-counter-state",
        "settled",
      );
      expect(mockRaf).not.toHaveBeenCalled();
      mockRaf.mockRestore();
    });

    it("cancels the prior frame and animates prop changes from the displayed value", () => {
      const callbacks = new Map<number, FrameRequestCallback>();
      let nextFrame = 0;
      const mockRaf = vi
        .spyOn(window, "requestAnimationFrame")
        .mockImplementation((callback) => {
          nextFrame += 1;
          callbacks.set(nextFrame, callback);
          return nextFrame;
        });
      const mockCancel = vi
        .spyOn(window, "cancelAnimationFrame")
        .mockImplementation((frame) => {
          callbacks.delete(frame);
        });
      const mockNow = vi.spyOn(performance, "now").mockReturnValue(0);

      const { rerender } = render(
        <AnimatedCounter value={100} duration={1000} />,
      );
      act(() => callbacks.get(1)?.(500));
      expect(screen.getByText("88")).toHaveAttribute(
        "data-praviar-counter-state",
        "animating",
      );

      mockNow.mockReturnValue(500);
      rerender(<AnimatedCounter value={200} duration={1000} />);
      expect(mockCancel).toHaveBeenCalled();
      expect(screen.getByText("88")).not.toHaveAttribute(
        "data-praviar-counter-state",
        "settled",
      );
      act(() => callbacks.get(nextFrame)?.(1500));
      expect(screen.getByText("200")).toHaveAttribute(
        "data-praviar-counter-state",
        "settled",
      );

      mockRaf.mockRestore();
      mockCancel.mockRestore();
      mockNow.mockRestore();
    });

    it("cancels the scheduled frame on unmount", () => {
      vi.spyOn(window, "requestAnimationFrame").mockImplementation(() => 17);
      const mockCancel = vi.spyOn(window, "cancelAnimationFrame");

      const { unmount } = render(
        <AnimatedCounter value={50} duration={1000} />,
      );
      unmount();

      expect(mockCancel).toHaveBeenCalledWith(17);
      vi.mocked(window.requestAnimationFrame).mockRestore();
      mockCancel.mockRestore();
    });
  });
});
