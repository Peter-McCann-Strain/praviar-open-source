"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { sanitizeReportDiagnosticText } from "./report-diagnostic-copy";

interface ThinkingPanelProps {
  patentId: string;
  text: string;
}

export function ThinkingPanel({ patentId, text }: ThinkingPanelProps) {
  const [open, setOpen] = useState(false);
  const safeText = sanitizeReportDiagnosticText(
    text,
    "Review basis note available.",
  );

  return (
    <div className="overflow-hidden rounded-lg border border-[var(--border-default)]">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 p-3 text-left transition-colors hover:bg-[var(--surface-muted)]"
      >
        {open ? (
          <ChevronDown className="h-4 w-4 text-[var(--text-tertiary)]" />
        ) : (
          <ChevronRight className="h-4 w-4 text-[var(--text-tertiary)]" />
        )}
        <span className="min-w-0 text-sm text-[var(--text-primary)] [overflow-wrap:anywhere]">
          {patentId} - Review basis note
        </span>
      </button>
      {open && (
        <div className="border-t border-[var(--border-subtle)] bg-[var(--surface-muted)] p-4">
          <pre className="max-h-72 overflow-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-[var(--text-secondary)] [overflow-wrap:anywhere]">
            {safeText}
          </pre>
        </div>
      )}
    </div>
  );
}
