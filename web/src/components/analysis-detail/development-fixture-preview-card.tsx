"use client";

import { FileSearch2, PauseCircle, ServerOff } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  clampPipelineStep,
  TOTAL_PIPELINE_STEPS,
} from "@/components/analysis-detail/helpers";

export function DevelopmentFixturePreviewCard({
  currentStep,
}: {
  currentStep: number;
}) {
  const safeCurrentStep = clampPipelineStep(currentStep);

  return (
    <Card
      className="border-warning/30"
      data-testid="development-fixture-preview"
    >
      <CardHeader className="border-b border-[var(--border-subtle)] bg-warning/5">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-warning/25 bg-warning/10 text-warning">
            <FileSearch2 className="h-5 w-5" aria-hidden="true" />
          </span>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-warning">
              Development fixture
            </p>
            <CardTitle className="mt-1 text-base">
              Static in-progress preview
            </CardTitle>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 p-4 sm:p-6">
        <p className="max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
          This record demonstrates the in-progress workspace at Step{" "}
          {safeCurrentStep} of {TOTAL_PIPELINE_STEPS}. It was seeded directly;
          no task was dispatched and no elapsed worker runtime is implied.
        </p>
        <dl className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-3">
            <dt className="flex items-center gap-2 text-xs font-semibold text-[var(--text-tertiary)]">
              <PauseCircle className="h-4 w-4" aria-hidden="true" />
              Illustrative checkpoint
            </dt>
            <dd className="mt-2 text-sm font-semibold text-[var(--text-primary)]">
              Step {safeCurrentStep} of {TOTAL_PIPELINE_STEPS}
            </dd>
          </div>
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-3">
            <dt className="flex items-center gap-2 text-xs font-semibold text-[var(--text-tertiary)]">
              <ServerOff className="h-4 w-4" aria-hidden="true" />
              Operational meaning
            </dt>
            <dd className="mt-2 text-sm font-semibold text-[var(--text-primary)]">
              Not a worker health signal
            </dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}
