"use client";

import { ThumbsDown, ThumbsUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { inputClass, textareaClass } from "./feedback-modal-constants";

interface FeedbackModalClaimPanelProps {
  claimNumber: string;
  elementIndex: string;
  mappingCorrect: boolean | null;
  correctedMapping: string;
  claimNotes: string;
  onClaimNumberChange: (value: string) => void;
  onElementIndexChange: (value: string) => void;
  onMappingCorrectChange: (value: boolean) => void;
  onCorrectedMappingChange: (value: string) => void;
  onClaimNotesChange: (value: string) => void;
}

export function FeedbackModalClaimPanel({
  claimNumber,
  elementIndex,
  mappingCorrect,
  correctedMapping,
  claimNotes,
  onClaimNumberChange,
  onElementIndexChange,
  onMappingCorrectChange,
  onCorrectedMappingChange,
  onClaimNotesChange,
}: FeedbackModalClaimPanelProps) {
  return (
    <>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <label
            htmlFor="feedback-claim-number"
            className="text-xs font-medium text-[var(--text-secondary)]"
          >
            Claim Number
          </label>
          <input
            id="feedback-claim-number"
            type="number"
            min={1}
            value={claimNumber}
            onChange={(e) => onClaimNumberChange(e.target.value)}
            placeholder="e.g. 1"
            className={inputClass}
          />
        </div>
        <div className="space-y-1">
          <label
            htmlFor="feedback-element-index"
            className="text-xs font-medium text-[var(--text-secondary)]"
          >
            Element Index
          </label>
          <input
            id="feedback-element-index"
            type="number"
            min={0}
            value={elementIndex}
            onChange={(e) => onElementIndexChange(e.target.value)}
            placeholder="e.g. 0"
            className={inputClass}
          />
        </div>
      </div>

      <div className="space-y-3">
        <p
          id="feedback-mapping-correct-label"
          className="text-sm font-medium text-[var(--text-primary)]"
        >
          Is the element mapping correct?
        </p>
        <div
          className="flex gap-3"
          role="group"
          aria-labelledby="feedback-mapping-correct-label"
        >
          <button
            type="button"
            onClick={() => onMappingCorrectChange(true)}
            aria-pressed={mappingCorrect === true}
            className={cn(
              "flex-1 flex items-center justify-center gap-2 rounded-lg border p-3 text-sm font-medium transition-colors",
              mappingCorrect === true
                ? "border-success bg-success/10 text-success"
                : "border-[var(--border-default)] bg-[var(--surface-muted)] text-[var(--text-secondary)] hover:border-[var(--border-emphasis)]",
            )}
          >
            <ThumbsUp className="h-4 w-4" aria-hidden="true" />
            Yes
          </button>
          <button
            type="button"
            onClick={() => onMappingCorrectChange(false)}
            aria-pressed={mappingCorrect === false}
            className={cn(
              "flex-1 flex items-center justify-center gap-2 rounded-lg border p-3 text-sm font-medium transition-colors",
              mappingCorrect === false
                ? "border-error bg-error/10 text-error"
                : "border-[var(--border-default)] bg-[var(--surface-muted)] text-[var(--text-secondary)] hover:border-[var(--border-emphasis)]",
            )}
          >
            <ThumbsDown className="h-4 w-4" aria-hidden="true" />
            No
          </button>
        </div>
      </div>

      {mappingCorrect === false && (
        <div className="space-y-1">
          <label
            htmlFor="feedback-corrected-mapping"
            className="text-xs font-medium text-[var(--text-secondary)]"
          >
            Corrected Mapping
          </label>
          <input
            id="feedback-corrected-mapping"
            value={correctedMapping}
            onChange={(e) => onCorrectedMappingChange(e.target.value)}
            placeholder="Correct element status (met/not_met/partially_met/unclear)"
            className={inputClass}
          />
        </div>
      )}

      <div className="space-y-1">
        <label
          htmlFor="feedback-claim-notes"
          className="text-xs font-medium text-[var(--text-secondary)]"
        >
          Notes
        </label>
        <textarea
          id="feedback-claim-notes"
          value={claimNotes}
          onChange={(e) => onClaimNotesChange(e.target.value)}
          placeholder="Additional claim-level notes..."
          rows={3}
          className={textareaClass}
        />
      </div>
    </>
  );
}
