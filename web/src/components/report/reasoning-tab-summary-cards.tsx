"use client";

import { Card, CardContent } from "@/components/ui/card";
import { formatDuration, formatTokens } from "./reasoning-tab-helpers";

interface ReasoningTabSummaryCardsProps {
  traceCount: number;
  totalRounds: number;
  totalTokens: number;
  totalDuration: number;
}

function SummaryCard({ value, label }: { value: string; label: string }) {
  return (
    <Card>
      <CardContent className="p-4 text-center">
        <p className="text-2xl font-bold text-[var(--text-primary)]">{value}</p>
        <p className="text-xs text-[var(--text-secondary)]">{label}</p>
      </CardContent>
    </Card>
  );
}

export function ReasoningTabSummaryCards({
  traceCount,
  totalRounds,
  totalTokens,
  totalDuration,
}: ReasoningTabSummaryCardsProps) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <SummaryCard value={String(traceCount)} label="Review Notes" />
      <SummaryCard value={String(totalRounds)} label="Review Passes" />
      <SummaryCard value={formatTokens(totalTokens)} label="Total Effort" />
      <SummaryCard
        value={formatDuration(totalDuration)}
        label="Total Duration"
      />
    </div>
  );
}
