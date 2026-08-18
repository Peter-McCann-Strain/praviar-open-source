"use client";

import { AlertTriangle, Scale, SearchCheck } from "lucide-react";
import type { FTOReport } from "@praviar/shared-types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { InvalidityTabAssessmentCard } from "@/components/report/invalidity-tab-assessment-card";

interface InvalidityTabProps {
  report: FTOReport;
}

export function InvalidityTab({ report }: InvalidityTabProps) {
  const assessments = report.invalidity_assessments ?? [];
  const reportContext = {
    generatedAt: report.generated_at,
    pipelineVersion: report.praviar_pipeline_version,
    reportId: report.report_id,
  };

  return (
    <div className="space-y-6">
      {assessments.map((inv) => (
        <InvalidityTabAssessmentCard
          key={inv.patent_id}
          assessment={inv}
          reportContext={reportContext}
        />
      ))}

      {assessments.length === 0 && (
        <Card className="overflow-hidden border-warning/25">
          <CardHeader className="border-b border-[var(--border-subtle)] bg-warning/5 p-4 sm:p-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex min-w-0 items-start gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-warning/25 bg-warning/10 text-warning">
                  <Scale className="h-5 w-5" aria-hidden="true" />
                </span>
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-warning">
                    Reliance boundary
                  </p>
                  <CardTitle className="mt-1 text-lg">
                    Invalidity has not been assessed
                  </CardTitle>
                </div>
              </div>
              <Badge variant="warning">Not assessed</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-5 p-4 sm:p-6">
            <p className="max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
              This report contains no governed prior-art, PTAB, enablement, or
              written-description assessment. Do not infer validity or a clean
              challenge posture from the absence of findings.
            </p>
            <dl className="grid gap-3 sm:grid-cols-3">
              <EmptyAssessmentFact
                icon={SearchCheck}
                label="Assessment coverage"
                value="No prior-art screen"
              />
              <EmptyAssessmentFact
                icon={AlertTriangle}
                label="Decision effect"
                value="Validity remains unknown"
              />
              <EmptyAssessmentFact
                icon={Scale}
                label="Required next step"
                value="Counsel-led validity review"
              />
            </dl>
            <p className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-3 text-xs leading-5 text-[var(--text-secondary)]">
              Review the material patent claims and cited art before relying on
              any launch, design-around, or challenge decision.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function EmptyAssessmentFact({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Scale;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-card)] p-3">
      <Icon className="h-4 w-4 text-brand-primary" aria-hidden="true" />
      <dt className="mt-3 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        {label}
      </dt>
      <dd className="mt-1 text-sm font-semibold leading-5 text-[var(--text-primary)]">
        {value}
      </dd>
    </div>
  );
}
