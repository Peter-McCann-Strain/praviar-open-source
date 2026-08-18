import { motion } from "motion/react";
import { CheckCircle2, FileCheck2, ShieldCheck } from "lucide-react";
import { METRICS } from "@/components/landing/pipeline-comparison-data";

export function PipelineComparisonMetrics({
  prefersReducedMotion = false,
  visible,
}: {
  prefersReducedMotion?: boolean;
  visible: boolean;
}) {
  if (!visible) return null;

  return (
    <motion.div
      initial={prefersReducedMotion ? false : { opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: prefersReducedMotion ? 0 : 0.5,
        delay: prefersReducedMotion ? 0 : 0.2,
      }}
    >
      <motion.div
        initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{
          delay: prefersReducedMotion ? 0 : 0.1,
          duration: prefersReducedMotion ? 0 : 0.4,
        }}
        className="mb-8 mt-6 text-center"
      >
        <div className="inline-flex items-center gap-2.5 rounded-full border border-success/20 bg-success/[0.04] px-5 py-2.5">
          <CheckCircle2 className="h-4 w-4 text-success" />
          <span className="text-sm text-[var(--text-secondary)]">
            One review path, one audit trail &mdash;{" "}
            <span className="font-medium text-[var(--text-primary)]">
              escalation is recorded only when evidence requires it
            </span>
          </span>
        </div>
      </motion.div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {METRICS.map((metric, index) => (
          <motion.div
            key={metric.label}
            initial={prefersReducedMotion ? false : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              delay: prefersReducedMotion ? 0 : 0.3 + index * 0.08,
              duration: prefersReducedMotion ? 0 : 0.4,
              ease: [0.25, 0.1, 0.25, 1],
            }}
            className="praviar-surface-premium card-shine rounded-lg p-4"
          >
            <div className="mb-3 flex items-center gap-1.5">
              <metric.icon className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
              <span className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
                {metric.label}
              </span>
            </div>
            <div className="space-y-1.5">
              <p className="text-xs leading-relaxed text-[var(--text-secondary)]">
                {metric.value}
              </p>
            </div>
          </motion.div>
        ))}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
        <motion.div
          initial={prefersReducedMotion ? false : { opacity: 0, x: -12 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{
            delay: prefersReducedMotion ? 0 : 0.6,
            duration: prefersReducedMotion ? 0 : 0.4,
          }}
          className="rounded-lg border border-brand-primary/15 bg-brand-primary/[0.03] p-4"
        >
          <div className="mb-2 flex items-center gap-2">
            <FileCheck2 className="h-3.5 w-3.5 text-brand-primary" />
            <span className="text-xs font-semibold uppercase tracking-wider text-brand-primary">
              Lean when evidence is sufficient
            </span>
          </div>
          <p className="text-xs leading-relaxed text-[var(--text-secondary)]">
            Straightforward records stay concise: claim parsing, source
            coverage, element status, and deterministic risk treatment remain
            visible without adding unnecessary trace weight.
          </p>
        </motion.div>
        <motion.div
          initial={prefersReducedMotion ? false : { opacity: 0, x: 12 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{
            delay: prefersReducedMotion ? 0 : 0.7,
            duration: prefersReducedMotion ? 0 : 0.4,
          }}
          className="rounded-lg border border-warning/25 bg-warning/[0.06] p-4"
        >
          <div className="mb-2 flex items-center gap-2">
            <ShieldCheck className="h-3.5 w-3.5 text-warning" />
            <span className="text-xs font-semibold uppercase tracking-wider text-warning">
              Escalated when the record demands it
            </span>
          </div>
          <p className="text-xs leading-relaxed text-[var(--text-secondary)]">
            Borderline claim elements trigger a recorded escalation: retrieve
            specification text, check claim-term support, verify the result, and
            preserve a counsel-readable handoff trail.
          </p>
        </motion.div>
      </div>
    </motion.div>
  );
}
