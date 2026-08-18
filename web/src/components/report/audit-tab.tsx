"use client";

import { FunnelExplorer } from "@/components/report/funnel-explorer";
import { MarkushEvidenceStatusCard } from "@/components/report/markush-evidence-status-card";
import { ReportMobileDisclosure } from "@/components/report/report-mobile-disclosure";
import type { FTOReport } from "@praviar/shared-types";
import {
  AnalysisSelectionCard,
  AuditReasoningCard,
  DecisionEvidenceCard,
  HardFilterRejectionsCard,
  TriageDecisionsCard,
} from "./audit-tab-sections";
import {
  getHardFilterRejectionEntries,
  getSortedTriageEntries,
  getThinkingPatents,
} from "./audit-tab-helpers";

interface AuditTabProps {
  report: FTOReport;
}

export function AuditTab({ report }: AuditTabProps) {
  const audit = report.audit_trail;
  const rejectionEntries = getHardFilterRejectionEntries(audit);
  const triageSorted = getSortedTriageEntries(audit);
  const thinkingPatents = getThinkingPatents(report);

  // audit_trail is OPTIONAL in the generated contract even though the web
  // barrel widens it to required. When the pipeline omits it entirely there is
  // no funnel/triage/selection data to show, and the funnel explorer (whose
  // prop type is non-optional) would dereference `undefined` and throw into the
  // tab ErrorBoundary. Render a clean empty state instead.
  if (!audit) {
    return (
      <div className="praviar-surface-premium rounded-lg p-8 text-center">
        <p className="text-sm text-[var(--text-secondary)]">
          No pipeline audit trail is available for this report.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <MarkushEvidenceStatusCard audit={audit} />
      <FunnelExplorer audit={audit} />
      <ReportMobileDisclosure
        label="Inspect decision evidence"
        description="Open the governed source, coverage, and decisive-reference record."
      >
        <DecisionEvidenceCard report={report} />
      </ReportMobileDisclosure>
      <ReportMobileDisclosure
        label="Inspect detailed pipeline audit"
        description="Open hard filters, triage, analysis selection, and reasoning traces."
      >
        <div className="space-y-6">
          <HardFilterRejectionsCard rejectionEntries={rejectionEntries} />
          <TriageDecisionsCard triageEntries={triageSorted} />
          <AnalysisSelectionCard analysisEntries={audit.analysis_audit} />
          <AuditReasoningCard thinkingPatents={thinkingPatents} />
        </div>
      </ReportMobileDisclosure>
    </div>
  );
}
