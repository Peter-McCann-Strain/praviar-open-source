import type { ComponentType } from "react";
import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { ArrowRight, Network, ShieldCheck, Wallet } from "lucide-react";

import { SyntheticEditorialDisclosure } from "@/components/marketing/synthetic-editorial-disclosure";
import { buttonVariants } from "@/components/ui/button";
import { MARKETING_DISCLAIMER, SEGMENT_PAGES } from "@/marketing/content";
import { getMarketingDemoArtifact } from "@/marketing/live-demo";
import {
  PUBLIC_CONTACT_ACTION,
  PUBLIC_METHODOLOGY_ACTION,
  PUBLIC_PRIMARY_ACTION,
  PUBLIC_PURCHASING_NOTICE,
} from "@/marketing/public-readiness";
import { cn } from "@/lib/utils";

const FOUNDER_PAGE = SEGMENT_PAGES[0];

export const metadata: Metadata = {
  title: "For Biotech Founders",
  description:
    "See how Praviar prepares an early patent screening brief for qualified patent counsel to review.",
};

const EVALUATION_STEPS = [
  {
    title: "Inspect the public sample",
    detail:
      "Use the fictional dossier to examine the format and evidence trail.",
  },
  {
    title: "Understand the public boundary",
    detail:
      "The trust page explains why confidential use is unavailable in this public preview.",
    href: "/trust",
  },
  {
    title: "Keep real matters outside the preview",
    detail:
      "Any independent deployment must establish governance for planned activity, markets, timing, and confidential data.",
  },
] as const;

export default function ForBiotechFoundersPage() {
  const demoArtifact = getMarketingDemoArtifact();

  return (
    <div className="light bg-[var(--bg-base)]">
      <section className="praviar-report-hero-field px-4 py-12 sm:px-6 md:py-16">
        <div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[0.95fr_1.05fr] lg:items-start lg:gap-10">
          <div className="space-y-6 lg:col-start-1 lg:row-start-1">
            <div className="space-y-5">
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                {FOUNDER_PAGE.eyebrow}
              </p>
              <h1 className="[font-family:var(--font-newsreader)] text-4xl leading-[1.02] text-[var(--text-primary)] sm:text-5xl">
                {FOUNDER_PAGE.title}
              </h1>
              <p className="max-w-2xl text-base leading-8 text-[var(--text-secondary)] sm:text-lg">
                {FOUNDER_PAGE.summary}
              </p>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
              <Link
                href={PUBLIC_PRIMARY_ACTION.href}
                className={cn(
                  buttonVariants({ size: "lg" }),
                  "w-full rounded-lg sm:w-auto",
                )}
              >
                {PUBLIC_PRIMARY_ACTION.label}
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
              <Link
                href={PUBLIC_METHODOLOGY_ACTION.href}
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
          </div>

          <figure
            className="relative overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-muted)] shadow-[var(--shadow-lg)] lg:col-start-2 lg:row-span-2 lg:row-start-1"
            aria-describedby="founder-editorial-disclosure"
            data-ai-generated="true"
            data-provenance="/brand/editorial/provenance.public.webmanifest#founder-conversation-v1.webp"
          >
            <div className="relative aspect-[4/5]">
              <Image
                src="/brand/editorial/founder-conversation-v1.webp"
                alt="Two experienced life-sciences professionals listen to one another in a bright atrium"
                fill
                priority
                sizes="(max-width: 1024px) 100vw, 52vw"
                className="object-cover object-center"
              />
            </div>
            <figcaption className="relative border-t border-[var(--border-subtle)] bg-[var(--surface-inverted)] px-4 py-4 text-[var(--surface-inverted-fg)] sm:absolute sm:inset-x-4 sm:bottom-4 sm:rounded-xl sm:border-white/20 sm:bg-[rgba(18,31,32,0.92)] sm:py-3 sm:text-white sm:shadow-lg sm:backdrop-blur-md">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-white/70">
                    Fictional dossier handoff
                  </p>
                  <p className="mt-1 text-lg font-semibold">
                    {demoArtifact.compoundName}
                  </p>
                </div>
                <span className="rounded-full border border-white/20 bg-white/10 px-2.5 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.1em]">
                  High sample priority
                </span>
              </div>
              <div className="mt-2 hidden rounded-lg border border-white/15 bg-black/15 px-3 py-2 sm:block">
                <p className="font-mono text-xs font-semibold">
                  {demoArtifact.claimSnapshot.patentId} · claim{" "}
                  {demoArtifact.claimSnapshot.claimNumber}
                </p>
                <p className="mt-1 line-clamp-2 text-xs leading-5 text-white/80">
                  {demoArtifact.keyFindings[0]}
                </p>
              </div>
              <p className="mt-2 text-sm font-semibold leading-6">
                Review the patent question while the development plan can still
                change.
              </p>
              <SyntheticEditorialDisclosure
                id="founder-editorial-disclosure"
                className="mt-1"
              />
            </figcaption>
          </figure>

          <div className="space-y-6 lg:col-start-1 lg:row-start-2">
            <div className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] p-5 shadow-[var(--shadow-sm)]">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                Expected artifact
              </p>
              <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
                The fictional dossier shows candidate families, claim support,
                source gaps, and questions for counsel.
              </p>
            </div>

            <ol
              className="grid gap-3 sm:grid-cols-3"
              aria-label="Public evaluation path"
            >
              {EVALUATION_STEPS.map((step, index) => (
                <li
                  key={step.title}
                  className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-4"
                >
                  <span className="text-xs font-semibold text-[var(--brand-primary)]">
                    0{index + 1}
                  </span>
                  <strong className="mt-2 block text-sm text-[var(--text-primary)]">
                    {step.title}
                  </strong>
                  <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
                    {step.detail}
                  </p>
                  {"href" in step ? (
                    <Link
                      href={step.href}
                      className="mt-3 inline-flex min-h-11 items-center text-xs font-semibold text-[var(--brand-primary)] underline-offset-4 hover:underline"
                    >
                      Trust and deployment
                    </Link>
                  ) : null}
                </li>
              ))}
            </ol>

            <div
              role="note"
              className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-4 text-xs leading-6 text-[var(--text-tertiary)]"
            >
              <p>{PUBLIC_PURCHASING_NOTICE}</p>
              <p className="mt-2">{MARKETING_DISCLAIMER}</p>
            </div>
          </div>
        </div>
      </section>

      <main className="mx-auto max-w-7xl space-y-10 px-4 py-12 sm:px-6 md:py-16">
        <section
          className="space-y-6"
          aria-labelledby="founder-workflow-heading"
        >
          <div className="max-w-3xl space-y-3">
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
              Scope and handoff
            </p>
            <h2
              id="founder-workflow-heading"
              className="[font-family:var(--font-newsreader)] text-4xl leading-[1.02] text-[var(--text-primary)]"
            >
              Give counsel a defined question and a traceable starting point.
            </h2>
          </div>

          <div className="praviar-surface-premium grid gap-5 rounded-xl p-5 lg:grid-cols-[0.8fr_1.2fr] lg:items-start">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                Scope the question
              </p>
              <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                A real matter is shaped by the activity under review and where
                and when it may happen.
              </p>
            </div>
            <dl className="grid gap-3 sm:grid-cols-2">
              <ScopeItem
                term="Planned activity"
                detail="Make, use, sell, offer for sale, or import"
              />
              <ScopeItem
                term="Market and timing"
                detail="Target jurisdictions, launch window, and relevant patent terms"
              />
            </dl>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <FounderWorkflowStep
              icon={Wallet}
              step="01"
              title="Set the review question"
              description="Record the compound, planned activity, markets, and timing."
            />
            <FounderWorkflowStep
              icon={ShieldCheck}
              step="02"
              title="Review candidate families"
              description="Inspect the source support and note gaps that need further checking."
            />
            <FounderWorkflowStep
              icon={Network}
              step="03"
              title="Prepare the counsel handoff"
              description="Share the evidence and unresolved questions in one brief."
            />
          </div>

          <aside
            aria-labelledby="founder-output-boundary"
            className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-5 py-4"
          >
            <p
              id="founder-output-boundary"
              className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]"
            >
              Product boundary
            </p>
            <p className="mt-2 max-w-5xl text-sm leading-7 text-[var(--text-secondary)]">
              Praviar organises an early patent review. It does not decide
              infringement, validity, enforceability, or legal clearance.
              Qualified patent counsel must interpret the evidence against the
              planned activity.
            </p>
          </aside>
        </section>

        <section
          aria-labelledby="founder-buying-heading"
          className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-6 shadow-[var(--shadow-sm)] md:p-8"
        >
          <div className="max-w-3xl">
            <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
              Evaluation boundary
            </p>
            <h2
              id="founder-buying-heading"
              className="mt-3 [font-family:var(--font-newsreader)] text-4xl leading-tight text-[var(--text-primary)]"
            >
              Evaluate the format without a purchasing claim.
            </h2>
            <p className="mt-4 text-sm leading-7 text-[var(--text-secondary)]">
              {PUBLIC_PURCHASING_NOTICE}
            </p>
          </div>

          <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
            <Link
              href={PUBLIC_PRIMARY_ACTION.href}
              className={cn(buttonVariants({ size: "lg" }), "rounded-lg")}
            >
              {PUBLIC_PRIMARY_ACTION.label}
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
        </section>
      </main>
    </div>
  );
}

function ScopeItem({ term, detail }: { term: string; detail: string }) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-4">
      <dt className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
        {term}
      </dt>
      <dd className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
        {detail}
      </dd>
    </div>
  );
}

function FounderWorkflowStep({
  icon: Icon,
  step,
  title,
  description,
}: {
  icon: ComponentType<{ className?: string }>;
  step: string;
  title: string;
  description: string;
}) {
  return (
    <article className="praviar-surface-premium rounded-xl p-5">
      <div className="flex items-center justify-between gap-4">
        <span className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
          {step}
        </span>
        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-[var(--bg-elevated)] text-[var(--text-primary)]">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </div>
      </div>
      <h3 className="mt-5 text-lg font-semibold text-[var(--text-primary)]">
        {title}
      </h3>
      <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
        {description}
      </p>
    </article>
  );
}
