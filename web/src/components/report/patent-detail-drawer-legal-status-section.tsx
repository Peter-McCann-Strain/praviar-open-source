"use client";

import { Shield } from "lucide-react";
import type { PatentHit } from "@praviar/shared-types";
import { PatentDetailDrawerLegalStatusBadge } from "@/components/report/patent-detail-drawer-legal-status-badge";
import { PatentDetailDrawerSection } from "@/components/report/patent-detail-drawer-section";
import { PatentDetailDrawerTermBreakdown } from "@/components/report/patent-detail-drawer-term-breakdown";

export function PatentDetailDrawerLegalStatusSection({
  patent,
}: {
  patent: PatentHit;
}) {
  return (
    <PatentDetailDrawerSection title="Legal Status & Term" icon={Shield}>
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <PatentDetailDrawerLegalStatusBadge status={patent.legal_status} />
          {patent.is_granted && (
            <span className="text-xs text-[var(--text-tertiary)]">Granted</span>
          )}
        </div>
        {patent.patent_term_info && (
          <PatentDetailDrawerTermBreakdown info={patent.patent_term_info} />
        )}
        {!patent.patent_term_info && patent.expiry_date && (
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
            <span className="text-[var(--text-tertiary)]">Filing Date</span>
            <span className="text-[var(--text-primary)]">
              {patent.filing_date ?? "—"}
            </span>
            <span className="text-[var(--text-tertiary)]">Expiry Date</span>
            <span className="text-[var(--text-primary)] font-semibold">
              {patent.expiry_date}
            </span>
          </div>
        )}
      </div>
    </PatentDetailDrawerSection>
  );
}
