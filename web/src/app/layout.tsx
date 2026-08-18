import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { headers } from "next/headers";
import { BRAND } from "@/marketing/content";
import { Providers } from "./providers";
import {
  assertClerkConfiguredForProduction,
  hasValidClerkPublishableKey,
  resolveAppUrl,
} from "@/lib/production-env";
import "./globals.css";
import { MotionConfig } from "motion/react";

// FAIL LOUD: Validate and normalize NEXT_PUBLIC_APP_URL in production.
const appUrl = resolveAppUrl({
  nodeEnv: process.env.NODE_ENV,
  appUrl: process.env.NEXT_PUBLIC_APP_URL,
});

export const metadata: Metadata = {
  metadataBase: new URL(appUrl),
  title: {
    default: `${BRAND.name} | Compound-first patent-risk screening`,
    template: `%s | ${BRAND.name}`,
  },
  description:
    "Compound-first patent-risk screening for biotech teams and qualified counsel, with inspectable claims, citations, source gaps, and preliminary report artifacts.",
  keywords: [
    "FTO",
    "patent-risk screening",
    "compound analysis",
    "freedom to operate",
  ],
  openGraph: {
    title: `${BRAND.name} | Compound-first patent-risk screening`,
    description:
      "Preliminary patent-risk screening with claim evidence, source gaps, and a qualified-counsel handoff.",
    type: "website",
    siteName: BRAND.name,
    images: [
      {
        url: "/opengraph-image",
        width: 1200,
        height: 630,
        alt: "Praviar FTO screening evidence workspace",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: `${BRAND.name} | Compound-first patent-risk screening`,
    description:
      "Compound-first FTO screening with risk findings, claim evidence, and shareable report artifacts.",
    images: ["/opengraph-image"],
  },
};

const clerkKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
const hasClerk = hasValidClerkPublishableKey(clerkKey);
assertClerkConfiguredForProduction({
  nodeEnv: process.env.NODE_ENV,
  clerkPublishableKey: clerkKey,
});

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // The middleware creates a fresh CSP nonce per request. Reading request
  // headers keeps the root dynamic so Next can attach that nonce to its inline
  // flight/bootstrap scripts instead of serving nonce-less prerendered HTML.
  await headers();
  const body = (
    <html lang="en" className="light" suppressHydrationWarning>
      <body className="antialiased bg-[var(--bg-base)] text-[var(--text-primary)] min-h-screen">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[100] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-[var(--bg-surface)] focus:text-[var(--text-primary)] focus:shadow-lg focus:outline-2 focus:outline-[var(--brand-primary)] focus:text-sm focus:font-medium"
        >
          Skip to main content
        </a>
        <MotionConfig reducedMotion="user">
          <Providers>{children}</Providers>
        </MotionConfig>
      </body>
    </html>
  );

  if (hasClerk) {
    return <ClerkProvider>{body}</ClerkProvider>;
  }

  return body;
}
