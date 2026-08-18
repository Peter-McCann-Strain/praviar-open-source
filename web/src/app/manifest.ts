import type { MetadataRoute } from "next";

import { BRAND } from "@/marketing/content";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: `${BRAND.name} - Compound-first FTO screening`,
    short_name: BRAND.shortName,
    description:
      "Compound-first FTO screening with risk findings, claim evidence, and shareable report artifacts.",
    id: "/",
    start_url: "/",
    scope: "/",
    display: "standalone",
    display_override: ["standalone", "browser"],
    background_color: "#F6F4EF",
    theme_color: "#0B1F24",
    categories: ["business", "productivity", "medical"],
    icons: [
      {
        src: "/icons/praviar-icon-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icons/praviar-icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icons/praviar-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
