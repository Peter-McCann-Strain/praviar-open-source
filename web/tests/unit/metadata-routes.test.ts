import { afterEach, describe, expect, it, vi } from "vitest";

import robots from "@/app/robots";
import sitemap from "@/app/sitemap";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("public metadata route origins", () => {
  it("uses a local-only fallback during non-production evaluation", () => {
    vi.stubEnv("NODE_ENV", "test");
    vi.stubEnv("NEXT_PUBLIC_APP_URL", undefined);

    expect(robots().sitemap).toBe("http://localhost:3000/sitemap.xml");
    expect(sitemap()[0]?.url).toBe("http://localhost:3000");
  });

  it("uses the explicitly configured canonical deployment origin", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "https://app.praviar.example/");

    expect(robots().sitemap).toBe("https://app.praviar.example/sitemap.xml");
    expect(
      sitemap().every(({ url }) =>
        url.startsWith("https://app.praviar.example"),
      ),
    ).toBe(true);
  });

  it("fails closed when production has no canonical origin", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_APP_URL", undefined);

    expect(() => robots()).toThrow("NEXT_PUBLIC_APP_URL is required");
    expect(() => sitemap()).toThrow("NEXT_PUBLIC_APP_URL is required");
  });
});
