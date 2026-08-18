"use client";

import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import { RiskBadge } from "@/components/shared/risk-badge";
import type { AnalysisListItem } from "@/types/api";
import type { RiskLevel } from "@praviar/shared-types";

interface AnalysisHeaderProps {
  analysis: AnalysisListItem;
  overallRisk: RiskLevel | null;
}

export function AnalysisHeader({ analysis, overallRisk }: AnalysisHeaderProps) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex min-w-0 items-start gap-4">
        <PraviarMarkFrame />
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
            Praviar FTO analysis
          </p>
          <div className="mt-1 flex min-w-0 items-start justify-between gap-3">
            <h1 className="min-w-0 type-heading-xl text-[var(--text-primary)] [overflow-wrap:anywhere]">
              {analysis.compound_name}
            </h1>
            {overallRisk ? (
              <span className="shrink-0 sm:hidden">
                <RiskBadge risk={overallRisk} size="md" />
              </span>
            ) : null}
          </div>
          <p className="mt-1 break-all font-mono text-sm text-[var(--text-secondary)]">
            {analysis.compound_smiles}
          </p>
          <p className="mt-1 text-xs text-[var(--text-tertiary)]">
            ID: {analysis.id}
          </p>
        </div>
      </div>
      <div className="hidden items-center gap-3 sm:flex">
        {overallRisk ? <RiskBadge risk={overallRisk} size="md" /> : null}
      </div>
    </div>
  );
}
