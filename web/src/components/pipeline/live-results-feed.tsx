"use client";

import { useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { SPRING_SNAPPY } from "@/lib/spring-presets";
import { cn } from "@/lib/utils";

interface LiveResult {
  id: string;
  label: string;
  detail?: string;
  badge?: { text: string; color: string };
}

interface LiveResultsFeedProps {
  results: LiveResult[];
  title?: string;
  maxVisible?: number;
  className?: string;
}

/**
 * Animated feed of streaming results during pipeline execution.
 * Shows the most recent items with a "See N more" collapse toggle.
 */
export function LiveResultsFeed({
  results,
  title,
  maxVisible = 5,
  className,
}: LiveResultsFeedProps) {
  const [expanded, setExpanded] = useState(false);
  const shouldReduceMotion = useReducedMotion();

  if (results.length === 0) return null;

  const visible = expanded ? results : results.slice(0, maxVisible);
  const hiddenCount = results.length - maxVisible;

  return (
    <div className={cn("space-y-2", className)}>
      {title && (
        <h4 className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
          {title}
        </h4>
      )}

      <div className="space-y-1" aria-live="polite">
        <AnimatePresence mode="popLayout">
          {visible.map((result) => (
            <motion.div
              key={result.id}
              layout
              initial={
                shouldReduceMotion ? false : { opacity: 0, y: -8, scale: 0.97 }
              }
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={
                shouldReduceMotion
                  ? { opacity: 0 }
                  : { opacity: 0, scale: 0.97 }
              }
              transition={shouldReduceMotion ? { duration: 0 } : SPRING_SNAPPY}
              className="praviar-glass-chip flex min-w-0 items-start gap-2 rounded-lg px-3 py-2"
            >
              <span className="patent-id min-w-0 flex-1 break-words text-[var(--text-primary)] [overflow-wrap:anywhere]">
                {result.label}
              </span>
              {result.detail && (
                <span className="min-w-0 max-w-[200px] break-words text-xs text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
                  {result.detail}
                </span>
              )}
              {result.badge && (
                <span
                  className={cn(
                    "shrink-0 rounded-full px-1.5 py-0.5 text-xs font-medium",
                    result.badge.color,
                  )}
                >
                  {result.badge.text}
                </span>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {hiddenCount > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          aria-expanded={expanded}
          className="flex min-h-11 min-w-11 items-center gap-1 rounded-md px-2 py-1 text-xs text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/40 focus-visible:ring-offset-2"
        >
          {expanded ? (
            <>
              <ChevronUp className="h-4 w-4 shrink-0" aria-hidden="true" />
              Show less
            </>
          ) : (
            <>
              <ChevronDown className="h-4 w-4 shrink-0" aria-hidden="true" />
              See {hiddenCount} more
            </>
          )}
        </button>
      )}
    </div>
  );
}
