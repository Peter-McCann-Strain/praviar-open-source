"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { GrahamFactors } from "@/components/report/invalidity-tab-helpers";

interface GrahamFactorsSectionProps {
  factors: GrahamFactors;
}

export function GrahamFactorsSection({ factors }: GrahamFactorsSectionProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="praviar-glass-panel-soft rounded-lg">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="w-full flex items-center gap-2 p-3 text-left hover:bg-[var(--surface-muted)] transition-colors"
      >
        {open ? (
          <ChevronDown className="h-4 w-4 text-[var(--text-tertiary)]" />
        ) : (
          <ChevronRight className="h-4 w-4 text-[var(--text-tertiary)]" />
        )}
        <span className="text-sm font-semibold text-[var(--text-primary)]">
          Graham Factors
        </span>
      </button>
      {open && (
        <div className="praviar-glass-strip border-t border-[var(--border-subtle)] p-4 space-y-3">
          {(
            [
              ["Scope & Content", factors.scope_and_content],
              [
                "Differences from Prior Art",
                factors.differences_from_prior_art,
              ],
              ["Level of Ordinary Skill", factors.level_of_ordinary_skill],
              ["Overall Obviousness", factors.overall_obviousness_assessment],
              ["Commercial Success", factors.commercial_success],
              ["Long-Felt Need", factors.long_felt_need],
              ["Failure of Others", factors.failure_of_others],
              ["Unexpected Results", factors.unexpected_results],
            ] as const
          )
            .filter(([, v]) => v)
            .map(([label, value]) => (
              <div key={label}>
                <p className="text-xs font-semibold text-[var(--text-tertiary)] mb-1">
                  {label}
                </p>
                <p className="text-sm text-[var(--text-primary)]">{value}</p>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
