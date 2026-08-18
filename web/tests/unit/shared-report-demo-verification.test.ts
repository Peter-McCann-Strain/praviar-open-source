import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/constants", () => ({
  API_BASE_URL: "",
  DEMO_MODE_ENABLED: true,
}));

import {
  requestSharedReportVerification,
  verifySharedReportRecipient,
} from "@/app/share/[token]/actions";
import {
  DEMO_SHARE_TOKEN,
  DEMO_SHARE_VERIFICATION_CODE,
} from "@/lib/demo-data";

afterEach(() => {
  vi.useRealTimers();
});

describe("synthetic demo recipient verification", () => {
  it("uses a production-valid opaque locator and explicitly displays its fixed code", async () => {
    expect(DEMO_SHARE_TOKEN).toMatch(/^[A-Za-z0-9_-]{40,64}$/);
    await expect(
      requestSharedReportVerification(DEMO_SHARE_TOKEN),
    ).resolves.toEqual({
      status: "sent",
      syntheticDemoCode: DEMO_SHARE_VERIFICATION_CODE,
    });
  });

  it("requires the exact synthetic code", async () => {
    await expect(
      verifySharedReportRecipient(DEMO_SHARE_TOKEN, "00000000"),
    ).resolves.toEqual({ status: "verification-required", invalid: true });
    await expect(
      verifySharedReportRecipient(
        DEMO_SHARE_TOKEN,
        DEMO_SHARE_VERIFICATION_CODE,
      ),
    ).resolves.toMatchObject({
      status: "ok",
      report: {
        verified_recipient_email: "recipient@demo.praviar.invalid",
        attributable_view_number: 1,
      },
    });
  });

  it("uses the wall clock for ordinary demo verification", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-14T18:45:00.000Z"));

    await expect(
      verifySharedReportRecipient(
        DEMO_SHARE_TOKEN,
        DEMO_SHARE_VERIFICATION_CODE,
      ),
    ).resolves.toMatchObject({
      status: "ok",
      report: {
        verified_session_expires_at: "2026-08-14T19:15:00.000Z",
      },
    });
  });
});
