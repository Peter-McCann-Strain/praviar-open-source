"use client";

import { Card, CardContent } from "@/components/ui/card";

export function TokenUsageSummaryCard({
  totalInputTokens,
  totalOutputTokens,
}: {
  totalInputTokens?: number | null;
  totalOutputTokens?: number | null;
}) {
  const inputTokens =
    typeof totalInputTokens === "number" && Number.isFinite(totalInputTokens)
      ? totalInputTokens
      : null;
  const outputTokens =
    typeof totalOutputTokens === "number" && Number.isFinite(totalOutputTokens)
      ? totalOutputTokens
      : null;
  const totalTokens =
    inputTokens != null && outputTokens != null
      ? inputTokens + outputTokens
      : null;

  return (
    <Card>
      <CardContent className="p-6">
        <div className="grid grid-cols-3 gap-6">
          <div>
            <p className="text-xs text-[var(--text-tertiary)] mb-1">
              Evidence Context
            </p>
            <p className="text-lg font-bold text-[var(--text-primary)]">
              {formatTokenValue(totalInputTokens)}
            </p>
          </div>
          <div>
            <p className="text-xs text-[var(--text-tertiary)] mb-1">
              Review Output
            </p>
            <p className="text-lg font-bold text-[var(--text-primary)]">
              {formatTokenValue(totalOutputTokens)}
            </p>
          </div>
          <div>
            <p className="text-xs text-[var(--text-tertiary)] mb-1">
              Total Effort
            </p>
            <p className="text-lg font-bold text-[var(--text-primary)]">
              {formatTokenValue(totalTokens)}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function formatTokenValue(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value)
    ? `${(value / 1000).toFixed(1)}k`
    : "Not reported";
}
