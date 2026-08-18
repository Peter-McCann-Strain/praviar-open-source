import type { Metadata } from "next";
import { SharePageShell } from "./share-page-shell";

export const metadata: Metadata = {
  title: "Verify shared FTO packet",
  description:
    "Mailbox-verified, read-only Praviar FTO report access for an intended external recipient.",
  robots: { index: false, follow: false },
};

export default async function SharedReportPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return (
    <SharePageShell
      token={token}
      initialResult={{ status: "verification-required", invalid: false }}
    />
  );
}
