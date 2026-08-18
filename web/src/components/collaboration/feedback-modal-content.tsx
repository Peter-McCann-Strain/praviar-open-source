"use client";

import { DialogContent } from "@/components/ui/dialog";
import type { FeedbackModalState } from "./feedback-modal-state";
import { FeedbackModalActions } from "./feedback-modal-actions";
import { FeedbackModalClaimPanel } from "./feedback-modal-claim-panel";
import { FeedbackModalHeader } from "./feedback-modal-header";
import { FeedbackModalPatentPanel } from "./feedback-modal-patent-panel";
import { FeedbackModalReportPanel } from "./feedback-modal-report-panel";
import { FeedbackModalTabs } from "./feedback-modal-tabs";
import { FeedbackModalTextPanel } from "./feedback-modal-text-panel";

interface FeedbackModalContentProps {
  patentId: string;
  currentRisk: string;
  isPending: boolean;
  onCancel: () => void;
  onSubmit: () => void;
  state: FeedbackModalState;
}

export function FeedbackModalContent({
  patentId,
  currentRisk,
  isPending,
  onCancel,
  onSubmit,
  state,
}: FeedbackModalContentProps) {
  const reportAssessmentComplete =
    state.riskCorrect !== null &&
    state.accuracy !== null &&
    (state.riskCorrect !== false || state.correctedRisk.length > 0);

  return (
    <DialogContent className="max-w-lg p-4 sm:p-6">
      <FeedbackModalHeader patentId={patentId} />

      <FeedbackModalTabs
        activeTab={state.activeTab}
        hasPatentContext={Boolean(patentId)}
        onTabChange={state.setActiveTab}
      />

      <div
        className="space-y-5 pt-1 max-h-[50vh] overflow-y-auto"
        role="tabpanel"
        id={`feedback-panel-${state.activeTab}`}
        aria-labelledby={`feedback-tab-${state.activeTab}`}
        tabIndex={0}
      >
        {state.activeTab === "report" && (
          <FeedbackModalReportPanel
            currentRisk={currentRisk}
            riskCorrect={state.riskCorrect}
            correctedRisk={state.correctedRisk}
            accuracy={state.accuracy}
            notes={state.notes}
            onRiskCorrectChange={state.setRiskCorrect}
            onCorrectedRiskChange={state.setCorrectedRisk}
            onAccuracyChange={state.setAccuracy}
            onNotesChange={state.setNotes}
          />
        )}

        {state.activeTab === "patent" && (
          <FeedbackModalPatentPanel
            patentIssueType={state.patentIssueType}
            patentSeverity={state.patentSeverity}
            patentOriginal={state.patentOriginal}
            patentCorrected={state.patentCorrected}
            patentReasoning={state.patentReasoning}
            onPatentIssueTypeChange={state.setPatentIssueType}
            onPatentSeverityChange={state.setPatentSeverity}
            onPatentOriginalChange={state.setPatentOriginal}
            onPatentCorrectedChange={state.setPatentCorrected}
            onPatentReasoningChange={state.setPatentReasoning}
          />
        )}

        {state.activeTab === "claim" && (
          <FeedbackModalClaimPanel
            claimNumber={state.claimNumber}
            elementIndex={state.elementIndex}
            mappingCorrect={state.mappingCorrect}
            correctedMapping={state.correctedMapping}
            claimNotes={state.claimNotes}
            onClaimNumberChange={state.setClaimNumber}
            onElementIndexChange={state.setElementIndex}
            onMappingCorrectChange={state.setMappingCorrect}
            onCorrectedMappingChange={state.setCorrectedMapping}
            onClaimNotesChange={state.setClaimNotes}
          />
        )}

        {state.activeTab === "text" && (
          <FeedbackModalTextPanel
            textSection={state.textSection}
            textSpan={state.textSpan}
            annotationType={state.annotationType}
            textCorrection={state.textCorrection}
            onTextSectionChange={state.setTextSection}
            onTextSpanChange={state.setTextSpan}
            onAnnotationTypeChange={state.setAnnotationType}
            onTextCorrectionChange={state.setTextCorrection}
          />
        )}
      </div>

      {!reportAssessmentComplete ? (
        <p role="status" className="text-xs leading-5 text-warning">
          Complete the overall risk decision and AI accuracy rating before
          submitting structured feedback.
        </p>
      ) : null}

      <FeedbackModalActions
        onCancel={onCancel}
        onSubmit={onSubmit}
        isPending={isPending}
        submitDisabled={!reportAssessmentComplete}
      />
    </DialogContent>
  );
}
