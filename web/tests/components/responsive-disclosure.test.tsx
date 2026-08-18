import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ResponsiveDisclosure } from "@/components/shared/responsive-disclosure";

const originalMatchMedia = window.matchMedia;

afterEach(() => {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: originalMatchMedia,
    writable: true,
  });
});

function installMatchMedia(initialMatches: boolean) {
  let matches = initialMatches;
  const listeners = new Set<() => void>();
  const query = {
    addEventListener: vi.fn((_event: string, listener: () => void) => {
      listeners.add(listener);
    }),
    get matches() {
      return matches;
    },
    media: "(min-width: 640px)",
    onchange: null,
    removeEventListener: vi.fn((_event: string, listener: () => void) => {
      listeners.delete(listener);
    }),
  };
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn(() => query),
    writable: true,
  });
  return {
    query,
    setMatches(nextMatches: boolean) {
      matches = nextMatches;
      for (const listener of listeners) listener();
    },
  };
}

function renderDisclosure() {
  render(
    <ResponsiveDisclosure summary={<summary>Reliance details</summary>}>
      <p>Material evidence caveat</p>
    </ResponsiveDisclosure>,
  );
  return screen.getByText("Material evidence caveat").closest("details");
}

describe("ResponsiveDisclosure", () => {
  it("exposes content in non-visual renderers without matchMedia", () => {
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: undefined,
      writable: true,
    });

    expect(renderDisclosure()).toHaveAttribute("open");
  });

  it("tracks the desktop media-query boundary without effect-driven state", () => {
    const media = installMatchMedia(false);
    const disclosure = renderDisclosure();

    expect(disclosure).not.toHaveAttribute("open");
    expect(media.query.addEventListener).toHaveBeenCalledWith(
      "change",
      expect.any(Function),
    );

    act(() => media.setMatches(true));
    expect(disclosure).toHaveAttribute("open");

    act(() => media.setMatches(false));
    expect(disclosure).not.toHaveAttribute("open");
  });
});
