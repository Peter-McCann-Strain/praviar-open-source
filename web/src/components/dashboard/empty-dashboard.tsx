"use client";

import Link from "next/link";
import { Atom, FileSearch, FileText, Globe, Target } from "lucide-react";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { EvidenceLaunchVisual } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { OnboardingTooltip } from "@/components/shared/onboarding-tooltip";
import { TOUR_STEPS } from "@/components/dashboard/helpers";
import { useAuthToken } from "@/hooks/use-auth-token";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";
import { storeMarketingCompoundHandoff } from "@/lib/marketing-compound-handoff";
import { WORKSPACE_SUPPORT_BOUNDARY_HREF } from "@/lib/support-boundary";

const EXAMPLES = [
  { label: "Succinic acid", value: "succinic acid" },
  { label: "Ibuprofen", value: "CC(C)Cc1ccc(cc1)C(C)C(=O)O" },
  { label: "Lactic acid", value: "OC(C)C(=O)O" },
];

export function EmptyDashboard({
  setupReadiness,
}: {
  setupReadiness?: ReactNode;
}) {
  const router = useRouter();
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const canCreateAnalysis = principal.data?.can_create_analysis === true;

  return (
    <>
      <section
        className="praviar-surface-premium overflow-hidden rounded-lg border border-[var(--card-border)]"
        data-testid="empty-dashboard-hero"
      >
        <div className="grid gap-6 p-5 md:grid-cols-[minmax(0,1fr)_minmax(280px,0.82fr)] md:items-center md:p-6">
          <div className="min-w-0">
            <div className="inline-flex items-center gap-2 rounded-full border border-brand-primary/20 bg-brand-primary/10 px-3 py-1 text-xs font-semibold uppercase text-brand-primary">
              <FileSearch className="h-3.5 w-3.5" />
              Patent intelligence workspace
            </div>
            <h2 className="mt-4 type-heading-xl text-[var(--text-primary)]">
              {canCreateAnalysis
                ? "Welcome to Praviar"
                : "Your shared FTO workspace"}
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-secondary)]">
              {canCreateAnalysis
                ? "Start with a compound and build a reviewable FTO packet with source provenance, claim-element mapping, and risk triage that remains ready for counsel review."
                : "Review analysis packets and decision summaries shared by your team. Restricted risk details and governed exports remain with counsel or an authorized workspace owner."}
            </p>

            {canCreateAnalysis ? (
              <div className="mt-5 flex flex-col gap-3 sm:flex-row">
                <Button asChild className="min-h-11 w-full gap-2 sm:w-auto">
                  <Link href="/analyses/new">
                    <FileSearch className="h-4 w-4" />
                    Start New Analysis
                  </Link>
                </Button>
              </div>
            ) : (
              <div className="mt-5 flex flex-col gap-3 sm:flex-row">
                <Button asChild className="min-h-11 w-full gap-2 sm:w-auto">
                  <Link href="/sample-reports/example-molecule-alpha">
                    <FileSearch className="h-4 w-4" />
                    View sample report
                  </Link>
                </Button>
                <Button
                  asChild
                  variant="outline"
                  className="min-h-11 w-full gap-2 sm:w-auto"
                >
                  <Link href={WORKSPACE_SUPPORT_BOUNDARY_HREF}>
                    <FileText className="h-4 w-4" />
                    Get access help
                  </Link>
                </Button>
              </div>
            )}

            {canCreateAnalysis ? (
              <div className="mt-6">
                <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
                  Try an example
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {EXAMPLES.map((example) => (
                    <button
                      key={example.value}
                      type="button"
                      onClick={() => {
                        storeMarketingCompoundHandoff(example.value);
                        router.push("/analyses/new");
                      }}
                      className="inline-flex min-h-11 items-center gap-2 rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-muted)] px-3 py-2 text-sm text-[var(--text-secondary)] transition-colors hover:border-brand-primary/40 hover:bg-brand-primary/10 hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60"
                    >
                      <Atom className="h-3.5 w-3.5" />
                      {example.label}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </div>

          <EvidenceLaunchVisual label="Praviar evidence launch preview" />
        </div>
      </section>

      {setupReadiness}

      <section
        aria-label="Workspace capabilities"
        className="grid grid-cols-1 gap-4 sm:grid-cols-3"
        data-testid="empty-dashboard-feature-proof"
      >
        <article className="praviar-surface-premium rounded-lg border border-[var(--card-border)] text-center">
          <div className="flex flex-col items-center gap-3 p-6">
            <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-info/10">
              <Globe className="h-6 w-6 text-info" />
            </div>
            <div>
              <p className="text-sm font-medium text-[var(--text-primary)]">
                Patent Risk Map
              </p>
              <p className="mt-1 text-xs text-[var(--text-tertiary)]">
                Configured-source search with coverage gaps surfaced
              </p>
            </div>
          </div>
        </article>
        <article className="praviar-surface-premium rounded-lg border border-[var(--card-border)] text-center">
          <div className="flex flex-col items-center gap-3 p-6">
            <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-info/10">
              <Target className="h-6 w-6 text-info" />
            </div>
            <div>
              <p className="text-sm font-medium text-[var(--text-primary)]">
                Claim Analysis
              </p>
              <p className="mt-1 text-xs text-[var(--text-tertiary)]">
                Claim-element mapping with cited evidence trails
              </p>
            </div>
          </div>
        </article>
        <article className="praviar-surface-premium rounded-lg border border-[var(--card-border)] text-center">
          <div className="flex flex-col items-center gap-3 p-6">
            <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-brand-primary/10">
              <FileText className="h-6 w-6 text-brand-primary" />
            </div>
            <div>
              <p className="text-sm font-medium text-[var(--text-primary)]">
                {canCreateAnalysis ? "Professional Report" : "Governed handoff"}
              </p>
              <p className="mt-1 text-xs text-[var(--text-tertiary)]">
                {canCreateAnalysis
                  ? "Export PDF with full citations and reasoning traces"
                  : "Ask counsel or the workspace owner for restricted details and approved artifacts"}
              </p>
            </div>
          </div>
        </article>
      </section>

      {canCreateAnalysis ? <OnboardingTooltip steps={TOUR_STEPS} /> : null}
    </>
  );
}
