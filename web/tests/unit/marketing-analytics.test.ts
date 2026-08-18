import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { trackMarketingEvent } from "@/lib/marketing-analytics";

describe("marketing analytics", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-17T12:00:00Z"));
    window.__praviarAnalyticsQueue = [];
    window.plausible = vi.fn();
    window.gtag = vi.fn();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("drops sensitive and value-derived properties before dispatch", () => {
    trackMarketingEvent("homepage_start_analysis_clicked", {
      destination: "sign_up",
      mode: "adaptive",
      compoundName: "secret candidate",
      query: "CC(=O)Oc1ccccc1C(=O)O",
      nested: { smiles: "secret" },
      compound_provided: true,
      compound_length_bucket: "short",
    });

    expect(window.__praviarAnalyticsQueue?.[0]).toEqual({
      name: "homepage_start_analysis_clicked",
      properties: {
        destination: "sign_up",
        mode: "adaptive",
      },
      timestamp: "2026-06-17T12:00:00.000Z",
    });
    expect(window.plausible).toHaveBeenCalledWith(
      "homepage_start_analysis_clicked",
      {
        props: {
          destination: "sign_up",
          mode: "adaptive",
        },
      },
    );
    expect(window.gtag).toHaveBeenCalledWith(
      "event",
      "homepage_start_analysis_clicked",
      {
        destination: "sign_up",
        mode: "adaptive",
      },
    );
  });
});
