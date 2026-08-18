import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { PageEventBeacon } from "@/components/marketing/page-event-beacon";
import { SampleReportDetailHero } from "@/components/marketing/sample-report-detail-hero";
import { SampleReportDetailLiveSections } from "@/components/marketing/sample-report-detail-live-sections";
import { SampleReportMobileCommandBar } from "@/components/marketing/sample-report-mobile-command-bar";
import { SampleReportDetailPreviewCard } from "@/components/marketing/sample-report-detail-preview-card";
import { getSampleReportEntry } from "@/components/marketing/sample-report-card";
import { getMarketingDemoArtifact } from "@/marketing/live-demo";
import {
  PUBLIC_METHODOLOGY_ACTION,
  PUBLIC_PURCHASING_NOTICE,
} from "@/marketing/public-readiness";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const entry = getSampleReportEntry(slug);

  if (!entry) {
    return {};
  }

  const sampleDescription =
    entry.status === "demo"
      ? `Fictional product sample, not legal advice. ${entry.summary}`
      : entry.summary;

  return {
    title: `${entry.compoundName} Sample Report`,
    description: sampleDescription,
    openGraph: {
      title: `${entry.compoundName} Sample Report`,
      description: sampleDescription,
      type: "article",
      images: [
        {
          url: "/opengraph-image",
          width: 1200,
          height: 630,
          alt: `${entry.compoundName} Praviar sample FTO report`,
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: `${entry.compoundName} Sample Report`,
      description: sampleDescription,
      images: ["/opengraph-image"],
    },
  };
}

export default async function SampleReportDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const entry = getSampleReportEntry(slug);

  if (!entry) {
    notFound();
  }

  const demoArtifact = getMarketingDemoArtifact();

  return (
    <div className="light bg-[var(--bg-base)]">
      <PageEventBeacon eventName="sample_report_opened" properties={{ slug }} />
      <SampleReportMobileCommandBar demoArtifact={demoArtifact} />

      <section
        id="sample-verdict-packet"
        className="praviar-report-hero-field scroll-mt-24 px-4 pb-14 pt-12 sm:px-6 md:pb-20 md:pt-16"
      >
        <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[0.95fr_1.05fr] lg:items-start">
          <SampleReportDetailHero
            entry={entry}
            familiesFlaggedForReviewCount={
              demoArtifact.familiesFlaggedForReviewCount
            }
            isSyntheticSample={entry.status === "demo"}
          />
          <SampleReportDetailPreviewCard
            demoArtifact={demoArtifact}
            className="lg:mt-4"
            mobileDisclosure
          />
        </div>
      </section>

      <section className="praviar-section-band px-4 py-12 sm:px-6 md:py-16">
        <div className="mx-auto max-w-7xl space-y-8">
          <div className="max-w-3xl space-y-3">
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
              Inside the report
            </p>
            <h2 className="[font-family:var(--font-newsreader)] text-4xl leading-[1.02] text-[var(--text-primary)]">
              Follow each concern back to the claim evidence.
            </h2>
            <p className="text-base leading-8 text-[var(--text-secondary)] sm:text-lg">
              The report is split into clear sections so your team and counsel
              can see what supports the finding and what still needs review.
            </p>
          </div>
          <div className="grid gap-8 lg:grid-cols-[15rem_minmax(0,1fr)] lg:items-start">
            <nav
              aria-label="Sample report evidence map"
              className="hidden gap-2 lg:sticky lg:top-24 lg:grid"
              data-testid="sample-report-evidence-map"
            >
              {[
                ["Summary", "#sample-verdict-packet"],
                ["Fictional run record", "#sample-trace-packet"],
                ["Claim chart", "#sample-claim-chart"],
                ["Source records", "#sample-evidence-ledger"],
                ["Illustrative search profile", "#sample-evidence-profile"],
                ["Consistency and limits", "#sample-verification-limits"],
              ].map(([label, href]) => (
                <a
                  key={href}
                  href={href}
                  className="rounded-lg border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-surface)_82%,transparent)] px-4 py-3 text-sm font-semibold text-[var(--text-primary)] shadow-[var(--shadow-xs)] transition-colors hover:border-[var(--border-emphasis)] hover:bg-[var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]"
                >
                  {label}
                </a>
              ))}
            </nav>
            <div className="min-w-0 space-y-6">
              <SampleReportDetailLiveSections demoArtifact={demoArtifact} />
            </div>
          </div>
        </div>
      </section>

      <section className="px-4 py-14 sm:px-6 md:py-20">
        <div className="mx-auto grid min-w-0 max-w-7xl gap-7 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-6 shadow-[var(--shadow-sm)] lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center md:p-8">
          <div className="min-w-0 max-w-3xl">
            <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
              Continue the public review
            </p>
            <h2 className="mt-3 [font-family:var(--font-newsreader)] text-4xl leading-tight text-[var(--text-primary)]">
              Review the method and the limits behind this fictional record.
            </h2>
            <p className="mt-4 text-base leading-8 text-[var(--text-secondary)]">
              This sample demonstrates an interface and review trail. It is not
              evidence of recall, accuracy, legal quality, production speed or a
              customer outcome.
            </p>
            <p
              className="mt-4 rounded-lg border border-warning/25 bg-warning/10 px-4 py-3 text-sm leading-6 text-[var(--text-secondary)]"
              role="note"
            >
              {PUBLIC_PURCHASING_NOTICE}
            </p>
          </div>
          <div className="flex min-w-0 flex-col gap-3">
            <a
              href="#sample-trace-packet"
              className={cn(
                buttonVariants({ size: "lg" }),
                "h-auto min-h-11 w-full min-w-0 whitespace-normal rounded-lg px-4 py-2 text-center leading-tight sm:w-auto",
              )}
            >
              Inspect the fictional run record
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </a>
            <Link
              href={PUBLIC_METHODOLOGY_ACTION.href}
              className={cn(
                buttonVariants({ variant: "outline", size: "lg" }),
                "h-auto min-h-11 w-full min-w-0 whitespace-normal rounded-lg px-4 py-2 text-center leading-tight sm:w-auto",
              )}
            >
              {PUBLIC_METHODOLOGY_ACTION.label}
            </Link>
            <Link
              href="/trust#assurance-heading"
              className="inline-flex min-h-11 items-center justify-center text-sm font-semibold text-[var(--brand-primary)] underline-offset-4 hover:underline"
            >
              Review current assurance status
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
