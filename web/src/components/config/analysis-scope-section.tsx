"use client";

import { useId } from "react";
import { ListChecks } from "lucide-react";
import { CollapsibleCard } from "@/components/config/collapsible-card";
import {
  CONFIG_COMPACT_SELECT_CLASS,
  CONFIG_FORM_ROW_CLASS,
  type ConfigStore,
} from "@/components/config/helpers";

interface AnalysisScopeSectionProps {
  config: ConfigStore;
}

export function AnalysisScopeSection({ config }: AnalysisScopeSectionProps) {
  const maxPatentsId = useId();
  const maxDoeCandidatesId = useId();
  const triageBatchSizeId = useId();

  return (
    <CollapsibleCard title="Evidence Review Limits" icon={ListChecks}>
      <div className={CONFIG_FORM_ROW_CLASS}>
        <div className="min-w-0">
          <label
            htmlFor={maxPatentsId}
            className="type-body-md font-medium text-[var(--text-primary)]"
          >
            Patent Review Limit
          </label>
          <p className="type-label-sm text-[var(--text-tertiary)]">
            Upper bound for claim-level review after adaptive triage
          </p>
        </div>
        <select
          id={maxPatentsId}
          value={config.maxAnalysisPatents}
          onChange={(e) =>
            config.setConfig({
              maxAnalysisPatents: Number.parseInt(e.target.value, 10),
            })
          }
          className={CONFIG_COMPACT_SELECT_CLASS}
        >
          <option value="5">5</option>
          <option value="10">10</option>
          <option value="20">20</option>
          <option value="30">30</option>
        </select>
      </div>
      <div className={CONFIG_FORM_ROW_CLASS}>
        <div className="min-w-0">
          <label
            htmlFor={maxDoeCandidatesId}
            className="type-body-md font-medium text-[var(--text-primary)]"
          >
            DoE Candidate Limit
          </label>
          <p className="type-label-sm text-[var(--text-tertiary)]">
            Upper bound for Doctrine of Equivalents review
          </p>
        </div>
        <select
          id={maxDoeCandidatesId}
          value={config.maxDoeCandidates}
          onChange={(e) =>
            config.setConfig({
              maxDoeCandidates: Number.parseInt(e.target.value, 10),
            })
          }
          className={CONFIG_COMPACT_SELECT_CLASS}
        >
          <option value="5">5</option>
          <option value="10">10</option>
          <option value="15">15</option>
          <option value="20">20</option>
        </select>
      </div>
      <div className={CONFIG_FORM_ROW_CLASS}>
        <div className="min-w-0">
          <label
            htmlFor={triageBatchSizeId}
            className="type-body-md font-medium text-[var(--text-primary)]"
          >
            Triage Batch Size
          </label>
          <p className="type-label-sm text-[var(--text-tertiary)]">
            Patents grouped per internal triage pass
          </p>
        </div>
        <select
          id={triageBatchSizeId}
          value={config.triageBatchSize}
          onChange={(e) =>
            config.setConfig({
              triageBatchSize: Number.parseInt(e.target.value, 10),
            })
          }
          className={CONFIG_COMPACT_SELECT_CLASS}
        >
          <option value="5">5</option>
          <option value="10">10</option>
          <option value="15">15</option>
        </select>
      </div>
    </CollapsibleCard>
  );
}
