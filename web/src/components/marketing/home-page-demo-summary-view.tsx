import { motion } from "motion/react";
import {
  AlertTriangle,
  DatabaseZap,
  FileText,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type { DemoArtifactPayload } from "@/marketing/live-demo";
import { MoleculeViewer2D } from "@/components/chemistry/molecule-viewer-2d";
import { formatFictionalFamiliesFlaggedForReview } from "@/components/marketing/home-page-helpers";
import { cn } from "@/lib/utils";

interface HomePageDemoViewProps {
  demoArtifact: DemoArtifactPayload;
  prefersReducedMotion: boolean;
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

export function HomePageDemoSummaryView({
  demoArtifact,
  prefersReducedMotion,
}: HomePageDemoViewProps) {
  const leadEvidence = demoArtifact.evidenceRows?.[0];
  const sourceReadyCount = demoArtifact.sourceHealth.filter((entry) =>
    ["ok", "success", "completed"].includes(entry.status),
  ).length;
  const sourceTotal = demoArtifact.sourceHealth.length;
  const unsupportedClaims = demoArtifact.verification.unsupportedVisibleClaims;
  const verificationWarnings = demoArtifact.verification.issues.length;
  const claimStatus = formatFictionalMappingStatus(
    demoArtifact.claimSnapshot.claimStatus,
  );
  const flaggedFamilies = formatFictionalFamiliesFlaggedForReview(
    demoArtifact.familiesFlaggedForReviewCount,
  );
  const priorityTone = demoArtifact.verdict === "high" ? "danger" : "warning";

  return (
    <motion.div
      key="summary"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: prefersReducedMotion ? 0 : 0.28 }}
      className="grid gap-3"
      data-testid="homepage-demo-summary"
    >
      <div className="grid gap-3 xl:grid-cols-[minmax(0,0.82fr)_minmax(0,1fr)]">
        <div className="rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)] p-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                Fictional compound evidence plate
              </p>
              <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                {demoArtifact.compoundName}
              </p>
            </div>
            <span
              className={cn(
                "rounded-full border px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.13em]",
                priorityTone === "danger"
                  ? "border-error/25 bg-error/10 text-error-emphasis"
                  : "border-warning/25 bg-warning/10 text-warning",
              )}
            >
              {flaggedFamilies}
            </span>
          </div>
          <MoleculeViewer2D
            smiles={demoArtifact.canonicalSmiles}
            width={300}
            height={142}
            label={demoArtifact.compoundName}
            className="mt-3 rounded-md border-[var(--border-subtle)] bg-[var(--bg-surface)]"
          />
        </div>

        <div className="grid min-w-0 gap-2 sm:grid-cols-2">
          <HeroSignal
            icon={AlertTriangle}
            label="Fictional sample priority"
            tone={priorityTone}
            value={flaggedFamilies}
            detail={demoArtifact.keyFindings[0]}
          />
          <HeroSignal
            icon={DatabaseZap}
            label="Illustrative source lanes"
            tone={sourceReadyCount === sourceTotal ? "success" : "warning"}
            value={`${sourceReadyCount}/${sourceTotal} fictional lanes available`}
            detail={`${demoArtifact.totalPatentsFound.toLocaleString()} fictional sample records searched; ${demoArtifact.patentsAfterTriage} retained for sample triage.`}
          />
          <HeroSignal
            icon={ShieldCheck}
            label="Sample check warning"
            tone="warning"
            value={
              unsupportedClaims === 0
                ? "Counsel review required"
                : `${unsupportedClaims} claims need support`
            }
            detail={`${verificationWarnings} verification warning${verificationWarnings === 1 ? "" : "s"} in this fictional sample.`}
          />
          <HeroSignal
            icon={Sparkles}
            label="Suggested next step"
            tone="neutral"
            value="Draft counsel handoff"
            detail={demoArtifact.designAround}
          />
        </div>
      </div>

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(15rem,0.66fr)]">
        <div className="overflow-hidden rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)]">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-subtle)] px-3 py-2.5">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                Claim chart preview
              </p>
              <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                {demoArtifact.claimSnapshot.patentId}
              </p>
            </div>
            <span className="rounded-full border border-warning/25 bg-warning/10 px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.13em] text-warning">
              Claim {demoArtifact.claimSnapshot.claimNumber} · {claimStatus}
            </span>
          </div>
          <div className="divide-y divide-[var(--border-subtle)]">
            {demoArtifact.claimSnapshot.elements.slice(0, 2).map((element) => (
              <div
                key={`${element.label}-${element.traceId}`}
                className="grid gap-2 px-3 py-2.5 sm:grid-cols-[6.5rem_minmax(0,1fr)]"
              >
                <div>
                  <p className="text-xs font-semibold text-[var(--text-primary)]">
                    {element.label}
                  </p>
                  <p
                    className={cn(
                      "mt-1 inline-flex rounded-full px-2 py-0.5 text-xs font-semibold uppercase tracking-[0.12em]",
                      element.status === "met"
                        ? "bg-error/10 text-error-emphasis"
                        : element.status === "not_met"
                          ? "bg-success/10 text-success-emphasis"
                          : "bg-warning/10 text-warning",
                    )}
                  >
                    {formatFictionalMappingStatus(element.status)}
                  </p>
                </div>
                <p className="line-clamp-2 text-xs leading-5 text-[var(--text-secondary)]">
                  Fictional evidence excerpt: {element.evidence}
                </p>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-brand-primary/15 bg-brand-primary/8 p-3">
          <div className="flex items-start gap-2">
            <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
              <FileText className="h-4 w-4" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                Fictional lead record
              </p>
              <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                {leadEvidence?.patentId ?? demoArtifact.claimSnapshot.patentId}
              </p>
              <p className="mt-1 line-clamp-4 text-xs leading-5 text-[var(--text-secondary)]">
                Fictional evidence excerpt:{" "}
                {leadEvidence?.rationale ??
                  demoArtifact.executiveSummary.split("\n\n")[0]}
              </p>
            </div>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <ProofDatum
              label="Illustrative timing"
              value={demoArtifact.runtimeLabel}
            />
            <ProofDatum
              label="Sample build"
              value={demoArtifact.provenance.pipelineVersion}
            />
          </div>
        </div>
      </div>

      <p className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]">
        Fictional sample summary:{" "}
        {demoArtifact.executiveSummary.split("\n\n")[0]}
      </p>
    </motion.div>
  );
}

type HeroSignalTone = "danger" | "neutral" | "success" | "warning";

function HeroSignal({
  detail,
  icon: Icon,
  label,
  tone,
  value,
}: {
  detail: string;
  icon: typeof AlertTriangle;
  label: string;
  tone: HeroSignalTone;
  value: string;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-2.5 shadow-[var(--shadow-xs)]">
      <div className="flex min-w-0 items-start gap-2">
        <span
          className={cn(
            "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border",
            tone === "danger"
              ? "border-error/25 bg-error/10 text-error"
              : tone === "warning"
                ? "border-warning/25 bg-warning/10 text-warning"
                : tone === "success"
                  ? "border-brand-primary/20 bg-brand-primary/10 text-brand-primary"
                  : "border-[var(--border-subtle)] bg-[var(--surface-subtle)] text-[var(--text-secondary)]",
          )}
        >
          <Icon className="h-4 w-4" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.13em] text-[var(--text-tertiary)]">
            {label}
          </p>
          <p className="mt-1 text-xs font-semibold leading-5 text-[var(--text-primary)]">
            {value}
          </p>
          <p className="mt-0.5 line-clamp-2 text-xs leading-4 text-[var(--text-tertiary)]">
            {detail}
          </p>
        </div>
      </div>
    </div>
  );
}

function ProofDatum({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-brand-primary/15 bg-[var(--bg-surface)]/72 px-2.5 py-2">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-1 truncate text-xs font-semibold text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}
