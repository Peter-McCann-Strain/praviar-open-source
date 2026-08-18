"use client";

import { cn } from "@/lib/utils";
import {
  ANNOTATION_TYPES,
  selectClass,
  textareaClass,
} from "./feedback-modal-constants";

interface FeedbackModalTextPanelProps {
  textSection: string;
  textSpan: string;
  annotationType: string;
  textCorrection: string;
  onTextSectionChange: (value: string) => void;
  onTextSpanChange: (value: string) => void;
  onAnnotationTypeChange: (value: string) => void;
  onTextCorrectionChange: (value: string) => void;
}

export function FeedbackModalTextPanel({
  textSection,
  textSpan,
  annotationType,
  textCorrection,
  onTextSectionChange,
  onTextSpanChange,
  onAnnotationTypeChange,
  onTextCorrectionChange,
}: FeedbackModalTextPanelProps) {
  return (
    <>
      <div className="space-y-2">
        <label
          htmlFor="feedback-text-section"
          className="text-sm font-medium text-[var(--text-primary)]"
        >
          Section
        </label>
        <select
          id="feedback-text-section"
          value={textSection}
          onChange={(e) => onTextSectionChange(e.target.value)}
          className={selectClass}
        >
          <option value="executive_summary">Executive Summary</option>
          <option value="narrative">Patent Narrative</option>
          <option value="risk_summary">Risk Summary</option>
          <option value="design_around">Design-Around</option>
          <option value="invalidity">Invalidity</option>
        </select>
      </div>

      <div className="space-y-1">
        <label
          htmlFor="feedback-text-span"
          className="text-xs font-medium text-[var(--text-secondary)]"
        >
          Text Span
        </label>
        <textarea
          id="feedback-text-span"
          value={textSpan}
          onChange={(e) => onTextSpanChange(e.target.value)}
          placeholder="Paste or type the text being annotated..."
          rows={2}
          className={textareaClass}
        />
      </div>

      <div className="space-y-2">
        <p
          id="feedback-annotation-type-label"
          className="text-sm font-medium text-[var(--text-primary)]"
        >
          Annotation Type
        </p>
        <div
          className="grid grid-cols-2 gap-2"
          role="group"
          aria-labelledby="feedback-annotation-type-label"
        >
          {ANNOTATION_TYPES.map((annotationTypeOption) => (
            <button
              key={annotationTypeOption.value}
              type="button"
              onClick={() => onAnnotationTypeChange(annotationTypeOption.value)}
              aria-pressed={annotationType === annotationTypeOption.value}
              className={cn(
                "rounded-lg border px-3 py-2 text-xs font-medium transition-colors",
                annotationType === annotationTypeOption.value
                  ? annotationTypeOption.value === "well_done"
                    ? "border-success bg-success/10 text-success"
                    : "border-warning bg-warning/10 text-warning"
                  : "border-[var(--border-default)] bg-[var(--surface-muted)] text-[var(--text-tertiary)] hover:border-[var(--border-emphasis)]",
              )}
            >
              {annotationTypeOption.label}
            </button>
          ))}
        </div>
      </div>

      {annotationType && annotationType !== "well_done" && (
        <div className="space-y-1">
          <label
            htmlFor="feedback-text-correction"
            className="text-xs font-medium text-[var(--text-secondary)]"
          >
            Correction
          </label>
          <textarea
            id="feedback-text-correction"
            value={textCorrection}
            onChange={(e) => onTextCorrectionChange(e.target.value)}
            placeholder="Corrected text..."
            rows={3}
            className={textareaClass}
          />
        </div>
      )}
    </>
  );
}
