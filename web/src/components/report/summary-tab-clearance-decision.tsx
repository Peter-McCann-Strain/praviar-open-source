"use client";

import { AlertTriangle, CheckCircle2, Scale, ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { ReportMobileDisclosure } from "@/components/report/report-mobile-disclosure";
import type { FTOReport } from "@praviar/shared-types";
import {
  formatDecisionLabel,
  getClearanceDecision,
  getCommercialExposure,
  getDecisionBadgeVariant,
  getDecisionMetricItems,
  getFutureRisk,
  getJurisdictionDecisions,
} from "./report-decision-helpers";

interface ClearanceDecisionSectionProps {
  report: FTOReport;
}

function DecisionIcon({
  outcome,
}: {
  outcome: "clear" | "unclear" | "blocked";
}) {
  switch (outcome) {
    case "clear":
      return <CheckCircle2 className="h-5 w-5 text-success" />;
    case "blocked":
      return <ShieldAlert className="h-5 w-5 text-error" />;
    case "unclear":
    default:
      return <AlertTriangle className="h-5 w-5 text-warning" />;
  }
}

export function ClearanceDecisionSection({
  report,
}: ClearanceDecisionSectionProps) {
  const decision = getClearanceDecision(report);
  if (!decision) {
    return null;
  }

  const jurisdictionDecisions = getJurisdictionDecisions(report);
  const commercialExposure = getCommercialExposure(report);
  const futureRisk = getFutureRisk(report);
  const metricItems = getDecisionMetricItems(report);

  return (
    <Card>
      <CardHeader className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <DecisionIcon outcome={decision.decision} />
            <div className="space-y-1">
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                Preliminary Review Posture
              </h3>
              <p className="text-sm text-[var(--text-secondary)]">
                AI-assisted screening posture with evidence-backed support for
                counsel review.
              </p>
            </div>
          </div>
          <Badge variant={getDecisionBadgeVariant(decision.decision)}>
            {formatDecisionLabel(decision.decision)}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        {commercialExposure?.summary ? (
          <div className="praviar-glass-panel-soft rounded-lg p-4">
            <div className="flex items-center gap-2">
              <Scale className="h-4 w-4 text-[var(--text-secondary)]" />
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                Commercial Exposure
              </p>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">
              {commercialExposure.summary}
            </p>
          </div>
        ) : null}

        <ReportMobileDisclosure
          label="Decision rationale & jurisdiction posture"
          description={`${jurisdictionDecisions.length} jurisdiction posture${jurisdictionDecisions.length === 1 ? "" : "s"} · ${metricItems.length} decision metrics.`}
          testId="clearance-decision-details"
        >
          <div className="space-y-5">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {metricItems.map((item) => (
                <div
                  key={item.label}
                  className="praviar-glass-chip rounded-lg px-4 py-3"
                >
                  <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
                    {item.label}
                  </p>
                  <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
                    {item.value}
                  </p>
                </div>
              ))}
            </div>

            {decision.decision_reasoning.length > 0 ? (
              <div className="space-y-3">
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  Posture Reasoning
                </p>
                <ul className="space-y-2">
                  {decision.decision_reasoning.map((reason, index) => (
                    <li
                      key={`${reason}-${index}`}
                      className="rounded-lg border border-[var(--border-subtle)] px-4 py-3 text-sm text-[var(--text-secondary)]"
                    >
                      {reason}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {jurisdictionDecisions.length > 0 ? (
              <div className="space-y-3">
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  Jurisdiction Postures
                </p>
                <div className="grid gap-3 md:grid-cols-2">
                  {jurisdictionDecisions.map((jurisdictionDecision) => (
                    <div
                      key={jurisdictionDecision.jurisdiction}
                      className="rounded-lg border border-[var(--border-subtle)] p-4"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm font-semibold text-[var(--text-primary)]">
                          {jurisdictionDecision.jurisdiction}
                        </p>
                        <Badge
                          variant={getDecisionBadgeVariant(
                            jurisdictionDecision.decision,
                          )}
                        >
                          {formatDecisionLabel(jurisdictionDecision.decision)}
                        </Badge>
                      </div>
                      <p className="mt-2 text-xs text-[var(--text-secondary)]">
                        Reviewed{" "}
                        {jurisdictionDecision.reviewed_patent_ids.length} patent
                        {jurisdictionDecision.reviewed_patent_ids.length === 1
                          ? ""
                          : "s"}
                        {jurisdictionDecision.blocking_patent_ids.length > 0
                          ? ` · ${jurisdictionDecision.blocking_patent_ids.length} blocking`
                          : ""}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {futureRisk.length > 0 ? (
              <div className="space-y-3">
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  Future Risk Signals
                </p>
                <div className="flex flex-wrap gap-2">
                  {futureRisk.map((risk) => (
                    <Badge
                      key={`${risk.patent_id}-${risk.risk_type}`}
                      variant="outline"
                    >
                      {risk.jurisdiction || "Global"} ·{" "}
                      {risk.risk_type.replace(/_/g, " ")}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </ReportMobileDisclosure>
      </CardContent>
    </Card>
  );
}
