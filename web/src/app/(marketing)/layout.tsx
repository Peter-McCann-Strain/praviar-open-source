import type { Metadata } from "next";
import { MarketingSiteShell } from "@/components/marketing/site-shell";
import { BRAND } from "@/marketing/content";

export const metadata: Metadata = {
  title: {
    default: `${BRAND.name} | ${BRAND.tagline}`,
    template: `%s | ${BRAND.name}`,
  },
};

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <MarketingSiteShell>{children}</MarketingSiteShell>;
}
