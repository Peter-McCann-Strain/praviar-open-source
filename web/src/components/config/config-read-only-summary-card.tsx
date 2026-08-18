"use client";

import type { ComponentType, ReactNode } from "react";
import {
  Brain,
  Database,
  Globe2,
  Pencil,
  Scale,
  ShieldCheck,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CONFIG_MANAGER_ROLE_SENTENCE } from "@/components/config/config-authority-copy";
import {
  getCoverageBudgetDetail,
  getCoverageBudgetImpact,
  getCoverageBudgetLabel,
  HITL_CHECKPOINTS,
  PATENT_SOURCES,
  type ConfigStore,
} from "@/components/config/helpers";

interface ConfigReadOnlySummaryCardProps {
  config: ConfigStore;
  enabledSources: string[];
  onEdit?: () => void;
}

interface SummaryBlockProps {
  title: string;
  value: string;
  detail: string;
  icon: ComponentType<{ className?: string }>;
  children?: ReactNode;
}

function SummaryBlock({
  title,
  value,
  detail,
  icon: Icon,
  children,
}: SummaryBlockProps) {
  return (
    <section className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/70 p-4">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
          <Icon className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
            {title}
          </p>
          <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
            {value}
          </p>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            {detail}
          </p>
        </div>
      </div>
      {children ? <div className="mt-3">{children}</div> : null}
    </section>
  );
}

function ChipList({
  values,
  fallback,
}: {
  values: string[];
  fallback: string;
}) {
  if (values.length === 0) {
    return <Badge variant="destructive">{fallback}</Badge>;
  }

  return (
    <div className="flex flex-wrap gap-2">
      {values.map((value) => (
        <Badge key={value} variant="secondary">
          {value}
        </Badge>
      ))}
    </div>
  );
}

function formatEffort(value: ConfigStore["thinkingEffortAnalysis"]): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function ConfigReadOnlySummaryCard({
  config,
  enabledSources,
  onEdit,
}: ConfigReadOnlySummaryCardProps) {
  const checkpointLabels = HITL_CHECKPOINTS.filter((checkpoint) =>
    config.hitlCheckpoints.includes(checkpoint.id),
  ).map((checkpoint) => checkpoint.label);
  const sourceCount = enabledSources.length;
  const jurisdictionCount = config.searchJurisdictions.length;

  return (
    <Card className="overflow-hidden">
      <CardHeader className="praviar-glass-strip border-b border-[var(--border-default)]">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle className="text-base">
              Current Organization Defaults
            </CardTitle>
            <p className="mt-1 text-sm leading-5 text-[var(--text-secondary)]">
              {onEdit
                ? "Saved defaults shape new analyses, evidence collection, and legal review posture."
                : `You can inspect the active policy. ${CONFIG_MANAGER_ROLE_SENTENCE}`}
            </p>
          </div>
          {onEdit ? (
            <Button
              variant="outline"
              size="sm"
              className="min-h-11 w-full gap-1.5 sm:w-auto"
              onClick={onEdit}
            >
              <Pencil className="h-3.5 w-3.5" />
              Edit defaults
            </Button>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 pt-6 lg:grid-cols-2">
        <SummaryBlock
          title="Coverage"
          value={getCoverageBudgetLabel(config.searchMaxRankedResults)}
          detail={getCoverageBudgetDetail(config.searchMaxRankedResults)}
          icon={Scale}
        >
          <p className="text-xs leading-5 text-[var(--text-tertiary)]">
            {getCoverageBudgetImpact(config.searchMaxRankedResults)}
          </p>
        </SummaryBlock>

        <SummaryBlock
          title="Patent Sources"
          value={
            sourceCount > 0
              ? `${sourceCount} of ${PATENT_SOURCES.length} enabled`
              : "No patent sources enabled"
          }
          detail={
            sourceCount > 0
              ? "Source breadth is ready for default evidence collection."
              : "Enable at least one source before saving defaults."
          }
          icon={Database}
        >
          <ChipList values={enabledSources} fallback="No sources enabled" />
        </SummaryBlock>

        <SummaryBlock
          title="Jurisdictions"
          value={
            jurisdictionCount > 0
              ? `${jurisdictionCount} selected`
              : "No jurisdictions selected"
          }
          detail={
            jurisdictionCount > 0
              ? "Jurisdiction matrix feeds the saved search payload."
              : "Select at least one jurisdiction before saving defaults."
          }
          icon={Globe2}
        >
          <ChipList
            values={config.searchJurisdictions}
            fallback="No jurisdictions selected"
          />
        </SummaryBlock>

        <SummaryBlock
          title="Legal Review"
          value={config.hitlEnabled ? "HITL enabled" : "HITL off"}
          detail={
            config.hitlEnabled
              ? `${checkpointLabels.length} checkpoint${checkpointLabels.length === 1 ? "" : "s"} before auto-skip at ${config.hitlAutoSkipMinutes} minutes.`
              : "Adaptive execution continues without review pauses."
          }
          icon={ShieldCheck}
        >
          <ChipList
            values={config.hitlEnabled ? checkpointLabels : []}
            fallback="No review pauses"
          />
        </SummaryBlock>

        <SummaryBlock
          title="Execution Rigor"
          value="Adaptive evidence gates"
          detail={`Analysis ${formatEffort(config.thinkingEffortAnalysis)} / Triage ${formatEffort(config.thinkingEffortTriage)} / Report ${formatEffort(config.thinkingEffortReport)}`}
          icon={Brain}
        />
      </CardContent>
    </Card>
  );
}
