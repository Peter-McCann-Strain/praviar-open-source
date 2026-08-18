"use client";

import Link from "next/link";
import { ArrowRight, FileText, ShieldCheck } from "lucide-react";

import { RiskBadge } from "@/components/shared/risk-badge";
import { getSamplePriorityLabel } from "@/components/marketing/home-page-helpers";
import { buttonVariants } from "@/components/ui/button";
import { SYNTHETIC_SAMPLE_DISCLAIMER } from "@/marketing/content";
import type { DemoArtifactPayload } from "@/marketing/live-demo";
import {
  PUBLIC_METHODOLOGY_ACTION,
  PUBLIC_PRIMARY_ACTION,
  PUBLIC_PURCHASING_NOTICE,
} from "@/marketing/public-readiness";
import { cn } from "@/lib/utils";

interface HomePageHeroShellProps {
  demoArtifact: DemoArtifactPayload;
}

function formatFictionalClaimReference(value: string): string {
  return value
    .replace(/\bpartially[_ ]met\b/giu, "partially mapped in fictional sample")
    .replace(/\bnot[_ ]met\b/giu, "not mapped in fictional sample")
    .replace(/\bmet\b/giu, "mapped in fictional sample");
}

export function HomePageHeroShell({ demoArtifact }: HomePageHeroShellProps) {
  const firstFinding = demoArtifact.keyFindings[0];
  const firstEvidence = demoArtifact.evidenceRows?.[0];
  const leadEvidenceReference =
    firstEvidence?.patentId ?? demoArtifact.claimSnapshot.patentId;
  const leadClaimReference = formatFictionalClaimReference(
    firstEvidence?.claimReference ??
      `Claim ${demoArtifact.claimSnapshot.claimNumber} · ${demoArtifact.claimSnapshot.claimStatus.replace(/_/g, " ")}`,
  );
  const leadEvidenceRationale =
    firstEvidence?.rationale ?? firstFinding ?? demoArtifact.executiveSummary;

  return (
    <div className="praviar-mobile-safe flex flex-col gap-5 md:gap-7">
      <div className="order-1 space-y-4 md:space-y-5">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
          Freedom-to-operate screening for biotech
        </p>
        <h1 className="max-w-3xl [font-family:var(--font-newsreader)] text-[2rem] leading-[0.98] text-[var(--text-primary)] sm:text-5xl sm:leading-[0.98] md:text-6xl 2xl:text-7xl">
          See which patent families may deserve attention before the programme
          advances.
        </h1>
        <p className="max-w-2xl text-[0.98rem] leading-7 text-[var(--text-secondary)] sm:text-lg sm:leading-8 md:text-xl">
          Praviar searches selected sources, prioritises candidate families, and
          organises the evidence into a brief for qualified patent counsel to
          review.
        </p>
        <p className="max-w-2xl text-sm font-medium leading-6 text-[var(--text-secondary)]">
          Built for biotech founders and IP teams preparing for lead selection,
          financing, licensing, or market entry.
        </p>
        <div className="flex flex-col gap-3 pt-1 sm:flex-row sm:flex-wrap">
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
        </div>
      </div>

      <div
        className="praviar-evidence-paper order-2 max-w-3xl rounded-lg border border-[var(--border-default)] p-4 shadow-[var(--shadow-sm)] sm:p-5"
        data-testid="homepage-public-preview"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              Current research preview
            </p>
            <h2 className="mt-2 text-xl font-semibold text-[var(--text-primary)]">
              Inspect the canonical fictional dossier
            </h2>
          </div>
          <span className="inline-flex items-center gap-2 rounded-full border border-brand-primary/20 bg-brand-primary/8 px-3 py-1.5 text-xs font-semibold text-brand-primary">
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            Informational only
          </span>
        </div>
        <div className="mt-4 rounded-lg bg-[var(--surface-muted)] p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
            Expected artifact
          </p>
          <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
            The sample shows candidate families, claim support, source gaps, and
            questions for counsel.
          </p>
        </div>
        <p className="mt-4 text-xs leading-5 text-[var(--text-tertiary)]">
          {PUBLIC_PURCHASING_NOTICE}
        </p>
      </div>

      <div
        className="praviar-hero-proof-card order-3 hidden rounded-lg border border-[var(--border-default)] p-5 shadow-[var(--shadow-md)] md:block lg:hidden"
        data-testid="homepage-hero-proof"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
              Fictional dossier preview
            </p>
            <h2 className="mt-1 text-xl font-semibold text-[var(--text-primary)] sm:text-2xl">
              {demoArtifact.compoundName}
            </h2>
          </div>
          <RiskBadge
            risk={demoArtifact.verdict}
            size="md"
            showIcon
            label={getSamplePriorityLabel(demoArtifact.verdict)}
            className="shadow-none"
          />
        </div>

        <div
          className="praviar-glass-chip mt-3 flex flex-wrap gap-2 rounded-md px-3 py-2 text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-tertiary)]"
          data-testid="homepage-hero-caveat"
        >
          <span>Synthetic patent data</span>
          <span aria-hidden="true">/</span>
          <span>Not a legal opinion</span>
        </div>

        <div className="mt-3 grid grid-cols-3 gap-2">
          <HeroProofMetric
            label="Fictional families flagged for review"
            value={String(demoArtifact.familiesFlaggedForReviewCount)}
          />
          <HeroProofMetric
            label="Sample records"
            value={demoArtifact.totalPatentsFound.toLocaleString()}
          />
          <HeroProofMetric
            label="Fictional records reviewed"
            value={String(demoArtifact.patentsAnalyzed)}
          />
        </div>

        <div className="praviar-glass-panel-soft mt-3 rounded-lg p-3 sm:p-4">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-error/10 text-error">
              <FileText className="h-4 w-4" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <p className="font-mono text-xs font-semibold text-[var(--text-primary)]">
                {leadEvidenceReference}
              </p>
              <p className="mt-1 text-xs font-semibold text-[var(--text-primary)] sm:text-sm">
                {leadClaimReference}
              </p>
              <p className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--text-secondary)] sm:text-sm sm:leading-6">
                Fictional evidence excerpt: {leadEvidenceRationale}
              </p>
            </div>
          </div>
        </div>

        <p className="mt-3 text-xs leading-5 text-[var(--text-tertiary)]">
          {SYNTHETIC_SAMPLE_DISCLAIMER}
        </p>
      </div>

      <div
        aria-hidden="true"
        className="relative order-4 aspect-[16/7] overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[radial-gradient(circle_at_20%_36%,rgba(238,183,122,0.3),transparent_34%),radial-gradient(circle_at_78%_32%,rgba(31,111,109,0.2),transparent_40%),linear-gradient(135deg,#faf5eb_0%,#eef4ef_100%)] shadow-[var(--shadow-sm)] lg:hidden"
      >
        <div className="absolute left-[12%] top-[18%] h-20 w-20 rounded-full border border-brand-primary/15 bg-white/30" />
        <div className="absolute right-[12%] top-[14%] h-28 w-28 rounded-full border border-white/60 bg-white/20" />
      </div>
    </div>
  );
}

function HeroProofMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="praviar-glass-chip rounded-lg px-2.5 py-2.5">
      <p className="text-lg font-semibold text-[var(--text-primary)]">
        {value}
      </p>
      <p className="mt-1 text-[0.65rem] font-semibold uppercase tracking-[0.1em] text-[var(--text-tertiary)]">
        {label}
      </p>
    </div>
  );
}
