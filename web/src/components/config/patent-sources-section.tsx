"use client";

import { CheckCircle2, Database } from "lucide-react";
import { CollapsibleCard } from "@/components/config/collapsible-card";
import { PATENT_SOURCES, type ConfigStore } from "@/components/config/helpers";
import { cn } from "@/lib/utils";

interface PatentSourcesSectionProps {
  config: ConfigStore;
}

export function PatentSourcesSection({ config }: PatentSourcesSectionProps) {
  const enabledCount = PATENT_SOURCES.filter(
    (source) => config[source.key],
  ).length;

  return (
    <CollapsibleCard title="Patent Sources" icon={Database}>
      <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/60 p-3 text-xs leading-5 text-[var(--text-secondary)]">
        {enabledCount} of {PATENT_SOURCES.length} patent sources enabled. At
        least one source must remain active before defaults can be saved.
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {PATENT_SOURCES.map((source) => {
          const checked = config[source.key];
          const disableRemoval = checked && enabledCount === 1;

          return (
            <label
              key={source.key}
              className={cn(
                "flex min-h-[5.5rem] cursor-pointer items-start gap-3 rounded-lg border p-3.5 transition-colors focus-within:ring-2 focus-within:ring-brand-primary/60 focus-within:ring-offset-2 focus-within:ring-offset-[var(--bg-base)]",
                checked
                  ? "border-brand-primary/40 bg-brand-primary/5"
                  : "border-[var(--border-default)] bg-[var(--surface-muted)] hover:border-[var(--border-emphasis)]",
                disableRemoval && "cursor-not-allowed opacity-80",
              )}
            >
              <input
                type="checkbox"
                checked={checked}
                disabled={disableRemoval}
                onChange={(e) =>
                  config.setConfig({ [source.key]: e.target.checked })
                }
                className="mt-0.5 h-4 w-4 shrink-0 accent-brand-primary focus-visible:outline-none disabled:cursor-not-allowed"
              />
              <span className="min-w-0 flex-1">
                <span className="flex items-center justify-between gap-2">
                  <span className="type-body-md font-medium text-[var(--text-primary)]">
                    {source.label}
                  </span>
                  {checked ? (
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-brand-primary" />
                  ) : null}
                </span>
                <p className="type-label-sm mt-0.5 text-[var(--text-tertiary)]">
                  {source.desc}
                </p>
                {disableRemoval ? (
                  <span className="mt-2 block text-xs font-medium text-brand-primary">
                    Last active source
                  </span>
                ) : null}
              </span>
            </label>
          );
        })}
      </div>
    </CollapsibleCard>
  );
}
