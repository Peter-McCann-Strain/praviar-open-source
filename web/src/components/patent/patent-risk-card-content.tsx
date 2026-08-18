"use client";

import { Button } from "@/components/ui/button";
import { PatentRiskCardDesignAround } from "@/components/patent/patent-risk-card-design-around";
import { PatentRiskCardLinks } from "@/components/patent/patent-risk-card-links";
import { PatentRiskCardOrangeBook } from "@/components/patent/patent-risk-card-orange-book";
import type { PatentAnalysis } from "@praviar/shared-types";

interface PatentRiskCardContentProps {
  analysis: PatentAnalysis;
  narrative?: string;
  showCorrectAssessmentButton: boolean;
  onCorrectClick: () => void;
}

export function PatentRiskCardContent({
  analysis,
  narrative,
  showCorrectAssessmentButton,
  onCorrectClick,
}: PatentRiskCardContentProps) {
  return (
    <>
      <PatentRiskCardLinks patentId={analysis.patent_id} />

      {narrative && (
        <p className="text-sm leading-relaxed text-[var(--text-primary)]">
          {narrative}
        </p>
      )}

      {analysis.orange_book_info?.is_listed && (
        <PatentRiskCardOrangeBook orangeBookInfo={analysis.orange_book_info} />
      )}

      {analysis.risk_summary && (
        <p className="text-sm text-[var(--text-secondary)]">
          {analysis.risk_summary}
        </p>
      )}

      <PatentRiskCardDesignAround
        suggestions={analysis.design_around_suggestions ?? []}
      />

      {showCorrectAssessmentButton && (
        <div className="flex justify-end">
          <Button variant="outline" size="sm" onClick={onCorrectClick}>
            Correct assessment
          </Button>
        </div>
      )}
    </>
  );
}
