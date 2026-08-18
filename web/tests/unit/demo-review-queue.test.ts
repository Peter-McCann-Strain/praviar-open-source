import { beforeEach, describe, expect, it } from "vitest";

import {
  buildDemoReviewQueue,
  resetDemoReviewQueueState,
} from "@/lib/demo-review-queue";
import { SHOWCASE_PAYLOAD } from "@/lib/showcase-report";

const CANONICAL_SCENARIO_CLOCK = "2026-01-15T10:30:00Z";

describe("demo review queue timeline", () => {
  beforeEach(() => {
    resetDemoReviewQueueState();
  });

  it("anchors the current queue snapshot to the canonical showcase clock", () => {
    const queue = buildDemoReviewQueue("all");

    expect(SHOWCASE_PAYLOAD.clock).toBe(CANONICAL_SCENARIO_CLOCK);
    expect(queue.updated_at).toBe(CANONICAL_SCENARIO_CLOCK);
    expect(queue.items).toMatchObject([
      {
        id: "rq-demo-1",
        escalated_at: "2026-01-15T00:15:00Z",
        last_activity_at: CANONICAL_SCENARIO_CLOCK,
        updated_at: CANONICAL_SCENARIO_CLOCK,
      },
      {
        id: "rq-demo-2",
        escalated_at: null,
        last_activity_at: "2026-01-15T09:05:00Z",
        updated_at: "2026-01-15T09:05:00Z",
      },
      {
        id: "rq-demo-3",
        escalated_at: "2026-01-13T07:10:00Z",
        last_activity_at: "2026-01-15T07:10:00Z",
        updated_at: "2026-01-15T07:10:00Z",
      },
    ]);
  });

  it("keeps every seeded review timestamp at or before the scenario clock", () => {
    const queue = buildDemoReviewQueue("all");
    const scenarioClockMs = Date.parse(CANONICAL_SCENARIO_CLOCK);
    const seededTimestamps = queue.items.flatMap((item) => [
      item.escalated_at,
      item.last_activity_at,
      item.updated_at,
    ]);

    expect(seededTimestamps).toContain(CANONICAL_SCENARIO_CLOCK);
    for (const timestamp of seededTimestamps) {
      if (timestamp === null) {
        continue;
      }

      expect(Date.parse(timestamp)).not.toBeNaN();
      expect(Date.parse(timestamp)).toBeLessThanOrEqual(scenarioClockMs);
    }
  });
});
