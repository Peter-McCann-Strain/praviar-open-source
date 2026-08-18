"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Handshake,
  Route,
  OctagonX,
  Radar,
  Scale,
  ShieldX,
  Sparkles,
  Users,
  type LucideIcon,
} from "lucide-react";
import { AIRecoveryBrief } from "@/components/shared/ai-recovery-brief";
import { Badge, badgeVariants } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ActionItem, FTOReport } from "@praviar/shared-types";

const priorityStyles: Record<string, string> = {
  critical: "border-error/35 bg-error/12 text-[var(--text-primary)]",
  high: "border-warning/35 bg-warning/12 text-[var(--text-primary)]",
  medium: "border-info/25 bg-info/10 text-info-emphasis",
  low: "border-success/25 bg-success/10 text-success",
};

const actionTypeConfig: Record<
  string,
  {
    icon: LucideIcon;
    label: string;
    shortLabel: string;
    prompt: string;
  }
> = {
  license: {
    icon: Handshake,
    label: "License",
    shortLabel: "License",
    prompt: "Explore licensing or cross-license options.",
  },
  design_around: {
    icon: Route,
    label: "Design around",
    shortLabel: "Design",
    prompt: "Evaluate feasible design alternatives.",
  },
  challenge_ipr: {
    icon: ShieldX,
    label: "Challenge (IPR)",
    shortLabel: "Challenge",
    prompt: "Assess invalidity or post-grant challenge path.",
  },
  monitor: {
    icon: Radar,
    label: "Monitor",
    shortLabel: "Monitor",
    prompt: "Track external activity and related filings.",
  },
  accept_risk: {
    icon: CheckCircle2,
    label: "Accept risk",
    shortLabel: "Accept",
    prompt: "Document residual risk tolerance.",
  },
  halt: {
    icon: OctagonX,
    label: "Halt",
    shortLabel: "Halt",
    prompt: "Pause commercial path pending review.",
  },
};

interface ActionItemsPanelSummary {
  actionCount: number;
  affectedPatentCount: number;
  criticalCount: number;
  evidenceRequiredCount: number;
  primaryActionLabel: string;
  triageItems: string[];
}

function ActionCard({ item, index }: { item: ActionItem; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const router = useRouter();
  const patentIds = item.patent_ids ?? [];
  const firstPatent = patentIds[0];
  const config = actionTypeConfig[item.action_type] ?? {
    icon: Clock,
    label: humanizeActionType(item.action_type),
    shortLabel: humanizeActionType(item.action_type),
    prompt: "Review this next step with counsel.",
  };
  const Icon = config.icon;
  const priorityClass = priorityStyles[item.priority] ?? priorityStyles.medium;
  const priorityLabel = humanizeActionType(item.priority);
  const hasReasoning = Boolean(item.reasoning?.trim());

  const openPatent = (patentId: string) => {
    router.replace(`?tab=patents&patent=${patentId}`);
  };

  return (
    <li className="grid min-w-0 gap-0 overflow-hidden rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)]/82 shadow-[var(--shadow-xs)] 2xl:grid-cols-[minmax(13rem,0.72fr)_minmax(8rem,0.38fr)_minmax(10rem,0.62fr)_minmax(0,1fr)_minmax(10rem,0.52fr)]">
      <div className="flex min-w-0 gap-3 border-b border-[var(--border-subtle)] p-4 2xl:border-b-0 2xl:border-r">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-brand-primary/15 bg-brand-primary/8 text-brand-primary">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
            Next action {index + 1}
          </p>
          <h3 className="mt-1 text-lg font-semibold leading-7 text-[var(--text-primary)] [overflow-wrap:anywhere]">
            {config.label}
          </h3>
          <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
            {config.prompt}
          </p>
        </div>
      </div>

      <div className="border-b border-[var(--border-subtle)] p-4 2xl:border-b-0 2xl:border-r">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
          Priority
        </p>
        <Badge className={cn("mt-2 capitalize", priorityClass)}>
          {priorityLabel}
        </Badge>
        <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
          Impact: {priorityLabel}
        </p>
      </div>

      <div className="border-b border-[var(--border-subtle)] p-4 2xl:border-b-0 2xl:border-r">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
          Affected patents
        </p>
        {patentIds.length > 0 ? (
          <div className="mt-2 flex min-w-0 flex-wrap gap-1.5">
            {patentIds.map((id) => (
              <button
                key={id}
                type="button"
                className={cn(
                  badgeVariants({ variant: "outline" }),
                  "min-h-11 max-w-full cursor-pointer px-3 py-1.5 font-mono text-xs hover:bg-[var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 [overflow-wrap:anywhere]",
                )}
                onClick={() => openPatent(id)}
                aria-label={`Open patent ${id} in the patents tab`}
              >
                {id}
              </button>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            Portfolio-level action
          </p>
        )}
        {patentIds.length > 1 ? (
          <p className="mt-2 text-xs text-[var(--text-tertiary)]">
            {patentIds.length} records require aligned review.
          </p>
        ) : null}
      </div>

      <div className="min-w-0 border-b border-[var(--border-subtle)] p-4 2xl:border-b-0 2xl:border-r">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
          Counsel context
        </p>
        <p className="mt-2 text-sm leading-6 text-[var(--text-primary)] [overflow-wrap:anywhere]">
          {item.description}
        </p>
        {hasReasoning ? (
          <div>
            <button
              type="button"
              onClick={() => setExpanded((value) => !value)}
              className="-ml-2 mt-2 flex min-h-11 items-center gap-1.5 rounded-md px-2 text-xs font-semibold text-[var(--brand-primary)] transition-colors hover:bg-[var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
              aria-expanded={expanded}
            >
              {expanded ? (
                <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
              )}
              Reasoning
            </button>
            {expanded ? (
              <p className="praviar-code-surface mt-2 rounded-md p-3 text-xs leading-relaxed text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
                {item.reasoning}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="flex min-w-0 flex-col justify-between gap-4 p-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
            Status
          </p>
          <Badge
            variant={hasReasoning ? "warning" : "secondary"}
            className="mt-2"
          >
            {hasReasoning ? "Evidence required" : "Counsel review"}
          </Badge>
          <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
            {item.estimated_timeline?.trim()
              ? item.estimated_timeline
              : "Timeline pending"}
          </p>
        </div>
        <Button
          type="button"
          variant={firstPatent ? "default" : "outline"}
          size="sm"
          className="min-h-11 w-full min-w-0 justify-between gap-2 whitespace-normal text-left leading-5"
          onClick={() => {
            if (firstPatent) {
              openPatent(firstPatent);
            }
          }}
          disabled={!firstPatent}
          aria-label={
            firstPatent
              ? `Open ${config.shortLabel} brief for ${firstPatent}`
              : `${config.shortLabel} brief unavailable until a patent is selected`
          }
        >
          <span className="min-w-0 [overflow-wrap:anywhere]">
            {firstPatent
              ? `Open ${config.shortLabel} brief`
              : "Brief unavailable"}
          </span>
          <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
        </Button>
      </div>
    </li>
  );
}

export function ActionItemsPanel({ report }: { report: FTOReport }) {
  const items = useMemo(() => report.action_items ?? [], [report.action_items]);
  const summary = useMemo(() => getActionItemsSummary(items), [items]);

  if (items.length === 0) return null;

  return (
    <section
      aria-labelledby="counsel-next-actions-title"
      className="overflow-hidden rounded-lg border border-[var(--border-default)] bg-[color-mix(in_srgb,var(--bg-elevated)_92%,transparent)] shadow-[var(--shadow-sm)]"
      data-testid="counsel-next-actions"
    >
      <div className="border-b border-[var(--border-default)] p-4 sm:p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex min-w-0 gap-3">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border border-brand-primary/15 bg-brand-primary/10 text-brand-primary">
              <Sparkles className="h-5 w-5" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <h2
                id="counsel-next-actions-title"
                className="text-xl font-semibold text-[var(--text-primary)]"
              >
                Counsel next actions
              </h2>
              <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                AI-assisted triage converts report findings into counsel-review
                work without changing the legal conclusion.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="secondary" className="gap-1.5">
              <Users className="h-3.5 w-3.5" aria-hidden="true" />
              Counsel review
            </Badge>
            <Badge variant="warning" className="gap-1.5">
              <Scale className="h-3.5 w-3.5" aria-hidden="true" />
              Evidence required
            </Badge>
          </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2 2xl:grid-cols-[minmax(0,1.3fr)_repeat(3,minmax(9rem,0.42fr))]">
          <div className="rounded-lg border border-brand-primary/15 bg-brand-primary/5 p-3">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-primary">
              Triage summary
            </p>
            <p className="mt-2 text-sm leading-6 text-[var(--text-primary)]">
              {summary.primaryActionLabel} leads the work queue across{" "}
              {summary.affectedPatentCount} affected patent
              {summary.affectedPatentCount === 1 ? "" : "s"}.
            </p>
          </div>
          <ActionSummaryMetric
            label="Next actions"
            value={summary.actionCount}
            detail="Queued for review"
          />
          <ActionSummaryMetric
            label="Urgent"
            value={summary.criticalCount}
            detail="Critical or high"
            tone={summary.criticalCount > 0 ? "warning" : "default"}
          />
          <ActionSummaryMetric
            label="Evidence"
            value={summary.evidenceRequiredCount}
            detail="Reasoning attached"
            tone={summary.evidenceRequiredCount > 0 ? "warning" : "default"}
          />
        </div>

        <AIRecoveryBrief
          className="mt-4"
          title="AI-assisted triage"
          items={summary.triageItems}
          note="No legal conclusion changed; use these prompts to prepare reviewer work."
        />
      </div>

      <div className="hidden border-b border-[var(--border-default)] px-4 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)] 2xl:grid 2xl:grid-cols-[minmax(13rem,0.72fr)_minmax(8rem,0.38fr)_minmax(10rem,0.62fr)_minmax(0,1fr)_minmax(10rem,0.52fr)]">
        <span>Next action</span>
        <span>Priority</span>
        <span>Affected patents</span>
        <span>Counsel context</span>
        <span>Status</span>
      </div>

      <ul
        aria-label="Counsel next action queue"
        className="grid gap-3 p-4 sm:p-5"
      >
        {items.map((item, index) => (
          <ActionCard
            key={`${item.action_type}-${item.patent_ids?.[0] ?? index}`}
            item={item}
            index={index}
          />
        ))}
      </ul>
    </section>
  );
}

function ActionSummaryMetric({
  detail,
  label,
  tone = "default",
  value,
}: {
  detail: string;
  label: string;
  tone?: "default" | "warning";
  value: number;
}) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/78 p-3">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p
        className={cn(
          "mt-1 text-2xl font-semibold leading-none",
          tone === "warning" ? "text-warning" : "text-[var(--text-primary)]",
        )}
      >
        {value}
      </p>
      <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
        {detail}
      </p>
    </div>
  );
}

function getActionItemsSummary(items: ActionItem[]): ActionItemsPanelSummary {
  const affectedPatents = new Set<string>();
  let criticalCount = 0;
  let evidenceRequiredCount = 0;
  const typeCounts = new Map<string, number>();

  for (const item of items) {
    typeCounts.set(
      item.action_type,
      (typeCounts.get(item.action_type) ?? 0) + 1,
    );
    if (item.priority === "critical" || item.priority === "high") {
      criticalCount += 1;
    }
    if (item.reasoning?.trim()) {
      evidenceRequiredCount += 1;
    }
    for (const patentId of item.patent_ids ?? []) {
      affectedPatents.add(patentId);
    }
  }

  const primaryType =
    [...typeCounts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ??
    "counsel_review";
  const primaryActionLabel =
    actionTypeConfig[primaryType]?.label ?? humanizeActionType(primaryType);
  const triageItems = [
    `${criticalCount} urgent action${
      criticalCount === 1 ? "" : "s"
    } should stay attached to reviewer handoff.`,
    `${affectedPatents.size} affected patent${
      affectedPatents.size === 1 ? "" : "s"
    } need action context before downstream reliance.`,
    `${evidenceRequiredCount} action${
      evidenceRequiredCount === 1 ? "" : "s"
    } include reasoning that should be checked against claim evidence.`,
  ];

  return {
    actionCount: items.length,
    affectedPatentCount: affectedPatents.size,
    criticalCount,
    evidenceRequiredCount,
    primaryActionLabel,
    triageItems,
  };
}

function humanizeActionType(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
