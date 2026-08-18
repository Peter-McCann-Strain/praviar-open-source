import Link from "next/link";
import { ArrowRight, CheckCircle2, Info } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import {
  PUBLIC_CONTACT_ACTION,
  PUBLIC_METHODOLOGY_ACTION,
  PUBLIC_PRIMARY_ACTION,
  PUBLIC_PURCHASING_NOTICE,
} from "@/marketing/public-readiness";
import { cn } from "@/lib/utils";

const PROJECT_SURFACES = [
  {
    title: "Next.js workbench",
    detail:
      "Compound intake, evidence drill-down, reviewer workflow, exports, and deterministic demo states.",
  },
  {
    title: "FastAPI service",
    detail:
      "Tenant-scoped persistence, asynchronous orchestration, report access policy, and generated contracts.",
  },
  {
    title: "Research pipeline",
    detail:
      "Chemistry resolution, retrieval, claim analysis, provenance, verification, and fail-closed decisions.",
  },
  {
    title: "Evaluation system",
    detail:
      "Offline fixtures, benchmark ledgers, failure accounting, and explicit evidence limitations.",
  },
] as const;

export function HomePageProjectSection() {
  return (
    <section
      id="project"
      className="praviar-section-band scroll-mt-28 px-4 py-14 sm:px-6 md:scroll-mt-32 md:py-20"
      aria-labelledby="public-project-heading"
    >
      <div className="mx-auto max-w-7xl space-y-7">
        <div className="grid gap-6 lg:grid-cols-[0.78fr_1.22fr] lg:items-end">
          <div className="max-w-2xl space-y-4">
            <p className="text-sm font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              Open engineering project
            </p>
            <h2
              id="public-project-heading"
              className="[font-family:var(--font-newsreader)] text-4xl leading-[1.06] text-[var(--text-primary)] md:text-5xl"
            >
              Inspect the implementation, evidence trail, and limits.
            </h2>
            <p className="text-base leading-7 text-[var(--text-secondary)]">
              The complete chemical patent-analysis system is open source for
              inspection, local use, and contribution: interface, API, evidence
              pipeline, vision ensemble, tests, and evaluation tools.
            </p>
          </div>

          <div
            role="note"
            className="flex gap-3 rounded-xl border border-[var(--border-default)] bg-[var(--surface-muted)] p-4 text-sm leading-6 text-[var(--text-secondary)]"
          >
            <Info
              className="mt-0.5 h-5 w-5 shrink-0 text-[var(--brand-primary)]"
              aria-hidden="true"
            />
            <p>{PUBLIC_PURCHASING_NOTICE}</p>
          </div>
        </div>

        <div
          className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
          data-testid="project-surface-grid"
        >
          {PROJECT_SURFACES.map((surface) => (
            <article
              key={surface.title}
              className="praviar-surface-premium flex min-h-full flex-col rounded-xl p-5"
            >
              <div className="flex items-center gap-2">
                <CheckCircle2
                  className="h-4 w-4 shrink-0 text-[var(--brand-primary)]"
                  aria-hidden="true"
                />
                <h3 className="font-semibold text-[var(--text-primary)]">
                  {surface.title}
                </h3>
              </div>
              <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
                {surface.detail}
              </p>
            </article>
          ))}
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
          <a
            href={PUBLIC_CONTACT_ACTION.href}
            className={cn(buttonVariants({ size: "lg" }), "rounded-lg")}
          >
            {PUBLIC_CONTACT_ACTION.label}
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </a>
          <Link
            href={PUBLIC_PRIMARY_ACTION.href}
            className={cn(
              buttonVariants({ variant: "outline", size: "lg" }),
              "rounded-lg",
            )}
          >
            {PUBLIC_PRIMARY_ACTION.label}
          </Link>
          <Link
            href={PUBLIC_METHODOLOGY_ACTION.href}
            className={cn(
              buttonVariants({ variant: "ghost", size: "lg" }),
              "rounded-lg",
            )}
          >
            {PUBLIC_METHODOLOGY_ACTION.label}
          </Link>
        </div>
      </div>
    </section>
  );
}
