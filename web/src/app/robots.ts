import type { MetadataRoute } from "next";
import { resolveAppUrl } from "@/lib/production-env";

export default function robots(): MetadataRoute.Robots {
  const siteUrl = resolveAppUrl({
    appUrl: process.env.NEXT_PUBLIC_APP_URL,
    nodeEnv: process.env.NODE_ENV,
  });

  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: [
        "/admin/",
        "/analyses/",
        "/api/",
        "/billing/",
        "/compounds/",
        "/reports/",
        "/reviews/",
        "/settings/",
        "/share/",
        "/sign-in",
        "/sign-up",
      ],
    },
    sitemap: `${siteUrl}/sitemap.xml`,
  };
}
