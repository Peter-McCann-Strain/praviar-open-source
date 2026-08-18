import { describe, it, expect } from "vitest";
import {
  SPRING_SNAPPY,
  SPRING_SMOOTH,
  SPRING_GENTLE,
  springTransition,
} from "@/lib/spring-presets";

describe("spring-presets", () => {
  it("exports SPRING_SNAPPY with correct shape", () => {
    expect(SPRING_SNAPPY).toEqual({
      type: "spring",
      stiffness: 300,
      damping: 30,
    });
  });

  it("exports SPRING_SMOOTH with correct shape", () => {
    expect(SPRING_SMOOTH).toEqual({
      type: "spring",
      stiffness: 200,
      damping: 25,
    });
  });

  it("exports SPRING_GENTLE with correct shape", () => {
    expect(SPRING_GENTLE).toEqual({
      type: "spring",
      stiffness: 100,
      damping: 20,
    });
  });

  it("springTransition returns correct preset by name", () => {
    expect(springTransition("snappy")).toBe(SPRING_SNAPPY);
    expect(springTransition("smooth")).toBe(SPRING_SMOOTH);
    expect(springTransition("gentle")).toBe(SPRING_GENTLE);
  });

  it("all presets have type spring", () => {
    for (const preset of [SPRING_SNAPPY, SPRING_SMOOTH, SPRING_GENTLE]) {
      expect(preset.type).toBe("spring");
      expect(preset.stiffness).toBeGreaterThan(0);
      expect(preset.damping).toBeGreaterThan(0);
    }
  });

  it("snappy has highest stiffness, gentle has lowest", () => {
    expect(SPRING_SNAPPY.stiffness).toBeGreaterThan(SPRING_SMOOTH.stiffness);
    expect(SPRING_SMOOTH.stiffness).toBeGreaterThan(SPRING_GENTLE.stiffness);
  });
});
