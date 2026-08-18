"use client";

import { AlertTriangle, CheckCircle } from "lucide-react";
import type { FTOReport } from "@praviar/shared-types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { sanitizeReportDiagnosticText } from "./report-diagnostic-copy";
import {
  limitationBadgeVariant,
  limitationCategoryLabel,
} from "./meta-tab-helpers";

export function DataLimitationsCard({
  dataLimitations,
  syntheticEvidence = false,
}: {
  dataLimitations: NonNullable<FTOReport["data_limitations"]>;
  syntheticEvidence?: boolean;
}) {
  const hasRelianceBoundary = dataLimitations.length > 0 || syntheticEvidence;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          {hasRelianceBoundary ? (
            <AlertTriangle className="h-5 w-5 text-warning" />
          ) : (
            <CheckCircle className="h-5 w-5 text-success" />
          )}
          <CardTitle className="text-sm">Data Limitations</CardTitle>
          {dataLimitations.length > 0 && (
            <Badge variant="warning" className="text-xs ml-auto">
              {dataLimitations.length}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {dataLimitations.length === 0 ? (
          <div
            className={
              syntheticEvidence
                ? "rounded-lg border border-warning/20 bg-warning/5 p-4 text-center"
                : "rounded-lg border border-success/10 bg-success/5 p-4 text-center"
            }
          >
            <p
              className={
                syntheticEvidence
                  ? "text-sm text-warning"
                  : "text-sm text-success"
              }
            >
              {syntheticEvidence
                ? "Fixture declares no data limitations"
                : "No data limitations detected"}
            </p>
            {syntheticEvidence ? (
              <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                This describes the development payload only; it is not evidence
                of production-corpus completeness.
              </p>
            ) : null}
          </div>
        ) : (
          <div className="space-y-3">
            {dataLimitations.map((limitation, idx) => (
              <div
                key={idx}
                className="praviar-glass-panel-soft rounded-lg p-4 space-y-2 [overflow-wrap:anywhere]"
              >
                <Badge
                  variant={limitationBadgeVariant(limitation.category)}
                  className="text-xs"
                >
                  {limitationCategoryLabel(limitation.category)}
                </Badge>
                <p className="text-sm text-[var(--text-primary)]">
                  {sanitizeReportDiagnosticText(
                    limitation.description,
                    "A data limitation affected this report.",
                  )}
                </p>
                <p className="text-xs text-[var(--text-secondary)]">
                  <span className="font-semibold">Impact:</span>{" "}
                  {sanitizeReportDiagnosticText(
                    limitation.impact,
                    "Review coverage before relying on this source.",
                  )}
                </p>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
