"use client";

import { cn } from "@/lib/utils";
import {
  ISSUE_TYPES,
  inputClass,
  selectClass,
  textareaClass,
} from "./feedback-modal-constants";

const SEVERITIES = ["critical", "major", "minor"] as const;

interface FeedbackModalPatentPanelProps {
  patentIssueType: string;
  patentSeverity: string;
  patentOriginal: string;
  patentCorrected: string;
  patentReasoning: string;
  onPatentIssueTypeChange: (value: string) => void;
  onPatentSeverityChange: (value: string) => void;
  onPatentOriginalChange: (value: string) => void;
  onPatentCorrectedChange: (value: string) => void;
  onPatentReasoningChange: (value: string) => void;
}

export function FeedbackModalPatentPanel({
  patentIssueType,
  patentSeverity,
  patentOriginal,
  patentCorrected,
  patentReasoning,
  onPatentIssueTypeChange,
  onPatentSeverityChange,
  onPatentOriginalChange,
  onPatentCorrectedChange,
  onPatentReasoningChange,
}: FeedbackModalPatentPanelProps) {
  return (
    <>
      <div className="space-y-2">
        <label
          htmlFor="feedback-patent-issue-type"
          className="text-sm font-medium text-[var(--text-primary)]"
        >
          Issue Type
        </label>
        <select
          id="feedback-patent-issue-type"
          value={patentIssueType}
          onChange={(e) => onPatentIssueTypeChange(e.target.value)}
          className={selectClass}
        >
          <option value="">Select issue type...</option>
          {ISSUE_TYPES.map((issueType) => (
            <option key={issueType.value} value={issueType.value}>
              {issueType.label}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-2">
        <p
          id="feedback-patent-severity-label"
          className="text-sm font-medium text-[var(--text-primary)]"
        >
          Severity
        </p>
        <div
          className="grid grid-cols-3 gap-2"
          role="group"
          aria-labelledby="feedback-patent-severity-label"
        >
          {SEVERITIES.map((severity) => (
            <button
              key={severity}
              type="button"
              onClick={() => onPatentSeverityChange(severity)}
              aria-pressed={severity === patentSeverity}
              className={cn(
                "rounded-lg border px-2 py-2 text-xs font-medium capitalize transition-colors min-[360px]:px-3",
                severity === patentSeverity
                  ? severity === "critical"
                    ? "border-error bg-error/10 text-error"
                    : severity === "major"
                      ? "border-warning bg-warning/10 text-warning"
                      : "border-info bg-info/10 text-info"
                  : "border-[var(--border-default)] bg-[var(--surface-muted)] text-[var(--text-tertiary)] hover:border-[var(--border-emphasis)]",
              )}
            >
              {severity}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <label
            htmlFor="feedback-patent-original"
            className="text-xs font-medium text-[var(--text-secondary)]"
          >
            Original Value
          </label>
          <input
            id="feedback-patent-original"
            value={patentOriginal}
            onChange={(e) => onPatentOriginalChange(e.target.value)}
            placeholder="What the pipeline produced"
            className={inputClass}
          />
        </div>
        <div className="space-y-1">
          <label
            htmlFor="feedback-patent-corrected"
            className="text-xs font-medium text-[var(--text-secondary)]"
          >
            Corrected Value
          </label>
          <input
            id="feedback-patent-corrected"
            value={patentCorrected}
            onChange={(e) => onPatentCorrectedChange(e.target.value)}
            placeholder="What it should be"
            className={inputClass}
          />
        </div>
      </div>

      <div className="space-y-1">
        <label
          htmlFor="feedback-patent-reasoning"
          className="text-xs font-medium text-[var(--text-secondary)]"
        >
          Reasoning
        </label>
        <textarea
          id="feedback-patent-reasoning"
          value={patentReasoning}
          onChange={(e) => onPatentReasoningChange(e.target.value)}
          placeholder="Why this correction is needed..."
          rows={3}
          className={textareaClass}
        />
      </div>
    </>
  );
}
