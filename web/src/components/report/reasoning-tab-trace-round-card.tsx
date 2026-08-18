"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { AgentRound } from "@praviar/shared-types";
import { sanitizeReportDiagnosticText } from "./report-diagnostic-copy";
import { formatDuration } from "./reasoning-tab-helpers";

export function ReasoningTraceRoundCard({ round }: { round: AgentRound }) {
  const [expanded, setExpanded] = useState(false);
  const safeDecision = sanitizeTraceText(
    round.decision,
    "Decision note available.",
  );

  return (
    <div className="overflow-hidden rounded-lg border border-[var(--border-default)]">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex min-h-11 w-full flex-col gap-2 px-3 py-2 text-left transition-colors hover:bg-[var(--surface-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 sm:flex-row sm:items-center sm:justify-between"
      >
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {expanded ? (
            <ChevronDown className="h-3 w-3 text-[var(--text-tertiary)]" />
          ) : (
            <ChevronRight className="h-3 w-3 text-[var(--text-tertiary)]" />
          )}
          <span className="text-xs font-medium text-[var(--text-primary)]">
            Round {round.round_number}
          </span>
          {round.tool_calls.length > 0 && (
            <Badge variant="secondary" className="text-xs px-1.5 py-0">
              {round.tool_calls.length} tool
              {round.tool_calls.length !== 1 ? "s" : ""}
            </Badge>
          )}
        </div>
        {round.decision ? (
          <span
            className="min-w-0 max-w-full break-words text-xs text-[var(--text-tertiary)] sm:max-w-[200px] sm:truncate"
            title={safeDecision}
          >
            {safeDecision}
          </span>
        ) : null}
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-3 border-t border-[var(--border-subtle)]">
          {round.thinking_summary && (
            <div className="pt-2">
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)] mb-1">
                Review Basis
              </p>
              <p className="text-xs text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap">
                {sanitizeTraceText(
                  round.thinking_summary,
                  "Review basis available.",
                )}
              </p>
            </div>
          )}

          {round.tool_calls.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)] mb-1">
                Evidence Checks
              </p>
              <div className="space-y-1.5">
                {round.tool_calls.map((tc, i) => (
                  <div
                    key={i}
                    className="rounded-md bg-[var(--surface-muted)] p-2 text-xs"
                  >
                    <div className="flex min-w-0 flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                      <span
                        className="min-w-0 break-all font-mono text-[var(--brand-primary)] sm:max-w-[18rem] sm:truncate"
                        title={tc.tool_name}
                      >
                        {tc.tool_name}
                      </span>
                      <span className="shrink-0 text-[var(--text-tertiary)] tabular-nums">
                        {formatDuration(tc.duration_ms)}
                      </span>
                    </div>
                    {tc.tool_output_summary && (
                      <p
                        className="mt-1 overflow-hidden text-ellipsis whitespace-nowrap text-[var(--text-secondary)]"
                        title={sanitizeTraceText(
                          tc.tool_output_summary,
                          "Evidence check summary available.",
                        )}
                      >
                        {sanitizeTraceText(
                          tc.tool_output_summary,
                          "Evidence check summary available.",
                        )}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {round.observations && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)] mb-1">
                Findings
              </p>
              <p className="text-xs text-[var(--text-primary)] leading-relaxed">
                {sanitizeTraceText(round.observations, "Findings available.")}
              </p>
            </div>
          )}

          {Object.keys(round.scratchpad_delta).length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)] mb-1">
                Internal note withheld
              </p>
              <p className="rounded-md bg-[var(--surface-muted)] p-2 text-xs leading-relaxed text-[var(--text-secondary)]">
                Internal scratchpad changes are retained for audit review and
                are not displayed in the customer report.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function sanitizeTraceText(value: string | null | undefined, fallback: string) {
  return sanitizeReportDiagnosticText(value, fallback);
}
