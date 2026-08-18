import Link from "next/link";
import { ArrowRight, FileText, ShieldCheck } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { MARKETING_DISCLAIMER } from "@/marketing/content";
import {
  PUBLIC_METHODOLOGY_ACTION,
  PUBLIC_PURCHASING_NOTICE,
} from "@/marketing/public-readiness";
import { cn } from "@/lib/utils";

const PUBLIC_BOUNDARIES = [
  {
    icon: FileText,
    title: "Fictional public sample",
    detail:
      "The sample shows the report format and evidence trail. It does not prove search accuracy or completeness.",
  },
  {
    icon: ShieldCheck,
    title: "Counsel makes the legal call",
    detail:
      "Praviar prepares material for review. Qualified patent counsel remains responsible for legal conclusions.",
  },
] as const;

export function HomePageTrustBand() {
  return (
    <section
      className="praviar-section-band scroll-mt-24 px-4 py-12 sm:px-6 md:py-16"
      aria-labelledby="homepage-trust-heading"
      data-testid="homepage-trust-band"
    >
      <div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
        <div className="max-w-2xl space-y-4">
          <p className="text-sm font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
            Public product boundary
          </p>
          <h2
            id="homepage-trust-heading"
            className="[font-family:var(--font-newsreader)] text-4xl leading-[1.06] text-[var(--text-primary)] md:text-5xl"
          >
            Know what the public preview can and cannot establish.
          </h2>
          <p className="text-base leading-7 text-[var(--text-secondary)]">
            Review the methodology and deployment limits before relying on the
            product story.
          </p>
          <div className="flex flex-col gap-3 pt-1 sm:flex-row sm:flex-wrap">
            <Link
              href="/trust"
              className={cn(buttonVariants({ size: "lg" }), "rounded-lg")}
            >
              Review deployment limits
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
            <Link
              href={PUBLIC_METHODOLOGY_ACTION.href}
              className={cn(
                buttonVariants({ variant: "outline", size: "lg" }),
                "rounded-lg",
              )}
            >
              {PUBLIC_METHODOLOGY_ACTION.label}
            </Link>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          {PUBLIC_BOUNDARIES.map((item) => {
            const Icon = item.icon;

            return (
              <article
                key={item.title}
                className="praviar-surface-premium rounded-xl p-5"
              >
                <Icon
                  className="h-5 w-5 text-[var(--brand-primary)]"
                  aria-hidden="true"
                />
                <h3 className="mt-4 font-semibold text-[var(--text-primary)]">
                  {item.title}
                </h3>
                <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                  {item.detail}
                </p>
              </article>
            );
          })}
          <div
            role="note"
            className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-muted)] p-4 text-xs leading-6 text-[var(--text-tertiary)] sm:col-span-2"
          >
            <p>{PUBLIC_PURCHASING_NOTICE}</p>
            <p className="mt-2">{MARKETING_DISCLAIMER}</p>
          </div>
        </div>
      </div>
    </section>
  );
}
