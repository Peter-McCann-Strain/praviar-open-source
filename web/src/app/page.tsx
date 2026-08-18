import type { Metadata } from "next";
import { MarketingHomePage } from "@/components/marketing/home-page";
import { MarketingSiteShell } from "@/components/marketing/site-shell";
import { getMarketingDemoArtifact } from "@/marketing/live-demo";

export const metadata: Metadata = {
  title: { absolute: "Praviar | Compound-first patent-risk screening" },
  description:
    "Turn a compound and its commercial context into a preliminary patent-risk dossier with potential blocker families, claim evidence, source gaps, and a clear handoff to qualified patent counsel.",
  alternates: { canonical: "/" },
  openGraph: {
    title: "Praviar | Compound-first patent-risk screening",
    description:
      "A preliminary patent-risk dossier with potential blocker families, claim evidence, source gaps, and counsel-review questions.",
    type: "website",
    images: [
      {
        url: "/opengraph-image",
        width: 1200,
        height: 630,
        alt: "Praviar compound-first FTO screening",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Praviar | Compound-first patent-risk screening",
    description:
      "Preliminary patent-risk screening with claim evidence, source gaps, and a qualified-counsel handoff.",
    images: ["/opengraph-image"],
  },
};

export default function LandingPage() {
  const demoArtifact = getMarketingDemoArtifact();

  return (
    <MarketingSiteShell>
      <MarketingHomePage demoArtifact={demoArtifact} />
    </MarketingSiteShell>
  );
}
