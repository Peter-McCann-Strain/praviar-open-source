"use client";

import {
  ChevronDown,
  ClipboardCheck,
  FileSearch,
  Globe2,
  Landmark,
  PackageCheck,
  Route,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { formatScopeLabel } from "@/components/analysis-wizard/matter-scope-preflight";
import { ResponsiveDisclosure } from "@/components/shared/responsive-disclosure";
import {
  PRODUCT_CONTEXT_LABELS,
  getProductContextEntries,
  getProductContextGaps,
  productContextPayloadToValue,
} from "@/lib/product-context";
import type { AnalysisListItem } from "@/types/api";
import type {
  AssetTypeHint,
  DevelopmentStage,
  IntendedAction,
  MatterScopePreflightValue,
} from "@/types/pipeline";
import { cn } from "@/lib/utils";

interface AnalysisLaunchContextCardProps {
  analysis: AnalysisListItem;
}

interface ContextStat {
  detail: string;
  icon: LucideIcon;
  label: string;
  tone?: "ready" | "attention" | "neutral";
  value: string;
}

const ASSET_TYPES: readonly AssetTypeHint[] = [
  "small_molecule",
  "markush_candidate",
  "biologic_or_sequence",
  "formulation",
  "process_or_synthesis",
  "combination",
  "unknown",
];

const DEVELOPMENT_STAGES: readonly DevelopmentStage[] = [
  "discovery",
  "lead_optimization",
  "preclinical",
  "clinical",
  "commercial",
];

const INTENDED_ACTIONS: readonly IntendedAction[] = [
  "manufacture_import",
  "commercial_launch",
  "formulation_review",
  "method_of_use_review",
  "design_around",
  "diligence_screen",
  "monitor_continuations",
];

function asAssetType(value: string | null | undefined): AssetTypeHint {
  return ASSET_TYPES.includes(value as AssetTypeHint)
    ? (value as AssetTypeHint)
    : "unknown";
}

function asDevelopmentStage(
  value: string | null | undefined,
): DevelopmentStage {
  return DEVELOPMENT_STAGES.includes(value as DevelopmentStage)
    ? (value as DevelopmentStage)
    : "discovery";
}

function asIntendedActions(values: readonly string[]): IntendedAction[] {
  return values.filter((value): value is IntendedAction =>
    INTENDED_ACTIONS.includes(value as IntendedAction),
  );
}

function formatTextList(values: readonly string[], emptyLabel: string) {
  return values.length > 0 ? values.join(", ") : emptyLabel;
}

function statToneClass(tone: ContextStat["tone"]) {
  if (tone === "ready") {
    return "border-success/25 bg-success/10 text-success";
  }
  if (tone === "attention") {
    return "border-warning/30 bg-warning/10 text-warning";
  }
  return "border-brand-primary/20 bg-brand-primary/10 text-brand-primary";
}

function buildMatterScope(
  analysis: AnalysisListItem,
): MatterScopePreflightValue {
  const launchContext = analysis.launch_context;
  const actions = asIntendedActions(launchContext?.intended_actions ?? []);

  return {
    assetTypeHint: asAssetType(launchContext?.asset_type_hint),
    developmentStage: asDevelopmentStage(launchContext?.development_stage),
    intendedActions: actions.length > 0 ? actions : ["diligence_screen"],
  };
}

export function AnalysisLaunchContextCard({
  analysis,
}: AnalysisLaunchContextCardProps) {
  const launchContext = analysis.launch_context;
  const hasLaunchContext = Boolean(launchContext);
  const matterScope = buildMatterScope(analysis);
  const productContext = productContextPayloadToValue(
    launchContext?.product_context,
  );
  const productEntries = getProductContextEntries(productContext);
  const knownPatentsOrAssignees = productContext.knownPatentsOrAssignees ?? [];
  const openGaps = hasLaunchContext
    ? getProductContextGaps({ context: productContext, matterScope })
    : [];
  const openGapLabels = openGaps.map((gap) => PRODUCT_CONTEXT_LABELS[gap]);
  const actionLabels = matterScope.intendedActions.map(formatScopeLabel);
  const targetJurisdictions = launchContext?.target_jurisdictions ?? [];

  if (!hasLaunchContext) {
    return null;
  }

  const stats: ContextStat[] = [
    {
      detail: "Launch-time matter class carried from intake.",
      icon: PackageCheck,
      label: "Product profile",
      tone: productEntries.length > 0 ? "ready" : "attention",
      value:
        productEntries.length > 0
          ? `${productEntries.length} product fact${
              productEntries.length === 1 ? "" : "s"
            }`
          : "No product facts",
    },
    {
      detail: "Evidence routing assumptions used by the adaptive run.",
      icon: ShieldCheck,
      label: "Evidence assumptions",
      tone: "neutral",
      value: `${formatScopeLabel(matterScope.assetTypeHint)}; ${formatScopeLabel(
        matterScope.developmentStage,
      )}`,
    },
    {
      detail: "Commercial lanes captured at launch.",
      icon: Globe2,
      label: "Target lanes",
      tone: targetJurisdictions.length > 0 ? "ready" : "neutral",
      value: formatTextList(targetJurisdictions, "Policy default"),
    },
    {
      detail: "Missing facts stay visible for reviewers.",
      icon: FileSearch,
      label: "Open context",
      tone: openGapLabels.length > 0 ? "attention" : "ready",
      value:
        openGapLabels.length > 0
          ? `${openGapLabels.length} gap${openGapLabels.length === 1 ? "" : "s"}`
          : "Core facts present",
    },
  ];

  return (
    <section
      aria-label="Launch context"
      className="overflow-hidden rounded-lg border border-brand-primary/15 bg-[var(--surface-card)] shadow-[var(--shadow-sm)]"
    >
      <ResponsiveDisclosure
        className="group"
        summary={
          <summary
            className="min-h-11 cursor-pointer list-none p-4 text-left sm:hidden [&::-webkit-details-marker]:hidden"
            data-testid="launch-context-mobile-summary"
          >
            <span className="flex items-start justify-between gap-3">
              <span className="min-w-0">
                <span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                  Launch context
                </span>
                <span className="mt-1 block text-sm font-semibold text-[var(--text-primary)]">
                  Review launch assumptions
                </span>
              </span>
              <ChevronDown
                className="mt-1 h-4 w-4 shrink-0 text-brand-primary transition-transform group-open:rotate-180"
                aria-hidden="true"
              />
            </span>
            <span className="mt-3 grid grid-cols-2 gap-2">
              {stats.map((stat) => (
                <span
                  key={stat.label}
                  className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-2.5 py-2"
                >
                  <span className="block text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-tertiary)]">
                    {stat.label}
                  </span>
                  <span className="mt-0.5 block truncate text-xs font-semibold text-[var(--text-primary)]">
                    {stat.value}
                  </span>
                </span>
              ))}
            </span>
          </summary>
        }
      >
        <div className="border-b border-[var(--border-subtle)] bg-[var(--surface-glass)] p-4 sm:p-5">
          <div className="flex min-w-0 flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                Launch context
              </p>
              <h2 className="mt-1 flex items-center gap-2 text-base font-semibold text-[var(--text-primary)]">
                <ClipboardCheck
                  className="h-4 w-4 text-brand-primary"
                  aria-hidden="true"
                />
                Product and evidence assumptions
              </h2>
              <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
                These launch-time facts stay attached to the analysis so
                reviewers can see what Praviar assumed about product form, use,
                process, and commercial intent.
              </p>
            </div>
            <span className="inline-flex w-fit items-center gap-2 rounded-md border border-brand-primary/20 bg-brand-primary/10 px-2.5 py-1 text-xs font-semibold text-brand-primary">
              <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
              Report Credit used
            </span>
          </div>
        </div>

        <div className="grid gap-3 p-4 md:grid-cols-2 xl:grid-cols-4 sm:p-5">
          {stats.map((stat) => {
            const Icon = stat.icon;

            return (
              <div
                key={stat.label}
                className="grid min-w-0 grid-cols-[2rem_minmax(0,1fr)] gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-3 py-2"
              >
                <span
                  className={cn(
                    "flex h-8 w-8 items-center justify-center rounded-md border",
                    statToneClass(stat.tone),
                  )}
                  aria-hidden="true"
                >
                  <Icon className="h-4 w-4" />
                </span>
                <span className="min-w-0">
                  <span className="block text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                    {stat.label}
                  </span>
                  <span className="mt-0.5 block text-sm font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
                    {stat.value}
                  </span>
                  <span className="mt-0.5 block text-xs leading-4 text-[var(--text-secondary)]">
                    {stat.detail}
                  </span>
                </span>
              </div>
            );
          })}
        </div>

        <div className="grid gap-4 border-t border-[var(--border-subtle)] p-4 lg:grid-cols-[minmax(0,1fr)_minmax(16rem,0.42fr)] sm:p-5">
          <div className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-subtle)] p-3">
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
              <PackageCheck className="h-3.5 w-3.5" aria-hidden="true" />
              Product profile
            </div>
            {productEntries.length > 0 ? (
              <div className="grid gap-2 md:grid-cols-2">
                {productEntries.slice(0, 10).map((entry) => (
                  <div
                    key={entry.key}
                    className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 py-2"
                  >
                    <p className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-tertiary)]">
                      {entry.label}
                    </p>
                    <p className="mt-1 text-sm font-medium text-[var(--text-primary)] [overflow-wrap:anywhere]">
                      {entry.value}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm leading-6 text-[var(--text-secondary)]">
                No product-specific facts were supplied at launch. Treat
                formulation, use, process, and territory assumptions as open
                until the report record resolves them.
              </p>
            )}
          </div>

          <div className="space-y-3 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-subtle)] p-3">
            <div className="flex items-start gap-2">
              <Route
                className="mt-0.5 h-4 w-4 shrink-0 text-brand-primary"
                aria-hidden="true"
              />
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                  Evidence assumptions
                </p>
                <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                  {formatTextList(actionLabels, "Diligence Screen")} in{" "}
                  {formatTextList(targetJurisdictions, "policy default lanes")}.
                </p>
              </div>
            </div>
            <div className="flex items-start gap-2">
              <PackageCheck
                className="mt-0.5 h-4 w-4 shrink-0 text-brand-primary"
                aria-hidden="true"
              />
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                  Matter type
                </p>
                <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                  {formatScopeLabel(launchContext?.matter_type ?? "unknown")}{" "}
                  run from {formatScopeLabel(matterScope.assetTypeHint)} intake.
                </p>
              </div>
            </div>
            <div
              className={cn(
                "rounded-md border px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]",
                openGapLabels.length > 0
                  ? "border-warning/25 bg-warning/10"
                  : "border-success/25 bg-success/10",
              )}
            >
              <span
                className={cn(
                  "font-semibold",
                  openGapLabels.length > 0 ? "text-warning" : "text-success",
                )}
              >
                {openGapLabels.length > 0 ? "Open context:" : "Context ready:"}
              </span>{" "}
              {openGapLabels.length > 0
                ? openGapLabels.join(", ")
                : "Core product assumptions are present."}
            </div>
            {knownPatentsOrAssignees.length > 0 ? (
              <div className="rounded-md border border-brand-primary/15 bg-brand-primary/8 px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]">
                <span className="inline-flex items-center gap-1 font-semibold text-brand-primary">
                  <Landmark className="h-3.5 w-3.5" aria-hidden="true" />
                  Known art:
                </span>{" "}
                {knownPatentsOrAssignees.join(", ")}
              </div>
            ) : null}
          </div>
        </div>
      </ResponsiveDisclosure>
    </section>
  );
}
