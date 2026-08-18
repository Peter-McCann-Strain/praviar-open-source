"use client";

import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
} from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { SPRING_SNAPPY } from "@/lib/spring-presets";
import { cn } from "@/lib/utils";

interface EvidenceCardProps {
  /** One-line summary shown when collapsed */
  summary: string;
  /** Status determines the color accent */
  status: "met" | "not_met" | "partially_met" | "unclear";
  /** Confidence percentage (0-1) */
  confidence?: number;
  /** Detailed content shown when expanded */
  children: React.ReactNode;
  /** Whether the card starts expanded */
  defaultExpanded?: boolean;
  className?: string;
}

const statusConfig = {
  met: {
    icon: AlertTriangle,
    color: "text-error",
    bg: "bg-error/5",
    border: "border-error/20",
    label: "Met (Risk)",
  },
  not_met: {
    icon: CheckCircle2,
    color: "text-success",
    bg: "bg-success/5",
    border: "border-success/20",
    label: "Not Met (Safe)",
  },
  partially_met: {
    icon: AlertTriangle,
    color: "text-warning",
    bg: "bg-warning/5",
    border: "border-warning/20",
    label: "Partially Met",
  },
  unclear: {
    icon: HelpCircle,
    color: "text-[var(--text-tertiary)]",
    bg: "bg-[var(--surface-muted)]",
    border: "border-[var(--border-subtle)]",
    label: "Unclear",
  },
};

/**
 * Progressive disclosure evidence card.
 * Layer 2: Shows summary (always visible) + evidence detail (click to expand).
 */
export function EvidenceCard({
  summary,
  status,
  confidence,
  children,
  defaultExpanded = false,
  className,
}: EvidenceCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const config = statusConfig[status];
  const Icon = config.icon;

  return (
    <div
      className={cn(
        "rounded-lg border overflow-hidden transition-colors",
        config.border,
        expanded ? config.bg : "bg-transparent",
        className,
      )}
    >
      {/* Summary row — always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        data-print-content
        className="flex w-full flex-wrap items-center gap-2 p-3 text-left transition-colors hover:bg-[var(--surface-hover)] sm:flex-nowrap sm:gap-3"
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4 text-[var(--text-tertiary)] shrink-0" />
        ) : (
          <ChevronRight className="h-4 w-4 text-[var(--text-tertiary)] shrink-0" />
        )}

        <Icon className={cn("h-4 w-4 shrink-0", config.color)} />

        <span className="min-w-[10rem] flex-1 text-sm leading-5 text-[var(--text-primary)] sm:truncate sm:leading-normal">
          {summary}
        </span>

        {confidence !== undefined && (
          <span className="text-xs text-[var(--text-tertiary)] tabular-nums shrink-0">
            {(confidence * 100).toFixed(0)}%
          </span>
        )}

        <span
          className={cn(
            "text-xs px-1.5 py-0.5 rounded font-medium shrink-0",
            config.color,
            config.bg,
          )}
        >
          {config.label}
        </span>
      </button>

      {/* Evidence detail — click to expand */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={SPRING_SNAPPY}
            className="overflow-hidden"
          >
            <div className="space-y-3 px-3 pb-3 pt-0 sm:pl-10">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
