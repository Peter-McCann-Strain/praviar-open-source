"use client";

import Image from "next/image";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { useReducedMotion } from "motion/react";
import {
  type ArtifactView,
  HomePageDemoPanel,
} from "@/components/marketing/home-page-demo-panel";
import { HomePageHeroShell } from "@/components/marketing/home-page-hero-shell";
import { HomePageProofSection } from "@/components/marketing/home-page-proof-section";
import { HomePageTrustBand } from "@/components/marketing/home-page-trust-band";
import { HomePageProjectSection } from "@/components/marketing/home-page-project-section";
import { SyntheticEditorialDisclosure } from "@/components/marketing/synthetic-editorial-disclosure";
import type { DemoArtifactPayload } from "@/marketing/live-demo";
import {
  PUBLIC_CONTACT_ACTION,
  PUBLIC_MARKETING_READINESS,
  PUBLIC_PRIMARY_ACTION,
} from "@/marketing/public-readiness";
import { StripMetric } from "@/components/marketing/home-page-helpers";

interface MarketingHomePageProps {
  demoArtifact: DemoArtifactPayload;
}

const AUDIENCE_PATHS = [
  {
    label: "Biotech founder",
    title: "Screen before the next commitment",
    body: "Inspect how an early screen could frame questions before lead selection, financing, licensing, or market entry.",
    href: PUBLIC_PRIMARY_ACTION.href,
    cta: "Inspect the founder example",
  },
  {
    label: "IP counsel",
    title: "Inspect the scope and evidence",
    body: "See which sources ran, read the claim basis and keep unresolved legal questions open for review.",
    href: "/sample-reports/example-molecule-alpha#sample-claim-chart",
    cta: "Inspect the fictional claim map",
  },
  {
    label: "Pharma BD",
    title: "Triage an asset before diligence",
    body: "Turn an early patent screen into a decision brief that legal, scientific and commercial teams can inspect together.",
    href: "/sample-reports/example-molecule-alpha#sample-evidence-ledger",
    cta: "Review the fictional diligence trail",
  },
  {
    label: "Diligence team",
    title: "Follow each concern to its source",
    body: "Review what was searched, why a family matters and which gaps still need official-register or counsel checks.",
    href: "/methodology#coverage-heading",
    cta: "Review source coverage",
  },
] as const;

export function MarketingHomePage({ demoArtifact }: MarketingHomePageProps) {
  const [artifactView, setArtifactView] = useState<ArtifactView>("summary");
  const prefersReducedMotion = useReducedMotion();

  return (
    <div
      className="overflow-x-hidden"
      data-public-readiness={PUBLIC_MARKETING_READINESS}
    >
      <section className="praviar-hero-field relative overflow-hidden px-4 pb-8 pt-8 sm:px-6 sm:pt-10 md:pb-10 md:pt-12 2xl:pt-14">
        <div className="relative mx-auto grid max-w-7xl gap-7 lg:grid-cols-[0.92fr_1.08fr] lg:items-center">
          <HomePageHeroShell demoArtifact={demoArtifact} />

          <div className="relative hidden min-h-[850px] lg:block">
            <div
              aria-hidden="true"
              className="absolute inset-x-0 top-0 aspect-[16/10] overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[radial-gradient(circle_at_24%_28%,rgba(238,183,122,0.28),transparent_32%),radial-gradient(circle_at_76%_34%,rgba(31,111,109,0.2),transparent_38%),linear-gradient(135deg,#faf5eb_0%,#eef4ef_100%)] shadow-[var(--shadow-md)]"
            >
              <div className="absolute left-[12%] top-[18%] h-36 w-36 rounded-full border border-brand-primary/15 bg-white/35" />
              <div className="absolute right-[10%] top-[16%] h-52 w-52 rounded-full border border-white/60 bg-white/20" />
              <div className="absolute bottom-[12%] left-[34%] h-24 w-72 rounded-full border border-brand-primary/10 bg-white/25 blur-sm" />
            </div>
            <div className="absolute right-0 top-64 z-10 w-[96%] origin-top-right scale-[0.9]">
              <HomePageDemoPanel
                artifactView={artifactView}
                demoArtifact={demoArtifact}
                prefersReducedMotion={Boolean(prefersReducedMotion)}
                setArtifactView={setArtifactView}
              />
            </div>
          </div>
        </div>
      </section>

      <section
        className="praviar-section-band border-y border-[var(--border-subtle)] px-4 py-7 sm:px-6"
        aria-label="What every dossier keeps visible"
      >
        <div className="mx-auto grid max-w-7xl grid-cols-2 gap-3 sm:gap-5 xl:grid-cols-4">
          <StripMetric label="Where and how you plan to launch" value="Scope" />
          <StripMetric
            label="What was searched and what was missed"
            value="Sources"
          />
          <StripMetric label="Why a family may matter" value="Claims" />
          <StripMetric label="Questions ready for counsel" value="Handoff" />
        </div>
      </section>

      <HomePageProofSection demoArtifact={demoArtifact} />

      <section className="border-y border-[var(--border-subtle)] bg-[var(--bg-base)] px-4 py-14 sm:px-6 md:py-20">
        <div className="mx-auto max-w-7xl space-y-8">
          <div className="grid gap-7 lg:grid-cols-[0.78fr_1.22fr] lg:items-center">
            <div className="max-w-xl space-y-3">
              <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                Choose your starting point
              </p>
              <h2 className="[font-family:var(--font-newsreader)] text-4xl leading-tight text-[var(--text-primary)] md:text-5xl">
                Put every team on the same evidence.
              </h2>
              <p className="text-lg leading-8 text-[var(--text-secondary)]">
                Start with the decision in front of you. Then let science,
                legal, and commercial reviewers follow the same fictional
                dossier from their own point of view.
              </p>
              <p className="text-sm leading-7 text-[var(--text-tertiary)]">
                Praviar structures the handoff. Qualified patent counsel still
                makes the legal call.
              </p>
            </div>
            <figure
              className="overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-card)] shadow-[var(--shadow-md)]"
              aria-describedby="home-editorial-disclosure"
              data-ai-generated="true"
              data-provenance="/brand/editorial/provenance.public.webmanifest#team-conversation-v1.webp"
            >
              <div className="relative aspect-[16/9]">
                <Image
                  src="/brand/editorial/team-conversation-v1.webp"
                  alt="Three experienced colleagues listen to one another during a calm conversation"
                  fill
                  sizes="(min-width: 1024px) 61vw, 100vw"
                  className="object-cover object-center"
                />
              </div>
              <figcaption className="border-t border-[var(--border-subtle)] px-4 py-3 text-[var(--text-tertiary)]">
                <SyntheticEditorialDisclosure id="home-editorial-disclosure" />
              </figcaption>
            </figure>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {AUDIENCE_PATHS.map((path) => (
              <article
                key={path.label}
                className="praviar-surface-premium flex min-h-full flex-col rounded-xl p-5"
              >
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                  {path.label}
                </p>
                <h3 className="mt-3 text-xl font-semibold leading-7 text-[var(--text-primary)]">
                  {path.title}
                </h3>
                <p className="mt-3 flex-1 text-sm leading-7 text-[var(--text-secondary)]">
                  {path.body}
                </p>
                <Link
                  href={path.href}
                  className="mt-5 inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-[var(--brand-primary)] underline-offset-4 hover:underline"
                >
                  {path.cta}
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Link>
              </article>
            ))}
          </div>
          <div className="praviar-surface-premium flex flex-col gap-5 rounded-xl p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
            <div className="max-w-3xl">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                Explore the implementation
              </p>
              <p className="mt-2 text-base font-semibold text-[var(--text-primary)]">
                Read the source, architecture, evaluation records, and known
                limitations behind this research preview.
              </p>
            </div>
            <a
              href={PUBLIC_CONTACT_ACTION.href}
              className="inline-flex min-h-11 shrink-0 items-center gap-2 text-sm font-semibold text-[var(--brand-primary)] underline-offset-4 hover:underline"
            >
              {PUBLIC_CONTACT_ACTION.label}
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </a>
          </div>
        </div>
      </section>

      <HomePageTrustBand />
      <HomePageProjectSection />
    </div>
  );
}
