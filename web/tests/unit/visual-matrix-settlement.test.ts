import { describe, expect, it } from "vitest";
import { waitForVisualMatrixQuietWindow } from "../e2e/fixtures/visual-matrix-settlement";

describe("visual matrix quiet-window settlement", () => {
  it("resets the quiet window when hostile work arrives after an initial zero", async () => {
    let nowMs = 0;

    await waitForVisualMatrixQuietWindow(
      () => {
        if (nowMs < 20) return { activityVersion: 0, pendingCount: 0 };
        if (nowMs < 40) return { activityVersion: 1, pendingCount: 1 };
        return { activityVersion: 2, pendingCount: 0 };
      },
      {
        label: "hostile late event",
        now: () => nowMs,
        pollIntervalMs: 10,
        quietWindowMs: 50,
        sleep: async (durationMs) => {
          nowMs += durationMs;
        },
        timeoutMs: 200,
      },
    );

    expect(nowMs).toBeGreaterThanOrEqual(90);
  });

  it("fails closed when pending work never settles", async () => {
    let nowMs = 0;

    await expect(
      waitForVisualMatrixQuietWindow(
        () => ({ activityVersion: 7, pendingCount: 1 }),
        {
          label: "stuck request",
          now: () => nowMs,
          pollIntervalMs: 10,
          quietWindowMs: 20,
          sleep: async (durationMs) => {
            nowMs += durationMs;
          },
          timeoutMs: 30,
        },
      ),
    ).rejects.toThrow(
      "stuck request did not reach a 20ms quiet window within 30ms",
    );
  });
});
