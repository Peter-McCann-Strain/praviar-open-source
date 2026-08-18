"use client";

import { Badge } from "@/components/ui/badge";
import type { ReasoningTrace } from "@praviar/shared-types";
import { ReasoningTraceCard } from "./reasoning-tab-trace-card";

interface ReasoningPatentGroupProps {
  patentId: string;
  traces: ReasoningTrace[];
}

export function ReasoningPatentGroup({
  patentId,
  traces,
}: ReasoningPatentGroupProps) {
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-[var(--text-primary)] flex items-center gap-2">
        <span className="font-mono">
          {patentId === "general" ? "General" : patentId}
        </span>
        <Badge variant="secondary" className="text-xs">
          {traces.length} agent{traces.length !== 1 ? "s" : ""}
        </Badge>
      </h3>
      {traces.map((trace, i) => (
        <ReasoningTraceCard
          key={`${trace.agent_type}-${trace.patent_id}-${i}`}
          trace={trace}
        />
      ))}
    </div>
  );
}
