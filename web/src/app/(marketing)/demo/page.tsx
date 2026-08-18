import type { Metadata } from "next";
import { MarketingDemoPage } from "@/components/marketing/demo-page";
import { BRAND } from "@/marketing/content";
import { getMarketingDemoArtifact } from "@/marketing/live-demo";

export const metadata: Metadata = {
  title: "Interactive Demo",
  description:
    "Explore a fictional Praviar patent-risk report with claim evidence, source gaps, verification warnings, and next steps.",
  openGraph: {
    title: `${BRAND.name} Interactive Demo`,
    description:
      "Inspect a synthetic first-pass FTO dossier before running your own compound.",
    type: "website",
    images: [
      {
        url: "/opengraph-image",
        width: 1200,
        height: 630,
        alt: "Praviar interactive FTO demo",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: `${BRAND.name} Interactive Demo`,
    description:
      "Inspect a synthetic first-pass FTO dossier before running your own compound.",
    images: ["/opengraph-image"],
  },
};

export default function DemoPage() {
  const demoArtifact = getMarketingDemoArtifact();

  return <MarketingDemoPage demoArtifact={demoArtifact} />;
}
