"use client";

import { useId } from "react";
import type { ConfigState } from "@/stores/config-store";

interface ConfigurationSearchParametersCitationProps {
  config: ConfigState;
}

export function ConfigurationSearchParametersCitation({
  config,
}: ConfigurationSearchParametersCitationProps) {
  const citationTraversalId = useId();
  const citationMaxDepthId = useId();

  return (
    <div className="flex items-center gap-4">
      <label
        htmlFor={citationTraversalId}
        className="flex cursor-pointer items-center gap-2"
      >
        <input
          id={citationTraversalId}
          type="checkbox"
          checked={config.citationTraversalEnabled}
          onChange={(event) =>
            config.setConfig({
              citationTraversalEnabled: event.target.checked,
            })
          }
          className="h-4 w-4 accent-brand-primary"
        />
        <span className="text-xs font-medium text-[var(--text-secondary)]">
          Citation Expansion
        </span>
      </label>
      {config.citationTraversalEnabled ? (
        <div className="flex items-center gap-2">
          <label
            htmlFor={citationMaxDepthId}
            className="text-xs text-[var(--text-tertiary)]"
          >
            Expansion hops:
          </label>
          <select
            id={citationMaxDepthId}
            value={config.citationMaxDepth}
            onChange={(event) =>
              config.setConfig({
                citationMaxDepth: Number.parseInt(event.target.value, 10),
              })
            }
            className="h-8 rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-muted)] px-2 text-xs text-[var(--text-secondary)]"
          >
            <option value={1}>1</option>
            <option value={2}>2</option>
            <option value={3}>3</option>
          </select>
        </div>
      ) : null}
    </div>
  );
}
