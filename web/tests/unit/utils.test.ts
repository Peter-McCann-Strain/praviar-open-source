import { describe, it, expect } from "vitest";
import {
  cn,
  formatNumber,
  formatDuration,
  truncate,
  formatDate,
} from "@/lib/utils";

describe("cn", () => {
  it("merges class names", () => {
    expect(cn("px-2", "py-1")).toBe("px-2 py-1");
  });

  it("handles conditional classes", () => {
    expect(cn("px-2", false && "py-1", "text-sm")).toBe("px-2 text-sm");
  });

  it("resolves Tailwind conflicts by keeping the last value", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
  });

  it("handles undefined and null inputs", () => {
    expect(cn("px-2", undefined, null, "py-1")).toBe("px-2 py-1");
  });

  it("returns empty string for no inputs", () => {
    expect(cn()).toBe("");
  });
});

describe("formatNumber", () => {
  it("formats thousands with commas", () => {
    expect(formatNumber(1234)).toBe("1,234");
  });

  it("formats zero", () => {
    expect(formatNumber(0)).toBe("0");
  });

  it("formats negative numbers", () => {
    expect(formatNumber(-5678)).toBe("-5,678");
  });

  it("formats large numbers", () => {
    expect(formatNumber(1000000)).toBe("1,000,000");
  });

  it("handles decimals", () => {
    expect(formatNumber(1234.5)).toBe("1,234.5");
  });
});

describe("formatDuration", () => {
  it("formats seconds only when under 60", () => {
    expect(formatDuration(45)).toBe("45s");
  });

  it("formats minutes and seconds when 60 or above", () => {
    expect(formatDuration(90)).toBe("1m 30s");
  });

  it("formats exactly 60 seconds as 1m 0s", () => {
    expect(formatDuration(60)).toBe("1m 0s");
  });

  it("rounds fractional seconds", () => {
    expect(formatDuration(45.7)).toBe("46s");
  });

  it("handles zero", () => {
    expect(formatDuration(0)).toBe("0s");
  });

  it("handles large durations", () => {
    expect(formatDuration(3661)).toBe("61m 1s");
  });
});

describe("truncate", () => {
  it("truncates a long string and appends ellipsis", () => {
    expect(truncate("Hello, World!", 5)).toBe("Hello...");
  });

  it("preserves a short string that fits within the length", () => {
    expect(truncate("Hi", 10)).toBe("Hi");
  });

  it("returns the original string when length matches exactly", () => {
    expect(truncate("Hello", 5)).toBe("Hello");
  });

  it("handles empty string", () => {
    expect(truncate("", 5)).toBe("");
  });

  it("handles length of zero", () => {
    expect(truncate("Hello", 0)).toBe("...");
  });
});

describe("formatDate", () => {
  it("formats an ISO date string", () => {
    const result = formatDate("2026-03-08T14:22:13.100Z");
    expect(result).toMatch(/Mar/);
    expect(result).toMatch(/2026/);
    expect(result).toMatch(/8/);
  });

  it("formats a Date object", () => {
    const result = formatDate(new Date(2025, 0, 15));
    expect(result).toMatch(/Jan/);
    expect(result).toMatch(/15/);
    expect(result).toMatch(/2025/);
  });

  it("uses en-US locale format with short month", () => {
    const result = formatDate("2025-12-25T00:00:00Z");
    expect(result).toMatch(/Dec/);
    expect(result).toMatch(/25/);
    expect(result).toMatch(/2025/);
  });
});
