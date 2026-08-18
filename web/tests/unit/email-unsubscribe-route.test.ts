import { createHash } from "node:crypto";

import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "@/app/api/email/unsubscribe/route";

const TOKEN = "t".repeat(80);

function oneClickRequest(extraBody = "") {
  const body = new URLSearchParams({
    "List-Unsubscribe": "One-Click",
  });
  if (extraBody) {
    body.set("source", extraBody);
  }
  return new NextRequest(
    `https://app.praviar.io/api/email/unsubscribe?token=${TOKEN}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body,
    },
  );
}

describe("digest one-click unsubscribe route", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://API.Praviar.IO:443/");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("forwards RFC 8058 requests to the public API and returns no content", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response('{"status":"unsubscribed"}', { status: 200 }),
      );

    const response = await POST(oneClickRequest());

    expect(response.status).toBe(204);
    expect(fetchMock).toHaveBeenCalledWith(
      `https://api.praviar.io/api/v1/notifications/unsubscribe/digest/${createHash("sha256").update(TOKEN, "ascii").digest("hex")}`,
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ token: TOKEN }),
        cache: "no-store",
      }),
    );
    expect(response.headers.get("referrer-policy")).toBe("no-referrer");
  });

  it("redirects footer confirmations without putting the token in the result URL", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response('{"status":"unsubscribed"}', { status: 200 }),
    );

    const response = await POST(oneClickRequest("footer"));

    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe(
      "https://app.praviar.io/unsubscribe/digest?result=processed",
    );
    expect(response.headers.get("location")).not.toContain(TOKEN);
  });

  it("reads footer capabilities from the HttpOnly cookie and deletes it", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response('{"status":"unsubscribed"}', { status: 200 }),
      );
    const body = new URLSearchParams({
      "List-Unsubscribe": "One-Click",
      source: "footer",
    });
    const request = new NextRequest(
      "https://app.praviar.io/api/email/unsubscribe",
      {
        method: "POST",
        headers: {
          Cookie: `praviar_digest_unsubscribe=${TOKEN}`,
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body,
      },
    );

    const response = await POST(request);

    expect(response.status).toBe(303);
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBe(
      JSON.stringify({ token: TOKEN }),
    );
    expect(response.headers.get("set-cookie")).toContain(
      "praviar_digest_unsubscribe=;",
    );
  });

  it("keeps malformed one-click responses indistinguishable", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const request = new NextRequest(
      "https://app.praviar.io/api/email/unsubscribe?token=short",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: new URLSearchParams({
          "List-Unsubscribe": "One-Click",
        }),
      },
    );

    const response = await POST(request);

    expect(response.status).toBe(204);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects literal upstream API origins in production", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    vi.stubEnv("NODE_ENV", "production");

    for (const apiUrl of [
      "https://127.0.0.1:8000",
      "https://8.8.8.8",
      "https://[2606:4700:4700::1111]",
    ]) {
      vi.stubEnv("NEXT_PUBLIC_API_URL", apiUrl);
      await expect(POST(oneClickRequest())).rejects.toThrow(
        "NEXT_PUBLIC_API_URL",
      );
    }

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
