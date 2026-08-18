import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { PipelineComparison } from "@/components/landing/pipeline-comparison";
import { SecondaryEvidenceHero } from "@/components/marketing/secondary-evidence-hero";
import { buttonVariants } from "@/components/ui/button";
import { BENCHMARK_SNAPSHOTS } from "@/marketing/content";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Deeper Evidence Checks",
  description:
    "See how Praviar gives uncertain or incomplete patent findings a deeper evidence check.",
};

export default function AdaptiveAgenticPage() {
  return (
    <div className="light">
      <SecondaryEvidenceHero
        eyebrow="Deeper Evidence Checks"
        title="A closer look when the first answer is not good enough."
        description="Every patent starts with the same structured review. When the evidence is incomplete or uncertain, Praviar looks deeper and records why."
        proofItems={[
          { label: "Start", value: "The same review path" },
          { label: "Go deeper", value: "Only when the evidence calls for it" },
          {
            label: "Walkthrough updated",
            value: BENCHMARK_SNAPSHOTS[0].lastUpdated,
          },
        ]}
        visualEyebrow="What changes"
        visualTitle="The evidence decides when more checking is needed. You do not have to choose a technical mode."
        visualItems={[
          { label: "First look", value: "Patent triage and claim mapping" },
          {
            label: "Closer look",
            value: "More evidence when a finding is uncertain",
          },
          {
            label: "Handoff",
            value: "A record counsel can follow",
          },
        ]}
        visualFooter="You receive one report. The review trail shows how much checking each finding received."
      />

      <div className="mx-auto max-w-7xl space-y-12 px-4 py-12 sm:px-6 md:py-16">
        <section className="-mx-4 border-y border-[var(--border-default)] bg-[var(--surface-muted)] sm:mx-0">
          <PipelineComparison />
        </section>

        <section className="grid gap-6 md:grid-cols-2">
          <div className="praviar-surface-premium rounded-lg p-7">
            <h2 className="text-2xl font-semibold text-[var(--text-primary)]">
              A quick first look helps when
            </h2>
            <ul className="mt-5 space-y-3">
              {[
                "You are screening a candidate quickly before investing more time.",
                "You need to compare several assets before choosing where to focus.",
                "The next step is deciding whether deeper review is worth it.",
              ].map((item) => (
                <li
                  key={item}
                  className="flex gap-3 text-sm leading-7 text-[var(--text-secondary)]"
                >
                  <CheckCircle2
                    className="mt-1 h-4 w-4 shrink-0 text-success"
                    aria-hidden="true"
                  />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-lg border border-[var(--surface-inverted)] bg-[var(--surface-inverted)] p-7 text-[var(--surface-inverted-fg)] shadow-[var(--shadow-lg)]">
            <h2 className="text-2xl font-semibold">
              A closer look matters when
            </h2>
            <ul className="mt-5 space-y-3 text-sm leading-7 text-[var(--surface-inverted-fg-muted)]">
              {[
                "One asset matters enough that stronger evidence changes the decision.",
                "The claim support is incomplete, borderline, or open to more than one reading.",
                "The output will be read by investors, partners, or outside counsel.",
              ].map((item) => (
                <li key={item} className="flex gap-3">
                  <CheckCircle2
                    className="mt-1 h-4 w-4 shrink-0 text-[var(--surface-inverted-accent)]"
                    aria-hidden="true"
                  />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="-mx-4 border-y border-[var(--border-emphasis)] bg-[var(--surface-muted)] px-4 py-8 sm:mx-0 sm:px-8">
          <div className="max-w-3xl space-y-4">
            <h2 className="[font-family:var(--font-newsreader)] text-4xl leading-[1.02] text-[var(--text-primary)]">
              Start with the compound. Praviar handles the review depth.
            </h2>
            <p className="text-lg leading-8 text-[var(--text-secondary)]">
              You do not need to pick a mode or configure an agent. If the first
              pass leaves an important question open, the evidence receives a
              closer check.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link
                href="/sample-reports/example-molecule-alpha"
                className={cn(
                  buttonVariants({ size: "lg" }),
                  "w-full rounded-lg sm:w-auto",
                )}
              >
                Open the fictional sample
              </Link>
              <Link
                href="/methodology"
                className={cn(
                  buttonVariants({ variant: "outline", size: "lg" }),
                  "w-full rounded-lg sm:w-auto",
                )}
              >
                Review the methodology
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
