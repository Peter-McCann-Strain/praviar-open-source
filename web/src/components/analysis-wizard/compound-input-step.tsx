"use client";

import { useRef, type ReactNode } from "react";
import { Atom, ChevronRight, ShieldCheck, TriangleAlert } from "lucide-react";
import { CompoundIdentityDecisionSheet } from "@/components/analysis-wizard/compound-identity-decision-sheet";
import {
  SmilesInput,
  detectInputType,
  getCompoundInputReadiness,
} from "@/components/chemistry/smiles-input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EXAMPLE_COMPOUNDS } from "@/components/analysis-wizard/helpers";
import { cn } from "@/lib/utils";

interface CompoundInputStepProps {
  compoundInput: string;
  identityConfirmed?: boolean;
  matterScopeSlot?: ReactNode;
  saltPolymorphForm?: string;
  onCompoundInputChange: (value: string) => void;
  onConfirmIdentity?: () => void;
  onInputTypeChange: (value: string | null) => void;
  onNext: () => void;
}

export function CompoundInputStep({
  compoundInput,
  identityConfirmed = false,
  matterScopeSlot,
  saltPolymorphForm = "",
  onCompoundInputChange,
  onConfirmIdentity,
  onInputTypeChange,
  onNext,
}: CompoundInputStepProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const inputType = detectInputType(compoundInput);
  const readiness = getCompoundInputReadiness(compoundInput);
  const hasCompound = compoundInput.trim().length > 0;
  const inputTypeAnnouncement = hasCompound
    ? `Detected input type: ${inputType ?? "compound"}. ${readiness.detail}`
    : "Compound input awaiting identifier";
  const ReadinessIcon = readiness.canProceed ? ShieldCheck : TriangleAlert;

  // Selecting an example sets the value through the parent (bypassing
  // SmilesInput's internal onChange), so the detected input type must be
  // propagated here too — otherwise the parent keeps a stale type and the
  // review step shows "Auto-detect" with no structure preview for the example.
  const handleSelectExample = (input: string) => {
    onCompoundInputChange(input);
    onInputTypeChange(detectInputType(input));
  };

  return (
    <Card className="overflow-hidden border-brand-primary/15">
      <div className="h-1 bg-gradient-to-r from-brand-primary via-brand-primary/30 to-transparent" />
      <CardHeader className="border-b border-[var(--border-subtle)] bg-[var(--surface-glass)] p-3 sm:p-5">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)] sm:text-xs">
              Molecule intake
            </p>
            <CardTitle
              aria-level={2}
              className="mt-1 flex items-center gap-2 text-sm sm:text-base"
            >
              <Atom className="h-4 w-4 text-brand-primary sm:h-5 sm:w-5" />
              Compound Input
            </CardTitle>
            <p className="mt-1 hidden max-w-2xl text-sm leading-5 text-[var(--text-secondary)] sm:block sm:leading-6">
              Provide a compound name, SMILES, InChI, InChIKey, or CAS number.
              Praviar will adapt the evidence path after launch.
            </p>
          </div>
          <span
            className={cn(
              "hidden w-fit items-center gap-2 rounded-md border px-2.5 py-1 text-xs font-medium sm:inline-flex",
              readiness.canProceed
                ? "border-brand-primary/25 bg-brand-primary/10 text-brand-primary"
                : hasCompound
                  ? "border-warning/30 bg-warning/10 text-warning"
                  : "border-[var(--border-subtle)] bg-[var(--surface-muted)] text-[var(--text-secondary)]",
            )}
            data-testid="compound-readiness-badge"
          >
            <ReadinessIcon className="h-3.5 w-3.5" />
            {readiness.label}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 p-3 sm:space-y-6 sm:p-5">
        <SmilesInput
          inputRef={inputRef}
          value={compoundInput}
          onChange={onCompoundInputChange}
          onInputTypeChange={onInputTypeChange}
          showPreview={true}
          placeholder="Name, SMILES, InChI, CAS"
          className="space-y-3 sm:space-y-4"
        />

        <p className="sr-only" role="status" aria-live="polite">
          {inputTypeAnnouncement}
        </p>

        {hasCompound ? (
          <CompoundIdentityDecisionSheet
            canConfirm={readiness.canProceed}
            compoundInput={compoundInput}
            inputType={inputType}
            isConfirmed={identityConfirmed}
            saltPolymorphForm={saltPolymorphForm}
            onConfirm={() => onConfirmIdentity?.()}
            onCorrect={() => {
              inputRef.current?.focus();
              inputRef.current?.select();
            }}
          />
        ) : null}

        <div
          className={cn(
            "grid gap-3 rounded-lg border border-brand-primary/15 bg-brand-primary/6 p-3 sm:p-4",
            !compoundInput &&
              "lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start",
          )}
          data-testid="compound-intake-action-bar"
        >
          <div className="grid min-w-0 gap-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center lg:order-2 lg:max-w-md lg:grid-cols-1">
            <div
              className={cn(
                "min-w-0 rounded-md border px-3 py-2 text-xs",
                readiness.canProceed
                  ? "border-success/20 bg-success/10"
                  : hasCompound
                    ? "border-warning/30 bg-warning/10"
                    : "border-[var(--border-subtle)] bg-[var(--surface-card)]",
              )}
              aria-live="polite"
              data-testid="compound-action-readiness-summary"
            >
              <p className="font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                {readiness.label}
              </p>
              <p className="mt-0.5 line-clamp-2 leading-5 text-[var(--text-secondary)]">
                {readiness.detail}
              </p>
            </div>
            <Button
              onClick={onNext}
              disabled={!readiness.canProceed || !identityConfirmed}
              variant={
                readiness.canProceed && identityConfirmed
                  ? "default"
                  : "outline"
              }
              className="min-h-11 w-full gap-2 sm:w-auto"
            >
              Next: Configure
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
          {!compoundInput ? (
            <div className="min-w-0 lg:order-1">
              <p className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-brand-primary">
                Sample compounds
              </p>
              <div className="flex flex-wrap gap-2">
                {EXAMPLE_COMPOUNDS.map((compound) => (
                  <button
                    key={compound.input}
                    type="button"
                    onClick={() => handleSelectExample(compound.input)}
                    className="flex min-h-11 items-center gap-2 rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-card)] px-3 py-2 text-sm text-[var(--text-secondary)] shadow-[var(--shadow-xs)] transition-colors hover:border-brand-primary/50 hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60"
                  >
                    <Atom className="h-3.5 w-3.5" aria-hidden="true" />
                    {compound.name}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        {matterScopeSlot}
      </CardContent>
    </Card>
  );
}
