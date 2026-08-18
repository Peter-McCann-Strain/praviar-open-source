import { describe, expect, it } from "vitest";
import { calculateTooltipPosition } from "@/components/shared/onboarding-tooltip-position";

const makeRect = (values: Partial<DOMRect>): DOMRect =>
  ({
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    width: 0,
    height: 0,
    x: 0,
    y: 0,
    toJSON: () => ({}),
    ...values,
  }) as DOMRect;

describe("calculateTooltipPosition", () => {
  it("prefers bottom placement when there is room below", () => {
    const position = calculateTooltipPosition(
      makeRect({
        top: 100,
        left: 100,
        right: 200,
        bottom: 140,
        width: 100,
        height: 40,
      }),
      200,
      80,
      1200,
      800,
    );

    expect(position.placement).toBe("bottom");
    expect(position.top).toBe(156);
  });

  it("falls back to top placement when below is constrained", () => {
    const position = calculateTooltipPosition(
      makeRect({
        top: 700,
        left: 100,
        right: 200,
        bottom: 740,
        width: 100,
        height: 40,
      }),
      200,
      80,
      1200,
      800,
    );

    expect(position.placement).toBe("top");
  });

  it("clamps tooltip coordinates to viewport bounds", () => {
    const position = calculateTooltipPosition(
      makeRect({
        top: 0,
        left: 0,
        right: 10,
        bottom: 10,
        width: 10,
        height: 10,
      }),
      500,
      500,
      320,
      240,
    );

    expect(position.left).toBeGreaterThanOrEqual(12);
    expect(position.top).toBeGreaterThanOrEqual(12);
  });
});
