import Link from "next/link";
import { Mail } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { PUBLIC_ASSURANCE_BOUNDARY_HREF } from "@/lib/support-boundary";

export function ContactCard() {
  return (
    <Card id="contact" className="scroll-mt-36">
      <CardContent className="flex flex-col gap-4 py-5 sm:flex-row sm:items-center">
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-brand-primary/10">
          <Mail className="h-5 w-5 text-brand-primary" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="type-label-sm text-[var(--text-primary)]">
            Support is deployment-specific
          </p>
          <p className="type-body-md text-[var(--text-secondary)]">
            This research preview does not publish a hosted support mailbox. If
            your organisation operates an instance, use the support channel it
            has approved.
          </p>
          <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">
            Do not send confidential molecule, report, or matter details through
            an unverified contact route.
          </p>
        </div>
        <Button asChild variant="outline" className="min-h-11 w-full sm:w-auto">
          <Link href={PUBLIC_ASSURANCE_BOUNDARY_HREF}>
            Review deployment boundary
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}
