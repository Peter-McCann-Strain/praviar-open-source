"use client";

import { useEffect, useState } from "react";
import { flushSync } from "react-dom";
import { motion, AnimatePresence } from "motion/react";
import { SPRING_SNAPPY } from "@/lib/spring-presets";
import { cn } from "@/lib/utils";
import type { FTOReport } from "@praviar/shared-types";
import { buildConfidenceDashboardState } from "./confidence-dashboard-helpers";
import { ConfidenceDashboardExpanded } from "./confidence-dashboard-expanded";
import { ConfidenceDashboardSummary } from "./confidence-dashboard-summary";

interface ConfidenceDashboardProps {
  report: FTOReport;
  className?: string;
  defaultExpanded?: boolean;
}

export function ConfidenceDashboard({
  report,
  className,
  defaultExpanded = false,
}: ConfidenceDashboardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [printing, setPrinting] = useState(false);
  const state = buildConfidenceDashboardState(report);
  const showExpanded = expanded || printing;

  useEffect(() => {
    const handleBeforePrint = () => {
      flushSync(() => setPrinting(true));
    };
    const handleAfterPrint = () => {
      flushSync(() => setPrinting(false));
    };
    window.addEventListener("beforeprint", handleBeforePrint);
    window.addEventListener("afterprint", handleAfterPrint);
    return () => {
      window.removeEventListener("beforeprint", handleBeforePrint);
      window.removeEventListener("afterprint", handleAfterPrint);
    };
  }, []);

  return (
    <div
      className={cn(
        "praviar-surface-premium overflow-hidden rounded-lg",
        className,
      )}
    >
      <ConfidenceDashboardSummary
        expanded={showExpanded}
        band={state.band}
        summaryLabel={state.summaryLabel}
        onToggle={() => setExpanded((current) => !current)}
      />

      <AnimatePresence>
        {showExpanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={SPRING_SNAPPY}
            className="overflow-hidden"
          >
            <ConfidenceDashboardExpanded state={state} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
