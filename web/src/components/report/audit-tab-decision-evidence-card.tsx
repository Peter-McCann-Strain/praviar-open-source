import { FileSearch } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { FTOReport } from "@praviar/shared-types";
import {
  formatDecisionLabel,
  getClearanceDecision,
  getCoverageSummary,
  getDecisionBadgeVariant,
  getDecisionReferences,
  getDecisionWarnings,
} from "./report-decision-helpers";
import { DecisionEvidenceGaps } from "./audit-tab-decision-evidence-gaps";
import { DecisionEvidenceReferences } from "./audit-tab-decision-evidence-references";
import { DecisionEvidenceSummary } from "./audit-tab-decision-evidence-summary";
import { DecisionEvidenceWarnings } from "./audit-tab-decision-evidence-warnings";
import { isHealthySourceStatus } from "@/components/report-page/report-reliance-readiness";

interface DecisionEvidenceCardProps {
  report: FTOReport;
}

export function DecisionEvidenceCard({ report }: DecisionEvidenceCardProps) {
  const decision = getClearanceDecision(report);
  const coverageSummary = getCoverageSummary(report);
  const warnings = getDecisionWarnings(report);
  const references = getDecisionReferences(report);
  const sourceHealthEntries = report.source_health?.entries ?? [];
  const failedSourceProviderCount = sourceHealthEntries.filter(
    (entry) => !isHealthySourceStatus(entry.status),
  ).length;

  if (!decision || !coverageSummary) {
    return null;
  }

  const gapBadges = [
    {
      label: "Missing Claims",
      count: coverageSummary.patents_missing_claims.length,
    },
    {
      label: "Missing Family Context",
      count: coverageSummary.patents_missing_family_context.length,
    },
    {
      label: "US Prosecution Gaps",
      count: coverageSummary.us_patents_missing_prosecution_context.length,
    },
    {
      label: "EP Register Gaps",
      count: coverageSummary.ep_patents_missing_register_context.length,
    },
    {
      label: "Verification Gaps",
      count: coverageSummary.verification_gaps.length,
    },
  ].filter((item) => item.count > 0);

  return (
    <Card>
      <CardHeader className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <FileSearch className="h-4 w-4 text-[var(--text-secondary)]" />
            <CardTitle className="text-sm">Decision Evidence</CardTitle>
          </div>
          <Badge variant={getDecisionBadgeVariant(decision.decision)}>
            {formatDecisionLabel(decision.decision)}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <DecisionEvidenceSummary
          decision={decision}
          failedSourceProviderCount={failedSourceProviderCount}
          sourceHealthProviderCount={sourceHealthEntries.length}
        />
        <DecisionEvidenceWarnings warnings={warnings} />
        <DecisionEvidenceGaps gapBadges={gapBadges} />
        <DecisionEvidenceReferences references={references} />
      </CardContent>
    </Card>
  );
}
