import type { MetadataRoute } from "next";
import { resolveAppUrl } from "@/lib/production-env";

const PUBLIC_PATHS = [
  "",
  "/demo",
  "/for-biotech-founders",
  "/methodology",
  "/trust",
  "/privacy",
  "/terms",
  "/sample-reports",
  "/sample-reports/example-molecule-alpha",
  "/compare/adaptive-agentic",
] as const;

export default function sitemap(): MetadataRoute.Sitemap {
  const siteUrl = resolveAppUrl({
    appUrl: process.env.NEXT_PUBLIC_APP_URL,
    nodeEnv: process.env.NODE_ENV,
  });
  const lastModified = new Date("2026-08-04T00:00:00.000Z");

  return PUBLIC_PATHS.map((path, index) => ({
    url: `${siteUrl}${path}`,
    lastModified,
    changeFrequency: index === 0 ? "weekly" : "monthly",
    priority: index === 0 ? 1 : path.includes("sample-reports") ? 0.8 : 0.7,
  }));
}
