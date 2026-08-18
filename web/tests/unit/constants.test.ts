import { afterEach, describe, it, expect, vi } from "vitest";
import {
  PIPELINE_STEPS,
  RISK_COLORS,
  ELEMENT_STATUS_COLORS,
} from "@/lib/constants";

describe("PIPELINE_STEPS", () => {
  it("has exactly 8 entries", () => {
    expect(PIPELINE_STEPS).toHaveLength(8);
  });

  it("each step has number, name, label, and icon", () => {
    for (const step of PIPELINE_STEPS) {
      expect(step).toHaveProperty("number");
      expect(step).toHaveProperty("name");
      expect(step).toHaveProperty("label");
      expect(step).toHaveProperty("icon");
      expect(typeof step.number).toBe("number");
      expect(typeof step.name).toBe("string");
      expect(typeof step.label).toBe("string");
      expect(typeof step.icon).toBe("string");
    }
  });

  it("does not preserve retired flask-era icon vocabulary", () => {
    const icons = PIPELINE_STEPS.map((step) => step.icon);

    expect(icons).not.toContain("flask-conical");
    expect(icons.join(" ")).not.toMatch(/flask/i);
    expect(PIPELINE_STEPS[0].icon).toBe("atom");
  });

  it("steps are numbered 1 through 8 in order", () => {
    PIPELINE_STEPS.forEach((step, index) => {
      expect(step.number).toBe(index + 1);
    });
  });

  it("step 1 is resolve", () => {
    expect(PIPELINE_STEPS[0].name).toBe("resolve");
    expect(PIPELINE_STEPS[0].label).toBe("Resolve Compound");
  });

  it("step 8 is report", () => {
    expect(PIPELINE_STEPS[7].name).toBe("report");
    expect(PIPELINE_STEPS[7].label).toBe("Report");
  });

  it("has the expected step names in order", () => {
    const names = PIPELINE_STEPS.map((s) => s.name);
    expect(names).toEqual([
      "resolve",
      "search",
      "triage",
      "analyze",
      "doe",
      "invalidity",
      "verify",
      "report",
    ]);
  });
});

describe("RISK_COLORS", () => {
  it("has all four risk levels", () => {
    expect(RISK_COLORS).toHaveProperty("high");
    expect(RISK_COLORS).toHaveProperty("medium");
    expect(RISK_COLORS).toHaveProperty("low");
    expect(RISK_COLORS).toHaveProperty("clear");
  });

  it("each risk level has bg, text, border, and hex", () => {
    for (const level of ["high", "medium", "low", "clear"] as const) {
      expect(RISK_COLORS[level]).toHaveProperty("bg");
      expect(RISK_COLORS[level]).toHaveProperty("text");
      expect(RISK_COLORS[level]).toHaveProperty("border");
      expect(RISK_COLORS[level]).toHaveProperty("hex");
    }
  });

  it("legacy hex values resolve through premium risk tokens", () => {
    for (const level of ["high", "medium", "low", "clear"] as const) {
      expect(RISK_COLORS[level].hex).toMatch(/^var\(--risk-[a-z]+\)$/);
    }
  });

  it("high risk is error", () => {
    expect(RISK_COLORS.high.hex).toBe("var(--risk-high)");
    expect(RISK_COLORS.high.text).toContain("error");
  });

  it("clear risk is info", () => {
    expect(RISK_COLORS.clear.hex).toBe("var(--risk-clear)");
    expect(RISK_COLORS.clear.text).toContain("info");
  });
});

describe("ELEMENT_STATUS_COLORS", () => {
  it("has all four statuses", () => {
    expect(ELEMENT_STATUS_COLORS).toHaveProperty("met");
    expect(ELEMENT_STATUS_COLORS).toHaveProperty("not_met");
    expect(ELEMENT_STATUS_COLORS).toHaveProperty("partially_met");
    expect(ELEMENT_STATUS_COLORS).toHaveProperty("unclear");
  });

  it("each status has bg, text, and label", () => {
    for (const status of [
      "met",
      "not_met",
      "partially_met",
      "unclear",
    ] as const) {
      expect(ELEMENT_STATUS_COLORS[status]).toHaveProperty("bg");
      expect(ELEMENT_STATUS_COLORS[status]).toHaveProperty("text");
      expect(ELEMENT_STATUS_COLORS[status]).toHaveProperty("label");
    }
  });

  it("met label is Met", () => {
    expect(ELEMENT_STATUS_COLORS.met.label).toBe("Met");
  });

  it("not_met label is Not Met", () => {
    expect(ELEMENT_STATUS_COLORS.not_met.label).toBe("Not Met");
  });

  it("partially_met label is Partial", () => {
    expect(ELEMENT_STATUS_COLORS.partially_met.label).toBe("Partial");
  });

  it("unclear label is Unclear", () => {
    expect(ELEMENT_STATUS_COLORS.unclear.label).toBe("Unclear");
  });
});

describe("Environment contract", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("uses NEXT_PUBLIC_API_URL when provided", async () => {
    vi.resetModules();
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://LOCALHOST:8000/");
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "false");

    const { API_BASE_URL, DEMO_MODE_ENABLED } = await import("@/lib/constants");

    expect(API_BASE_URL).toBe("http://localhost:8000");
    expect(DEMO_MODE_ENABLED).toBe(false);
  });

  it("rejects a local API origin in production", async () => {
    vi.resetModules();
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://127.0.0.1:8000");
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "false");

    await expect(import("@/lib/constants")).rejects.toThrow(
      /must use a DNS hostname, not an IP address/i,
    );
  });

  it("allows missing API URL only when demo mode is enabled", async () => {
    vi.resetModules();
    vi.stubEnv("NEXT_PUBLIC_API_URL", undefined);
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "true");

    const { API_BASE_URL, DEMO_MODE_ENABLED } = await import("@/lib/constants");

    expect(API_BASE_URL).toBeNull();
    expect(DEMO_MODE_ENABLED).toBe(true);
  });

  it("throws when both API URL and demo mode are absent", async () => {
    vi.resetModules();
    vi.stubEnv("NEXT_PUBLIC_API_URL", undefined);
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "false");

    await expect(import("@/lib/constants")).rejects.toThrow(
      /NEXT_PUBLIC_API_URL is required unless NEXT_PUBLIC_DEMO_MODE=true/i,
    );
  });
});
