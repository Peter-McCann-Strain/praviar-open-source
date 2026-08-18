"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import { CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { RiskBadge } from "@/components/shared/risk-badge";
import { getPatentJurisdictionCode } from "@/components/patent/patent-risk-card-helpers";
import type { PatentAnalysis } from "@praviar/shared-types";

interface PatentRiskCardSummaryProps {
  analysis: PatentAnalysis;
  expanded: boolean;
  onToggle: () => void;
}

export function PatentRiskCardSummary({
  analysis,
  expanded,
  onToggle,
}: PatentRiskCardSummaryProps) {
  const jurisdictionCode = getPatentJurisdictionCode(analysis.patent_id);

  return (
    <CardHeader
      className="cursor-pointer p-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/50 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)] sm:p-6"
      role="button"
      tabIndex={0}
      aria-expanded={expanded}
      onClick={onToggle}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onToggle();
        }
      }}
    >
      <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          {expanded ? (
            <ChevronDown className="h-4 w-4 flex-shrink-0 text-[var(--text-tertiary)]" />
          ) : (
            <ChevronRight className="h-4 w-4 flex-shrink-0 text-[var(--text-tertiary)]" />
          )}
          <RiskBadge
            risk={analysis.risk_level}
            size="sm"
            className="shrink-0"
          />
          <div className="min-w-0">
            <p className="break-all font-mono text-sm text-[var(--text-primary)] [overflow-wrap:anywhere]">
              {jurisdictionCode ? (
                <span
                  aria-label={`Jurisdiction ${jurisdictionCode}`}
                  className="mr-2 inline-flex rounded border border-[var(--border-default)] bg-[var(--surface-hover)] px-1.5 py-0.5 font-sans text-xs font-semibold leading-none text-[var(--text-secondary)]"
                >
                  {jurisdictionCode}
                </span>
              ) : null}
              {analysis.patent_id}
            </p>
            <p className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
              {analysis.title} — {analysis.assignee}
            </p>
          </div>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2 sm:justify-end">
          {analysis.expiry_date && (
            <Badge variant="secondary">Exp: {analysis.expiry_date}</Badge>
          )}
          <Badge variant="secondary">
            {(analysis.claims_analyzed ?? []).length}{" "}
            {(analysis.claims_analyzed ?? []).length === 1 ? "claim" : "claims"}
          </Badge>
        </div>
      </div>
    </CardHeader>
  );
}
