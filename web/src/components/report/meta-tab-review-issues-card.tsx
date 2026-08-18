"use client";

import { AlertTriangle, CheckCircle } from "lucide-react";
import type { FTOReport } from "@praviar/shared-types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { sanitizeReportDiagnosticText } from "./report-diagnostic-copy";

type ReviewIssue = NonNullable<FTOReport["review_issues"]>[number];

function issueLabel(value: string) {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function severityVariant(severity: ReviewIssue["severity"]) {
  if (severity === "critical" || severity === "major") return "destructive";
  if (severity === "minor") return "warning";
  return "secondary";
}

export function ReviewIssuesCard({
  reviewIssues,
}: {
  reviewIssues: NonNullable<FTOReport["review_issues"]>;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          {reviewIssues.length > 0 ? (
            <AlertTriangle className="h-5 w-5 text-error" aria-hidden="true" />
          ) : (
            <CheckCircle className="h-5 w-5 text-success" aria-hidden="true" />
          )}
          <CardTitle className="text-sm">Critic Review Issues</CardTitle>
          {reviewIssues.length > 0 ? (
            <Badge variant="destructive" className="ml-auto text-xs">
              {reviewIssues.length}
            </Badge>
          ) : null}
        </div>
      </CardHeader>
      <CardContent>
        {reviewIssues.length === 0 ? (
          <div className="rounded-lg border border-success/10 bg-success/5 p-4 text-center">
            <p className="text-sm text-success">
              No critic review issues recorded
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {reviewIssues.map((issue, index) => (
              <article
                key={`${issue.patent_id}-${issue.issue_type}-${index}`}
                className="space-y-2 rounded-lg border border-error/15 bg-error/5 p-4 [overflow-wrap:anywhere]"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge
                    variant={severityVariant(issue.severity)}
                    className="text-xs"
                  >
                    {issueLabel(issue.severity)}
                  </Badge>
                  <Badge variant="outline" className="text-xs">
                    {issueLabel(issue.issue_type)}
                  </Badge>
                  <span className="font-mono text-xs font-semibold text-[var(--text-primary)]">
                    {issue.patent_id}
                  </span>
                </div>
                <p className="text-sm leading-6 text-[var(--text-primary)]">
                  {sanitizeReportDiagnosticText(
                    issue.description,
                    "A material report finding requires review.",
                  )}
                </p>
                {issue.suggested_correction ? (
                  <p className="text-xs leading-5 text-[var(--text-secondary)]">
                    <span className="font-semibold">Suggested correction:</span>{" "}
                    {sanitizeReportDiagnosticText(
                      issue.suggested_correction,
                      "Re-check the affected finding against its cited evidence.",
                    )}
                  </p>
                ) : null}
              </article>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
