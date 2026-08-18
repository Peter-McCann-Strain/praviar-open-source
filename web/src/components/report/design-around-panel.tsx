"use client";

import { useState } from "react";
import { Lightbulb, ChevronDown, ChevronRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { RiskBadge } from "@/components/shared/risk-badge";
import type {
  FTOReport,
  DesignAroundSuggestion,
  RiskLevel,
} from "@praviar/shared-types";

interface DesignAroundPanelProps {
  report: FTOReport;
}

interface PatentGroup {
  patent_id: string;
  risk_level: RiskLevel;
  title: string;
  suggestions: DesignAroundSuggestion[];
}

function feasibilityBorderColor(feasibility: string): string {
  const lower = feasibility.toLowerCase();
  if (lower.startsWith("high")) return "border-l-success";
  if (lower.startsWith("moderate")) return "border-l-warning";
  if (lower.startsWith("low")) return "border-l-error";
  return "border-l-[var(--border-default)]";
}

function feasibilityBadgeVariant(feasibility: string) {
  const lower = feasibility.toLowerCase();
  if (lower.startsWith("high")) return "success" as const;
  if (lower.startsWith("moderate")) return "warning" as const;
  if (lower.startsWith("low")) return "destructive" as const;
  return "secondary" as const;
}

function feasibilityLabel(feasibility: string): string {
  const lower = feasibility.toLowerCase();
  if (lower.startsWith("high")) return "High Feasibility";
  if (lower.startsWith("moderate")) return "Moderate Feasibility";
  if (lower.startsWith("low")) return "Low Feasibility";
  return feasibility;
}

export function DesignAroundPanel({ report }: DesignAroundPanelProps) {
  const groups: PatentGroup[] = report.patent_analyses
    .filter(
      (pa) =>
        (pa.risk_level === "high" || pa.risk_level === "medium") &&
        (pa.design_around_suggestions?.length ?? 0) > 0,
    )
    .map((pa) => ({
      patent_id: pa.patent_id,
      risk_level: pa.risk_level,
      title: pa.title,
      suggestions: pa.design_around_suggestions,
    }));

  if (groups.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Lightbulb className="h-5 w-5 text-[var(--brand-primary)]" />
          <CardTitle className="text-sm">Design-Around Strategies</CardTitle>
          <Badge variant="default" className="ml-auto">
            {groups.reduce((sum, g) => sum + g.suggestions.length, 0)}{" "}
            suggestions
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {groups.map((group) => (
          <PatentGroupSection key={group.patent_id} group={group} />
        ))}
      </CardContent>
    </Card>
  );
}

function PatentGroupSection({ group }: { group: PatentGroup }) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="rounded-lg border border-[var(--border-default)] overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        className="flex items-center gap-3 w-full px-4 py-3 text-left hover:bg-[var(--surface-hover)] transition-colors"
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4 text-[var(--text-tertiary)] flex-shrink-0" />
        ) : (
          <ChevronRight className="h-4 w-4 text-[var(--text-tertiary)] flex-shrink-0" />
        )}
        <span className="text-sm font-mono text-[var(--text-primary)]">
          {group.patent_id}
        </span>
        <RiskBadge risk={group.risk_level} size="sm" />
        <span className="text-xs text-[var(--text-secondary)] truncate">
          {group.title}
        </span>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3">
          {group.suggestions.map((suggestion, idx) => (
            <div
              key={idx}
              className={`praviar-glass-chip border-l-4 ${feasibilityBorderColor(suggestion.feasibility)} rounded-r-lg p-4 space-y-2`}
            >
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant="secondary" className="text-xs">
                  Avoids Element {suggestion.element_avoided}
                </Badge>
                <Badge
                  variant={feasibilityBadgeVariant(suggestion.feasibility)}
                  className="text-xs"
                >
                  {feasibilityLabel(suggestion.feasibility)}
                </Badge>
              </div>
              <p className="text-sm text-[var(--text-primary)] leading-relaxed">
                {suggestion.suggestion}
              </p>
              <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                {suggestion.feasibility}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
