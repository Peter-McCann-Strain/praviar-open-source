"use client";

import { useState } from "react";
import Link from "next/link";
import { useReducedMotion } from "motion/react";
import {
  ArrowRight,
  BriefcaseBusiness,
  Code2,
  FileSearch,
  Scale,
  ShieldCheck,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import {
  type ArtifactView,
  HomePageDemoPanel,
} from "@/components/marketing/home-page-demo-panel";
import { PraviarLockup } from "@/components/brand/praviar-lockup";
import { RiskBadge } from "@/components/shared/risk-badge";
import { buttonVariants } from "@/components/ui/button";
import {
  SectionHeading,
  StripMetric,
} from "@/components/marketing/home-page-helpers";
import type { DemoArtifactPayload } from "@/marketing/live-demo";
import {
  BRAND,
  MARKETING_DISCLAIMER,
  SYNTHETIC_SAMPLE_DISCLAIMER,
} from "@/marketing/content";
import { cn } from "@/lib/utils";
import {
  PUBLIC_METHODOLOGY_ACTION,
  PUBLIC_PRIMARY_ACTION,
  PUBLIC_PURCHASING_NOTICE,
} from "@/marketing/public-readiness";

interface MarketingDemoPageProps {
  demoArtifact: DemoArtifactPayload;
}

export function MarketingDemoPage({ demoArtifact }: MarketingDemoPageProps) {
  const [artifactView, setArtifactView] = useState<ArtifactView>("summary");
  const prefersReducedMotion = useReducedMotion();
  return (
    <div className="overflow-x-hidden bg-[var(--bg-base)]">
      <section className="praviar-report-hero-field px-4 pb-12 pt-10 sm:px-6 md:pb-16 md:pt-14">
        <div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[minmax(0,0.9fr)_minmax(480px,1.1fr)] lg:items-start">
          <div className="space-y-6">
            <PraviarLockup size="hero" tagline={BRAND.tagline} />
            <div className="max-w-3xl space-y-4">
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                Interactive Demo
              </p>
              <h1 className="[font-family:var(--font-newsreader)] text-4xl leading-[1.02] text-[var(--text-primary)] sm:text-5xl md:text-6xl">
                Inspect a fictional preliminary patent-screening dossier.
              </h1>
              <p className="max-w-2xl text-base leading-8 text-[var(--text-secondary)] sm:text-lg">
                Explore a fictional report from the first finding to the claim
                evidence, source gaps, verification warning, and counsel
                handoff.
              </p>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
              <Link
                href={PUBLIC_PRIMARY_ACTION.href}
                className={cn(
                  buttonVariants({ size: "lg" }),
                  "w-full justify-center rounded-lg sm:w-auto",
                )}
              >
                {PUBLIC_PRIMARY_ACTION.label}
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
              <Link
                href={PUBLIC_METHODOLOGY_ACTION.href}
                className={cn(
                  buttonVariants({ variant: "outline", size: "lg" }),
                  "w-full justify-center rounded-lg sm:w-auto",
                )}
              >
                {PUBLIC_METHODOLOGY_ACTION.label}
              </Link>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <StripMetric
                label="Fictional records retrieved"
                value={demoArtifact.totalPatentsFound.toLocaleString()}
              />
              <StripMetric
                label="Sample records reviewed"
                value={String(demoArtifact.patentsAnalyzed)}
              />
              <StripMetric
                label="Illustrative timing"
                value={demoArtifact.runtimeLabel}
              />
            </div>

            <div className="praviar-glass-panel-soft rounded-lg p-4 text-sm leading-7 text-[var(--text-secondary)]">
              <div className="flex flex-wrap items-center gap-2">
                <RiskBadge
                  risk={demoArtifact.verdict}
                  size="sm"
                  label="High sample priority"
                />
                <span className="font-mono text-xs text-[var(--text-tertiary)]">
                  {demoArtifact.provenance.reportId}
                </span>
              </div>
              <p className="mt-3">{SYNTHETIC_SAMPLE_DISCLAIMER}</p>
            </div>
          </div>

          <HomePageDemoPanel
            artifactView={artifactView}
            demoArtifact={demoArtifact}
            prefersReducedMotion={Boolean(prefersReducedMotion)}
            setArtifactView={setArtifactView}
          />
        </div>
      </section>

      <section className="px-4 py-14 sm:px-6 md:py-20">
        <div className="mx-auto max-w-7xl space-y-8">
          <SectionHeading
            eyebrow="What each user gets"
            title="See what each person can take from the report."
            description="Scan the finding, follow the claim support, and see the questions that remain before anyone spends time on the next review."
          />
          <div className="grid gap-4 lg:grid-cols-3">
            <DemoPersonaCard
              icon={BriefcaseBusiness}
              title="Founder or BD lead"
              body="See how a structured brief can frame the questions to take into a deeper counsel review."
            />
            <DemoPersonaCard
              icon={Scale}
              title="Patent counsel"
              body="Inspect the claim chart, citations, source gaps, and verification warnings before relying on the screening output."
            />
            <DemoPersonaCard
              icon={ShieldCheck}
              title="Team admin"
              body="Inspect the source architecture, sharing model, and review controls behind the research preview."
            />
          </div>
        </div>
      </section>

      <section className="praviar-section-band px-4 py-14 sm:px-6 md:py-20">
        <div className="mx-auto grid min-w-0 max-w-7xl gap-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(360px,0.6fr)] lg:items-stretch">
          <div className="min-w-0 space-y-4">
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
              Open-source implementation
            </p>
            <h2 className="[font-family:var(--font-newsreader)] text-4xl leading-[1.04] text-[var(--text-primary)] md:text-5xl">
              Follow the engineering from interface to evidence ledger.
            </h2>
            <p className="max-w-3xl text-lg leading-8 text-[var(--text-secondary)]">
              The public repository documents the web application, API, evidence
              pipeline, evaluation harness, and their limitations.{" "}
              {PUBLIC_PURCHASING_NOTICE}
            </p>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Link
                href={PUBLIC_PRIMARY_ACTION.href}
                className={cn(
                  buttonVariants({ size: "lg" }),
                  "w-full justify-center rounded-lg sm:w-auto",
                )}
              >
                {PUBLIC_PRIMARY_ACTION.label}
              </Link>
              <Link
                href="/trust#current-assurance"
                className={cn(
                  buttonVariants({ variant: "outline", size: "lg" }),
                  "w-full justify-center rounded-lg sm:w-auto",
                )}
              >
                Review launch readiness
              </Link>
            </div>
          </div>

          <div className="praviar-credit-ledger-field min-w-0 overflow-hidden rounded-lg border border-brand-primary/16 p-4 shadow-[var(--shadow-lg)] sm:p-5">
            <div className="min-w-0 rounded-lg bg-[var(--surface-inverted)] p-4 text-[var(--surface-inverted-fg)] shadow-[var(--shadow-md)] sm:p-5">
              <div className="flex items-start gap-3">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-[rgba(246,244,239,0.18)] bg-[rgba(246,244,239,0.08)]">
                  <Code2 className="h-5 w-5" aria-hidden="true" />
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-semibold">Demo-to-source path</p>
                  <p className="mt-1 text-xs leading-5 text-[var(--surface-inverted-fg-muted)]">
                    Inspect the synthetic sample, then trace the implementation
                    and reproducibility evidence in the public repository.
                  </p>
                </div>
              </div>
              <div className="mt-5 grid gap-3">
                <DemoLedgerLine
                  icon={FileSearch}
                  label="Frontend"
                  value="Next.js"
                />
                <DemoLedgerLine icon={Scale} label="Backend" value="FastAPI" />
                <DemoLedgerLine
                  icon={ShieldCheck}
                  label="Pipeline"
                  value="Python"
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="px-4 py-10 sm:px-6">
        <p className="mx-auto max-w-7xl text-sm leading-7 text-[var(--text-tertiary)]">
          {MARKETING_DISCLAIMER}
        </p>
      </section>
    </div>
  );
}

function DemoPersonaCard({
  body,
  icon: Icon,
  title,
}: {
  body: string;
  icon: LucideIcon;
  title: string;
}) {
  return (
    <div className="praviar-surface-premium rounded-lg p-6">
      <span className="flex h-11 w-11 items-center justify-center rounded-lg border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
        <Icon className="h-5 w-5" aria-hidden="true" />
      </span>
      <h3 className="mt-5 text-xl font-semibold text-[var(--text-primary)]">
        {title}
      </h3>
      <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
        {body}
      </p>
    </div>
  );
}

function DemoLedgerLine({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
}) {
  return (
    <div className="flex min-w-0 items-center justify-between gap-3 rounded-lg border border-[rgba(246,244,239,0.14)] bg-[rgba(246,244,239,0.07)] px-3 py-2">
      <span className="inline-flex min-w-0 items-center gap-2 text-xs text-[var(--surface-inverted-fg-muted)]">
        <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span className="truncate">{label}</span>
      </span>
      <span className="max-w-[7.5rem] break-words text-right text-xs font-semibold leading-5 sm:max-w-none sm:shrink-0 sm:text-sm">
        {value}
      </span>
    </div>
  );
}
