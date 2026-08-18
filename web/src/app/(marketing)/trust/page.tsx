import type { Metadata } from "next";

import { TrustPageContent } from "@/components/marketing/trust-page";

export const metadata: Metadata = {
  title: "Trust and Security",
  description:
    "See how Praviar keeps patent findings linked to sources, records human review, and protects each organisation's workspace.",
};

export default function TrustPage() {
  return <TrustPageContent />;
}
