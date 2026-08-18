"use client";

import { motion, useReducedMotion } from "motion/react";
import {
  ADAPTIVE_TIMELINE_TRACE,
  MAX_DELAY,
} from "@/components/landing/pipeline-comparison-data";
import { PipelineComparisonExecutionPanel } from "@/components/landing/pipeline-comparison-execution-panel";
import { PipelineComparisonMetrics } from "@/components/landing/pipeline-comparison-metrics";

/* ─── Main export ───────────────────────────────────────────────────── */

export function PipelineComparison() {
  const prefersReducedMotion = useReducedMotion() === true;
  const presentationElapsed = MAX_DELAY + 2;

  return (
    <section className="overflow-visible px-4 py-16 sm:px-6">
      <div className="max-w-6xl mx-auto">
        {/* Section header */}
        <motion.div
          initial={false}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: prefersReducedMotion ? 0 : 0.5 }}
          className="text-center mb-12"
        >
          <div className="inline-flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-[var(--surface-muted)] px-4 py-1.5 text-sm text-[var(--text-secondary)] mb-6">
            Adaptive evidence path
          </div>
          <h2 className="type-display-md text-[var(--text-primary)] mb-4">
            One review path, with deeper evidence when the record requires it.
          </h2>
          <p className="text-lg text-[var(--text-secondary)] max-w-2xl mx-auto">
            This example shows what happens when the first evidence is not
            enough. Praviar records the gap, looks more closely, and keeps the
            added support with the brief for counsel. It is not a promise about
            speed or completeness.
          </p>
        </motion.div>

        <div className="mx-auto max-w-4xl">
          <PipelineComparisonExecutionPanel
            steps={ADAPTIVE_TIMELINE_TRACE}
            elapsed={presentationElapsed}
            prefersReducedMotion={prefersReducedMotion}
          />
        </div>

        {/* Comparison metrics + guidance */}
        <PipelineComparisonMetrics
          visible
          prefersReducedMotion={prefersReducedMotion}
        />
      </div>
    </section>
  );
}
