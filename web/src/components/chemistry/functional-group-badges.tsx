"use client";

import { cn } from "@/lib/utils";

/* Functional-group badges map each chemistry class onto Praviar semantic and
 * brand tokens so the chemistry namespace stays inside the premium palette:
 *   info / brand-primary → informational functional groups
 *   error                → high-risk functional groups
 *   warning              → copper caution and premium tags
 *   success              → watch/clear chemistry cues
 * The previous map used raw Tailwind palette utilities that broke the
 * brand-system invariant enforced in tests/design-system. */
const GROUP_COLORS: Record<string, string> = {
  hydroxyl: "bg-info/15 text-info-emphasis border-info/25",
  carboxyl: "bg-error/15 text-error-emphasis border-error/25",
  amine: "bg-info/15 text-info-emphasis border-info/25",
  amide: "bg-brand-primary/15 text-brand-primary-dim border-brand-primary/25",
  ester: "bg-info/15 text-info-emphasis border-info/25",
  ether: "bg-brand-primary/15 text-brand-primary-dim border-brand-primary/25",
  ketone: "bg-warning/15 text-warning-emphasis border-warning/25",
  aldehyde: "bg-success/15 text-success-emphasis border-success/25",
  nitrile: "bg-info/15 text-info-emphasis border-info/25",
  nitro: "bg-error/15 text-error-emphasis border-error/25",
  sulfone: "bg-success/15 text-success-emphasis border-success/25",
  phosphate: "bg-warning/15 text-warning-emphasis border-warning/25",
  halide: "bg-success/15 text-success-emphasis border-success/25",
  aromatic: "bg-info/15 text-info-emphasis border-info/25",
  alkene: "bg-warning/15 text-warning-emphasis border-warning/25",
  alkyne: "bg-warning/15 text-warning-emphasis border-warning/25",
};

const DEFAULT_COLOR =
  "bg-[var(--surface-active)] text-[var(--text-secondary)] border-[var(--border-emphasis)]";

interface FunctionalGroupBadgesProps {
  groups: string[];
  className?: string;
}

export function FunctionalGroupBadges({
  groups,
  className,
}: FunctionalGroupBadgesProps) {
  if (!groups.length) return null;

  return (
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      {groups.map((group) => {
        const key = group.toLowerCase().replace(/[^a-z]/g, "");
        const color = GROUP_COLORS[key] || DEFAULT_COLOR;
        return (
          <span
            key={group}
            className={cn(
              "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium",
              color,
            )}
          >
            {group}
          </span>
        );
      })}
    </div>
  );
}
