"use client";

import { useId } from "react";
import { Search } from "lucide-react";
import { CollapsibleCard } from "@/components/config/collapsible-card";
import {
  CONFIG_COMPACT_SELECT_CLASS,
  CONFIG_FORM_ROW_CLASS,
  CONFIG_SWITCH_LABEL_CLASS,
  type ConfigStore,
} from "@/components/config/helpers";

interface SearchDepthSectionProps {
  config: ConfigStore;
}

export function SearchDepthSection({ config }: SearchDepthSectionProps) {
  const maxRankedResultsId = useId();
  const tanimotoThresholdId = useId();
  const includeExpiredId = useId();

  return (
    <CollapsibleCard title="Search Coverage" icon={Search} defaultOpen={true}>
      <div className={CONFIG_FORM_ROW_CLASS}>
        <div className="min-w-0">
          <label
            htmlFor={maxRankedResultsId}
            className="type-body-md font-medium text-[var(--text-primary)]"
          >
            Ranked Result Budget
          </label>
          <p className="type-label-sm text-[var(--text-tertiary)]">
            Upper bound for patents passed through scoring
          </p>
        </div>
        <select
          id={maxRankedResultsId}
          value={config.searchMaxRankedResults}
          onChange={(e) =>
            config.setConfig({
              searchMaxRankedResults: Number.parseInt(e.target.value, 10),
            })
          }
          className={CONFIG_COMPACT_SELECT_CLASS}
        >
          <option value="50">50</option>
          <option value="100">100</option>
          <option value="200">200</option>
          <option value="500">500</option>
        </select>
      </div>
      <div className={CONFIG_FORM_ROW_CLASS}>
        <div className="min-w-0">
          <label
            htmlFor={tanimotoThresholdId}
            className="type-body-md font-medium text-[var(--text-primary)]"
          >
            Tanimoto Threshold
          </label>
          <p className="type-label-sm text-[var(--text-tertiary)]">
            Structural similarity cutoff (lower = broader)
          </p>
        </div>
        <select
          id={tanimotoThresholdId}
          value={config.searchTanimotoThreshold}
          onChange={(e) =>
            config.setConfig({
              searchTanimotoThreshold: Number.parseFloat(e.target.value),
            })
          }
          className={CONFIG_COMPACT_SELECT_CLASS}
        >
          <option value="0.40">0.40 (Broad)</option>
          <option value="0.55">0.55 (Default)</option>
          <option value="0.70">0.70 (Narrow)</option>
          <option value="0.85">0.85 (Exact)</option>
        </select>
      </div>
      <div className={CONFIG_FORM_ROW_CLASS}>
        <div className="min-w-0">
          <label
            htmlFor={includeExpiredId}
            className="type-body-md font-medium text-[var(--text-primary)]"
          >
            Include Expired Patents
          </label>
          <p className="type-label-sm text-[var(--text-tertiary)]">
            Analyze patents past their expiry date
          </p>
        </div>
        <label className={CONFIG_SWITCH_LABEL_CLASS}>
          <input
            id={includeExpiredId}
            type="checkbox"
            checked={config.includeExpired}
            onChange={(e) =>
              config.setConfig({ includeExpired: e.target.checked })
            }
            className="peer sr-only"
          />
          <div className="h-6 w-11 rounded-full bg-[var(--border-default)] after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:bg-[var(--text-secondary)] after:transition-all peer-focus-visible:outline-none peer-focus-visible:ring-2 peer-focus-visible:ring-brand-primary/70 peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-[var(--bg-base)] peer-checked:bg-brand-primary-dim peer-checked:after:translate-x-full peer-checked:after:bg-[var(--brand-paper)]" />
        </label>
      </div>
    </CollapsibleCard>
  );
}
