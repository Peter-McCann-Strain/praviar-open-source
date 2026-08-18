"use client";

import { useId } from "react";
import { JURISDICTION_GROUPS, type ConfigState } from "@/stores/config-store";
import { cn } from "@/lib/utils";
import {
  formatSelectedJurisdictionCount,
  nextSearchJurisdictions,
} from "@/components/analysis-wizard/configuration-search-parameters-helpers";

interface ConfigurationSearchParametersJurisdictionsProps {
  config: ConfigState;
}

export function ConfigurationSearchParametersJurisdictions({
  config,
}: ConfigurationSearchParametersJurisdictionsProps) {
  const requiredNoteId = useId();

  return (
    <div>
      <label className="mb-1.5 block text-xs font-medium text-[var(--text-secondary)]">
        Search Jurisdictions
      </label>
      <p className="mb-2 text-xs text-[var(--text-tertiary)]">
        {formatSelectedJurisdictionCount(config.searchJurisdictions.length)}
      </p>
      <p
        id={requiredNoteId}
        className="mb-3 text-xs text-[var(--text-tertiary)]"
      >
        At least one jurisdiction is required for launch.
      </p>
      {JURISDICTION_GROUPS.map((group) => (
        <div key={group.label} className="mb-3">
          <p className="mb-1.5 text-xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]">
            {group.label}
          </p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {group.items.map((jurisdiction) => {
              const isSelected = config.searchJurisdictions.includes(
                jurisdiction.code,
              );
              const isRequiredSelection =
                isSelected && config.searchJurisdictions.length === 1;

              return (
                <label
                  key={jurisdiction.code}
                  className={cn(
                    "flex cursor-pointer items-center gap-2 rounded-lg border p-2.5 transition-colors",
                    isSelected
                      ? "border-brand-primary/50 bg-brand-primary/5"
                      : "border-[var(--border-default)] bg-[var(--surface-muted)] hover:border-[var(--border-emphasis)]",
                    isRequiredSelection && "cursor-not-allowed opacity-80",
                  )}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    disabled={isRequiredSelection}
                    aria-describedby={
                      isRequiredSelection ? requiredNoteId : undefined
                    }
                    onChange={(event) => {
                      const next = nextSearchJurisdictions(
                        config.searchJurisdictions,
                        jurisdiction.code,
                        event.target.checked,
                      );
                      if (next) {
                        config.setConfig({ searchJurisdictions: next });
                      }
                    }}
                    className="h-3.5 w-3.5 accent-brand-primary disabled:cursor-not-allowed"
                    aria-label={`Select ${jurisdiction.label} (${jurisdiction.code})`}
                  />
                  <div>
                    <span className="text-xs font-medium text-[var(--text-primary)]">
                      {jurisdiction.code}
                    </span>
                    <p className="text-xs text-[var(--text-tertiary)]">
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
  );
}
