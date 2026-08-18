import { afterEach, describe, expect, it, vi } from "vitest";
import {
  motionAwareScrollBehavior,
  prefersReducedMotion,
} from "@/lib/motion-preferences";

function mockMatchMedia(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
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

describe("motion-preferences", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("uses smooth scroll when reduced motion is not preferred", () => {
    mockMatchMedia(false);

    expect(prefersReducedMotion()).toBe(false);
    expect(motionAwareScrollBehavior()).toBe("smooth");
  });

  it("uses instant scroll when reduced motion is preferred", () => {
    mockMatchMedia(true);

    expect(prefersReducedMotion()).toBe(true);
    expect(motionAwareScrollBehavior()).toBe("auto");
  });
});
