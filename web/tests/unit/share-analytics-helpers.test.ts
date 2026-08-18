import { afterEach, describe, expect, it, vi } from "vitest";
import { copyTextToClipboard } from "@/components/report/share-analytics-helpers";

describe("copyTextToClipboard", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("rejects when neither clipboard API nor the fallback accepts the copy", async () => {
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error("blocked")) },
    });
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: vi.fn().mockReturnValue(false),
    });

    await expect(copyTextToClipboard("verification receipt")).rejects.toThrow(
      "Clipboard copy was not accepted",
    );
    expect(document.querySelector("textarea")).toBeNull();
  });
});
