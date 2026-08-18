import Link from "next/link";
import { ArrowRight, FileSearch, Scale, ShieldCheck } from "lucide-react";
import { SearchFunnel } from "@/components/charts/search-funnel";
import { TimingWaterfall } from "@/components/charts/timing-waterfall";
import { FtoDossierPreview } from "@/components/brand/fto-dossier-preview";
import {
  EditorialBlock,
  getSamplePriorityLabel,
  SectionHeading,
} from "@/components/marketing/home-page-helpers";
import { PROOF_ARTIFACTS } from "@/marketing/content";
import type { DemoArtifactPayload } from "@/marketing/live-demo";
import {
  PUBLIC_METHODOLOGY_ACTION,
  PUBLIC_PRIMARY_ACTION,
} from "@/marketing/public-readiness";
import { cn } from "@/lib/utils";

interface HomePageProofSectionProps {
  demoArtifact: DemoArtifactPayload;
}

function formatFictionalMappingStatus(status: string): string {
  const normalizedStatus = status.trim().toLowerCase().replace(/_/g, " ");

  if (normalizedStatus === "met") return "Mapped in fictional sample";
  if (normalizedStatus === "partially met") {
    return "Partially mapped in fictional sample";
  }
  if (normalizedStatus === "not met") return "Not mapped in fictional sample";
  return `Fictional mapping: ${normalizedStatus || "not recorded"}`;
}

export function HomePageProofSection({
  demoArtifact,
}: HomePageProofSectionProps) {
  return (
    <section className="scroll-mt-24 px-4 py-14 sm:px-6 md:py-24">
      <div className="mx-auto max-w-7xl space-y-8 lg:space-y-14">
        <SectionHeading
          eyebrow="What the dossier keeps visible"
          title="See the candidate family, its support, and the question for counsel."
          description="Each concern stays linked to claim evidence and the sources searched. Unresolved questions remain open for human review."
        />

        <div
          data-testid="homepage-proof-mobile-summary"
          className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-5 shadow-[var(--shadow-sm)] lg:hidden"
        >
          <p className="text-sm leading-7 text-[var(--text-secondary)]">
            The fictional sample contains a screening summary, claim support,
            source gaps, and questions for counsel.
          </p>
          <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
            <Link
              href={PUBLIC_PRIMARY_ACTION.href}
              className="inline-flex min-h-11 items-center gap-2 font-semibold text-[var(--brand-primary)] underline-offset-4 hover:underline"
            >
              {PUBLIC_PRIMARY_ACTION.label}
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
            <Link
              href={PUBLIC_METHODOLOGY_ACTION.href}
              className="inline-flex min-h-11 items-center font-semibold text-[var(--text-secondary)] underline-offset-4 hover:underline"
            >
              {PUBLIC_METHODOLOGY_ACTION.label}
            </Link>
          </div>
        </div>

        <div className="hidden space-y-14 lg:block">
          <EditorialBlock
            icon={FileSearch}
            eyebrow="Screening summary"
            title={PROOF_ARTIFACTS[0].title}
            summary={PROOF_ARTIFACTS[0].summary}
            visual={<VerdictVisual demoArtifact={demoArtifact} />}
          />

          <EditorialBlock
            reverse
            icon={Scale}
            eyebrow="Claim map"
            title={PROOF_ARTIFACTS[1].title}
            summary={PROOF_ARTIFACTS[1].summary}
            visual={<ClaimMapVisual demoArtifact={demoArtifact} />}
          />

          <EditorialBlock
            icon={ShieldCheck}
            eyebrow="Audit trail"
            title={PROOF_ARTIFACTS[2].title}
            summary={PROOF_ARTIFACTS[2].summary}
            visual={<AuditTrailVisual demoArtifact={demoArtifact} />}
          />
        </div>
      </div>
    </section>
  );
}

function VerdictVisual({ demoArtifact }: HomePageProofSectionProps) {
  const evidenceRows =
    demoArtifact.evidenceRows?.slice(0, 4).map((row) => ({
      reference: row.patentId,
      assignee: row.assignee,
      claimReference: row.claimReference,
      expiry: row.expiryDate ?? undefined,
      rationale: row.rationale,
      risk: row.riskLevel,
    })) ?? [];

  return (
    <FtoDossierPreview
      compact
      mobileSummaryOnly
      compoundName={demoArtifact.compoundName}
      risk={demoArtifact.verdict}
      summary={demoArtifact.executiveSummary.split("\n\n")[0]}
      metrics={[
        {
          label: "Fictional families flagged for review",
          value: String(demoArtifact.familiesFlaggedForReviewCount),
        },
        {
          label: "Fictional sample records",
          value: demoArtifact.totalPatentsFound.toLocaleString(),
        },
        { label: "Illustrative timing", value: demoArtifact.runtimeLabel },
      ]}
      riskDrivers={demoArtifact.keyFindings.map((finding, index) => ({
        label: `Driver ${index + 1}`,
        reference:
          demoArtifact.evidenceRows?.[index]?.patentId ??
          demoArtifact.claimSnapshot.patentId,
        detail: finding,
        severity:
          demoArtifact.evidenceRows?.[index]?.riskLevel ?? demoArtifact.verdict,
      }))}
      evidenceRows={evidenceRows}
      claimPreview={{
        title: demoArtifact.claimSnapshot.patentTitle,
        reference: `${demoArtifact.claimSnapshot.patentId} · claim ${demoArtifact.claimSnapshot.claimNumber}`,
        text:
          demoArtifact.claimSnapshot.elements[0]?.evidence ??
          demoArtifact.claimSnapshot.claimStatus,
        rationale: demoArtifact.designAround,
      }}
      eyebrow="Shared report summary"
      evidenceLabel={`${demoArtifact.patentsAnalyzed} fictional records reviewed`}
      statusLabel="Fictional sample"
      riskLabelOverrides={{
        high: getSamplePriorityLabel("high"),
        medium: getSamplePriorityLabel("medium"),
        low: getSamplePriorityLabel("low"),
        clear: getSamplePriorityLabel("clear"),
      }}
      provenanceItems={["Source-linked", "Counsel handoff", "Read-only"]}
      className="shadow-[var(--shadow-md)]"
    />
  );
}

function ClaimMapVisual({ demoArtifact }: HomePageProofSectionProps) {
  return (
    <div className="praviar-evidence-paper space-y-4 rounded-lg border border-[var(--border-default)] p-6 shadow-[var(--shadow-md)]">
      <div>
        <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
          Fictional lead record
        </p>
        <h3 className="mt-2 text-xl font-semibold text-[var(--text-primary)]">
          {demoArtifact.claimSnapshot.patentId}
        </h3>
      </div>
      {demoArtifact.claimSnapshot.elements.map((element) => (
        <div
          key={element.label}
          className="rounded-lg bg-[var(--surface-muted)] p-4"
        >
          <div className="flex items-center justify-between gap-4">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {element.label}
            </p>
            <span
              className={cn(
                "rounded-full px-2.5 py-1 text-xs font-semibold uppercase",
                element.status === "met"
                  ? "bg-error/15 text-error-emphasis"
                  : "bg-success/15 text-success-emphasis",
              )}
            >
              {formatFictionalMappingStatus(element.status)}
            </span>
          </div>
          <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
            Fictional evidence excerpt: {element.evidence}
          </p>
        </div>
      ))}
    </div>
  );
}

function AuditTrailVisual({ demoArtifact }: HomePageProofSectionProps) {
  return (
    <div className="praviar-evidence-paper grid gap-4 rounded-lg border border-[var(--border-default)] p-5 shadow-[var(--shadow-md)] lg:grid-cols-2">
      <div className="rounded-lg bg-[var(--surface-muted)] p-4">
        <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
          Fictional search funnel
        </p>
        <div className="mt-4 h-[260px]">
          <SearchFunnel data={demoArtifact.searchFunnel} height={260} />
        </div>
      </div>
      <div className="rounded-lg bg-[var(--surface-muted)] p-4">
        <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
          Illustrative timing
        </p>
        <div className="mt-4 h-[260px]">
          <TimingWaterfall data={demoArtifact.timing} height={260} />
        </div>
      </div>
    </div>
  );
}
