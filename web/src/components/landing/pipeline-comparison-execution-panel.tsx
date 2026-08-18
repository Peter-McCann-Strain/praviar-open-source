import { motion } from "motion/react";
import {
  TIMELINE_CONFIG,
  type TraceStep,
} from "@/components/landing/pipeline-comparison-data";
import { PipelineComparisonTraceMessage } from "@/components/landing/pipeline-comparison-trace-message";

interface PipelineComparisonExecutionPanelProps {
  elapsed: number;
  prefersReducedMotion?: boolean;
  steps: TraceStep[];
}

export function PipelineComparisonExecutionPanel({
  elapsed,
  prefersReducedMotion = false,
  steps,
}: PipelineComparisonExecutionPanelProps) {
  const config = TIMELINE_CONFIG;
  const visibleSteps = steps.filter((step) => elapsed >= step.delay);
  const isComplete = visibleSteps.length === steps.length;
  const progress = Math.min((visibleSteps.length / steps.length) * 100, 100);
  const isActive = elapsed >= 0 && !isComplete;

  return (
    <div
      className={`praviar-surface-premium flex flex-col overflow-hidden rounded-lg transition-all duration-500 ${
        isComplete
          ? "border-success/25 shadow-lg shadow-success/5"
          : isActive
            ? `${config.accentBorder} shadow-md`
            : "border-[var(--border-default)]"
      }`}
    >
      <div className="flex items-center gap-2.5 border-b border-[var(--border-subtle)] px-4 py-3">
        <div
          className={`flex h-7 w-7 items-center justify-center rounded-lg ${config.accentBg}`}
        >
          <span
            aria-hidden="true"
            className={`h-2.5 w-2.5 rounded-full ${config.progressBar}`}
          />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-[var(--text-primary)]">
            {config.label}
          </div>
          <div className="text-xs text-[var(--text-tertiary)]">
            {config.tagline}
          </div>
        </div>
        {isComplete && (
          <motion.div
            initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={
              prefersReducedMotion
                ? { duration: 0 }
                : { type: "spring", stiffness: 300, damping: 20 }
            }
            className="shrink-0 rounded-full border border-success/25 bg-success/15 px-2.5 py-0.5 text-xs font-bold uppercase tracking-wider text-success-emphasis"
          >
            Complete
          </motion.div>
        )}
      </div>

      <div
        data-testid="pipeline-comparison-trace-scroll"
        aria-label="Representative adaptive evidence trace"
        className="min-h-[200px] max-h-[200px] flex-1 space-y-1.5 overflow-y-auto p-3 sm:min-h-[280px] sm:max-h-[280px] lg:min-h-[340px] lg:max-h-[340px]"
        role="region"
        tabIndex={0}
        style={{
          maskImage:
            visibleSteps.length > 7
              ? "linear-gradient(to bottom, transparent 0%, var(--brand-ink, #0B1F24) 10%, var(--brand-ink, #0B1F24) 100%)"
              : undefined,
        }}
      >
        {visibleSteps.map((step, index) => (
          <PipelineComparisonTraceMessage
            key={`${step.delay}-${index}`}
            step={step}
            prefersReducedMotion={prefersReducedMotion}
          />
        ))}

        {elapsed < 0 && (
          <div className="flex h-full flex-col justify-center rounded-md border border-dashed border-brand-primary/20 bg-brand-primary/5 p-3">
            <p className="text-xs font-semibold text-[var(--text-secondary)]">
              Evidence route ready
            </p>
            <p className="mt-1 text-xs leading-4 text-[var(--text-tertiary)]">
              The review begins when this workspace enters view.
            </p>
            <ol className="mt-3 grid grid-cols-3 gap-1.5 text-center text-xs font-semibold uppercase tracking-[0.08em] text-[var(--brand-primary-dim)]">
              <li className="rounded-md border border-brand-primary/15 bg-[var(--bg-surface)]/70 px-1 py-2">
                Intake
              </li>
              <li className="rounded-md border border-brand-primary/15 bg-[var(--bg-surface)]/70 px-1 py-2">
                Evaluate
              </li>
              <li className="rounded-md border border-brand-primary/15 bg-[var(--bg-surface)]/70 px-1 py-2">
                Handoff
              </li>
            </ol>
          </div>
        )}
      </div>

      <div className="border-t border-[var(--border-subtle)] px-4 py-2.5">
        <div className="mb-1.5 flex items-center justify-between text-xs text-[var(--text-tertiary)]">
          <span className="tabular-nums">
            {visibleSteps.length} / {steps.length} steps
          </span>
          <span className="font-mono tabular-nums">
            {Math.round(progress)}%
          </span>
        </div>
        <div className="h-1 overflow-hidden rounded-full bg-[var(--bg-elevated)]">
          <motion.div
            className={`h-full rounded-full ${config.progressBar}`}
            animate={{ width: `${progress}%` }}
            transition={{
              duration: prefersReducedMotion ? 0 : 0.3,
              ease: "easeOut",
            }}
          />
        </div>
      </div>
    </div>
  );
}
