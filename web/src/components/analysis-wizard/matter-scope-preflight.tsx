"use client";

import type { KeyboardEvent } from "react";
import {
  Atom,
  GitBranch,
  Layers3,
  Lightbulb,
  ListChecks,
  Microscope,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type {
  AssetTypeHint,
  DevelopmentStage,
  IntendedAction,
  MatterScopePreflightValue,
} from "@/types/pipeline";

interface MatterScopePreflightProps {
  className?: string;
  compoundInput: string;
  inputType: string | null;
  onChange: (value: MatterScopePreflightValue) => void;
  value: MatterScopePreflightValue;
}

const ASSET_OPTIONS: Array<{
  detail: string;
  icon: LucideIcon;
  label: string;
  value: AssetTypeHint;
}> = [
  {
    detail: "Compound, salt, polymorph, or chemical entity.",
    icon: Atom,
    label: "Small molecule",
    value: "small_molecule",
  },
  {
    detail: "Generic claim space around candidate families.",
    icon: GitBranch,
    label: "Markush candidate",
    value: "markush_candidate",
  },
  {
    detail: "Antibody, peptide, nucleic acid, or sequence asset.",
    icon: Microscope,
    label: "Biologic/sequence",
    value: "biologic_or_sequence",
  },
  {
    detail: "Composition, excipient, dosage, or delivery review.",
    icon: Layers3,
    label: "Formulation",
    value: "formulation",
  },
  {
    detail: "Manufacturing route, intermediate, or process claim.",
    icon: ListChecks,
    label: "Process/synthesis",
    value: "process_or_synthesis",
  },
  {
    detail: "Combination therapy, kit, or multi-asset matter.",
    icon: ShieldCheck,
    label: "Combination",
    value: "combination",
  },
];

const STAGE_OPTIONS: Array<{ label: string; value: DevelopmentStage }> = [
  { label: "Discovery", value: "discovery" },
  { label: "Lead optimization", value: "lead_optimization" },
  { label: "Preclinical", value: "preclinical" },
  { label: "Clinical", value: "clinical" },
  { label: "Commercial", value: "commercial" },
];

const ACTION_OPTIONS: Array<{
  detail: string;
  label: string;
  value: IntendedAction;
}> = [
  {
    detail: "Freedom to make, import, or supply.",
    label: "Manufacture/import",
    value: "manufacture_import",
  },
  {
    detail: "Market entry, launch, or territory review.",
    label: "Commercial launch",
    value: "commercial_launch",
  },
  {
    detail: "Composition, dosage, or delivery questions.",
    label: "Formulation review",
    value: "formulation_review",
  },
  {
    detail: "Indication, treatment, or use limitations.",
    label: "Method-of-use",
    value: "method_of_use_review",
  },
  {
    detail: "Alternative structures, routes, or claim avoidance.",
    label: "Design-around",
    value: "design_around",
  },
  {
    detail: "Fundraise, deal, acquisition, or board diligence.",
    label: "Diligence screen",
    value: "diligence_screen",
  },
  {
    detail: "Watch continuations, grants, and changing families.",
    label: "Monitor continuations",
    value: "monitor_continuations",
  },
];

function formatScopeLabel(value: string): string {
  if (value === "unknown") {
    return "General matter";
  }

  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function getMatterScopeSuggestion({
  compoundInput,
  inputType,
}: {
  compoundInput: string;
  inputType: string | null;
}): MatterScopePreflightValue {
  const normalized = compoundInput.trim().toLowerCase();
  const assetTypeHint: AssetTypeHint =
    normalized.includes("antibody") ||
    normalized.includes("sequence") ||
    normalized.includes("peptide")
      ? "biologic_or_sequence"
      : normalized.includes("formulation") ||
          normalized.includes("dosage") ||
          normalized.includes("excipient")
        ? "formulation"
        : normalized.includes("synthesis") ||
            normalized.includes("process") ||
            normalized.includes("route")
          ? "process_or_synthesis"
          : inputType === "SMILES" ||
              inputType === "InChI" ||
              inputType === "InChIKey" ||
              inputType === "CAS Number" ||
              inputType === "Name"
            ? "small_molecule"
            : "unknown";

  return {
    assetTypeHint,
    developmentStage: "discovery",
    intendedActions:
      assetTypeHint === "formulation"
        ? ["formulation_review", "diligence_screen"]
        : assetTypeHint === "process_or_synthesis"
          ? ["manufacture_import", "design_around"]
          : ["diligence_screen"],
  };
}

function handleRadioNavigation<Value extends string>(
  event: KeyboardEvent<HTMLButtonElement>,
  options: readonly { value: Value }[],
  currentValue: Value,
  onSelect: (value: Value) => void,
) {
  const currentIndex = options.findIndex(
    (option) => option.value === currentValue,
  );
  const lastIndex = options.length - 1;
  let nextIndex: number | null = null;

  if (event.key === "ArrowRight" || event.key === "ArrowDown") {
    nextIndex = currentIndex >= lastIndex ? 0 : currentIndex + 1;
  } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
    nextIndex = currentIndex <= 0 ? lastIndex : currentIndex - 1;
  } else if (event.key === "Home") {
    nextIndex = 0;
  } else if (event.key === "End") {
    nextIndex = lastIndex;
  }

  if (nextIndex == null) {
    return;
  }

  event.preventDefault();
  onSelect(options[nextIndex].value);

  const group = event.currentTarget.closest('[role="radiogroup"]');
  const radios = Array.from(
    group?.querySelectorAll<HTMLElement>('[role="radio"]') ?? [],
  );
  const focusNext = () => {
    radios[nextIndex]?.focus();
  };

  if (typeof window.requestAnimationFrame === "function") {
    window.requestAnimationFrame(focusNext);
  } else {
    window.setTimeout(focusNext, 0);
  }
}

export function MatterScopePreflight({
  className,
  compoundInput,
  inputType,
  onChange,
  value,
}: MatterScopePreflightProps) {
  const suggestion = getMatterScopeSuggestion({ compoundInput, inputType });
  const hasCompound = compoundInput.trim().length > 0;
  const selectedAsset =
    ASSET_OPTIONS.find((option) => option.value === value.assetTypeHint) ??
    ASSET_OPTIONS[0];
  const selectedActions = new Set(value.intendedActions);

  const setAssetType = (assetTypeHint: AssetTypeHint) => {
    onChange({ ...value, assetTypeHint });
  };
  const setStage = (developmentStage: DevelopmentStage) => {
    onChange({ ...value, developmentStage });
  };
  const toggleAction = (action: IntendedAction) => {
    const next = selectedActions.has(action)
      ? value.intendedActions.filter((item) => item !== action)
      : [...value.intendedActions, action];

    onChange({
      ...value,
      intendedActions: next.length > 0 ? next : ["diligence_screen"],
    });
  };
  const applySuggestion = () => {
    onChange(suggestion);
  };

  return (
    <section
      aria-label="Matter scope preflight"
      className={cn(
        "overflow-hidden rounded-lg border border-brand-primary/15 bg-[var(--surface-card)] shadow-[var(--shadow-sm)]",
        className,
      )}
    >
      <div className="border-b border-[var(--border-subtle)] bg-[var(--surface-glass)] p-3 sm:p-5">
        <div className="flex min-w-0 flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              Matter scope preflight
            </p>
            <h2 className="mt-1 flex items-center gap-2 text-base font-semibold text-[var(--text-primary)]">
              <Lightbulb
                className="h-4 w-4 text-brand-primary"
                aria-hidden="true"
              />
              What are we clearing?
            </h2>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
              Confirm the asset, stage, and intended FTO actions before launch.
              Praviar uses this context to route evidence, not to create a legal
              clearance opinion.
            </p>
          </div>
          <div className="rounded-md border border-brand-primary/20 bg-brand-primary/10 px-3 py-2 text-xs text-brand-primary">
            <p className="font-semibold">Preflight assist</p>
            <p className="mt-1 text-xs leading-4 text-[var(--text-secondary)]">
              {hasCompound
                ? `Suggested: ${formatScopeLabel(
                    suggestion.assetTypeHint,
                  )}; ${formatScopeLabel(suggestion.developmentStage)}`
                : "Enter a compound to refine the evidence scope."}
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-2 min-h-11 bg-[var(--bg-surface)]/80"
              disabled={!hasCompound}
              onClick={applySuggestion}
            >
              Apply suggestion
            </Button>
          </div>
        </div>
      </div>

      <div className="space-y-4 p-3 sm:p-5">
        <div>
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
              Asset type
            </p>
            <Badge variant="secondary">{selectedAsset.label}</Badge>
          </div>
          <div
            className="mt-2 grid gap-2 md:grid-cols-2 xl:grid-cols-3"
            role="radiogroup"
            aria-label="Asset type"
          >
            {ASSET_OPTIONS.map((option) => {
              const Icon = option.icon;
              const selected = option.value === value.assetTypeHint;

              return (
                <button
                  key={option.value}
                  type="button"
                  role="radio"
                  className={cn(
                    "grid min-h-[5rem] grid-cols-[2rem_minmax(0,1fr)] gap-2 rounded-md border px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60",
                    selected
                      ? "border-brand-primary/35 bg-brand-primary/10"
                      : "border-[var(--border-subtle)] bg-[var(--surface-subtle)] hover:border-brand-primary/30",
                  )}
                  aria-checked={selected}
                  tabIndex={selected ? 0 : -1}
                  onClick={() => setAssetType(option.value)}
                  onKeyDown={(event) =>
                    handleRadioNavigation(
                      event,
                      ASSET_OPTIONS,
                      value.assetTypeHint,
                      setAssetType,
                    )
                  }
                >
                  <span
                    className={cn(
                      "mt-0.5 flex h-8 w-8 items-center justify-center rounded-md border",
                      selected
                        ? "border-brand-primary/30 bg-brand-primary/10 text-brand-primary"
                        : "border-[var(--border-subtle)] bg-[var(--surface-card)] text-[var(--text-tertiary)]",
                    )}
                    aria-hidden="true"
                  >
                    <Icon className="h-4 w-4" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-[var(--text-primary)]">
                      {option.label}
                    </span>
                    <span className="mt-0.5 block text-xs leading-5 text-[var(--text-secondary)]">
                      {option.detail}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,0.72fr)_minmax(0,1fr)]">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
              Development stage
            </p>
            <div
              className="mt-2 flex flex-wrap gap-2"
              role="radiogroup"
              aria-label="Development stage"
            >
              {STAGE_OPTIONS.map((option) => {
                const selected = option.value === value.developmentStage;

                return (
                  <button
                    key={option.value}
                    type="button"
                    role="radio"
                    className={cn(
                      "min-h-11 rounded-md border px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60",
                      selected
                        ? "border-brand-primary/35 bg-brand-primary/10 text-brand-primary"
                        : "border-[var(--border-subtle)] bg-[var(--surface-subtle)] text-[var(--text-secondary)] hover:border-brand-primary/30",
                    )}
                    aria-checked={selected}
                    tabIndex={selected ? 0 : -1}
                    onClick={() => setStage(option.value)}
                    onKeyDown={(event) =>
                      handleRadioNavigation(
                        event,
                        STAGE_OPTIONS,
                        value.developmentStage,
                        setStage,
                      )
                    }
                  >
                    {option.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
              Intended actions
            </p>
            <div
              className="mt-2 grid gap-2 sm:grid-cols-2"
              role="group"
              aria-label="Intended actions"
            >
              {ACTION_OPTIONS.map((option) => {
                const selected = selectedActions.has(option.value);

                return (
                  <button
                    key={option.value}
                    type="button"
                    role="checkbox"
                    className={cn(
                      "min-h-[4rem] rounded-md border px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60",
                      selected
                        ? "border-brand-primary/35 bg-brand-primary/10"
                        : "border-[var(--border-subtle)] bg-[var(--surface-subtle)] hover:border-brand-primary/30",
                    )}
                    aria-checked={selected}
                    onClick={() => toggleAction(option.value)}
                  >
                    <span className="block text-sm font-semibold text-[var(--text-primary)]">
                      {option.label}
                    </span>
                    <span className="mt-0.5 block text-xs leading-5 text-[var(--text-secondary)]">
                      {option.detail}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export {
  ACTION_OPTIONS,
  ASSET_OPTIONS,
  STAGE_OPTIONS,
  formatScopeLabel,
  getMatterScopeSuggestion,
};
