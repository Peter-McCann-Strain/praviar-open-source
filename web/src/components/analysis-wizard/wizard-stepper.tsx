"use client";

import { ChevronRight } from "lucide-react";
import { WIZARD_STEPS } from "@/components/analysis-wizard/helpers";
import { cn } from "@/lib/utils";

interface WizardStepperProps {
  step: number;
  onStepChange: (step: number) => void;
}

const MOBILE_STEP_LABELS: Record<number, string> = {
  1: "Molecule",
  2: "Scope",
  3: "Launch",
};

export function WizardStepper({ step, onStepChange }: WizardStepperProps) {
  return (
    <nav
      aria-label="New analysis progress"
      className="praviar-surface-premium rounded-lg p-1 sm:p-2"
    >
      <ol className="grid grid-cols-3 items-stretch gap-1 sm:flex sm:flex-wrap sm:items-center sm:justify-center sm:gap-3">
        {WIZARD_STEPS.map((wizardStep, index) => {
          const Icon = wizardStep.icon;
          const isCurrent = step === wizardStep.number;
          const isComplete = step > wizardStep.number;
          const isNavigable = isComplete;
          const stateLabel = isCurrent
            ? "Current step"
            : isComplete
              ? "Completed step"
              : "Upcoming step";
          const stepContent = (
            <>
              <span
                className={cn(
                  "flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold sm:h-7 sm:w-7 sm:text-xs",
                  isCurrent
                    ? "bg-brand-primary text-[var(--surface-inverted-fg)]"
                    : isComplete
                      ? "bg-success/15 text-success"
                      : "bg-[var(--surface-active)] text-[var(--text-tertiary)]",
                )}
                aria-hidden="true"
              >
                {wizardStep.number}
              </span>
              <Icon className="hidden h-4 w-4 sm:block" aria-hidden="true" />
              <span className="min-w-0 text-center sm:text-left">
                <span className="block max-w-full sm:hidden">
                  {MOBILE_STEP_LABELS[wizardStep.number] ?? wizardStep.label}
                </span>
                <span className="hidden max-w-full sm:block sm:text-nowrap">
                  {wizardStep.label}
                </span>
                <span className="sr-only">
                  {stateLabel}, step {wizardStep.number} of{" "}
                  {WIZARD_STEPS.length}.
                </span>
              </span>
            </>
          );

          return (
            <li
              key={wizardStep.number}
              className="min-w-0 sm:flex sm:items-center sm:gap-4"
            >
              {isNavigable ? (
                <button
                  type="button"
                  onClick={() => onStepChange(wizardStep.number)}
                  className="flex min-h-10 w-full min-w-0 flex-col items-center justify-center gap-0.5 rounded-lg bg-[var(--surface-hover)] px-1.5 py-1.5 text-center text-xs font-medium leading-3 text-success transition-all hover:bg-success/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60 sm:min-h-11 sm:w-auto sm:flex-row sm:gap-2 sm:rounded-full sm:px-5 sm:py-2.5 sm:text-left sm:text-sm sm:leading-5"
                >
                  {stepContent}
                </button>
              ) : (
                <span
                  aria-current={isCurrent ? "step" : undefined}
                  aria-disabled={isCurrent ? undefined : "true"}
                  className={cn(
                    "flex min-h-10 w-full min-w-0 flex-col items-center justify-center gap-0.5 rounded-lg px-1.5 py-1.5 text-center text-xs font-medium leading-3 transition-all sm:min-h-11 sm:w-auto sm:flex-row sm:gap-2 sm:rounded-full sm:px-5 sm:py-2.5 sm:text-left sm:text-sm sm:leading-5",
                    isCurrent
                      ? "bg-brand-primary/20 text-brand-primary ring-1 ring-brand-primary"
                      : "bg-[var(--surface-muted)] text-[var(--text-tertiary)]",
                  )}
                >
                  {stepContent}
                </span>
              )}
              {index < WIZARD_STEPS.length - 1 ? (
                <ChevronRight className="hidden h-4 w-4 text-[var(--text-disabled)] sm:block" />
              ) : null}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
