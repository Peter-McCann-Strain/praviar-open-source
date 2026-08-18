"use client";

import type { ComponentType } from "react";
import {
  AlertTriangle,
  Database,
  Globe2,
  Loader2,
  Save,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  CONFIG_MANAGER_ROLE_PHRASE,
  CONFIG_MANAGER_ROLE_SENTENCE,
} from "@/components/config/config-authority-copy";
import {
  getCoverageBudgetDetail,
  getCoverageBudgetLabel,
  PATENT_SOURCES,
  type ConfigStore,
} from "@/components/config/helpers";

interface ConfigStatusProps {
  config: ConfigStore;
  enabledSources: string[];
  validationIssues: string[];
  authenticated: boolean;
  saving: boolean;
  editing: boolean;
  resetPending: boolean;
  defaultsLoading: boolean;
  defaultsUnavailable: boolean;
  canManageDefaults?: boolean;
}

interface ConfigGovernanceRailProps {
  config: ConfigStore;
  saving: boolean;
  editing: boolean;
  resetPending: boolean;
  canManageDefaults?: boolean;
}

interface StatusMetricProps {
  label: string;
  value: string;
  detail: string;
  icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  tone?: "default" | "warning" | "destructive" | "success";
}

interface PolicyPostureInput {
  validationIssues: string[];
  authenticated: boolean;
  saving: boolean;
  editing: boolean;
  resetPending: boolean;
  defaultsLoading: boolean;
  defaultsUnavailable: boolean;
  canManageDefaults: boolean;
}

export const CONFIG_POLICY_STATUS_ID = "config-policy-posture-status";
export const CONFIG_POLICY_BLOCKERS_ID = "config-policy-posture-blockers";
export const CONFIG_RESET_WARNING_ID = "config-reset-warning";

function StatusMetric({
  label,
  value,
  detail,
  icon: Icon,
  tone = "default",
}: StatusMetricProps) {
  const toneClass =
    tone === "destructive"
      ? "border-error/25 bg-error/10 text-[var(--color-error-badge-fg)]"
      : tone === "warning"
        ? "border-warning/25 bg-warning/10 text-[var(--color-warning-badge-fg)]"
        : tone === "success"
          ? "border-success/25 bg-success/10 text-[var(--color-success-badge-fg)]"
          : "border-brand-primary/20 bg-brand-primary/10 text-brand-primary";

  return (
    <div className="flex min-w-0 items-start gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/65 p-3">
      <span
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md border ${toneClass}`}
      >
        <Icon aria-hidden={true} className="h-4 w-4" />
      </span>
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
          {label}
        </p>
        <p className="truncate text-sm font-semibold text-[var(--text-primary)]">
          {value}
        </p>
        <p className="mt-0.5 text-xs leading-5 text-[var(--text-secondary)]">
          {detail}
        </p>
      </div>
    </div>
  );
}

function getConfigPolicyPosture({
  validationIssues,
  authenticated,
  saving,
  editing,
  resetPending,
  defaultsLoading,
  defaultsUnavailable,
  canManageDefaults,
}: PolicyPostureInput) {
  if (defaultsLoading) {
    return {
      label: "Loading organization defaults",
      badge: "Loading",
      badgeVariant: "secondary" as const,
      detail:
        "Praviar is retrieving the saved organization policy before this workspace can change defaults.",
      blockers: ["Save is paused until current organization defaults load."],
      icon: Loader2,
      toneClass:
        "border-brand-primary/20 bg-brand-primary/10 text-brand-primary",
      animated: true,
    };
  }

  if (defaultsUnavailable) {
    return {
      label: "Defaults unavailable",
      badge: "Unavailable",
      badgeVariant: "destructive" as const,
      detail:
        "Existing defaults were not changed. Reload or sign in again before saving a new organization policy.",
      blockers: ["Organization defaults could not be loaded."],
      icon: AlertTriangle,
      toneClass: "border-error/25 bg-error/10 text-error",
      animated: false,
    };
  }

  if (!authenticated) {
    return {
      label: "Sign in required",
      badge: "Auth required",
      badgeVariant: "warning" as const,
      detail:
        "Use an authorized Praviar session before saving organization defaults.",
      blockers: ["Sign in to save organization defaults."],
      icon: AlertTriangle,
      toneClass: "border-warning/25 bg-warning/10 text-warning",
      animated: false,
    };
  }

  if (!canManageDefaults) {
    return {
      label: "Read-only organization defaults",
      badge: "View only",
      badgeVariant: "secondary" as const,
      detail: `You can inspect the active organization policy. ${CONFIG_MANAGER_ROLE_SENTENCE}`,
      blockers: [],
      icon: ShieldCheck,
      toneClass:
        "border-brand-primary/20 bg-brand-primary/10 text-brand-primary",
      animated: false,
    };
  }

  if (saving) {
    return {
      label: "Saving organization defaults",
      badge: "Saving",
      badgeVariant: "secondary" as const,
      detail:
        "Controls stay locked while Praviar writes the policy profile for future analyses.",
      blockers: [],
      icon: Loader2,
      toneClass:
        "border-brand-primary/20 bg-brand-primary/10 text-brand-primary",
      animated: true,
    };
  }

  if (resetPending) {
    return {
      label: "Reset armed",
      badge: "Confirm reset",
      badgeVariant: "warning" as const,
      detail:
        "Confirm reset only if you want to restore the default policy profile in this workspace.",
      blockers: ["Save is paused while reset confirmation is armed."],
      icon: AlertTriangle,
      toneClass: "border-warning/25 bg-warning/10 text-warning",
      animated: false,
    };
  }

  if (validationIssues.length > 0) {
    return {
      label: "Review required",
      badge: "Review",
      badgeVariant: "warning" as const,
      detail:
        "Resolve source, jurisdiction, or review-gate issues before saving organization defaults.",
      blockers: validationIssues,
      icon: AlertTriangle,
      toneClass: "border-warning/25 bg-warning/10 text-warning",
      animated: false,
    };
  }

  return {
    label: "Ready to save",
    badge: "Ready",
    badgeVariant: "success" as const,
    detail: editing
      ? "The draft policy is valid; saving updates defaults for future analyses only."
      : "Defaults are valid for future analyses; open edit mode to adjust the profile.",
    blockers: [],
    icon: ShieldCheck,
    toneClass: "border-success/25 bg-success/10 text-success",
    animated: false,
  };
}

export function ConfigStatusStrip({
  config,
  enabledSources,
  validationIssues,
  authenticated,
  saving,
  editing,
  resetPending,
  defaultsLoading,
  defaultsUnavailable,
  canManageDefaults = true,
}: ConfigStatusProps) {
  const hasReviewGateIssue =
    config.hitlEnabled && config.hitlCheckpoints.length === 0;
  const posture = getConfigPolicyPosture({
    validationIssues,
    authenticated,
    saving,
    editing,
    resetPending,
    defaultsLoading,
    defaultsUnavailable,
    canManageDefaults,
  });
  const PostureIcon = posture.icon;
  const hitlDetail = config.hitlEnabled
    ? `${config.hitlCheckpoints.length} review checkpoint${config.hitlCheckpoints.length === 1 ? "" : "s"}`
    : "No review pauses";

  return (
    <section
      aria-labelledby="config-policy-posture-heading"
      className="overflow-hidden rounded-lg border border-[var(--border-default)] bg-[color-mix(in_srgb,var(--brand-paper)_90%,var(--brand-soft-mint)_10%)] shadow-[var(--shadow-sm)]"
      data-config-policy-posture
    >
      <div className="grid gap-4 p-4 sm:p-5 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.35fr)]">
        <div className="flex min-w-0 items-start gap-3">
          <span
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border ${posture.toneClass}`}
          >
            <PostureIcon
              aria-hidden="true"
              className={`h-5 w-5 ${posture.animated ? "animate-spin motion-reduce:animate-none" : ""}`}
            />
          </span>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
              Organization defaults
            </p>
            <h2
              id="config-policy-posture-heading"
              className="mt-1 text-lg font-semibold text-[var(--text-primary)]"
            >
              Policy posture
            </h2>
            <div
              id={CONFIG_POLICY_STATUS_ID}
              role="status"
              aria-live="polite"
              aria-atomic="true"
              className="mt-3 flex flex-wrap items-center gap-2"
            >
              <Badge variant={posture.badgeVariant}>{posture.badge}</Badge>
              <span className="text-sm font-medium text-[var(--text-primary)]">
                {posture.label}
              </span>
            </div>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-secondary)]">
              {posture.detail}
            </p>
            {posture.blockers.length > 0 ? (
              <ul
                id={CONFIG_POLICY_BLOCKERS_ID}
                className="mt-3 space-y-1.5 text-sm leading-6 text-[var(--text-secondary)]"
              >
                {posture.blockers.map((issue) => (
                  <li key={issue} className="flex gap-2">
                    <AlertTriangle
                      aria-hidden="true"
                      className="mt-1 h-3.5 w-3.5 shrink-0 text-warning"
                    />
                    <span>{issue}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <StatusMetric
            label="Coverage"
            value={getCoverageBudgetLabel(config.searchMaxRankedResults)}
            detail={getCoverageBudgetDetail(config.searchMaxRankedResults)}
            icon={SlidersHorizontal}
          />
          <StatusMetric
            label="Sources"
            value={`${enabledSources.length} of ${PATENT_SOURCES.length} enabled`}
            detail={
              enabledSources.length > 0 ? "Ready for search" : "Save blocked"
            }
            icon={Database}
            tone={enabledSources.length > 0 ? "success" : "destructive"}
          />
          <StatusMetric
            label="Jurisdictions"
            value={`${config.searchJurisdictions.length} selected`}
            detail="Feeds saved search payload"
            icon={Globe2}
            tone={
              config.searchJurisdictions.length > 0 ? "success" : "destructive"
            }
          />
          <StatusMetric
            label="Review gates"
            value={hasReviewGateIssue ? "Needs attention" : hitlDetail}
            detail={
              config.hitlEnabled
                ? "Human checkpoints are explicit"
                : "No public mode switches"
            }
            icon={hasReviewGateIssue ? AlertTriangle : ShieldCheck}
            tone={hasReviewGateIssue ? "warning" : "success"}
          />
        </div>
      </div>
    </section>
  );
}

export function ConfigGovernanceRail({
  config,
  saving,
  editing,
  resetPending,
  canManageDefaults = true,
}: ConfigGovernanceRailProps) {
  const hitlSummary = config.hitlEnabled
    ? `${config.hitlCheckpoints.length} HITL checkpoint${config.hitlCheckpoints.length === 1 ? "" : "s"} configured`
    : "Human review pauses are off for these defaults";

  return (
    <aside
      aria-labelledby="config-governance-heading"
      className="space-y-4 lg:sticky lg:top-24 lg:self-start"
    >
      <Card className="overflow-hidden">
        <CardHeader className="border-b border-[var(--border-default)]">
          <CardTitle id="config-governance-heading" className="text-base">
            Governance
          </CardTitle>
          <p className="text-sm leading-5 text-[var(--text-secondary)]">
            {canManageDefaults
              ? "Defaults apply to new analyses after an authorized save."
              : CONFIG_MANAGER_ROLE_SENTENCE}
          </p>
        </CardHeader>
        <CardContent className="space-y-4 pt-6">
          <div className="grid gap-3">
            <div className="flex items-start gap-3">
              <Save
                aria-hidden="true"
                className="mt-0.5 h-4 w-4 text-brand-primary"
              />
              <div>
                <p className="text-sm font-medium text-[var(--text-primary)]">
                  {canManageDefaults
                    ? saving
                      ? "Saving organization defaults"
                      : "Local draft"
                    : "Read-only policy view"}
                </p>
                <p className="text-xs leading-5 text-[var(--text-secondary)]">
                  {canManageDefaults
                    ? editing
                      ? "Changes remain in the workspace until Save Defaults succeeds."
                      : "Open edit mode to prepare a new default policy."
                    : `Ask ${CONFIG_MANAGER_ROLE_PHRASE} to update these defaults or your role.`}
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <ShieldCheck
                aria-hidden="true"
                className="mt-0.5 h-4 w-4 text-brand-primary"
              />
              <div>
                <p className="text-sm font-medium text-[var(--text-primary)]">
                  Evidence gates stay adaptive
                </p>
                <p className="text-xs leading-5 text-[var(--text-secondary)]">
                  Public depth switches stay hidden; escalation remains
                  internal.
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <ShieldCheck
                aria-hidden="true"
                className="mt-0.5 h-4 w-4 text-brand-primary"
              />
              <div>
                <p className="text-sm font-medium text-[var(--text-primary)]">
                  Review policy is explicit
                </p>
                <p className="text-xs leading-5 text-[var(--text-secondary)]">
                  {hitlSummary}.
                </p>
              </div>
            </div>
          </div>

          {resetPending ? (
            <div
              id={CONFIG_RESET_WARNING_ID}
              className="rounded-lg border border-warning/25 bg-warning/10 p-3 text-xs leading-5 text-warning"
            >
              Reset is armed. Confirm only if you want to restore the default
              policy profile in this workspace.
            </div>
          ) : null}
        </CardContent>
      </Card>
    </aside>
  );
}
