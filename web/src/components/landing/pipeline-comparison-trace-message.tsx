import { motion } from "motion/react";
import {
  STEP_STYLES,
  type TraceStep,
} from "@/components/landing/pipeline-comparison-data";

export function PipelineComparisonTraceMessage({
  prefersReducedMotion = false,
  step,
}: {
  prefersReducedMotion?: boolean;
  step: TraceStep;
}) {
  const style = STEP_STYLES[step.type];
  const Icon = style.icon;
  const isThinking = step.type === "thinking";
  const isRisk = step.type === "risk";

  const direction =
    step.type === "tool_call"
      ? { x: -8, y: 0 }
      : step.type === "tool_result"
        ? { x: 8, y: 0 }
        : { x: 0, y: 10 };

  return (
    <motion.div
      initial={prefersReducedMotion ? false : { opacity: 0, ...direction }}
      animate={{ opacity: 1, x: 0, y: 0 }}
      transition={{
        duration: prefersReducedMotion ? 0 : 0.3,
        ease: [0.25, 0.1, 0.25, 1],
      }}
      className={`flex items-start gap-2 rounded-lg border px-3 py-2 ${style.bg} ${style.border} ${
        step.status === "met"
          ? "border-l-2 border-l-success"
          : step.status === "not_met"
            ? "border-l-2 border-l-error"
            : ""
      }`}
    >
      <Icon className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${style.iconColor}`} />
      <span
        className={`flex-1 text-xs leading-relaxed ${
          isThinking
            ? "italic text-[var(--text-secondary)]"
            : "text-[var(--text-primary)]"
        }`}
      >
        {step.text}
      </span>
      {isRisk && step.risk && (
        <span
          className={`shrink-0 rounded-full border px-2 py-0.5 text-xs font-bold uppercase ${
            step.risk === "high"
              ? "border-error/30 bg-error/15 text-error-emphasis"
              : step.risk === "medium"
                ? "border-warning/30 bg-warning/15 text-warning-emphasis"
                : "border-success/30 bg-success/15 text-success-emphasis"
          }`}
        >
          {step.risk}
        </span>
      )}
    </motion.div>
  );
}
