"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import {
  ArrowUpRight,
  ChevronDown,
  CircleCheck,
  FileCheck2,
  Gauge,
  GitBranch,
  PackagePlus,
  SearchCheck,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import { formatScopeLabel } from "@/components/analysis-wizard/matter-scope-preflight";
import { getCompoundInputReadiness } from "@/components/chemistry/smiles-input";
import { getEnabledSources } from "@/components/config/helpers";
import { ChartSwatch } from "@/components/charts/chart-swatch";
import { Button } from "@/components/ui/button";
import type { BillingStatus } from "@/hooks/use-billing";
import type { CreditCapacityRequestSource } from "@/hooks/use-billing";
import { getRuntimeSearchJurisdictions } from "@/lib/jurisdiction-bundles";
import {
  formatReportCreditCapacityBreakdown,
  formatReportRequestCount,
  getReportCreditCapacitySnapshot,
} from "@/lib/report-credit-capacity";
import type { ConfigState } from "@/stores/config-store";
import type { MatterScopePreflightValue } from "@/types/pipeline";
import { cn } from "@/lib/utils";
import { ResponsiveDisclosure } from "@/components/shared/responsive-disclosure";

interface EvidenceLaunchRailProps {
  className?: string;
  billingStatus?: BillingStatus;
  canManageBilling?: boolean;
  compoundInput: string;
  config: ConfigState;
  getCreditPackHref?: (pack: string) => string;
  isBillingAccessRestricted?: boolean;
  isBillingLoading?: boolean;
  matterScope?: MatterScopePreflightValue;
  onRequestReportCredits?: (
    requestedReports: number,
    source: CreditCapacityRequestSource,
  ) => void;
  requestReportCreditsPending?: boolean;
  sessionReady?: boolean;
  step: number;
}

const EVIDENCE_LAUNCH_STEPS = [
  {
    icon: SearchCheck,
    label: "Source search",
    copy: "Patent and chemistry sources are queried under org policy.",
  },
  {
    icon: GitBranch,
    label: "Adaptive triage",
    copy: "Relevance gates narrow candidates before claim review.",
  },
  {
    icon: FileCheck2,
    label: "Claim packet",
    copy: "Material claims are mapped into a reviewer-ready record.",
  },
  {
    icon: ShieldCheck,
    label: "Counsel handoff",
    copy: "Uncertainty and evidence gaps remain explicit.",
  },
] as const;

type ReadinessState = "ready" | "attention" | "pending";

const READINESS_SWATCH_COLORS: Record<ReadinessState, string> = {
  ready: "var(--color-success)",
  attention: "var(--color-warning)",
  pending: "var(--text-tertiary)",
};

interface ReadinessItem {
  label: string;
  value: string;
  detail: string;
  state: ReadinessState;
}

interface LaunchCopilotBrief {
  action: string;
  detail: string;
  evidence: string;
  state: ReadinessState;
  title: string;
}

interface CapacityCreditAction {
  body: string;
  cta: string;
  href?: string;
  request?: {
    requestedReports: number;
    source: CreditCapacityRequestSource;
  };
  title: string;
  tone: "blocked" | "tight";
}

function buildLaunchCreditReturnTo() {
  return "/analyses/new?resume=credit_checkout";
}

function buildLaunchCreditPackHref(pack = "portfolio_5") {
  const params = new URLSearchParams({
    intent: "credits",
    needed_reports: "1",
    pack,
    return_to: buildLaunchCreditReturnTo(),
    source: "launch",
  });
  return `/billing?${params.toString()}`;
}

function getLaunchStageState(index: number, step: number) {
  if (index === 0) {
    return step === 1 ? "current" : "prepared";
  }
  if (index === 1) {
    if (step === 2) return "current";
    return step > 2 ? "prepared" : "pending";
  }
  if (index === 2) {
    return step === 3 ? "current" : "pending";
  }
  return "after launch";
}

function formatCount(value: number, singular: string, plural = `${singular}s`) {
  return `${value.toLocaleString()} ${value === 1 ? singular : plural}`;
}

function buildCapacityReadiness({
  billingStatus,
  isBillingAccessRestricted,
  isBillingLoading,
  sessionReady,
}: {
  billingStatus?: BillingStatus;
  isBillingAccessRestricted: boolean;
  isBillingLoading: boolean;
  sessionReady: boolean;
}): ReadinessItem {
  if (!sessionReady) {
    return {
      label: "Capacity",
      value: "Session pending",
      detail: "Secure session required before launch",
      state: "pending",
    };
  }

  if (isBillingAccessRestricted) {
    return {
      label: "Capacity",
      value: "Access restricted",
      detail: "Report Credit capacity hidden until access is restored",
      state: "attention",
    };
  }

  if (isBillingLoading) {
    return {
      label: "Capacity",
      value: "Checking",
      detail: "Retrieving current workspace capacity",
      state: "pending",
    };
  }

  if (!billingStatus) {
    return {
      label: "Capacity",
      value: "Policy check",
      detail: "Quota is enforced before analysis starts",
      state: "pending",
    };
  }

  if (billingStatus.plan === "enterprise") {
    return {
      label: "Capacity",
      value: "Enterprise",
      detail: "Contracted capacity applies at launch",
      state: "ready",
    };
  }

  const capacity = getReportCreditCapacitySnapshot(billingStatus);

  return {
    label: "Capacity",
    value:
      capacity.effectiveRemaining > 0
        ? `${formatReportRequestCount(capacity.effectiveRemaining)} available`
        : "0 report requests available",
    detail: formatReportCreditCapacityBreakdown(capacity),
    state: capacity.effectiveRemaining > 0 ? "ready" : "attention",
  };
}

function buildCapacityCreditAction({
  billingStatus,
  canManageBilling,
  getCreditPackHref,
  isBillingAccessRestricted,
  isBillingLoading,
  sessionReady,
}: {
  billingStatus?: BillingStatus;
  canManageBilling: boolean;
  getCreditPackHref?: (pack: string) => string;
  isBillingAccessRestricted: boolean;
  isBillingLoading: boolean;
  sessionReady: boolean;
}): CapacityCreditAction | null {
  if (
    !sessionReady ||
    isBillingAccessRestricted ||
    isBillingLoading ||
    !billingStatus ||
    billingStatus.plan === "enterprise"
  ) {
    return null;
  }

  const capacity = getReportCreditCapacitySnapshot(billingStatus);

  if (capacity.effectiveRemaining <= 0) {
    if (!canManageBilling) {
      return {
        title: "Workspace admin action required",
        body: "Only workspace administrators can add Report Credits. Ask an admin to add at least one credit before this FTO report can launch.",
        cta: "Request Report Credits",
        request: {
          requestedReports: 1,
          source: "analysis_launch",
        },
        tone: "blocked",
      };
    }
    return {
      title: "Report Credits required before launch",
      body: "Buy 1 Report Credit to launch this first-pass FTO report without changing subscription tier. Larger packs remain available on the billing page.",
      cta: "Buy 1 Report Credit",
      href:
        getCreditPackHref?.("single_analysis") ??
        buildLaunchCreditPackHref("single_analysis"),
      tone: "blocked",
    };
  }

  if (capacity.effectiveRemaining <= 5) {
    if (!canManageBilling) {
      return {
        title: "Capacity is tight",
        body: `${formatReportRequestCount(
          capacity.effectiveRemaining,
        )} remains. Ask a workspace administrator to review Report Credit capacity before the next diligence run.`,
        cta: "Notify workspace admin",
        request: {
          requestedReports: 5,
          source: "capacity_watch",
        },
        tone: "tight",
      };
    }
    return {
      title: "Capacity is tight",
      body: `${formatReportRequestCount(
        capacity.effectiveRemaining,
      )} remains. Review the 5-Report-Credit Portfolio Pack before the next diligence run.`,
      cta: "Review Report Credit Packs",
      href:
        getCreditPackHref?.("portfolio_5") ??
        buildLaunchCreditPackHref("portfolio_5"),
      tone: "tight",
    };
  }

  return null;
}

function buildLaunchCopilotBrief({
  currentStageLabel,
  readinessItems,
  step,
}: {
  currentStageLabel: string;
  readinessItems: ReadinessItem[];
  step: number;
}): LaunchCopilotBrief {
  const firstPending = readinessItems.find((item) => item.state === "pending");
  const firstAttention = readinessItems.find(
    (item) => item.state === "attention",
  );
  const firstBlocker = firstAttention ?? firstPending ?? null;

  if (firstBlocker?.label === "Compound") {
    const needsIdentifier = firstBlocker.value === "Needed";

    return {
      title: needsIdentifier
        ? "Add the compound identifier"
        : "Review the compound identifier",
      action: firstBlocker.detail,
      detail:
        "Praviar needs a resolvable compound context before it can route source search, triage, and claim review.",
      evidence: "Compound readiness is the open launch check.",
      state: "attention",
    };
  }

  if (firstBlocker?.label === "Sources") {
    return {
      title: "Enable production evidence",
      action: "Turn on at least one patent or chemistry source.",
      detail:
        "A first-pass FTO report request should not launch without an evidence source selected.",
      evidence: firstBlocker.detail,
      state: "attention",
    };
  }

  if (firstBlocker?.label === "Jurisdictions") {
    return {
      title: "Select search jurisdictions",
      action: "Choose at least one runtime search lane.",
      detail:
        "Jurisdiction scope controls which patent families seed the adaptive review path.",
      evidence: firstBlocker.detail,
      state: "attention",
    };
  }

  if (firstBlocker?.label === "Capacity") {
    if (firstBlocker.state === "attention") {
      const accessRestricted = firstBlocker.value === "Access restricted";
      return {
        title: accessRestricted
          ? "Restore billing access"
          : "Restore Report Credit capacity",
        action: accessRestricted
          ? "Restore billing access before launch."
          : "Add Report Credit capacity before launch.",
        detail: accessRestricted
          ? "Launch controls stay guarded while Report Credit capacity is hidden."
          : "Launch controls stay guarded while the workspace has no report-request capacity.",
        evidence: firstBlocker.detail,
        state: "attention",
      };
    }

    return {
      title: "Wait for launch capacity",
      action:
        "Keep configuring while Praviar confirms the latest report request capacity.",
      detail:
        "Launch controls stay guarded until the workspace capacity check completes.",
      evidence: firstBlocker.detail,
      state: firstBlocker.state,
    };
  }

  if (step < 3) {
    return {
      title: "Continue to launch review",
      action: "Confirm the evidence scope, then review the launch packet.",
      detail:
        "Core readiness checks are clear; the final step keeps the first-pass FTO boundary visible before submission.",
      evidence: `Current path stage: ${currentStageLabel}.`,
      state: "ready",
    };
  }

  return {
    title: "Ready for final launch check",
    action: "Start the analysis when the packet matches the matter.",
    detail:
      "The launch will create a source-linked first-pass FTO report request for review, not a legal clearance opinion.",
    evidence: "All visible launch readiness checks are clear.",
    state: "ready",
  };
}

export function EvidenceLaunchRail({
  className,
  billingStatus,
  canManageBilling = false,
  compoundInput,
  config,
  getCreditPackHref,
  isBillingAccessRestricted = false,
  isBillingLoading = false,
  matterScope,
  onRequestReportCredits,
  requestReportCreditsPending = false,
  sessionReady = true,
  step,
}: EvidenceLaunchRailProps) {
  const trimmedInput = compoundInput.trim();
  const compoundReadiness = getCompoundInputReadiness(trimmedInput);
  const inputType = compoundReadiness.inputType;
  const enabledSources = getEnabledSources(config);
  const sourceLabel =
    enabledSources.length > 0
      ? enabledSources.join(", ")
      : "Enable at least one patent source";
  const runtimeSearchJurisdictions = getRuntimeSearchJurisdictions({
    jurisdictionBundle: config.jurisdictionBundle,
    searchJurisdictions: config.searchJurisdictions,
    targetJurisdictions: config.targetJurisdictions,
  });
  const searchJurisdictionLabel =
    runtimeSearchJurisdictions.length > 0
      ? runtimeSearchJurisdictions.join(", ")
      : "Select at least one search jurisdiction";
  const reviewGateLabel =
    config.hitlEnabled && config.hitlCheckpoints.length > 0
      ? `Identity + ${formatCount(config.hitlCheckpoints.length, "additional gate")}`
      : "Resolved identity approval";
  const matterScopeLabel = matterScope
    ? `${formatScopeLabel(matterScope.assetTypeHint)}; ${formatScopeLabel(
        matterScope.developmentStage,
      )}`
    : null;
  const matterActionLabel = matterScope
    ? formatCount(matterScope.intendedActions.length, "action")
    : null;
  const readinessItems: ReadinessItem[] = [
    {
      label: "Compound",
      value: compoundReadiness.canProceed
        ? "Ready"
        : trimmedInput
          ? "Needs review"
          : "Needed",
      detail: compoundReadiness.canProceed
        ? (inputType ?? "Name, SMILES, InChI, InChIKey, or CAS")
        : compoundReadiness.detail,
      state: compoundReadiness.canProceed ? "ready" : "attention",
    },
    ...(matterScope
      ? [
          {
            label: "Scope",
            value: matterScopeLabel ?? "Matter scope",
            detail: `${matterActionLabel ?? "1 action"} confirmed for evidence routing`,
            state: "ready" as const,
          },
        ]
      : []),
    {
      label: "Sources",
      value:
        enabledSources.length > 0
          ? formatCount(enabledSources.length, "source")
          : "No sources",
      detail: sourceLabel,
      state: enabledSources.length > 0 ? "ready" : "attention",
    },
    {
      label: "Jurisdictions",
      value:
        runtimeSearchJurisdictions.length > 0
          ? formatCount(runtimeSearchJurisdictions.length, "lane")
          : "No lanes",
      detail: searchJurisdictionLabel,
      state: runtimeSearchJurisdictions.length > 0 ? "ready" : "attention",
    },
    {
      label: "Review",
      value: reviewGateLabel,
      detail: "Counsel handoff stays explicit",
      state: "ready",
    },
    buildCapacityReadiness({
      billingStatus,
      isBillingAccessRestricted,
      isBillingLoading,
      sessionReady,
    }),
  ];
  const readyCount = readinessItems.filter(
    (item) => item.state === "ready",
  ).length;
  const capacityCreditAction = buildCapacityCreditAction({
    billingStatus,
    canManageBilling,
    getCreditPackHref,
    isBillingAccessRestricted,
    isBillingLoading,
    sessionReady,
  });
  const currentStage =
    EVIDENCE_LAUNCH_STEPS.find(
      (_, index) => getLaunchStageState(index, step) === "current",
    ) ?? EVIDENCE_LAUNCH_STEPS[0];
  const launchCopilotBrief = buildLaunchCopilotBrief({
    currentStageLabel: currentStage.label,
    readinessItems,
    step,
  });

  return (
    <ResponsiveDisclosure
      className="group min-w-0 sm:contents"
      data-testid="evidence-launch-mobile-disclosure"
      summary={
        <summary className="flex min-h-16 cursor-pointer list-none items-center justify-between gap-3 rounded-lg border border-brand-primary/20 bg-[var(--surface-card)] px-3 py-3 text-left shadow-[var(--shadow-xs)] marker:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 sm:hidden [&::-webkit-details-marker]:hidden">
          <span className="min-w-0">
            <span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              Run readiness · {readyCount}/{readinessItems.length}
            </span>
            <span className="mt-0.5 block text-sm font-semibold text-[var(--text-primary)]">
              Next blocker · {launchCopilotBrief.title}
            </span>
            <span className="mt-0.5 line-clamp-1 block text-xs text-[var(--text-secondary)]">
              Current handoff: {currentStage.label}
            </span>
          </span>
          <ChevronDown
            className="h-4 w-4 shrink-0 text-brand-primary transition-transform group-open:rotate-180 motion-reduce:transition-none"
            aria-hidden="true"
          />
        </summary>
      }
    >
      <aside
        aria-label="Evidence launch readiness"
        className={cn(
          "praviar-surface-premium relative mt-2 min-w-0 overflow-hidden rounded-lg p-4 sm:mt-0 lg:sticky lg:top-28",
          className,
        )}
      >
        <div
          className="praviar-evidence-field-pattern pointer-events-none absolute inset-0"
          aria-hidden="true"
        />

        <div className="relative space-y-4">
          <div className="flex items-start gap-3">
            <PraviarMarkFrame size="dialog" />
            <div className="min-w-0 flex-1">
              <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                  Run readiness
                </p>
                <span className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-brand-primary/20 bg-brand-primary/10 px-2 py-1 text-xs font-semibold text-brand-primary">
                  <CircleCheck className="h-3 w-3" aria-hidden="true" />
                  {readyCount}/{readinessItems.length} ready
                </span>
              </div>
              <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                Readiness, scope, capacity, and handoff stay visible before the
                FTO report request is submitted.
              </p>
            </div>
          </div>

          {capacityCreditAction ? (
            <CapacityCreditRecoveryCard
              action={capacityCreditAction}
              onRequestReportCredits={onRequestReportCredits}
              requestReportCreditsPending={requestReportCreditsPending}
            />
          ) : (
            <LaunchCopilotBriefCard brief={launchCopilotBrief} />
          )}

          <div className="grid grid-cols-2 gap-2 lg:grid-cols-1 2xl:grid-cols-2">
            {readinessItems.map((item) => (
              <div
                key={item.label}
                role="group"
                aria-label={`${item.label}: ${item.value}; ${item.detail}; ${item.state}`}
                className={cn(
                  "min-w-0 rounded-md border bg-[var(--surface-glass)] px-3 py-2 shadow-[var(--shadow-xs)]",
                  item.state === "ready"
                    ? "border-brand-primary/15"
                    : item.state === "attention"
                      ? "border-warning/30 bg-warning/10"
                      : "border-[var(--border-subtle)]",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                    {item.label}
                  </p>
                  <ChartSwatch
                    className="h-2 w-2"
                    color={READINESS_SWATCH_COLORS[item.state]}
                  />
                </div>
                <p className="mt-1 text-sm font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
                  {item.value}
                </p>
                <p className="mt-0.5 text-xs leading-4 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                  {item.detail}
                </p>
              </div>
            ))}
          </div>

          <div className="rounded-md border border-brand-primary/15 bg-[var(--brand-ink)] px-3 py-2 text-[var(--brand-paper)] shadow-[var(--shadow-xs)]">
            <div className="flex items-center gap-2 text-xs font-semibold">
              <Gauge
                className="h-3.5 w-3.5 text-brand-accent"
                aria-hidden="true"
              />
              <span>
                1 Report Credit = 1 first-pass FTO report request for 1 compound
              </span>
            </div>
            <p className="mt-1 text-xs leading-4 text-[color-mix(in_srgb,var(--brand-paper)_78%,var(--brand-soft-mint))]">
              Included Report Credits are used first; purchased Report Credits
              extend report request capacity without changing plan tier.
            </p>
          </div>

          <LaunchRailDisclosure
            detail={`${trimmedInput || "Awaiting input"} · ${sourceLabel}`}
            title="Scope"
          >
            <div className="grid gap-2">
              <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-glass)] px-3 py-2">
                <p className="text-xs font-medium uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                  Compound
                </p>
                <p
                  className="mt-1 line-clamp-3 text-sm font-medium text-[var(--text-primary)] [overflow-wrap:anywhere]"
                  title={trimmedInput || undefined}
                >
                  {trimmedInput || "Awaiting input"}
                </p>
                <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                  {inputType ?? "Name, SMILES, InChI, InChIKey, or CAS"}
                </p>
              </div>
              {matterScope ? (
                <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-glass)] px-3 py-2">
                  <p className="text-xs font-medium uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                    Matter scope
                  </p>
                  <p className="mt-1 text-sm font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
                    {matterScopeLabel}
                  </p>
                  <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                    {matterScope.intendedActions
                      .map(formatScopeLabel)
                      .join(", ")}
                  </p>
                </div>
              ) : null}
              <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-glass)] px-3 py-2">
                <p className="text-xs font-medium uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                  Sources
                </p>
                <p className="mt-1 line-clamp-2 text-sm text-[var(--text-primary)] [overflow-wrap:anywhere]">
                  {sourceLabel}
                </p>
              </div>
              <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-glass)] px-3 py-2">
                <p className="text-xs font-medium uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                  Jurisdictions
                </p>
                <p className="mt-1 text-sm text-[var(--text-primary)] [overflow-wrap:anywhere]">
                  {searchJurisdictionLabel}
                </p>
              </div>
            </div>
          </LaunchRailDisclosure>

          <LaunchRailDisclosure
            detail={`Current: ${currentStage.label}`}
            title="Handoff path"
          >
            <ol className="space-y-2">
              {EVIDENCE_LAUNCH_STEPS.map((item, index) => {
                const Icon = item.icon;
                const stageState = getLaunchStageState(index, step);
                const isCurrent = stageState === "current";
                const isPrepared = stageState === "prepared";

                return (
                  <li
                    key={item.label}
                    aria-current={isCurrent ? "step" : undefined}
                    className={cn(
                      "grid grid-cols-[auto_minmax(0,1fr)] gap-3 rounded-md border px-3 py-2.5",
                      isCurrent
                        ? "border-brand-primary/20 bg-brand-primary/10"
                        : isPrepared
                          ? "border-success/20 bg-success/10"
                          : "border-[var(--border-subtle)] bg-[var(--surface-card)]",
                    )}
                  >
                    <span
                      className={cn(
                        "mt-0.5 flex h-7 w-7 items-center justify-center rounded-md",
                        isCurrent
                          ? "bg-brand-primary/15 text-brand-primary"
                          : isPrepared
                            ? "bg-success/15 text-success"
                            : "bg-[var(--surface-muted)] text-[var(--text-tertiary)]",
                      )}
                    >
                      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-medium text-[var(--text-primary)]">
                        {item.label}
                      </span>
                      <span
                        className={cn(
                          "mt-1 inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold uppercase tracking-[0.1em]",
                          isCurrent
                            ? "border-brand-primary/25 bg-brand-primary/10 text-brand-primary"
                            : isPrepared
                              ? "border-success/25 bg-success/10 text-success"
                              : "border-[var(--border-subtle)] bg-[var(--surface-muted)] text-[var(--text-tertiary)]",
                        )}
                      >
                        {stageState}
                      </span>
                      <span className="mt-0.5 block text-xs leading-5 text-[var(--text-secondary)]">
                        {item.copy}
                      </span>
                    </span>
                  </li>
                );
              })}
            </ol>
          </LaunchRailDisclosure>
        </div>
      </aside>
    </ResponsiveDisclosure>
  );
}

function CapacityCreditRecoveryCard({
  action,
  onRequestReportCredits,
  requestReportCreditsPending,
}: {
  action: CapacityCreditAction;
  onRequestReportCredits?: (
    requestedReports: number,
    source: CreditCapacityRequestSource,
  ) => void;
  requestReportCreditsPending: boolean;
}) {
  const launchPosture =
    action.tone === "blocked"
      ? "Start Analysis remains disabled until report-request capacity is available."
      : "Start Analysis remains available, but the next diligence run may require more capacity.";

  return (
    <section
      aria-label="Launch capacity recovery"
      className={cn(
        "rounded-md border px-3 py-3 shadow-[var(--shadow-xs)]",
        action.tone === "blocked"
          ? "border-warning/35 bg-warning/12"
          : "border-brand-primary/20 bg-brand-primary/10",
      )}
      data-testid="launch-copilot-brief"
    >
      <div
        className="flex flex-col gap-3 sm:flex-row sm:items-start"
        data-testid="capacity-credit-action"
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-brand-accent/25 bg-brand-accent/10 text-brand-accent sm:mt-0.5">
          <PackagePlus className="h-4 w-4" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
            {action.tone === "blocked" ? "Launch blocked" : "Capacity watch"}
          </p>
          <h2 className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
            {action.title}
          </h2>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            {action.body}
          </p>
          <p className="mt-2 text-xs font-semibold leading-5 text-[var(--text-primary)]">
            {launchPosture}
          </p>
          <p className="mt-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/74 px-2.5 py-1.5 text-xs leading-4 text-[var(--text-tertiary)]">
            Capacity is checked against included allowance plus purchased Report
            Credits.
          </p>
          {action.href ? (
            <Button
              asChild
              variant={action.tone === "blocked" ? "default" : "outline"}
              className="mt-3 min-h-11 w-full gap-2 sm:w-auto"
            >
              <Link href={action.href}>
                {action.cta}
                <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </Button>
          ) : action.request ? (
            <Button
              type="button"
              variant={action.tone === "blocked" ? "default" : "outline"}
              className="mt-3 min-h-11 w-full gap-2 sm:w-auto"
              disabled={requestReportCreditsPending || !onRequestReportCredits}
              onClick={() =>
                onRequestReportCredits?.(
                  action.request!.requestedReports,
                  action.request!.source,
                )
              }
            >
              {requestReportCreditsPending ? "Sending request…" : action.cta}
              <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
            </Button>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function LaunchCopilotBriefCard({ brief }: { brief: LaunchCopilotBrief }) {
  return (
    <section
      aria-label="AI launch brief"
      className={cn(
        "rounded-md border px-3 py-3 shadow-[var(--shadow-xs)]",
        brief.state === "ready"
          ? "border-brand-primary/20 bg-brand-primary/10"
          : brief.state === "attention"
            ? "border-warning/35 bg-warning/12"
            : "border-[var(--border-subtle)] bg-[var(--surface-glass)]",
      )}
      data-testid="launch-copilot-brief"
    >
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border",
            brief.state === "ready"
              ? "border-brand-primary/25 bg-brand-primary/12 text-brand-primary"
              : brief.state === "attention"
                ? "border-warning/30 bg-warning/12 text-warning"
                : "border-[var(--border-subtle)] bg-[var(--surface-muted)] text-[var(--text-tertiary)]",
          )}
        >
          <Sparkles className="h-4 w-4" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
            AI launch brief
          </p>
          <h2 className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
            {brief.title}
          </h2>
          <p className="mt-1 text-xs font-semibold leading-5 text-[var(--text-primary)]">
            {brief.action}
          </p>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            {brief.detail}
          </p>
          <p className="mt-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/74 px-2.5 py-1.5 text-xs leading-4 text-[var(--text-tertiary)]">
            {brief.evidence}
          </p>
        </div>
      </div>
    </section>
  );
}

function LaunchRailDisclosure({
  children,
  detail,
  title,
}: {
  children: ReactNode;
  detail: string;
  title: string;
}) {
  return (
    <details className="group rounded-md border border-[var(--border-subtle)] bg-[var(--surface-glass)] shadow-[var(--shadow-xs)]">
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 marker:hidden [&::-webkit-details-marker]:hidden">
        <span className="min-w-0">
          <span className="block text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
            {title}
          </span>
          <span className="mt-0.5 line-clamp-1 block text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
            {detail}
          </span>
        </span>
        <ChevronDown
          className="h-4 w-4 shrink-0 text-brand-primary transition-transform group-open:rotate-180"
          aria-hidden="true"
        />
      </summary>
      <div className="border-t border-[var(--border-subtle)] p-2">
        {children}
      </div>
    </details>
  );
}
