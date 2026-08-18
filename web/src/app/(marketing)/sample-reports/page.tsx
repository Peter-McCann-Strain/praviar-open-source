import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { ArrowRight, CheckCircle2, ShieldAlert } from "lucide-react";
import { SampleReportDetailPreviewCard } from "@/components/marketing/sample-report-detail-preview-card";
import { SyntheticEditorialDisclosure } from "@/components/marketing/synthetic-editorial-disclosure";
import { buttonVariants } from "@/components/ui/button";
import { MARKETING_DISCLAIMER } from "@/marketing/content";
import { getMarketingDemoArtifact } from "@/marketing/live-demo";
import { cn } from "@/lib/utils";
import {
  PUBLIC_CONTACT_ACTION,
  PUBLIC_METHODOLOGY_ACTION,
  PUBLIC_PRIMARY_ACTION,
  PUBLIC_PURCHASING_NOTICE,
} from "@/marketing/public-readiness";

export const metadata: Metadata = {
  title: "Sample Dossier",
  description:
    "Inspect the structure of a fictional preliminary patent-screening dossier for biotech teams and patent counsel.",
};

export default function SampleReportsPage() {
  const demoArtifact = getMarketingDemoArtifact();

  return (
    <div className="light bg-[var(--bg-base)]">
      <section className="praviar-report-hero-field px-4 pb-14 pt-12 sm:px-6 md:pb-20 md:pt-16">
        <div className="mx-auto grid max-w-7xl gap-x-10 gap-y-6 lg:grid-cols-[0.95fr_1.05fr] lg:items-start">
          <div className="max-w-3xl space-y-4 lg:col-start-1 lg:row-start-1">
            <p className="type-marketing-label">Sample Dossier</p>
            <h1 className="[font-family:var(--font-newsreader)] text-4xl leading-[1.02] text-[var(--text-primary)] sm:text-5xl">
              See the report before you run one.
            </h1>
            <p className="text-base leading-8 text-[var(--text-secondary)] sm:text-lg">
              Follow a fictional compound from the first screening priority to
              the claim evidence, research hypotheses, and questions for patent
              counsel.
            </p>
            <div className="flex flex-col gap-3 pt-2 sm:flex-row sm:flex-wrap">
              <Link
                href="/sample-reports/example-molecule-alpha"
                className={cn(
                  buttonVariants({ size: "lg" }),
                  "w-full rounded-lg sm:w-auto",
                )}
              >
                Open the sample dossier
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
              <Link
                href="/methodology"
                className={cn(
                  buttonVariants({ variant: "outline", size: "lg" }),
                  "w-full rounded-lg sm:w-auto",
                )}
              >
                {PUBLIC_METHODOLOGY_ACTION.label}
              </Link>
              <a
                href={PUBLIC_CONTACT_ACTION.href}
                className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold text-[var(--brand-primary)] underline-offset-4 hover:underline sm:w-auto"
              >
                {PUBLIC_CONTACT_ACTION.label}
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </a>
            </div>
            <nav
              aria-label="Choose a sample perspective"
              className="grid gap-2 sm:grid-cols-3"
            >
              {[
                ["Founder summary", "#sample-verdict-packet"],
                ["Counsel claim review", "#sample-claim-chart"],
                ["Diligence source trail", "#sample-evidence-ledger"],
              ].map(([label, target]) => (
                <Link
                  key={label}
                  href={`/sample-reports/example-molecule-alpha${target}`}
                  className="flex min-h-11 items-center justify-between rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:border-[var(--border-emphasis)] hover:text-[var(--text-primary)]"
                >
                  {label}
                  <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                </Link>
              ))}
            </nav>
            <figure
              className="relative min-h-72 overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[radial-gradient(circle_at_84%_18%,rgba(31,111,109,0.18),transparent_30%),radial-gradient(circle_at_76%_84%,rgba(238,183,122,0.24),transparent_34%),linear-gradient(135deg,#fbf7ef_0%,#edf3ef_100%)] shadow-[var(--shadow-md)]"
              data-testid="sample-report-anatomy"
            >
              <div
                aria-hidden="true"
                className="absolute right-[10%] top-[12%] h-36 w-36 rounded-full border border-white/60 bg-white/20"
              />
              <figcaption className="relative flex min-h-72 max-w-sm flex-col justify-center p-5 sm:p-6">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                  One fictional public dossier
                </p>
                <ol className="mt-4 space-y-2">
                  {[
                    [
                      "Start with the screening priority",
                      "#sample-verdict-packet",
                    ],
                    ["Read the claim basis", "#sample-claim-chart"],
                    ["Inspect the cited evidence", "#sample-evidence-ledger"],
                    [
                      "Consider research directions",
                      "#sample-evidence-profile",
                    ],
                    [
                      "Take the open questions to counsel",
                      "#sample-verification-limits",
                    ],
                  ].map(([item, target], index) => (
                    <li
                      key={item}
                      className="rounded-lg border border-white/60 bg-white/78 text-sm font-semibold text-[var(--text-primary)] shadow-[var(--shadow-xs)] backdrop-blur-sm"
                    >
                      <Link
                        href={`/sample-reports/example-molecule-alpha${target}`}
                        className="flex min-h-11 items-center gap-3 px-3 py-2.5"
                      >
                        <span className="font-mono text-xs text-[var(--brand-primary)]">
                          {String(index + 1).padStart(2, "0")}
                        </span>
                        {item}
                      </Link>
                    </li>
                  ))}
                </ol>
              </figcaption>
            </figure>
          </div>

          <SampleReportDetailPreviewCard
            demoArtifact={demoArtifact}
            className="lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:mt-4"
            compactItemLimit={1}
            mobileSummaryOnly
            mobileVisualHidden
          />

          <div className="space-y-6 lg:col-start-1 lg:row-start-2">
            <div
              className="hidden gap-3 lg:grid lg:grid-cols-3"
              data-testid="sample-index-supporting-metrics"
            >
              {[
                {
                  label: "Fictional records retrieved",
                  value: demoArtifact.totalPatentsFound.toLocaleString(),
                },
                {
                  label: "Sample records reviewed",
                  value: String(demoArtifact.patentsAnalyzed),
                },
                {
                  label: "Illustrative timing",
                  value: demoArtifact.runtimeLabel,
                },
              ].map((metric) => (
                <div
                  key={metric.label}
                  className="praviar-glass-chip rounded-lg p-4"
                >
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                    {metric.label}
                  </p>
                  <p className="mt-2 text-lg font-semibold text-[var(--text-primary)]">
                    {metric.value}
                  </p>
                </div>
              ))}
            </div>

            <div className="praviar-glass-panel-soft rounded-lg p-4 text-xs leading-6 text-[var(--text-secondary)]">
              <span className="font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                Sample source
              </span>{" "}
              <span className="font-mono [overflow-wrap:anywhere]">
                {demoArtifact.sourceReference}
              </span>
            </div>

            <p className="max-w-2xl text-sm leading-7 text-[var(--text-tertiary)]">
              {MARKETING_DISCLAIMER}
            </p>
          </div>
        </div>
      </section>

      <section className="border-b border-[var(--border-subtle)] bg-[var(--surface-card)] px-4 py-12 sm:px-6 md:py-16">
        <div className="mx-auto grid max-w-7xl gap-7 lg:grid-cols-[1.15fr_0.85fr] lg:items-center">
          <figure
            className="overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-base)] shadow-[var(--shadow-md)]"
            aria-describedby="sample-review-editorial-disclosure"
            data-ai-generated="true"
            data-provenance="/brand/editorial/provenance.public.webmanifest#counsel-conversation-v1.webp"
          >
            <div className="relative aspect-[16/10]">
              <Image
                src="/brand/editorial/counsel-conversation-v1.webp"
                alt="Two experienced professionals exchange a thoughtful look during a quiet conversation"
                fill
                sizes="(min-width: 1024px) 58vw, 100vw"
                className="object-cover object-center"
              />
            </div>
            <figcaption className="border-t border-[var(--border-subtle)] px-4 py-3 text-[var(--text-tertiary)]">
              <SyntheticEditorialDisclosure id="sample-review-editorial-disclosure" />
            </figcaption>
          </figure>
          <div className="max-w-xl space-y-4">
            <p className="type-marketing-label">Built for a shared review</p>
            <h2 className="[font-family:var(--font-newsreader)] text-4xl leading-tight text-[var(--text-primary)] md:text-5xl">
              Move from the priority to the source.
            </h2>
            <p className="text-lg leading-8 text-[var(--text-secondary)]">
              The dossier keeps the finding, claim support, cited evidence, and
              open questions together. Your team can inspect the trail before
              counsel makes the legal call.
            </p>
            <Link
              href="/sample-reports/example-molecule-alpha#sample-claim-chart"
              className="inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-[var(--brand-primary)] underline-offset-4 hover:underline"
            >
              Follow the fictional claim evidence
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-7xl space-y-10 px-4 py-12 sm:px-6 md:py-20">
        <div className="max-w-3xl space-y-3">
          <p className="type-marketing-label">Read the sample honestly</p>
          <h2 className="[font-family:var(--font-newsreader)] text-4xl leading-[1.02] text-[var(--text-primary)]">
            What this dossier shows, and what it cannot prove.
          </h2>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <article className="rounded-2xl border border-success/25 bg-success/5 p-6">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-success-emphasis">
              What you can inspect
            </p>
            <ul className="mt-5 space-y-3 text-sm leading-7 text-[var(--text-secondary)]">
              {[
                "The report structure from finding to cited claim evidence",
                "How missing sources, uncertainty and reviewer checks appear",
                "The questions and research directions prepared for counsel",
              ].map((item) => (
                <li key={item} className="flex gap-3">
                  <CheckCircle2
                    className="mt-1 h-4 w-4 shrink-0 text-success-emphasis"
                    aria-hidden="true"
                  />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </article>
          <article className="rounded-2xl border border-warning/25 bg-warning/5 p-6">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-warning-emphasis">
              What it does not prove
            </p>
            <ul className="mt-5 space-y-3 text-sm leading-7 text-[var(--text-secondary)]">
              {[
                "Recall, completeness or search accuracy on a real matter",
                "Not a legal opinion, clearance decision or counsel review",
                "A customer result, benchmark result or production outcome",
              ].map((item) => (
                <li key={item} className="flex gap-3">
                  <ShieldAlert
                    className="mt-1 h-4 w-4 shrink-0 text-warning-emphasis"
                    aria-hidden="true"
                  />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </article>
        </div>
        <section className="praviar-section-band rounded-2xl border border-[var(--border-default)] p-6 md:p-8">
          <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
            <div className="min-w-0 max-w-3xl">
              <p className="type-marketing-label">Informational launch</p>
              <h2 className="mt-3 [font-family:var(--font-newsreader)] text-3xl leading-tight text-[var(--text-primary)] md:text-4xl">
                Inspect the fictional workflow before workspace access opens.
              </h2>
              <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                {PUBLIC_PURCHASING_NOTICE} The sample and methodology remain
                available so your team can evaluate the review structure now.
              </p>
            </div>
            <div className="flex min-w-0 flex-col gap-3 sm:flex-row lg:flex-col">
              <Link
                href={PUBLIC_PRIMARY_ACTION.href}
                className={cn(
                  buttonVariants({ size: "lg" }),
                  "h-auto min-h-11 w-full min-w-0 whitespace-normal rounded-lg px-4 py-2 text-center leading-tight sm:w-auto",
                )}
              >
                {PUBLIC_PRIMARY_ACTION.label}
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
              <Link
                href={PUBLIC_METHODOLOGY_ACTION.href}
                className={cn(
                  buttonVariants({ variant: "outline", size: "lg" }),
                  "h-auto min-h-11 w-full min-w-0 whitespace-normal rounded-lg px-4 py-2 text-center leading-tight sm:w-auto",
                )}
              >
                {PUBLIC_METHODOLOGY_ACTION.label}
              </Link>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
