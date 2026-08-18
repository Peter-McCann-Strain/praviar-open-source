import type { FeedbackPayload } from "@/hooks/use-feedback";

export interface BuildFeedbackPayloadArgs {
  analysisId: string;
  patentId: string;
  accuracy: number;
  riskCorrect: boolean;
  correctedRisk: string;
  notes: string;
  patentIssueType: string;
  patentSeverity: string;
  patentOriginal: string;
  patentCorrected: string;
  patentReasoning: string;
  claimNumber: string;
  elementIndex: string;
  mappingCorrect: boolean | null;
  correctedMapping: string;
  claimNotes: string;
  textSection: string;
  textSpan: string;
  annotationType: string;
  textCorrection: string;
}

export function buildFeedbackPayload({
  analysisId,
  patentId,
  accuracy,
  riskCorrect,
  correctedRisk,
  notes,
  patentIssueType,
  patentSeverity,
  patentOriginal,
  patentCorrected,
  patentReasoning,
  claimNumber,
  elementIndex,
  mappingCorrect,
  correctedMapping,
  claimNotes,
  textSection,
  textSpan,
  annotationType,
  textCorrection,
}: BuildFeedbackPayloadArgs): FeedbackPayload {
  const corrections: FeedbackPayload["corrections"] = [];
  const reportNotes = notes.trim();
  if (reportNotes) {
    corrections.push({
      patent_id: patentId,
      field: "report_notes",
      original_value: "",
      corrected_value: "",
      notes: reportNotes,
    });
  }
  if (patentIssueType) {
    corrections.push({
      patent_id: patentId,
      field: `patent:${patentIssueType}:${patentSeverity}`,
      original_value: patentOriginal,
      corrected_value: patentCorrected,
      notes: patentReasoning,
    });
  }
  if (claimNumber) {
    corrections.push({
      patent_id: patentId,
      field: `claim:${claimNumber}:element:${parseInt(elementIndex, 10) || 0}:mapping:${
        mappingCorrect === true
          ? "correct"
          : mappingCorrect === false
            ? "incorrect"
            : "unreviewed"
      }`,
      original_value: "",
      corrected_value: correctedMapping,
      notes: claimNotes,
    });
  }
  if (textSpan && annotationType) {
    corrections.push({
      patent_id: patentId,
      field: `text:${textSection}:${annotationType}`,
      original_value: textSpan,
      corrected_value: textCorrection,
      notes: "",
    });
  }

  return {
    analysis_id: analysisId,
    overall_accuracy: accuracy / 100,
    risk_level_correct: riskCorrect,
    corrected_risk:
      riskCorrect === false && correctedRisk ? correctedRisk : undefined,
    corrections,
  };
}
