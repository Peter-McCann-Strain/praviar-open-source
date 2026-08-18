"use client";

import { AlertTriangle } from "lucide-react";
import { AnnotatedText } from "@/components/report/annotated-text";
import { Card, CardContent } from "@/components/ui/card";
import type { CitationRef } from "@/types/citation";
import type { FTOReport } from "@praviar/shared-types";

interface AnalysisSummarySectionProps {
  report: FTOReport;
  citationMap: Map<number, CitationRef>;
  onCitationClick: (index: number) => void;
}

export function AnalysisSummarySection({
  report,
  citationMap,
  onCitationClick,
}: AnalysisSummarySectionProps) {
  const summaryValidationIssues =
    report.risk_summary.summary_validation_issues ?? [];

  return (
    <Card data-print-keep-together>
      <CardContent className="space-y-4 p-6">
        <h3 className="type-heading-md text-[var(--text-primary)]">
          Analysis Summary
        </h3>

        {report.risk_summary.executive_summary.length < 50 ? (
          <div className="flex items-start gap-3 rounded-lg border border-info/20 bg-info/5 p-3">
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-info" />
            <p className="text-xs text-info">
              Detailed risk analysis restricted to legal/IP role users. Contact
              your organization administrator for access.
            </p>
          </div>
        ) : null}

        <AnnotatedText
          text={report.risk_summary.executive_summary}
          citations={citationMap}
          onCitationClick={onCitationClick}
        />

        {summaryValidationIssues.length > 0 ? (
          <div className="space-y-2 rounded-lg border border-warning/20 bg-warning/5 p-3">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 flex-shrink-0 text-warning" />
              <p className="text-sm font-semibold text-warning">
                AI Self-Assessment Issues
              </p>
            </div>
            <p className="text-xs text-[var(--text-secondary)]">
              The AI flagged potential issues with its own summary:
            </p>
            <ul className="space-y-1">
              {summaryValidationIssues.map((issue, index) => (
                <li
                  key={index}
                  className="flex items-start gap-2 text-xs text-[var(--text-primary)]"
                >
                  <span className="mt-0.5 flex-shrink-0 text-warning">
                    &bull;
                  </span>
                  {issue}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {report.risk_summary.overall_risk === "high" ? (
          <div className="flex items-center gap-3 rounded-lg border border-error/20 bg-error/5 p-3">
            <AlertTriangle className="h-5 w-5 flex-shrink-0 text-error" />
            <p className="text-sm text-error">
              Immediate IP/legal review recommended before commercial
              development.
            </p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
