"use client";

import { useId } from "react";
import { Brain, Globe } from "lucide-react";
import { CollapsibleCard } from "@/components/config/collapsible-card";
import {
  CONFIG_FIELD_CLASS,
  EFFORT_LEVELS,
  type ConfigStore,
} from "@/components/config/helpers";
import { JURISDICTION_GROUPS } from "@/stores/config-store";
import { cn } from "@/lib/utils";

interface JurisdictionsThinkingSectionProps {
  config: ConfigStore;
}

export function JurisdictionsThinkingSection({
  config,
}: JurisdictionsThinkingSectionProps) {
  const analysisEffortId = useId();
  const triageEffortId = useId();
  const reportEffortId = useId();
  const effortControls = [
    {
      id: analysisEffortId,
      key: "thinkingEffortAnalysis" as const,
      label: "Analysis",
    },
    {
      id: triageEffortId,
      key: "thinkingEffortTriage" as const,
      label: "Triage",
    },
    {
      id: reportEffortId,
      key: "thinkingEffortReport" as const,
      label: "Report",
    },
  ];

  return (
    <CollapsibleCard title="Jurisdictions & Execution Rigor" icon={Globe}>
      <div>
        <label className="mb-1 block type-body-md font-medium text-[var(--text-primary)]">
          Search Jurisdictions
        </label>
        <p className="mb-3 type-label-sm text-[var(--text-tertiary)]">
          {config.searchJurisdictions.length} selected for adaptive evidence
          collection
        </p>
        {JURISDICTION_GROUPS.map((group) => (
          <div key={group.label} className="mb-3">
            <p className="mb-1.5 type-label-sm font-medium uppercase tracking-wider text-[var(--text-tertiary)]">
              {group.label}
            </p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {group.items.map((jurisdiction) => {
                const checked = config.searchJurisdictions.includes(
                  jurisdiction.code,
                );
                const disableRemoval =
                  checked && config.searchJurisdictions.length === 1;

                return (
                  <label
                    key={jurisdiction.code}
                    className={cn(
                      "flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border p-2.5 transition-colors focus-within:ring-2 focus-within:ring-brand-primary/60 focus-within:ring-offset-2 focus-within:ring-offset-[var(--bg-base)]",
                      checked
                        ? "border-brand-primary/50 bg-brand-primary/5"
                        : "border-[var(--border-default)] bg-[var(--surface-muted)] hover:border-[var(--border-emphasis)]",
                      disableRemoval && "cursor-not-allowed opacity-80",
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={disableRemoval}
                      onChange={(e) => {
                        const next = e.target.checked
                          ? [...config.searchJurisdictions, jurisdiction.code]
                          : config.searchJurisdictions.filter(
                              (code) => code !== jurisdiction.code,
                            );
                        if (next.length > 0) {
                          config.setConfig({ searchJurisdictions: next });
                        }
                      }}
                      className="h-4 w-4 shrink-0 accent-brand-primary focus-visible:outline-none disabled:cursor-not-allowed"
                      aria-label={`Select ${jurisdiction.label} (${jurisdiction.code})`}
                    />
                    <div>
                      <span className="type-label-sm text-[var(--text-primary)]">
                        {jurisdiction.code}
                      </span>
                      <p className="type-label-sm text-[var(--text-tertiary)]">
                        {jurisdiction.label}
                      </p>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      <div>
        <label className="mb-3 flex items-center gap-2 type-body-md font-medium text-[var(--text-primary)]">
          <Brain className="h-3.5 w-3.5 text-brand-primary" />
          Execution Rigor by Stage
        </label>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {effortControls.map((effort) => (
            <div key={effort.key}>
              <label
                htmlFor={effort.id}
                className="mb-1 block type-label-sm text-[var(--text-secondary)]"
              >
                {effort.label}
              </label>
              <select
                id={effort.id}
                value={config[effort.key]}
                onChange={(e) =>
                  config.setConfig({
                    [effort.key]: e.target
                      .value as ConfigStore[typeof effort.key],
                  })
                }
                className={`${CONFIG_FIELD_CLASS} w-full text-left`}
              >
                {EFFORT_LEVELS.map((level) => (
                  <option key={level} value={level}>
                    {level.charAt(0).toUpperCase() + level.slice(1)}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      </div>
    </CollapsibleCard>
  );
}
