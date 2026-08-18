"use client";

import { useId } from "react";
import { Brain } from "lucide-react";
import { CollapsibleSection } from "@/components/analysis-wizard/collapsible-section";
import { RangeSlider } from "@/components/analysis-wizard/range-slider";
import {
  THINKING_EFFORT_OPTIONS,
  updateThinkingEffort,
} from "@/components/analysis-wizard/configuration-advanced-settings-helpers";
import type { ConfigState } from "@/stores/config-store";

interface ConfigurationAnalysisParametersProps {
  config: ConfigState;
}

export function ConfigurationAnalysisParameters({
  config,
}: ConfigurationAnalysisParametersProps) {
  const thinkingEffortId = useId();
  const thinkingEfforts = THINKING_EFFORT_OPTIONS.map((option) => ({
    ...option,
    value: config[option.key],
    id: `${thinkingEffortId}-${option.key}`,
  }));

  return (
    <CollapsibleSection title="Analysis Parameters" icon={Brain}>
      <div className="space-y-5 pt-3">
        <RangeSlider
          label="Patent Review Limit"
          value={config.maxAnalysisPatents}
          onChange={(value) => config.setConfig({ maxAnalysisPatents: value })}
          min={5}
          max={30}
          step={5}
        />

        <RangeSlider
          label="DoE Candidate Limit"
          value={config.maxDoeCandidates}
          onChange={(value) => config.setConfig({ maxDoeCandidates: value })}
          min={5}
          max={20}
          step={5}
        />

        <RangeSlider
          label="Triage Batch Size"
          value={config.triageBatchSize}
          onChange={(value) => config.setConfig({ triageBatchSize: value })}
          min={5}
          max={15}
          step={5}
        />

        <RangeSlider
          label="Internal Reasoning Budget"
          value={config.analysisThinkingBudget}
          onChange={(value) =>
            config.setConfig({ analysisThinkingBudget: value })
          }
          min={4000}
          max={32000}
          step={2000}
          suffix="tokens"
          formatValue={(value) => value.toLocaleString()}
        />

        <div>
          <label className="mb-2 block text-xs font-medium text-[var(--text-secondary)]">
            Internal Reasoning by Stage
          </label>
          <div className="grid gap-3 sm:grid-cols-3">
            {thinkingEfforts.map((effort) => (
              <div key={effort.key}>
                <label
                  htmlFor={effort.id}
                  className="mb-1 block text-xs text-[var(--text-tertiary)]"
                >
                  {effort.label}
                </label>
                <select
                  id={effort.id}
                  value={effort.value}
                  onChange={(event) =>
                    updateThinkingEffort(
                      config,
                      effort.key,
                      event.target.value as "high" | "medium" | "low",
                    )
                  }
                  className="h-8 w-full rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-muted)] px-2 text-xs text-[var(--text-secondary)]"
                >
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </select>
              </div>
            ))}
          </div>
        </div>
      </div>
    </CollapsibleSection>
  );
}
