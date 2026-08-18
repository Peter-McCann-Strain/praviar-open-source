"use client";

import {
  Atom,
  ChevronLeft,
  FileCheck2,
  Globe2,
  Loader2,
  PackageCheck,
  type LucideIcon,
  Rocket,
  SearchCheck,
  ShieldCheck,
} from "lucide-react";
import { getCompoundInputReadiness } from "@/components/chemistry/smiles-input";
import { MoleculeViewer2D } from "@/components/chemistry/molecule-viewer-2d";
import { formatScopeLabel } from "@/components/analysis-wizard/matter-scope-preflight";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getEnabledSources } from "@/components/config/helpers";
import {
  formatJurisdictionList,
  getLaunchReadyJurisdictions,
  getRuntimeSearchJurisdictions,
  getStagedJurisdictions,
} from "@/lib/jurisdiction-bundles";
import {
  PRODUCT_CONTEXT_LABELS,
  getProductContextEntries,
  getProductContextGaps,
  getProductContextLaunchBlocker,
  getProductContextLaunchGaps,
} from "@/lib/product-context";
import type { ConfigState } from "@/stores/config-store";
import type {
  MatterScopePreflightValue,
  ProductContextValue,
} from "@/types/pipeline";
import { cn } from "@/lib/utils";

interface ReviewLaunchStepProps {
  compoundInput: string;
  inputType: string | null;
  config: ConfigState;
  matterScope: MatterScopePreflightValue;
  productContext?: ProductContextValue;
  launchCapacity: LaunchCapacitySummary;
  isLaunching: boolean;
  canLaunch: boolean;
  launchBlocker?: string | null;
  launchError: string | null;
  launchErrorAction?: {
    href?: string;
    label: string;
    onClick?: () => void;
    pending?: boolean;
  } | null;
  onBack: () => void;
  onLaunch: () => void;
}

interface ReviewRowProps {
  label: string;
  value: string;
  valueClassName?: string;
}

type PreflightTone = "ready" | "attention" | "neutral";

export interface LaunchCapacitySummary {
  additionalCapacityRemaining?: number | null;
  creditBackedRemaining: number | null;
  includedRemaining: number | null;
  isAccessRestricted?: boolean;
  isEnterprise: boolean;
  isLoading: boolean;
  purchasedCredits: number | null;
  totalRemaining: number | null;
}

interface PreflightItem {
  detail: string;
  icon: LucideIcon;
  label: string;
  tone: PreflightTone;
  value: string;
}

function ReviewRow({ label, value, valueClassName }: ReviewRowProps) {
  return (
    <div className="grid gap-1 sm:grid-cols-[minmax(0,10rem)_minmax(0,1fr)] sm:gap-3">
      <span className="text-sm text-[var(--text-secondary)]">{label}</span>
      <span
        className={cn(
          "min-w-0 break-words text-sm text-[var(--text-primary)] sm:text-right",
          valueClassName,
        )}
      >
        {value}
      </span>
    </div>
  );
}

function preflightToneClass(tone: PreflightTone): string {
  if (tone === "ready") {
    return "border-success/25 bg-success/10 text-success";
  }
  if (tone === "attention") {
    return "border-warning/30 bg-warning/10 text-warning";
  }
  return "border-brand-primary/20 bg-brand-primary/10 text-brand-primary";
}

function PreflightBrief({ items }: { items: PreflightItem[] }) {
  return (
    <section
      aria-label="Launch review brief"
      className="rounded-lg border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-elevated)_86%,transparent)] p-3 shadow-[var(--shadow-xs)] sm:p-4"
    >
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
            Launch review brief
          </p>
          <h3 className="mt-1 text-base font-semibold text-[var(--text-primary)]">
            Readiness contract
          </h3>
        </div>
        <span className="inline-flex w-fit items-center gap-2 rounded-md border border-brand-primary/20 bg-brand-primary/10 px-2.5 py-1 text-xs font-medium text-brand-primary">
          <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
          Draft report request
        </span>
      </div>
      <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        {items.map((item) => {
          const Icon = item.icon;

          return (
            <div
              key={item.label}
              className="grid min-w-0 grid-cols-[2rem_minmax(0,1fr)] gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 py-2"
            >
              <span
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md border ${preflightToneClass(
                  item.tone,
                )}`}
                aria-hidden="true"
              >
                <Icon className="h-4 w-4" />
              </span>
              <span className="min-w-0">
                <span className="block text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                  {item.label}
                </span>
                <span className="mt-0.5 block text-sm font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
                  {item.value}
                </span>
                <span className="mt-0.5 block text-xs leading-4 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                  {item.detail}
                </span>
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function formatCredits(value: number) {
  return `${value.toLocaleString()} Report Credit${value === 1 ? "" : "s"}`;
}

function formatAdditionalCapacity(value: number) {
  return `${value.toLocaleString()} additional workspace report request${
    value === 1 ? "" : "s"
  }`;
}

function LaunchAssuranceStrip({
  capacity,
  canLaunch,
}: {
  capacity: LaunchCapacitySummary;
  canLaunch: boolean;
}) {
  const knownCapacity =
    !capacity.isAccessRestricted &&
    !capacity.isEnterprise &&
    capacity.totalRemaining != null &&
    capacity.includedRemaining != null &&
    capacity.creditBackedRemaining != null &&
    capacity.purchasedCredits != null
      ? {
          creditBackedRemaining: capacity.creditBackedRemaining,
          additionalCapacityRemaining:
            capacity.additionalCapacityRemaining ?? 0,
          includedRemaining: capacity.includedRemaining,
          purchasedCredits: capacity.purchasedCredits,
          totalRemaining: capacity.totalRemaining,
        }
      : null;
  const hasKnownCapacity = knownCapacity != null;
  const capacityTone =
    capacity.isEnterprise || (!capacity.isAccessRestricted && canLaunch)
      ? "ready"
      : "attention";
  const capacityLabel = capacity.isEnterprise
    ? "Enterprise capacity"
    : capacity.isAccessRestricted
      ? "Access restricted"
      : capacity.isLoading || !hasKnownCapacity
        ? "Capacity check pending"
        : `${formatCredits(knownCapacity.totalRemaining)} available`;
  const capacityDetail = capacity.isEnterprise
    ? "Report request capacity is governed by the contracted enterprise allowance."
    : capacity.isAccessRestricted
      ? "Report Credit capacity is hidden until billing access is restored."
      : hasKnownCapacity
        ? `${formatCredits(knownCapacity.includedRemaining)} included, ${formatCredits(
            knownCapacity.creditBackedRemaining,
          )} credit-backed remaining${
            knownCapacity.additionalCapacityRemaining > 0
              ? `, ${formatAdditionalCapacity(
                  knownCapacity.additionalCapacityRemaining,
                )}`
              : ""
          }, ${formatCredits(
            knownCapacity.purchasedCredits,
          )} unused purchased. Included allowance is consumed first.`
        : "Praviar confirms included allowance plus purchased Report Credits before enabling submission.";

  return (
    <section
      aria-label="Launch capacity and trust boundary"
      className="grid gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-glass)] p-3 shadow-[var(--shadow-xs)] md:grid-cols-[minmax(0,0.72fr)_minmax(0,1fr)]"
      data-testid="launch-capacity-assurance"
    >
      <div
        className={cn(
          "rounded-md border px-3 py-2",
          capacityTone === "ready"
            ? "border-success/25 bg-success/10"
            : "border-warning/30 bg-warning/10",
        )}
      >
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
          Report Credit capacity
        </p>
        <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
          {capacityLabel}
        </p>
        <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
          {capacityDetail}
        </p>
      </div>
      <div className="rounded-md border border-brand-primary/20 bg-brand-primary/8 px-3 py-2">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
          Launch boundary
        </p>
        <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
          First-pass FTO report request
        </p>
        <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
          Start Analysis consumes launch capacity for a source-linked first-pass
          workflow. Identifier resolution is checked before patent claim search,
          and unresolved compounds stop for correction rather than becoming a
          legal clearance opinion.
        </p>
      </div>
    </section>
  );
}

interface ChipListProps {
  items: readonly string[];
  emptyLabel: string;
}

function ChipList({ items, emptyLabel }: ChipListProps) {
  if (items.length === 0) {
    return (
      <span className="text-sm text-[var(--text-secondary)]">{emptyLabel}</span>
    );
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <span
          key={item}
          className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-card)] px-2 py-1 text-xs font-medium text-[var(--text-secondary)]"
        >
          {item}
        </span>
      ))}
    </div>
  );
}

export function ReviewLaunchStep({
  compoundInput,
  inputType,
  config,
  matterScope,
  productContext,
  launchCapacity,
  isLaunching,
  canLaunch,
  launchBlocker = null,
  launchError,
  launchErrorAction = null,
  onBack,
  onLaunch,
}: ReviewLaunchStepProps) {
  const compoundReadiness = getCompoundInputReadiness(compoundInput);
  const enabledSources = getEnabledSources(config);
  const launchReadyJurisdictions = getLaunchReadyJurisdictions(
    config.targetJurisdictions,
  );
  const stagedJurisdictions = getStagedJurisdictions(
    config.targetJurisdictions,
  );
  const runtimeSearchJurisdictions = getRuntimeSearchJurisdictions({
    jurisdictionBundle: config.jurisdictionBundle,
    searchJurisdictions: config.searchJurisdictions,
    targetJurisdictions: config.targetJurisdictions,
  });
  const reviewGateLabel =
    config.hitlEnabled && config.hitlCheckpoints.length > 0
      ? `Identity approval, then ${config.hitlCheckpoints
          .join(", ")
          .replace(/_/g, " ")}`
      : "Resolved identity approval before search";
  const sourceCountLabel =
    enabledSources.length > 0
      ? `${enabledSources.length.toLocaleString()} source${
          enabledSources.length === 1 ? "" : "s"
        } selected`
      : "No patent sources selected";
  const sourceDetailLabel =
    enabledSources.length > 0
      ? enabledSources.join(", ")
      : "No patent sources enabled";
  const searchLaneLabel =
    runtimeSearchJurisdictions.length > 0
      ? `${runtimeSearchJurisdictions.length.toLocaleString()} search lane${
          runtimeSearchJurisdictions.length === 1 ? "" : "s"
        }`
      : "No search lanes selected";
  const intendedActionLabels =
    matterScope.intendedActions.length > 0
      ? matterScope.intendedActions.map(formatScopeLabel)
      : ["Diligence Screen"];
  const productContextEntries = getProductContextEntries(productContext);
  const productContextGaps = getProductContextGaps({
    context: productContext,
    matterScope,
  });
  const productContextLaunchBlocker = getProductContextLaunchBlocker({
    context: productContext,
    matterScope,
  });
  const productContextLaunchGaps = getProductContextLaunchGaps({
    context: productContext,
    matterScope,
  });
  const productContextGapLabels = productContextGaps.map(
    (field) => PRODUCT_CONTEXT_LABELS[field],
  );
  const effectiveCanLaunch = canLaunch && !productContextLaunchBlocker;
  const effectiveLaunchBlocker = launchBlocker ?? productContextLaunchBlocker;
  const preflightItems: PreflightItem[] = [
    {
      detail: `${formatScopeLabel(
        matterScope.assetTypeHint,
      )}; ${formatScopeLabel(
        matterScope.developmentStage,
      )}; ${intendedActionLabels.join(", ")} confirmed for evidence routing.`,
      icon: Atom,
      label: "Matter identity",
      tone: "neutral",
      value: compoundInput.trim() || "Identity pending",
    },
    {
      detail:
        "The launch creates a first-pass FTO report request, not a legal clearance opinion.",
      icon: ShieldCheck,
      label: "Trust boundary",
      tone: "neutral",
      value: reviewGateLabel,
    },
    {
      detail:
        productContextGapLabels.length === 0
          ? "Core product facts are captured for this matter type."
          : productContextLaunchBlocker
            ? "Core launch facts are required or explicitly marked unknown before submission."
            : `Open context: ${productContextGapLabels.slice(0, 3).join(", ")}${
                productContextGapLabels.length > 3 ? "..." : ""
              }.`,
      icon: PackageCheck,
      label: "Product context",
      tone: productContextLaunchBlocker
        ? "attention"
        : productContextGapLabels.length === 0
          ? "ready"
          : productContextEntries.length > 0
            ? "neutral"
            : "attention",
      value:
        productContextEntries.length > 0
          ? `${productContextEntries.length} fact${
              productContextEntries.length === 1 ? "" : "s"
            } captured`
          : "No product facts supplied",
    },
    {
      detail:
        enabledSources.length > 0
          ? `${formatJurisdictionList(runtimeSearchJurisdictions)} will seed the runtime search scope.`
          : "Enable at least one source before launch.",
      icon: SearchCheck,
      label: "Evidence path",
      tone:
        enabledSources.length > 0 && runtimeSearchJurisdictions.length > 0
          ? "ready"
          : "attention",
      value: `${sourceCountLabel}; ${searchLaneLabel}`,
    },
    {
      detail:
        effectiveLaunchBlocker ??
        "Capacity, policy, and configuration checks are clear for this launch.",
      icon: FileCheck2,
      label: "Launch decision",
      tone: effectiveCanLaunch ? "ready" : "attention",
      value: effectiveCanLaunch ? "Ready to submit" : "Action required",
    },
  ];

  return (
    <Card
      className="overflow-hidden border-brand-primary/15"
      aria-busy={isLaunching}
    >
      <div className="h-1 bg-gradient-to-r from-brand-primary via-brand-primary/30 to-transparent" />
      <CardHeader className="border-b border-[var(--border-subtle)] bg-[var(--surface-glass)] p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              Launch packet
            </p>
            <CardTitle
              aria-level={2}
              className="mt-1 flex items-center gap-2 text-base"
            >
              <Rocket className="h-5 w-5 text-brand-primary" />
              Confirm & Launch
            </CardTitle>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-[var(--text-secondary)]">
              Confirm readiness, scope, capacity, and handoff before Praviar
              opens the adaptive evidence path.
            </p>
          </div>
          <span className="inline-flex w-fit items-center gap-2 rounded-md border border-brand-primary/25 bg-brand-primary/10 px-2.5 py-1 text-xs font-medium text-brand-primary">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
            Human-review evidence packet
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {!effectiveCanLaunch ? (
          <div
            className="rounded-lg border border-info/25 bg-info/10 p-3 text-sm text-info"
            role="status"
            aria-live="polite"
          >
            {effectiveLaunchBlocker ??
              "Preparing secure session before launch controls are enabled."}
          </div>
        ) : null}
        {isLaunching ? (
          <div
            className="rounded-lg border border-brand-primary/25 bg-brand-primary/10 p-3 text-sm text-brand-primary"
            role="status"
            aria-live="polite"
          >
            Starting analysis and opening the evidence run.
          </div>
        ) : null}
        {launchError ? (
          <div
            className="rounded-lg border border-error/25 bg-error/10 p-3 text-sm text-error"
            role="alert"
          >
            <p>{launchError}</p>
            {launchErrorAction ? (
              launchErrorAction.href ? (
                <Button
                  asChild
                  variant="outline"
                  className="mt-3 min-h-11 border-error/30 bg-[var(--surface-card)] text-error hover:bg-error/12 hover:text-error"
                >
                  <a href={launchErrorAction.href}>{launchErrorAction.label}</a>
                </Button>
              ) : (
                <Button
                  type="button"
                  variant="outline"
                  className="mt-3 min-h-11 border-error/30 bg-[var(--surface-card)] text-error hover:bg-error/12 hover:text-error"
                  disabled={launchErrorAction.pending}
                  onClick={launchErrorAction.onClick}
                >
                  {launchErrorAction.pending
                    ? "Sending request…"
                    : launchErrorAction.label}
                </Button>
              )
            ) : null}
          </div>
        ) : null}
        <PreflightBrief items={preflightItems} />
        <div className="grid gap-5 xl:grid-cols-[minmax(0,0.42fr)_minmax(0,1fr)]">
          {inputType === "SMILES" ? (
            <MoleculeViewer2D
              smiles={compoundInput}
              width={280}
              height={210}
              className="w-full"
            />
          ) : null}
          {inputType === "InChI" ? (
            <div className="rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)] p-4 text-sm text-[var(--text-secondary)]">
              Structure preview will appear after InChI resolution.
            </div>
          ) : null}
          {inputType !== "SMILES" && inputType !== "InChI" ? (
            <div className="rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)] p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
                <Atom className="h-4 w-4 text-brand-primary" />
                Structure resolution
              </div>
              <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                Identifier accepted. Canonical structure is checked before
                patent claim search.
              </p>
            </div>
          ) : null}

          <div className="space-y-4 rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)] p-4">
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-card)] p-3">
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                <FileCheck2 className="h-3.5 w-3.5" aria-hidden="true" />
                Matter
              </div>
              <ReviewRow
                label="Compound"
                value={compoundInput}
                valueClassName="font-mono break-all"
              />
              <ReviewRow
                label="Input Type"
                value={inputType || "Auto-detect"}
                valueClassName="text-brand-primary"
              />
              <ReviewRow
                label="Identifier status"
                value={compoundReadiness.detail}
              />
              <ReviewRow
                label="Asset type"
                value={formatScopeLabel(matterScope.assetTypeHint)}
              />
              <ReviewRow
                label="Development stage"
                value={formatScopeLabel(matterScope.developmentStage)}
              />
              <div className="grid gap-1 sm:grid-cols-[minmax(0,10rem)_minmax(0,1fr)] sm:gap-3">
                <span className="text-sm text-[var(--text-secondary)]">
                  Intended actions
                </span>
                <div className="sm:justify-self-end">
                  <ChipList
                    items={intendedActionLabels}
                    emptyLabel="Diligence screen"
                  />
                </div>
              </div>
            </div>

            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-card)] p-3">
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                <PackageCheck className="h-3.5 w-3.5" aria-hidden="true" />
                Product profile
              </div>
              {productContextEntries.length > 0 ? (
                <div className="space-y-2">
                  {productContextEntries.map((entry) => (
                    <ReviewRow
                      key={entry.key}
                      label={entry.label}
                      value={entry.value}
                    />
                  ))}
                </div>
              ) : (
                <p className="text-sm leading-6 text-[var(--text-secondary)]">
                  {productContextLaunchBlocker
                    ? "No product-specific facts supplied. Core product context must be supplied or explicitly marked unknown before this launch scope can start."
                    : "No product-specific facts supplied. Praviar will run a compound-first diligence screen with open formulation, use, and process assumptions."}
                </p>
              )}
              {productContextLaunchBlocker ? (
                <div className="mt-3 rounded-md border border-error/25 bg-error/10 px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]">
                  <span className="font-semibold text-error">
                    Launch blocked:
                  </span>{" "}
                  {productContextLaunchGaps
                    .map((field) => PRODUCT_CONTEXT_LABELS[field])
                    .join(", ")}
                  . Enter facts or &quot;Unknown&quot; before submission.
                </div>
              ) : productContextGapLabels.length > 0 ? (
                <div className="mt-3 rounded-md border border-warning/25 bg-warning/10 px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]">
                  <span className="font-semibold text-warning">
                    Open context:
                  </span>{" "}
                  {productContextGapLabels.join(", ")}. Launch remains available
                  when these facts are not yet known.
                </div>
              ) : null}
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div
                className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-card)] p-3"
                data-testid="review-launch-source-card"
              >
                <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                  <SearchCheck className="h-3.5 w-3.5" aria-hidden="true" />
                  Sources
                </div>
                <p className="mb-2 text-sm leading-6 text-[var(--text-primary)] [overflow-wrap:anywhere]">
                  {sourceDetailLabel}
                </p>
                <ChipList
                  items={enabledSources}
                  emptyLabel="No patent sources enabled"
                />
              </div>
              <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-card)] p-3">
                <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                  <Globe2 className="h-3.5 w-3.5" aria-hidden="true" />
                  Target lanes
                </div>
                <ChipList
                  items={config.targetJurisdictions}
                  emptyLabel="Policy default"
                />
              </div>
            </div>

            <div className="space-y-3 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-card)] p-3">
              <ReviewRow
                label="Evidence Plan"
                value="Adaptive evidence execution"
                valueClassName="font-medium text-brand-primary"
              />
              <ReviewRow
                label="Evidence Scope"
                value="Calibrated internally from compound risk, source coverage, and confidence gates"
              />
              <ReviewRow
                label="Launch-ready lanes"
                value={formatJurisdictionList(
                  launchReadyJurisdictions,
                  "No launch-ready lanes",
                )}
              />
              {stagedJurisdictions.length > 0 ? (
                <ReviewRow
                  label="Staged lanes"
                  value={formatJurisdictionList(stagedJurisdictions)}
                />
              ) : null}
              <ReviewRow
                label="Runtime search scope"
                value={formatJurisdictionList(runtimeSearchJurisdictions)}
              />
              <ReviewRow
                label="Citation Expansion"
                value={
                  config.citationTraversalEnabled
                    ? "Adaptive citation expansion enabled"
                    : "Captured only when evidence gates require it"
                }
              />
              <ReviewRow label="Review Gates" value={reviewGateLabel} />
            </div>
          </div>
        </div>

        <LaunchAssuranceStrip
          capacity={launchCapacity}
          canLaunch={effectiveCanLaunch}
        />

        <div className="flex flex-col justify-between gap-3 sm:flex-row">
          <Button
            variant="outline"
            onClick={onBack}
            className="min-h-11 w-full gap-2 sm:w-auto"
          >
            <ChevronLeft className="h-4 w-4" />
            Back
          </Button>
          <Button
            onClick={onLaunch}
            size="lg"
            className="w-full gap-2 sm:w-auto"
            disabled={isLaunching || !effectiveCanLaunch}
          >
            {isLaunching ? (
              <Loader2 className="h-5 w-5 animate-spin motion-reduce:animate-none" />
            ) : (
              <Rocket className="h-5 w-5" />
            )}
            {isLaunching ? "Starting..." : "Start Analysis"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
