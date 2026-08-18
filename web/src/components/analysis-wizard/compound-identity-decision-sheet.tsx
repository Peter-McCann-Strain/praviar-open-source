"use client";

import {
  CheckCheck,
  CircleAlert,
  GitCompareArrows,
  Layers3,
  PencilLine,
  ScanSearch,
  ShieldCheck,
} from "lucide-react";
import type { InputType } from "@/components/chemistry/smiles-input";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface CompoundIdentityDecisionSheetProps {
  canConfirm: boolean;
  compoundInput: string;
  inputType: InputType;
  isConfirmed: boolean;
  onConfirm: () => void;
  onCorrect: () => void;
  saltPolymorphForm?: string;
}

type IdentitySignalTone = "attention" | "pending" | "ready";

interface IdentitySignal {
  detail: string;
  label: string;
  tone: IdentitySignalTone;
  value: string;
}

function signalToneClass(tone: IdentitySignalTone): string {
  if (tone === "ready") {
    return "border-success/25 bg-success/8";
  }
  if (tone === "attention") {
    return "border-warning/30 bg-warning/8";
  }
  return "border-brand-primary/20 bg-brand-primary/6";
}

function getSaltSignal(
  compoundInput: string,
  inputType: InputType,
  saltPolymorphForm: string,
): IdentitySignal {
  const declaredForm = saltPolymorphForm.trim();
  const explicitlyUnknown = declaredForm.toLowerCase() === "unknown";
  const hasMultipleSmilesFragments =
    inputType === "SMILES" && compoundInput.includes(".");

  if (declaredForm && !explicitlyUnknown) {
    return {
      detail:
        "This declared product form stays in the matter context. After canonical resolution, the pipeline derives a free-base search form when chemistry supports it so the resolved record shows whether it differs.",
      label: "Salt / form provenance",
      tone: "ready",
      value: `Declared: ${declaredForm}`,
    };
  }

  if (explicitlyUnknown) {
    return {
      detail:
        "The matter records the form as unknown. Free-base derivation is still attempted after canonical resolution, but no product-form identity is asserted here.",
      label: "Salt / form provenance",
      tone: "attention",
      value: "Explicitly unknown",
    };
  }

  if (hasMultipleSmilesFragments) {
    return {
      detail:
        "The submitted SMILES contains multiple fragments. The pipeline derives a free-base search form after resolution when parsing supports it; inspect the resolved record before relying on the selected fragment.",
      label: "Salt / form provenance",
      tone: "attention",
      value: "Multi-fragment input detected",
    };
  }

  return {
    detail:
      "No salt, polymorph, hydrate, solvate, or crystal form is declared. The pipeline attempts a free-base search form after resolution, but product-form scope remains open.",
    label: "Salt / form provenance",
    tone: "attention",
    value: "Not declared",
  };
}

function getStereoSignal(
  compoundInput: string,
  inputType: InputType,
): IdentitySignal {
  if (inputType !== "SMILES") {
    return {
      detail:
        "Stereochemistry cannot be confirmed from this submitted identifier before resolution. The resolved record supplies the structure used to derive a stereo-stripped search form when chemistry supports it.",
      label: "Stereo provenance",
      tone: "pending",
      value: "Pending resolved structure",
    };
  }

  const hasAtomStereo = compoundInput.includes("@");
  const hasBondStereo = /[/\\]/u.test(compoundInput);

  if (hasAtomStereo || hasBondStereo) {
    const markerTypes = [
      hasAtomStereo ? "atom" : null,
      hasBondStereo ? "bond" : null,
    ].filter(Boolean);

    return {
      detail:
        "The submitted stereochemical notation remains part of canonical resolution. The pipeline also derives a stereo-stripped search form for broader racemate or stereoisomer coverage.",
      label: "Stereo provenance",
      tone: "ready",
      value: `${markerTypes.join(" + ")} markers submitted`,
    };
  }

  return {
    detail:
      "No explicit stereochemical markers are present in the submitted SMILES. The resolved structure remains authoritative, and a stereo-stripped search form is derived after resolution.",
    label: "Stereo provenance",
    tone: "attention",
    value: "No explicit markers submitted",
  };
}

export function CompoundIdentityDecisionSheet({
  canConfirm,
  compoundInput,
  inputType,
  isConfirmed,
  onConfirm,
  onCorrect,
  saltPolymorphForm = "",
}: CompoundIdentityDecisionSheetProps) {
  const submittedInput = compoundInput.trim();
  const canonicalDetail =
    inputType === "SMILES"
      ? "The 2D preview checks browser renderability only; it is not canonical confirmation. The pipeline must resolve the canonical structure before claim search."
      : "The pipeline resolves this identifier before claim search and records canonical structure identifiers when the configured identity source supplies them.";
  const identitySignals: IdentitySignal[] = [
    {
      detail: canonicalDetail,
      label: "Canonical identity",
      tone: "pending",
      value: "Pending authoritative resolution",
    },
    getSaltSignal(submittedInput, inputType, saltPolymorphForm),
    getStereoSignal(submittedInput, inputType),
    {
      detail:
        "The current resolved-identity contract does not expose a separate tautomer-normalized structure. Do not infer tautomer coverage from the syntax preview or canonical label.",
      label: "Tautomer provenance",
      tone: "attention",
      value: "No explicit variant in contract",
    },
  ];

  return (
    <section
      aria-labelledby="compound-identity-decision-title"
      className="overflow-hidden rounded-lg border border-brand-primary/20 bg-[var(--surface-card)] shadow-[var(--shadow-sm)]"
      data-testid="compound-identity-decision-sheet"
    >
      <div className="grid gap-3 border-b border-[var(--border-subtle)] bg-[var(--surface-glass)] p-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start sm:p-4">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-primary">
            Identity decision
          </p>
          <h3
            id="compound-identity-decision-title"
            className="mt-1 flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)] sm:text-base"
          >
            <GitCompareArrows
              className="h-4 w-4 text-brand-primary"
              aria-hidden="true"
            />
            Submitted input → resolved search identity
          </h3>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-[var(--text-secondary)] sm:text-sm sm:leading-6">
            Confirm the exact identifier being submitted. Canonical chemistry
            remains pending until the pipeline resolves it; unresolved compounds
            stop before patent claim search.
          </p>
        </div>
        <span
          className={cn(
            "inline-flex min-h-8 w-fit items-center gap-2 rounded-md border px-2.5 py-1 text-xs font-semibold",
            isConfirmed
              ? "border-success/25 bg-success/10 text-success"
              : "border-warning/30 bg-warning/10 text-warning",
          )}
          aria-live="polite"
          data-testid="compound-identity-confirmation-status"
        >
          {isConfirmed ? (
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <CircleAlert className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          {isConfirmed
            ? "Confirmed for resolution"
            : canConfirm
              ? "Review before continuing"
              : "Correct before confirming"}
        </span>
      </div>

      <div className="space-y-3 p-3 sm:p-4">
        <div className="grid gap-2 rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-subtle)] p-3 sm:grid-cols-[minmax(0,0.24fr)_minmax(0,1fr)] sm:gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.13em] text-[var(--text-tertiary)]">
              Submitted as
            </p>
            <p className="mt-1 text-sm font-semibold text-brand-primary">
              {inputType ?? "Identifier"}
            </p>
          </div>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.13em] text-[var(--text-tertiary)]">
              Exact launch value
            </p>
            <p
              className="mt-1 break-all font-mono text-sm leading-5 text-[var(--text-primary)]"
              title={submittedInput}
            >
              {submittedInput}
            </p>
            <p className="mt-1 text-xs leading-4 text-[var(--text-secondary)]">
              Leading and trailing whitespace is removed at the launch boundary;
              no canonical structure is asserted by this field.
            </p>
          </div>
        </div>

        <dl className="grid gap-2 md:grid-cols-2">
          {identitySignals.map((signal) => (
            <div
              key={signal.label}
              className={cn(
                "min-w-0 rounded-md border p-3",
                signalToneClass(signal.tone),
              )}
            >
              <dt className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                {signal.label === "Canonical identity" ? (
                  <ScanSearch className="h-3.5 w-3.5" aria-hidden="true" />
                ) : (
                  <Layers3 className="h-3.5 w-3.5" aria-hidden="true" />
                )}
                {signal.label}
              </dt>
              <dd className="mt-1">
                <p className="text-sm font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
                  {signal.value}
                </p>
                <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                  {signal.detail}
                </p>
              </dd>
            </div>
          ))}
        </dl>

        <div className="flex flex-col gap-2 border-t border-[var(--border-subtle)] pt-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="max-w-2xl text-xs leading-5 text-[var(--text-secondary)]">
            Confirmation applies to the submitted identifier only. Verify the
            resolved canonical identity and derived search forms in the
            resulting packet before relying on coverage.
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button
              type="button"
              variant="outline"
              className="min-h-11 gap-2"
              onClick={onCorrect}
            >
              <PencilLine className="h-4 w-4" aria-hidden="true" />
              Correct identifier
            </Button>
            <Button
              type="button"
              variant={isConfirmed ? "secondary" : "default"}
              className="min-h-11 gap-2"
              disabled={!canConfirm}
              onClick={onConfirm}
            >
              <CheckCheck className="h-4 w-4" aria-hidden="true" />
              {isConfirmed
                ? "Submitted identity confirmed"
                : "Confirm for resolution"}
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
