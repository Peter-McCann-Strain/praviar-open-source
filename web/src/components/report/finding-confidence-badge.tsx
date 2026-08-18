"use client";

import * as React from "react";
import { Shield, ShieldAlert, ShieldCheck, ShieldQuestion } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export type ConfidenceLevel = "HIGH" | "MODERATE" | "LOW" | "UNKNOWN";

export interface FindingConfidenceBadgeProps {
  /** Confidence level for the finding. Unknown/missing values render as UNKNOWN. */
  level: ConfidenceLevel | string | null | undefined;
  /** One-line rationale shown on hover (e.g. "FWR test passed all 3 prongs"). */
  rationale?: string;
  /** Optional compact provenance detail — "3 of 3 prongs", "5/8 sources". */
  detail?: string;
  /** Badge size. `sm` is the default. */
  size?: "sm" | "md";
  /** Extra classes for the badge surface. */
  className?: string;
}

interface LevelSpec {
  label: string;
  Icon: React.ComponentType<{ className?: string }>;
  /** Classes map to the existing semantic design tokens (success = low-risk = high confidence). */
  surface: string;
}

const LEVEL_STYLES: Record<ConfidenceLevel, LevelSpec> = {
  HIGH: {
    label: "High confidence",
    Icon: ShieldCheck,
    surface: "border-success/30 bg-success/10 text-success",
  },
  MODERATE: {
    label: "Moderate confidence",
    Icon: Shield,
    surface: "border-warning/30 bg-warning/10 text-warning",
  },
  LOW: {
    label: "Low confidence",
    Icon: ShieldAlert,
    surface: "border-error/30 bg-error/10 text-error",
  },
  UNKNOWN: {
    label: "Unknown confidence",
    Icon: ShieldQuestion,
    surface:
      "border-[var(--border-default)] bg-[var(--surface-active)] text-[var(--text-secondary)]",
  },
};

const SIZE_STYLES: Record<
  NonNullable<FindingConfidenceBadgeProps["size"]>,
  {
    container: string;
    icon: string;
  }
> = {
  sm: {
    container: "gap-1 px-2 py-0.5 text-xs",
    icon: "h-3 w-3",
  },
  md: {
    container: "gap-1.5 px-2.5 py-1 text-xs",
    icon: "h-3.5 w-3.5",
  },
};

function normalizeLevel(
  value: FindingConfidenceBadgeProps["level"],
): ConfidenceLevel {
  if (!value) return "UNKNOWN";
  const upper = String(value).toUpperCase();
  if (upper === "HIGH" || upper === "MODERATE" || upper === "LOW") {
    return upper;
  }
  // Map common synonyms onto the 4-level scale.
  if (upper === "MEDIUM" || upper === "MED") return "MODERATE";
  return "UNKNOWN";
}

/**
 * Per-finding confidence pill with a tooltip rationale.
 *
 * The colour mapping is counter-intuitive by design: HIGH confidence in a
 * finding means a LOW risk of being wrong, so it uses the success (green)
 * token. LOW confidence reuses the error (red) token. The icon glyph
 * distinguishes the level without relying on colour alone for accessibility.
 */
export function FindingConfidenceBadge({
  level,
  rationale,
  detail,
  size = "sm",
  className,
}: FindingConfidenceBadgeProps) {
  const normalized = normalizeLevel(level);
  const spec = LEVEL_STYLES[normalized];
  const sizing = SIZE_STYLES[size];
  const Icon = spec.Icon;

  const badge = (
    <span
      className={cn(
        "inline-flex items-center rounded-full border font-semibold transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] focus-visible:ring-offset-0",
        spec.surface,
        sizing.container,
        className,
      )}
      role="status"
      aria-label={`${spec.label}${detail ? ` — ${detail}` : ""}`}
      data-testid="finding-confidence-badge"
      data-level={normalized}
    >
      <Icon className={cn("shrink-0", sizing.icon)} aria-hidden="true" />
      <span>{normalized}</span>
      {detail ? (
        <span
          className="ml-1 font-normal opacity-80"
          data-testid="finding-confidence-detail"
        >
          {detail}
        </span>
      ) : null}
    </span>
  );

  if (!rationale) {
    return badge;
  }

  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
          >
            {badge}
          </button>
        </TooltipTrigger>
        <TooltipContent
          side="top"
          className="max-w-xs text-xs leading-snug"
          data-testid="finding-confidence-tooltip"
        >
          {rationale}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export default FindingConfidenceBadge;
