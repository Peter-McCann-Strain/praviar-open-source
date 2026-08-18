import { motion } from "motion/react";
import type { DemoArtifactPayload } from "@/marketing/live-demo";
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

export function HomePageDemoClaimView({
  demoArtifact,
  prefersReducedMotion,
}: HomePageDemoViewProps) {
  return (
    <motion.div
      key="claim"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: prefersReducedMotion ? 0 : 0.28 }}
      className="space-y-5"
    >
      <div className="rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)] p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
          Fictional claim snapshot
        </p>
        <h3 className="mt-3 text-xl font-semibold text-[var(--text-primary)]">
          {demoArtifact.claimSnapshot.patentId}
        </h3>
        <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
          {demoArtifact.claimSnapshot.patentTitle}
        </p>
        <div className="praviar-glass-pill mt-4 inline-flex rounded-full px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
          Claim {demoArtifact.claimSnapshot.claimNumber} ·{" "}
          {formatFictionalMappingStatus(demoArtifact.claimSnapshot.claimStatus)}
        </div>
      </div>
      <div className="space-y-3">
        {demoArtifact.claimSnapshot.elements.map((element) => (
          <div
            key={`${element.label}-${element.status}`}
            className="praviar-surface-premium rounded-lg p-4"
          >
            <div className="flex items-center justify-between gap-4">
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {element.label}
              </p>
              <span
                className={cn(
                  "rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.14em]",
                  element.status === "met"
                    ? "bg-error/15 text-error-emphasis"
                    : element.status === "not_met"
                      ? "bg-success/15 text-success-emphasis"
                      : "bg-info/15 text-info-emphasis",
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
    </motion.div>
  );
}
