import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/constants", () => ({
  API_BASE_URL: "https://api.example.test",
  DEMO_MODE_ENABLED: false,
}));

import {
  requestSharedReportVerification,
  verifySharedReportRecipient,
} from "@/app/share/[token]/actions";

const TOKEN = "T".repeat(43);
const ACCESS_SECRET = "A".repeat(43);
const ATTRIBUTED_REPORT = {
  compound_name: "Succinic acid",
  overall_risk: "high",
  blocking_patents_count: 2,
  total_patents_found: 42,
  executive_summary: "Two patent families need review.",
  key_findings: [],
  generated_at: "2026-04-09T11:24:00.000Z",
  share_expires_at: "2027-05-09T11:24:00.000Z",
  verified_recipient_email: "counsel@example.com",
  attributable_view_number: 3,
  verified_session_expires_at: "2027-07-13T12:30:00.000Z",
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("recipient-bound shared report actions", () => {
  it("rejects malformed locators before any request", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(requestSharedReportVerification("short")).resolves.toEqual({
      status: "not-found",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("requests a mailbox challenge without recipient identity", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "verification_sent" }), {
        status: 200,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(requestSharedReportVerification(TOKEN)).resolves.toEqual({
      status: "sent",
    });
    expect(fetchMock).toHaveBeenCalledWith(
      `https://api.example.test/share/${TOKEN}/challenge`,
      expect.objectContaining({ method: "POST", cache: "no-store" }),
    );
  });

  it("keeps the access proof inside the server action", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            access_secret: ACCESS_SECRET,
            access_expires_at: "2026-07-13T12:30:00.000Z",
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(ATTRIBUTED_REPORT), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const result = await verifySharedReportRecipient(TOKEN, "24681357");

    expect(result).toMatchObject({
      status: "ok",
      report: {
        verified_recipient_email: "counsel@example.com",
        attributable_view_number: 3,
      },
    });
    const reportHeaders = fetchMock.mock.calls[1]?.[1]?.headers as Record<
      string,
      string
    >;
    expect(reportHeaders["X-Praviar-Grant-Access"]).toBe(ACCESS_SECRET);
    expect(JSON.stringify(result)).not.toContain(ACCESS_SECRET);
    expect(fetchMock.mock.calls.flat().join(" ")).not.toContain(
      `access_secret=${ACCESS_SECRET}`,
    );
  });

  it("requires fresh verification when the attributed session is expired", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            access_secret: ACCESS_SECRET,
            access_expires_at: "2026-07-13T12:30:00.000Z",
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ...ATTRIBUTED_REPORT,
            verified_session_expires_at: "2026-01-01T00:00:00.000Z",
          }),
          { status: 200 },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      verifySharedReportRecipient(TOKEN, "24681357"),
    ).resolves.toEqual({
      status: "verification-required",
      invalid: false,
    });
  });
});
