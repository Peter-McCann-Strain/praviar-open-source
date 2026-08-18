"use client";

import Link from "next/link";
import {
  Activity,
  ArrowRight,
  Bot,
  ClipboardCheck,
  FileSearch,
  MessageSquareQuote,
  Scale,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { relativeTime } from "@/components/dashboard/helpers";
import { getReportAccessHref } from "@/lib/report-permissions";
import { cn } from "@/lib/utils";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useHydrationSafeRelativeTime } from "@/hooks/use-hydration-safe-relative-time";
import {
  canAccessWorkspaceHref,
  usePrincipalCapabilities,
} from "@/hooks/use-principal-capabilities";
import type { AnalysisListItem } from "@/types/api";

interface AiCommandPanelProps {
  analyses: AnalysisListItem[];
  sampleWindowSize?: number;
}

interface AiCommandAction {
  id: string;
  title: string;
  description: string;
  href: string;
  cta: string;
  icon: LucideIcon;
  tone: "critical" | "active" | "review" | "neutral";
  meta: string;
}

const ACTION_TONE_CLASSES: Record<AiCommandAction["tone"], string> = {
  critical: "border-l-error bg-error/5 hover:bg-error/10",
  active: "border-l-info bg-info/5 hover:bg-info/10",
  review: "border-l-warning bg-warning/10 hover:bg-warning/15",
  neutral:
    "border-l-brand-primary bg-brand-primary/5 hover:bg-brand-primary/10",
};

const ACTION_ICON_CLASSES: Record<AiCommandAction["tone"], string> = {
  critical: "bg-error/12 text-error",
  active: "bg-info/12 text-info",
  review: "bg-warning/14 text-[var(--text-primary)]",
  neutral: "bg-brand-primary/12 text-brand-primary",
};

const ACTION_META_CLASSES: Record<AiCommandAction["tone"], string> = {
  critical: "border-error/20 bg-error/10 text-error",
  active: "border-info/20 bg-info/10 text-info",
  review: "border-warning/25 bg-warning/12 text-[var(--text-primary)]",
  neutral:
    "border-brand-primary/20 bg-brand-primary/8 text-[var(--brand-primary-dim)]",
};

function sortByUpdatedAt(left: AnalysisListItem, right: AnalysisListItem) {
  return Date.parse(right.updated_at) - Date.parse(left.updated_at);
}

function reportHref(analysis: AnalysisListItem) {
  return getReportAccessHref(
    analysis.id,
    analysis.current_user_role,
    analysis.risk_ratings_restricted,
  );
}

function reportAiHref(
  analysis: AnalysisListItem,
  aiContext: "blocker_brief" | "external_readout" | "review_questions",
  tab: "overview" | "patents" | "comments" | "audit" | "evidence" = "overview",
) {
  const params = new URLSearchParams({
    ai_context: aiContext,
    tab,
  });
  return `${reportHref(analysis)}?${params.toString()}`;
}

function buildAiCommandActions(
  analyses: AnalysisListItem[],
): AiCommandAction[] {
  const completed = analyses
    .filter((analysis) => analysis.status === "completed")
    .sort(sortByUpdatedAt);
  const highRisk = [...completed]
    .filter(
      (analysis) =>
        !analysis.risk_ratings_restricted &&
        analysis.overall_risk === "high" &&
        (analysis.blocking_patents_count ?? 0) > 0,
    )
    .sort(
      (left, right) =>
        (right.blocking_patents_count ?? 0) -
          (left.blocking_patents_count ?? 0) || sortByUpdatedAt(left, right),
    )[0];
  const reviewTarget = completed.find(
    (analysis) =>
      analysis.flagged_for_review ||
      analysis.review_status?.status === "changes_requested" ||
      analysis.review_status?.status === "under_review",
  );
  const running = analyses
    .filter((analysis) => analysis.status === "running")
    .sort(sortByUpdatedAt)[0];
  const shared = completed.find((analysis) => analysis.share_active);
  const actions: AiCommandAction[] = [];

  if (highRisk) {
    actions.push({
      id: `blocker-${highRisk.id}`,
      title: "Draft blocking-patent brief",
      description: `${highRisk.compound_name}: cite claim elements, legal status, expiry, and design-around assumptions before counsel review.`,
      href: reportAiHref(highRisk, "blocker_brief", "patents"),
      cta: "Open report brief",
      icon: Scale,
      tone: "critical",
      meta: `${(highRisk.blocking_patents_count ?? 0).toLocaleString()} blocker${
        highRisk.blocking_patents_count === 1 ? "" : "s"
      }`,
    });
  }

  if (reviewTarget && reviewTarget.id !== highRisk?.id) {
    const reviewStatus =
      reviewTarget.review_status?.status === "changes_requested"
        ? "changes requested"
        : reviewTarget.review_status?.status === "under_review"
          ? "under review"
          : "flagged";
    actions.push({
      id: `review-${reviewTarget.id}`,
      title: "Prepare reviewer questions",
      description: `${reviewTarget.compound_name}: turn open caveats into source-linked reviewer prompts and owner-ready follow-ups.`,
      href: reportAiHref(reviewTarget, "review_questions", "evidence"),
      cta: "Review evidence",
      icon: ClipboardCheck,
      tone: "review",
      meta: reviewStatus,
    });
  }

  if (running) {
    actions.push({
      id: `running-${running.id}`,
      title: "Monitor adaptive run",
      description: `${running.compound_name}: watch source coverage, escalation gates, and claim-packet readiness as the run advances.`,
      href: `/analyses/${running.id}`,
      cta: "Track run",
      icon: Activity,
      tone: "active",
      meta: `${running.progress_pct}% complete`,
    });
  }

  if (shared && !actions.some((action) => action.id.endsWith(shared.id))) {
    actions.push({
      id: `shared-${shared.id}`,
      title: "Summarize external readout",
      description: shared.risk_ratings_restricted
        ? `${shared.compound_name}: prepare a concise source-grounded update from visible share activity, review state, and permitted evidence changes.`
        : `${shared.compound_name}: prepare a concise source-grounded update from shared report activity and material risk movements.`,
      href: reportAiHref(shared, "external_readout", "audit"),
      cta: "Open shared packet",
      icon: MessageSquareQuote,
      tone: "neutral",
      meta: shared.share_view_count
        ? `${shared.share_view_count.toLocaleString()} view${
            shared.share_view_count === 1 ? "" : "s"
          }`
        : "shared",
    });
  }

  if (actions.length === 0) {
    actions.push({
      id: "launch-preflight",
      title: "Launch compound preflight",
      description:
        "Start a source-aware preflight that estimates jurisdictions, evidence gates, and Report Credit capacity before submitting a run.",
      href: "/analyses/new",
      cta: "Start preflight",
      icon: FileSearch,
      tone: "neutral",
      meta: "ready",
    });
  }

  return actions.slice(0, 3);
}

export function AiCommandPanel({
  analyses,
  sampleWindowSize,
}: AiCommandPanelProps) {
  const formatRelativeTime = useHydrationSafeRelativeTime(relativeTime);
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const actions = buildAiCommandActions(analyses).filter((action) =>
    canAccessWorkspaceHref(principal.data, action.href),
  );
  if (actions.length === 0) {
    actions.push({
      id: "review-library",
      title: "Review existing analysis packets",
      description:
        "Open the organization library to inspect permitted report summaries, status, and handoff records.",
      href: "/analyses",
      cta: "Open library",
      icon: FileSearch,
      tone: "neutral",
      meta: "read only",
    });
  }
  const contextWindowSize = sampleWindowSize ?? analyses.length;
  const riskRatingsRestricted = analyses.some(
    (analysis) => analysis.risk_ratings_restricted === true,
  );
  const contextWindowLabel =
    contextWindowSize > 0
      ? `the latest ${contextWindowSize.toLocaleString()} ${
          contextWindowSize === 1 ? "analysis" : "analyses"
        }`
      : "current workspace context";
  const latestUpdatedAt = analyses.slice().sort(sortByUpdatedAt)[0]?.updated_at;
  const highRiskCount = analyses.filter(
    (analysis) => analysis.overall_risk === "high",
  ).length;
  const blockerCount = analyses.reduce(
    (total, analysis) =>
      total +
      (analysis.status === "completed"
        ? (analysis.blocking_patents_count ?? 0)
        : 0),
    0,
  );
  const reviewCount = analyses.filter(
    (analysis) =>
      analysis.flagged_for_review ||
      analysis.review_status?.status === "changes_requested" ||
      analysis.review_status?.status === "under_review",
  ).length;
  const runningCount = analyses.filter(
    (analysis) => analysis.status === "running",
  ).length;
  const sharedCount = analyses.filter(
    (analysis) => analysis.share_active,
  ).length;

  return (
    <section
      aria-labelledby="dashboard-ai-command-title"
      className="praviar-surface-premium overflow-hidden rounded-lg border border-[var(--card-border)]"
      data-testid="dashboard-ai-command-panel"
      data-praviar-ai-workbench="governed-next-actions"
    >
      <div className="relative overflow-hidden border-b border-[var(--border-subtle)] bg-[var(--surface-muted)]/38 px-4 py-4 sm:px-5">
        <div
          className="praviar-command-deck-art pointer-events-none absolute inset-y-0 right-0 hidden w-1/2 opacity-35 2xl:block"
          aria-hidden="true"
        />
        <div
          className="relative grid gap-4 2xl:grid-cols-[minmax(0,1fr)_minmax(18rem,0.54fr)] 2xl:items-start"
          data-testid="dashboard-ai-command-header-grid"
        >
          <div className="flex min-w-0 items-start gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-brand-primary/20 bg-brand-primary/10 text-brand-primary shadow-[var(--shadow-xs)]">
              <Bot className="h-5 w-5" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                Praviar AI workbench
              </p>
              <h2
                id="dashboard-ai-command-title"
                className="mt-0.5 text-lg font-semibold text-[var(--text-primary)] sm:text-xl"
              >
                Evidence-ready next moves
              </h2>
              <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
                Grounded in {contextWindowLabel}: claim evidence, reviewer
                state, share activity, and active pipeline gates.
              </p>
            </div>
          </div>

          <div
            className="grid grid-cols-3 gap-2"
            role="group"
            aria-label="AI workbench operating signals"
          >
            <div
              className={cn(
                "min-w-0 rounded-md border px-3 py-2",
                riskRatingsRestricted
                  ? "border-warning/25 bg-warning/10"
                  : "border-error/20 bg-error/8",
              )}
            >
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                {riskRatingsRestricted ? "Risk posture" : "Blockers"}
              </p>
              <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
                {riskRatingsRestricted
                  ? "Counsel only"
                  : blockerCount.toLocaleString()}
              </p>
            </div>
            <div className="min-w-0 rounded-md border border-warning/25 bg-warning/10 px-3 py-2">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                Review
              </p>
              <p className="mt-1 text-lg font-semibold tabular-nums text-[var(--text-primary)]">
                {reviewCount.toLocaleString()}
              </p>
            </div>
            <div className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-glass)] px-3 py-2">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                Updated
              </p>
              <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                {latestUpdatedAt
                  ? formatRelativeTime(latestUpdatedAt)
                  : "No data"}
              </p>
            </div>
          </div>
        </div>
      </div>

      <div
        className="grid gap-0 2xl:grid-cols-[minmax(0,1.38fr)_minmax(18rem,0.62fr)]"
        data-testid="dashboard-ai-command-body-grid"
      >
        <ol className="divide-y divide-[var(--border-subtle)]">
          {actions.map((action) => {
            const Icon = action.icon;

            return (
              <li key={action.id}>
                <Link
                  href={action.href}
                  className={cn(
                    "group grid min-w-0 gap-3 border-l-2 px-4 py-4 transition-colors sm:grid-cols-[auto_minmax(0,1fr)] sm:items-start sm:px-5 2xl:grid-cols-[auto_minmax(0,1fr)_auto] 2xl:items-center",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]",
                    ACTION_TONE_CLASSES[action.tone],
                  )}
                >
                  <span
                    className={cn(
                      "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
                      ACTION_ICON_CLASSES[action.tone],
                    )}
                  >
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <span className="min-w-0">
                    <span className="flex min-w-0 flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-[var(--text-primary)]">
                        {action.title}
                      </span>
                      <span
                        className={cn(
                          "rounded-full border px-2 py-0.5 text-xs font-semibold uppercase tracking-[0.1em]",
                          ACTION_META_CLASSES[action.tone],
                        )}
                      >
                        {action.meta}
                      </span>
                    </span>
                    <span className="mt-1 block max-w-3xl text-xs leading-5 text-[var(--text-secondary)]">
                      {action.description}
                    </span>
                  </span>
                  <span className="inline-flex min-h-10 w-fit items-center justify-center gap-1.5 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 text-xs font-semibold text-brand-primary shadow-[var(--shadow-xs)] transition-colors group-hover:border-brand-primary/35 group-hover:bg-brand-primary/10 sm:col-start-2 2xl:col-start-auto">
                    {action.cta}
                    <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                  </span>
                </Link>
              </li>
            );
          })}
        </ol>

        <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-surface)]/62 p-4 sm:p-5 2xl:border-l 2xl:border-t-0">
          <div
            className="grid gap-2 text-xs sm:grid-cols-3 2xl:grid-cols-1"
            role="group"
            aria-label="AI workbench guardrails"
          >
            <span className="inline-flex min-h-10 items-center gap-2 rounded-md border border-brand-primary/20 bg-brand-primary/8 px-3 font-semibold text-[var(--brand-primary-dim)]">
              <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
              Claim-cited output
            </span>
            <span className="inline-flex min-h-10 items-center gap-2 rounded-md border border-warning/25 bg-warning/10 px-3 font-semibold text-[var(--text-primary)]">
              <ClipboardCheck className="h-3.5 w-3.5" aria-hidden="true" />
              Human review gate
            </span>
            <span className="inline-flex min-h-10 items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-glass)] px-3 font-semibold text-[var(--text-secondary)]">
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              Tenant-scoped context
            </span>
          </div>

          <div className="mt-4 grid gap-2 sm:grid-cols-3 2xl:grid-cols-1">
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-3 py-2">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                {riskRatingsRestricted ? "Evidence context" : "High risk"}
              </p>
              <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                {riskRatingsRestricted
                  ? "Role-filtered · governed"
                  : `${highRiskCount.toLocaleString()} active signal${
                      highRiskCount === 1 ? "" : "s"
                    }`}
              </p>
            </div>
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-3 py-2">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                Running
              </p>
              <p className="mt-1 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
                {runningCount.toLocaleString()} adaptive run
                {runningCount === 1 ? "" : "s"}
              </p>
            </div>
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-3 py-2">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                Shared
              </p>
              <p className="mt-1 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
                {sharedCount.toLocaleString()} external readout
                {sharedCount === 1 ? "" : "s"}
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export { buildAiCommandActions };
