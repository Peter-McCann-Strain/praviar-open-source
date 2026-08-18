import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { OnboardingTooltip } from "@/components/shared/onboarding-tooltip";
import {
  onboardingStorageKeys,
  TEST_ONBOARDING_IDENTITY,
} from "@/lib/onboarding-storage";

const TEST_STORAGE_KEYS = onboardingStorageKeys(TEST_ONBOARDING_IDENTITY);

if (!TEST_STORAGE_KEYS) {
  throw new Error("Test onboarding identity must produce scoped keys");
}

describe("OnboardingTooltip", () => {
  const mockMatchMedia = vi.fn();
  const step = {
    target: "[data-testid='tour-target']",
    title: "Tour step",
    description: "Tour description",
  };

  const attachTourTarget = () => {
    const target = document.createElement("div");
    target.setAttribute("data-testid", "tour-target");
    Object.defineProperty(target, "getBoundingClientRect", {
      value: () => ({
        bottom: 120,
        height: 40,
        left: 40,
        right: 240,
        top: 80,
        width: 200,
        x: 40,
        y: 80,
        toJSON: () => ({}),
      }),
      configurable: true,
    });
    Object.defineProperty(target, "scrollIntoView", {
      value: vi.fn(),
      configurable: true,
    });
    document.body.appendChild(target);
    return target;
  };

  beforeEach(() => {
    localStorage.clear();
    mockMatchMedia.mockReturnValue({
      matches: false,
      media: "(prefers-reduced-motion: reduce)",
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    });
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: mockMatchMedia,
    });
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    document.body.innerHTML = "";
  });

  it("starts after the delay when the tour has not been completed", async () => {
    attachTourTarget();
    localStorage.setItem(TEST_STORAGE_KEYS.welcome, "true");

    render(<OnboardingTooltip steps={[step]} />);

    expect(screen.queryByText("Tour step")).not.toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(800);
    });

    expect(screen.getByText("Tour step")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Tour step" })).toHaveClass(
      "w-[min(320px,calc(100vw-24px))]",
      "max-w-[calc(100vw-24px)]",
    );
    expect(screen.getByRole("button", { name: "Finish" })).toHaveFocus();
  });

  it("waits for the welcome modal to be dismissed before starting", async () => {
    attachTourTarget();

    render(<OnboardingTooltip steps={[step]} />);

    await act(async () => {
      vi.advanceTimersByTime(800);
    });
    expect(screen.queryByText("Tour step")).not.toBeInTheDocument();

    localStorage.setItem(TEST_STORAGE_KEYS.welcome, "true");
    await act(async () => {
      vi.advanceTimersByTime(250);
      vi.advanceTimersByTime(800);
    });

    expect(screen.getByText("Tour step")).toBeInTheDocument();
  });

  it("ignores hidden matching targets and uses the visible target", async () => {
    vi.useRealTimers();
    localStorage.setItem(TEST_STORAGE_KEYS.welcome, "true");

    const hiddenTarget = attachTourTarget();
    Object.defineProperty(hiddenTarget, "getBoundingClientRect", {
      value: () => ({
        bottom: 40,
        height: 40,
        left: -300,
        right: -100,
        top: 0,
        width: 200,
        x: -300,
        y: 0,
        toJSON: () => ({}),
      }),
      configurable: true,
    });
    const visibleTarget = attachTourTarget();
    const visibleScroll = vi.fn();
    Object.defineProperty(visibleTarget, "scrollIntoView", {
      value: visibleScroll,
      configurable: true,
    });

    render(<OnboardingTooltip steps={[step]} />);

    expect(await screen.findByText("Tour step")).toBeInTheDocument();
    expect(visibleScroll).toHaveBeenCalled();
  });

  it("waits for missing targets without marking the tour complete", async () => {
    localStorage.setItem(TEST_STORAGE_KEYS.welcome, "true");
    const onSkip = vi.fn();

    render(<OnboardingTooltip steps={[step]} forceStart onSkip={onSkip} />);

    await act(async () => {
      vi.advanceTimersByTime(250);
    });

    expect(screen.queryByText("Tour step")).not.toBeInTheDocument();
    expect(onSkip).not.toHaveBeenCalled();
    expect(localStorage.getItem(TEST_STORAGE_KEYS.tour)).toBeNull();

    attachTourTarget();

    await act(async () => {
      vi.advanceTimersByTime(250);
    });

    expect(screen.getByText("Tour step")).toBeInTheDocument();
    expect(localStorage.getItem(TEST_STORAGE_KEYS.tour)).toBeNull();
  });

  it("scrolls the target into view and completes the tour", async () => {
    vi.useRealTimers();

    const scrollIntoView = vi.fn();
    const target = attachTourTarget();
    Object.defineProperty(target, "scrollIntoView", {
      value: scrollIntoView,
      configurable: true,
    });

    const onComplete = vi.fn();

    render(
      <OnboardingTooltip steps={[step]} forceStart onComplete={onComplete} />,
    );

    expect(await screen.findByText("Tour step")).toBeInTheDocument();
    expect(scrollIntoView).toHaveBeenCalledWith({
      behavior: "smooth",
      block: "nearest",
    });

    fireEvent.click(screen.getByRole("button", { name: "Finish" }));

    await waitFor(() => {
      expect(localStorage.getItem(TEST_STORAGE_KEYS.tour)).toBe("true");
      expect(onComplete).toHaveBeenCalledTimes(1);
    });
  });

  it("uses instant scroll when reduced motion is preferred", async () => {
    vi.useRealTimers();
    mockMatchMedia.mockReturnValue({
      matches: true,
      media: "(prefers-reduced-motion: reduce)",
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    });

    const scrollIntoView = vi.fn();
    const target = attachTourTarget();
    Object.defineProperty(target, "scrollIntoView", {
      value: scrollIntoView,
      configurable: true,
    });

    render(<OnboardingTooltip steps={[step]} forceStart />);

    expect(await screen.findByText("Tour step")).toBeInTheDocument();
    expect(scrollIntoView).toHaveBeenCalledWith({
      behavior: "auto",
      block: "nearest",
    });
  });

  it("traps keyboard focus and lets Escape close the modal-looking tour", async () => {
    vi.useRealTimers();
    attachTourTarget();
    const onSkip = vi.fn();

    render(<OnboardingTooltip steps={[step]} forceStart onSkip={onSkip} />);

    const dialog = await screen.findByRole("dialog", { name: "Tour step" });
    const nextButton = screen.getByRole("button", { name: "Finish" });
    const closeButton = screen.getAllByRole("button", {
      name: "Skip tour",
    })[0];

    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(nextButton).toHaveFocus();

    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(closeButton).toHaveFocus();

    fireEvent.keyDown(dialog, { key: "Escape" });

    await waitFor(() => {
      expect(onSkip).toHaveBeenCalledTimes(1);
      expect(
        screen.queryByRole("dialog", { name: "Tour step" }),
      ).not.toBeInTheDocument();
    });
  });
});
