"use client";

import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { FeedbackModal } from "@/components/collaboration/feedback-modal";
import { PatentRiskCardContent } from "@/components/patent/patent-risk-card-content";
import { PatentRiskCardSummary } from "@/components/patent/patent-risk-card-summary";
import { getRiskBorderClass } from "@/components/patent/patent-risk-card-helpers";
import type { PatentAnalysis } from "@praviar/shared-types";

interface PatentRiskCardProps {
  analysis: PatentAnalysis;
  analysisId?: string;
  narrative?: string;
  defaultExpanded?: boolean;
  onCorrect?: () => void;
  canSubmitFeedback?: boolean;
}

export function PatentRiskCard({
  analysis,
  analysisId,
  narrative,
  defaultExpanded = false,
  onCorrect,
  canSubmitFeedback = true,
}: PatentRiskCardProps) {
  const [expandedState, setExpandedState] = useState(() => ({
    defaultExpanded,
    expanded: defaultExpanded,
    patentId: analysis.patent_id,
  }));
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const expanded =
    expandedState.patentId === analysis.patent_id &&
    expandedState.defaultExpanded === defaultExpanded
      ? expandedState.expanded
      : defaultExpanded;

  const handleCorrectClick = () => {
    if (onCorrect) {
      onCorrect();
    } else if (analysisId) {
      setFeedbackOpen(true);
    }
  };

  return (
    <>
      <Card className={getRiskBorderClass(analysis.risk_level)}>
        <PatentRiskCardSummary
          analysis={analysis}
          expanded={expanded}
          onToggle={() =>
            setExpandedState({
              defaultExpanded,
              expanded: !expanded,
              patentId: analysis.patent_id,
            })
          }
        />
        {expanded && (
          <CardContent className="space-y-4 pt-0">
            <PatentRiskCardContent
              analysis={analysis}
              narrative={narrative}
              showCorrectAssessmentButton={Boolean(
                onCorrect || (analysisId && canSubmitFeedback),
              )}
              onCorrectClick={handleCorrectClick}
            />
          </CardContent>
        )}
      </Card>

      {/* Feedback modal */}
      {analysisId && canSubmitFeedback ? (
        <FeedbackModal
          analysisId={analysisId}
          patentId={analysis.patent_id}
          currentRisk={analysis.risk_level}
          open={feedbackOpen}
          onOpenChange={setFeedbackOpen}
        />
      ) : null}
    </>
  );
}
