"use client";

import { useId, useState } from "react";
import { ChevronDown, ChevronRight, Clock, Cpu, Zap } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { ReasoningTrace } from "@praviar/shared-types";
import { sanitizeReportDiagnosticText } from "./report-diagnostic-copy";
import {
  AGENT_COLORS,
  formatDuration,
  formatTokens,
} from "./reasoning-tab-helpers";
import { ReasoningTraceConfidenceBar } from "./reasoning-tab-trace-confidence-bar";
import { ReasoningTraceRoundCard } from "./reasoning-tab-trace-round-card";

export function ReasoningTraceCard({ trace }: { trace: ReasoningTrace }) {
  const [expanded, setExpanded] = useState(false);
  const contentId = useId();
  const agentLabel = trace.agent_type.replace(/_/g, " ");
  const agentColor =
    AGENT_COLORS[trace.agent_type] ??
    "bg-[var(--surface-hover)] text-[var(--text-secondary)]";

  return (
    <Card>
      <CardHeader className="p-0">
        <button
          type="button"
          aria-controls={contentId}
          aria-expanded={expanded}
          aria-label={`${expanded ? "Collapse" : "Expand"} ${agentLabel} decision note for ${trace.patent_id}`}
          className="w-full cursor-pointer rounded-t-lg p-6 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
          onClick={() => setExpanded(!expanded)}
        >
          <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              {expanded ? (
                <ChevronDown
                  aria-hidden="true"
                  className="h-4 w-4 text-[var(--text-tertiary)] flex-shrink-0"
                />
              ) : (
                <ChevronRight
                  aria-hidden="true"
                  className="h-4 w-4 text-[var(--text-tertiary)] flex-shrink-0"
                />
              )}
              <Badge className={cn("text-xs", agentColor)}>{agentLabel}</Badge>
              <span
                className="min-w-0 max-w-full break-all font-mono text-sm text-[var(--text-primary)] sm:max-w-[18rem] sm:truncate"
                title={trace.patent_id}
              >
                {trace.patent_id}
              </span>
            </div>
            <div className="flex min-w-0 flex-wrap items-center gap-3 sm:justify-end">
              <ReasoningTraceConfidenceBar value={trace.confidence} />
              <Badge
                variant="secondary"
                className="min-w-0 max-w-full gap-1 text-xs sm:max-w-[16rem]"
                title={trace.model}
              >
                <Cpu aria-hidden="true" className="h-2.5 w-2.5" />
                <span className="min-w-0 truncate">{trace.model}</span>
              </Badge>
            </div>
          </div>
        </button>
      </CardHeader>

      {expanded && (
        <CardContent
          id={contentId}
          role="region"
          aria-label={`${agentLabel} decision-note details for ${trace.patent_id}`}
          className="space-y-4 pt-0"
        >
          <div className="flex items-center gap-4 text-xs text-[var(--text-tertiary)]">
            <span className="flex items-center gap-1">
              <Zap aria-hidden="true" className="h-3 w-3" />
              {trace.rounds.length} round{trace.rounds.length !== 1 ? "s" : ""}
            </span>
            <span className="flex items-center gap-1">
              <Clock aria-hidden="true" className="h-3 w-3" />
              {formatDuration(trace.total_duration_ms)}
            </span>
            <span>
              {formatTokens(trace.total_input_tokens)} in /{" "}
              {formatTokens(trace.total_output_tokens)} out
            </span>
          </div>

          <div className="space-y-2">
            {trace.rounds.map((round) => (
              <ReasoningTraceRoundCard key={round.round_number} round={round} />
            ))}
          </div>

          {trace.self_critique && (
            <div className="rounded-lg border border-warning/20 bg-warning/5 p-3">
              <p className="text-xs font-semibold uppercase tracking-wider text-warning mb-1">
                Review Check
              </p>
              <p className="text-xs text-[var(--text-primary)] leading-relaxed">
                {sanitizeTraceText(
                  trace.self_critique,
                  "Review check available.",
                )}
              </p>
            </div>
          )}

          {trace.revisions_made.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)] mb-1">
                Updates Made
              </p>
              <ul className="space-y-1">
                {trace.revisions_made.map((rev, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-xs text-[var(--text-primary)]"
                  >
                    <span className="text-[var(--brand-primary)] mt-0.5 flex-shrink-0">
                      &bull;
                    </span>
                    {sanitizeTraceText(rev, "Revision note available.")}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {trace.final_output_summary && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)] mb-1">
                Decision Summary
              </p>
              <p className="text-xs text-[var(--text-primary)] leading-relaxed">
                {sanitizeTraceText(
                  trace.final_output_summary,
                  "Decision summary available.",
                )}
              </p>
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}

function sanitizeTraceText(value: string | null | undefined, fallback: string) {
  return sanitizeReportDiagnosticText(value, fallback);
}
