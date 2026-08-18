"use client";

import { Dialog } from "@/components/ui/dialog";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useSubmitFeedback, type FeedbackPayload } from "@/hooks/use-feedback";
import { useToastStore } from "@/stores/toast-store";
import { logError } from "@/lib/error-logger";
import { FeedbackModalContent } from "./feedback-modal-content";
import { buildFeedbackPayload } from "./feedback-modal-payload";
import { useFeedbackModalState } from "./feedback-modal-state";

interface FeedbackModalProps {
  analysisId: string;
  patentId: string;
  currentRisk: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function FeedbackModal({
  analysisId,
  patentId,
  currentRisk,
  open,
  onOpenChange,
}: FeedbackModalProps) {
  const token = useAuthToken();
  const toast = useToastStore();
  const feedbackMutation = useSubmitFeedback(token);
  const state = useFeedbackModalState();

  const handleSubmit = async () => {
    const accuracy = state.accuracy;
    const riskCorrect = state.riskCorrect;
    if (
      accuracy === null ||
      riskCorrect === null ||
      (riskCorrect === false && !state.correctedRisk)
    ) {
      toast.addToast(
        "Complete the overall risk decision and AI accuracy rating before submitting feedback.",
        "warning",
      );
      return;
    }

    const payload: FeedbackPayload = buildFeedbackPayload({
      analysisId,
      patentId,
      accuracy,
      riskCorrect,
      correctedRisk: state.correctedRisk,
      notes: state.notes,
      patentIssueType: state.patentIssueType,
      patentSeverity: state.patentSeverity,
      patentOriginal: state.patentOriginal,
      patentCorrected: state.patentCorrected,
      patentReasoning: state.patentReasoning,
      claimNumber: state.claimNumber,
      elementIndex: state.elementIndex,
      mappingCorrect: state.mappingCorrect,
      correctedMapping: state.correctedMapping,
      claimNotes: state.claimNotes,
      textSection: state.textSection,
      textSpan: state.textSpan,
      annotationType: state.annotationType,
      textCorrection: state.textCorrection,
    });

    try {
      await feedbackMutation.mutateAsync(payload);
      toast.addToast("Feedback submitted successfully", "success");
      state.reset();
      onOpenChange(false);
    } catch (err) {
      logError(err, {
        source: "FeedbackModal",
        extra: { action: "submit_feedback" },
      });
      toast.addToast("Failed to submit feedback", "error");
    }
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) state.reset();
    onOpenChange(nextOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <FeedbackModalContent
        patentId={patentId}
        currentRisk={currentRisk}
        isPending={feedbackMutation.isPending}
        onCancel={() => handleOpenChange(false)}
        onSubmit={handleSubmit}
        state={state}
      />
    </Dialog>
  );
}
