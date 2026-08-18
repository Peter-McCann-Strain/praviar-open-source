"use client";

import { Gauge, MessageSquareText, ThumbsDown, ThumbsUp } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  RISK_LEVELS,
  riskColor,
  textareaClass,
} from "./feedback-modal-constants";

interface FeedbackModalReportPanelProps {
  currentRisk: string;
  riskCorrect: boolean | null;
  correctedRisk: string;
  accuracy: number | null;
  notes: string;
  onRiskCorrectChange: (value: boolean) => void;
  onCorrectedRiskChange: (value: string) => void;
  onAccuracyChange: (value: number) => void;
  onNotesChange: (value: string) => void;
}

export function FeedbackModalReportPanel({
  currentRisk,
  riskCorrect,
  correctedRisk,
  accuracy,
  notes,
  onRiskCorrectChange,
  onCorrectedRiskChange,
  onAccuracyChange,
  onNotesChange,
}: FeedbackModalReportPanelProps) {
  return (
    <>
      <div className="space-y-3">
        <p
          id="feedback-risk-correct-label"
          className="flex items-center gap-2 text-sm font-medium text-[var(--text-primary)]"
        >
          <Gauge className="h-4 w-4 text-brand-primary" aria-hidden="true" />
          Is the overall risk level correct?
        </p>
        <p className="text-xs text-[var(--text-tertiary)]">
          Current assessment:{" "}
          <span
            className={cn("font-semibold uppercase", {
              "text-error": currentRisk.toLowerCase() === "high",
              "text-warning": currentRisk.toLowerCase() === "medium",
              "text-info": currentRisk.toLowerCase() === "low",
              "text-success": currentRisk.toLowerCase() === "clear",
            })}
          >
            {currentRisk}
          </span>
        </p>
        <div
          className="flex gap-3"
          role="group"
          aria-labelledby="feedback-risk-correct-label"
        >
          <button
            type="button"
            onClick={() => onRiskCorrectChange(true)}
            aria-pressed={riskCorrect === true}
            className={cn(
              "flex-1 flex items-center justify-center gap-2 rounded-lg border p-3 text-sm font-medium transition-colors",
              riskCorrect === true
                ? "border-success bg-success/10 text-success"
                : "border-[var(--border-default)] bg-[var(--surface-muted)] text-[var(--text-secondary)] hover:border-[var(--border-emphasis)]",
            )}
          >
            <ThumbsUp className="h-4 w-4" aria-hidden="true" />
            Yes
          </button>
          <button
            type="button"
            onClick={() => onRiskCorrectChange(false)}
            aria-pressed={riskCorrect === false}
            className={cn(
              "flex-1 flex items-center justify-center gap-2 rounded-lg border p-3 text-sm font-medium transition-colors",
              riskCorrect === false
                ? "border-error bg-error/10 text-error"
                : "border-[var(--border-default)] bg-[var(--surface-muted)] text-[var(--text-secondary)] hover:border-[var(--border-emphasis)]",
            )}
          >
            <ThumbsDown className="h-4 w-4" aria-hidden="true" />
            No
          </button>
        </div>
      </div>

      {riskCorrect === false && (
        <div className="space-y-2">
          <p
            id="feedback-correct-risk-label"
            className="text-sm font-medium text-[var(--text-primary)]"
          >
            Correct risk level
          </p>
          <div
            className="grid grid-cols-2 gap-2 min-[360px]:grid-cols-4"
            role="group"
            aria-labelledby="feedback-correct-risk-label"
          >
            {RISK_LEVELS.map((level) => (
              <button
                key={level}
                type="button"
                onClick={() => onCorrectedRiskChange(level)}
                aria-pressed={correctedRisk === level}
                className={cn(
                  "rounded-lg border px-2 py-2 text-xs font-semibold uppercase transition-colors",
                  correctedRisk === level
                    ? riskColor(level)
                    : "border-[var(--border-default)] bg-[var(--surface-muted)] text-[var(--text-tertiary)] hover:border-[var(--border-emphasis)]",
                )}
              >
                {level}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <label
            htmlFor="feedback-overall-accuracy"
            className="text-sm font-medium text-[var(--text-primary)]"
          >
            Overall AI accuracy
          </label>
          <span className="text-sm font-mono text-brand-primary">
            {accuracy != null ? `${accuracy}%` : "\u2014"}
          </span>
        </div>
        <input
          id="feedback-overall-accuracy"
          type="range"
          min={0}
          max={100}
          step={5}
          value={accuracy ?? 50}
          onChange={(e) => onAccuracyChange(Number(e.target.value))}
          className="w-full h-2 rounded-full appearance-none bg-[var(--surface-active)] accent-brand-primary cursor-pointer
            [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4
            [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-brand-primary [&::-webkit-slider-thumb]:shadow-lg
            [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:rounded-full
            [&::-moz-range-thumb]:bg-brand-primary [&::-moz-range-thumb]:border-0"
        />
      </div>

      <div className="space-y-2">
        <label
          htmlFor="feedback-report-notes"
          className="flex items-center gap-2 text-sm font-medium text-[var(--text-primary)]"
        >
          <MessageSquareText
            className="h-4 w-4 text-brand-primary"
            aria-hidden="true"
          />
          Notes
        </label>
        <textarea
          id="feedback-report-notes"
          value={notes}
          onChange={(e) => onNotesChange(e.target.value)}
          placeholder="General comments on the report quality..."
          rows={3}
          className={textareaClass}
        />
      </div>
    </>
  );
}
