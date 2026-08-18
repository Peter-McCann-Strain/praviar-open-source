"use client";

import Link from "next/link";
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  Gauge,
  Scale,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  WalletCards,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import { useAuthToken } from "@/hooks/use-auth-token";
import {
  canAccessWorkspaceHref,
  usePrincipalCapabilities,
} from "@/hooks/use-principal-capabilities";
import type { BillingStatus } from "@/hooks/use-billing";
import type { AnalysisListItem } from "@/types/api";

interface ExecutiveDecisionBriefProps {
  analyses: AnalysisListItem[];
  isBillingAccessRestricted?: boolean;
  billingStatus?: BillingStatus | null;
  isBillingLoading?: boolean;
  sampleWindowSize: number;
  totalAnalyses: number;
}

interface DecisionMetric {
  detail: string;
  href: string;
  icon: LucideIcon;
  label: string;
  tone: "critical" | "success" | "warning" | "active";
  value: string;
}

interface NextMove {
  cta: string;
  detail: string;
  href: string;
  label: string;
  tone: DecisionMetric["tone"];
}

const TONE_CLASSES: Record<DecisionMetric["tone"], string> = {
  active: "border-info/22 bg-info/8 text-info",
  critical: "border-error/24 bg-error/8 text-error",
  success: "border-success/24 bg-success/8 text-success",
  warning: "border-warning/28 bg-warning/10 text-[var(--text-primary)]",
};

const BAR_CLASSES: Record<DecisionMetric["tone"], string> = {
  active: "bg-info",
  critical: "bg-error",
  success: "bg-success",
  warning: "bg-warning",
};

function isCompleted(analysis: AnalysisListItem) {
  return analysis.status === "completed";
}

function hasCounselAttention(analysis: AnalysisListItem) {
  return (
    isCompleted(analysis) &&
    (analysis.flagged_for_review ||
      (!analysis.risk_ratings_restricted && analysis.overall_risk === "high") ||
      (analysis.review_status?.is_persisted &&
        analysis.review_status.status === "changes_requested"))
  );
}

function sortByUpdatedAt(left: AnalysisListItem, right: AnalysisListItem) {
  return Date.parse(right.updated_at) - Date.parse(left.updated_at);
}

function getCapacityMetric(
  billingStatus: BillingStatus | null | undefined,
  isBillingAccessRestricted: boolean | undefined,
  isBillingLoading: boolean | undefined,
): DecisionMetric {
  if (isBillingAccessRestricted) {
    return {
      detail: "Billing capacity hidden until access is restored",
      href: "/billing",
      icon: WalletCards,
      label: "Capacity runway",
      tone: "warning",
      value: "Restricted",
    };
  }

  if (isBillingLoading) {
    return {
      detail: "Billing runway is syncing",
      href: "/billing",
      icon: WalletCards,
      label: "Capacity runway",
      tone: "active",
      value: "Checking",
    };
  }

  if (!billingStatus) {
    return {
      detail: "Open billing for plan and Report Credit capacity",
      href: "/billing",
      icon: WalletCards,
      label: "Capacity runway",
      tone: "warning",
      value: "Needs sync",
    };
  }

  if (
    billingStatus.plan === "enterprise" &&
    billingStatus.analyses_limit <= 0
  ) {
    return {
      detail: "Contracted capacity managed with Praviar",
      href: "/billing",
      icon: WalletCards,
      label: "Capacity runway",
      tone: "success",
      value: "Custom",
    };
  }

  const remaining = Math.max(
    billingStatus.analyses_limit - billingStatus.analyses_used,
    0,
  );
  const prepaidCredits = Math.max(0, billingStatus.purchased_credits_balance);
  const tone = remaining <= 2 ? "warning" : "success";

  return {
    detail:
      prepaidCredits > 0
        ? `${prepaidCredits.toLocaleString()} prepaid Report Credit${
            prepaidCredits === 1 ? "" : "s"
          } included`
        : "No prepaid Report Credits in reserve",
    href: "/billing?intent=credits",
    icon: WalletCards,
    label: "Capacity runway",
    tone,
    value: `${remaining.toLocaleString()} left`,
  };
}

function buildNextMove(analyses: AnalysisListItem[]): NextMove {
  const completed = analyses.filter(isCompleted).sort(sortByUpdatedAt);
  const blocker = completed
    .filter(
      (analysis) =>
        !analysis.risk_ratings_restricted &&
        (analysis.blocking_patents_count ?? 0) > 0,
    )
    .sort(
      (left, right) =>
        (right.blocking_patents_count ?? 0) -
          (left.blocking_patents_count ?? 0) || sortByUpdatedAt(left, right),
    )[0];

  if (blocker) {
    return {
      cta: "Open blocker brief",
      detail: `${blocker.compound_name}: cite claim elements, legal status, expiry, and design-around assumptions before the next counsel readout.`,
      href: `/analyses/${blocker.id}/report?ai_context=blocker_brief&tab=patents`,
      label: "Draft blocking-patent brief",
      tone: "critical",
    };
  }

  const reviewTarget = completed.find(hasCounselAttention);
  if (reviewTarget) {
    return {
      cta: "Prepare questions",
      detail: `${reviewTarget.compound_name}: convert unresolved caveats into source-linked reviewer prompts.`,
      href: `/analyses/${reviewTarget.id}/report?ai_context=review_questions&tab=evidence`,
      label: "Prepare reviewer questions",
      tone: "warning",
    };
  }

  const running = analyses
    .filter((analysis) => analysis.status === "running")
    .sort(sortByUpdatedAt)[0];
  if (running) {
    return {
      cta: "Track live run",
      detail: `${running.compound_name}: monitor source coverage, escalation gates, and claim-packet readiness.`,
      href: `/analyses/${running.id}`,
      label: "Monitor adaptive run",
      tone: "active",
    };
  }

  return {
    cta: "Start preflight",
    detail:
      "Launch the next source-aware preflight with matter scope, jurisdictions, evidence gates, and Report Credit runway visible before submission.",
    href: "/analyses/new",
    label: "Launch compound preflight",
    tone: "success",
  };
}

function buildDecisionMetrics({
  analyses,
  billingStatus,
  isBillingAccessRestricted,
  isBillingLoading,
}: {
  analyses: AnalysisListItem[];
  billingStatus?: BillingStatus | null;
  isBillingAccessRestricted?: boolean;
  isBillingLoading?: boolean;
}): DecisionMetric[] {
  const completed = analyses.filter(isCompleted);
  const riskRatingsRestricted = analyses.some(
    (analysis) => analysis.risk_ratings_restricted === true,
  );
  const blockedAssets = completed.filter(
    (analysis) =>
      !analysis.risk_ratings_restricted &&
      (analysis.blocking_patents_count ?? 0) > 0,
  );
  const clearAssets = completed.filter(
    (analysis) => analysis.overall_risk === "clear",
  );
  const reviewAssets = completed.filter(hasCounselAttention);

  if (riskRatingsRestricted) {
    return [
      {
        detail:
          "Risk ratings and blocker counts are hidden for this role; no zero-risk conclusion is inferred",
        href: "/analyses",
        icon: ShieldCheck,
        label: "Risk posture",
        tone: "warning",
        value: "Counsel only",
      },
      {
        detail:
          reviewAssets.length > 0
            ? "Visible review or owner signals needing action"
            : "No visible review handoff is waiting in this window",
        href: "/reviews?filter=escalated&sort=priority",
        icon: Scale,
        label: "Review handoffs",
        tone: reviewAssets.length > 0 ? "warning" : "success",
        value: reviewAssets.length.toLocaleString(),
      },
      {
        detail: "Evidence packets completed in the current dashboard window",
        href: "/analyses?status=completed",
        icon: ClipboardCheck,
        label: "Completed reports",
        tone: "active",
        value: completed.length.toLocaleString(),
      },
      getCapacityMetric(
        billingStatus,
        isBillingAccessRestricted,
        isBillingLoading,
      ),
    ];
  }

  return [
    {
      detail:
        blockedAssets.length > 0
          ? "Prioritize claim charts and design-around assumptions"
          : "No blocking patents in the current decision window",
      href: "/analyses?risk=high",
      icon: TriangleAlert,
      label: "Blocked assets",
      tone: blockedAssets.length > 0 ? "critical" : "success",
      value: blockedAssets.length.toLocaleString(),
    },
    {
      detail:
        clearAssets.length > 0
          ? "Candidates that can progress to stakeholder review"
          : "No clear-to-progress reports in this window yet",
      href: "/analyses?risk=clear",
      icon: CheckCircle2,
      label: "Clear to progress",
      tone: "success",
      value: clearAssets.length.toLocaleString(),
    },
    {
      detail:
        reviewAssets.length > 0
          ? "Open risk or reviewer signals needing owner action"
          : "No counsel bottleneck detected in completed reports",
      href: "/reviews?filter=escalated&sort=priority",
      icon: Scale,
      label: "Counsel bottleneck",
      tone: reviewAssets.length > 0 ? "warning" : "success",
      value: reviewAssets.length.toLocaleString(),
    },
    getCapacityMetric(
      billingStatus,
      isBillingAccessRestricted,
      isBillingLoading,
    ),
  ];
}

export function ExecutiveDecisionBrief({
  analyses,
  isBillingAccessRestricted,
  billingStatus,
  isBillingLoading,
  sampleWindowSize,
  totalAnalyses,
}: ExecutiveDecisionBriefProps) {
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const metrics = buildDecisionMetrics({
    analyses,
    billingStatus,
    isBillingAccessRestricted,
    isBillingLoading,
  });
  const nextMove = buildNextMove(analyses);
  const visibleMetrics = metrics.filter((metric) =>
    canAccessWorkspaceHref(principal.data, metric.href),
  );
  const visibleNextMove = canAccessWorkspaceHref(principal.data, nextMove.href)
    ? nextMove
    : {
        cta: "Review analysis library",
        detail:
          "Inspect permitted report packets and current review state from the organization library.",
        href: "/analyses",
        label: "Continue with existing work",
        tone: "active" as const,
      };
  const completedCount = analyses.filter(isCompleted).length;
  const riskRatingsRestricted = analyses.some(
    (analysis) => analysis.risk_ratings_restricted === true,
  );
  const windowLabel =
    totalAnalyses > sampleWindowSize
      ? `Latest ${sampleWindowSize.toLocaleString()} of ${totalAnalyses.toLocaleString()} analyses`
      : `Latest ${sampleWindowSize.toLocaleString()} ${
          sampleWindowSize === 1 ? "analysis" : "analyses"
        }`;

  return (
    <section
      aria-labelledby="dashboard-executive-brief-title"
      className="praviar-surface-premium relative isolate overflow-hidden rounded-lg border border-[var(--card-border)]"
      data-testid="dashboard-executive-decision-brief"
    >
      <div
        className="praviar-command-deck-art pointer-events-none absolute inset-y-0 right-0 -z-10 hidden w-1/2 opacity-35 xl:block"
        aria-hidden="true"
      />
      <div className="grid gap-0 xl:grid-cols-[minmax(0,1fr)_minmax(22rem,0.46fr)]">
        <div className="min-w-0">
          <div className="grid gap-3 border-b border-[var(--border-subtle)] bg-[var(--surface-muted)]/38 px-4 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start sm:px-5">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand-primary">
                Executive decision brief
              </p>
              <h2
                id="dashboard-executive-brief-title"
                className="mt-1 text-xl font-semibold text-[var(--text-primary)] sm:text-2xl"
              >
                {riskRatingsRestricted
                  ? "Portfolio workflow ready for leadership"
                  : "Portfolio calls ready for leadership"}
              </h2>
              <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
                {riskRatingsRestricted
                  ? "Operational posture across visible review handoffs, completed evidence packets, and billing runway. Governed risk details remain intentionally restricted."
                  : "Review-workflow posture across blockers, progressable reports, counsel load, and billing runway."}
              </p>
            </div>
            <div className="grid w-full gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-glass)] px-3 py-2 text-xs shadow-[var(--shadow-xs)] sm:w-auto sm:min-w-48">
              <div className="flex items-center justify-between gap-4">
                <span className="text-[var(--text-tertiary)]">Window</span>
                <span className="font-semibold text-[var(--text-primary)]">
                  {windowLabel}
                </span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="text-[var(--text-tertiary)]">Completed</span>
                <span className="font-semibold tabular-nums text-[var(--text-primary)]">
                  {completedCount.toLocaleString()}
                </span>
              </div>
            </div>
          </div>

          <div
            className={cn(
              "grid gap-px bg-[var(--border-subtle)] sm:grid-cols-2",
              visibleMetrics.length >= 4
                ? "2xl:grid-cols-4"
                : visibleMetrics.length === 3
                  ? "2xl:grid-cols-3"
                  : "2xl:grid-cols-2",
            )}
          >
            {visibleMetrics.map(
              ({ detail, href, icon: Icon, label, tone, value }) => (
                <Link
                  key={label}
                  href={href}
                  className="group relative min-w-0 bg-[var(--bg-surface)]/78 px-4 py-4 transition-colors hover:bg-[var(--surface-hover)] focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)] sm:px-5"
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      "absolute inset-x-0 top-0 h-1",
                      BAR_CLASSES[tone],
                    )}
                  />
                  <span className="flex min-w-0 items-start gap-3">
                    <span
                      className={cn(
                        "flex h-10 w-10 shrink-0 items-center justify-center rounded-md border",
                        TONE_CLASSES[tone],
                      )}
                    >
                      <Icon className="h-4 w-4" aria-hidden="true" />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                        {label}
                      </span>
                      <span className="mt-1 block text-2xl font-semibold leading-none tabular-nums text-[var(--text-primary)]">
                        {value}
                      </span>
                    </span>
                  </span>
                  <span className="mt-3 block min-h-10 text-xs leading-5 text-[var(--text-secondary)]">
                    {detail}
                  </span>
                  <span className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-brand-primary">
                    Inspect
                    <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                  </span>
                </Link>
              ),
            )}
          </div>
        </div>

        <div className="min-w-0 border-t border-[var(--border-subtle)] bg-[var(--bg-surface)]/70 p-4 sm:p-5 xl:border-l xl:border-t-0">
          <div className="flex min-w-0 items-start gap-3">
            <span
              className={cn(
                "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border",
                TONE_CLASSES[visibleNextMove.tone],
              )}
              aria-hidden="true"
            >
              <Sparkles className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand-primary">
                AI next move
              </p>
              <h3 className="mt-1 text-base font-semibold text-[var(--text-primary)]">
                {visibleNextMove.label}
              </h3>
              <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
                {visibleNextMove.detail}
              </p>
            </div>
          </div>

          <Link
            href={visibleNextMove.href}
            className="mt-4 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-md bg-brand-primary px-3 text-sm font-semibold text-[var(--brand-paper)] shadow-[var(--shadow-xs)] transition-colors hover:bg-brand-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]"
          >
            {visibleNextMove.cta}
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>

          <div
            className="mt-4 grid gap-2 text-xs"
            aria-label="Executive AI trust controls"
            role="group"
          >
            <span className="inline-flex min-h-10 items-center gap-2 rounded-md border border-brand-primary/20 bg-brand-primary/8 px-3 font-semibold text-[var(--brand-primary-dim)]">
              <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
              Source-linked
            </span>
            <span className="inline-flex min-h-10 items-center gap-2 rounded-md border border-warning/25 bg-warning/10 px-3 font-semibold text-[var(--text-primary)]">
              <ClipboardCheck className="h-3.5 w-3.5" aria-hidden="true" />
              Human review gate
            </span>
            <span className="inline-flex min-h-10 items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-glass)] px-3 font-semibold text-[var(--text-secondary)]">
              <Gauge className="h-3.5 w-3.5" aria-hidden="true" />
              Calibrated to current evidence
            </span>
            <span className="inline-flex min-h-10 items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-glass)] px-3 font-semibold text-[var(--text-secondary)]">
              <Activity className="h-3.5 w-3.5" aria-hidden="true" />
              Tenant-scoped context
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}

export { buildDecisionMetrics, buildNextMove };
