import type { ModelUsageResponse } from "@/hooks/use-admin-analytics";

export const PERIOD_OPTIONS = [
  { label: "7 days", value: "week" },
  { label: "30 days", value: "month" },
  { label: "90 days", value: "quarter" },
] as const;

export const STEP_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--chart-6)",
  "var(--chart-7)",
  "var(--chart-8)",
];

export const MODEL_COLORS = [
  "var(--chart-model-1)",
  "var(--chart-model-2)",
  "var(--chart-model-3)",
  "var(--chart-model-4)",
  "var(--chart-model-5)",
  "var(--chart-model-6)",
];

export function formatCurrency(value: number): string {
  if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}k`;
  if (value >= 1) return `$${value.toFixed(2)}`;
  return `$${value.toFixed(4)}`;
}

export function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export function formatDuration(seconds: number | null): string {
  if (seconds === null) return "N/A";
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  return `${(seconds / 60).toFixed(1)}m`;
}

export function formatPercentLike(value: number | null): string {
  if (value === null) return "N/A";
  return `${value.toFixed(value % 1 === 0 ? 0 : 1)}%`;
}

export interface ModelDonutDatum {
  id: string;
  name: string;
  fullName: string;
  value: number;
  cost: number;
  tokens: string;
}

export function buildModelDonutData(modelData: ModelUsageResponse | undefined) {
  if (!modelData?.models) return [];
  const displayNameCounts = new Map<string, number>();
  const baseNames = modelData.models.map(
    (model) => model.model_name.split("/").pop() ?? model.model_name,
  );

  for (const baseName of baseNames) {
    displayNameCounts.set(baseName, (displayNameCounts.get(baseName) ?? 0) + 1);
  }

  return modelData.models.map(
    (m, index): ModelDonutDatum => ({
      id: `${m.model_name}-${index}`,
      name:
        displayNameCounts.get(baseNames[index]) === 1
          ? baseNames[index]
          : m.model_name,
      fullName: m.model_name,
      value: m.total_tokens,
      cost: m.estimated_cost_usd,
      tokens: formatTokens(m.total_tokens),
    }),
  );
}

export function buildCostAnalyticsCsv(
  dailyCosts: Array<{
    date: string;
    total_cost_usd: number;
    analysis_count: number;
    total_input_tokens: number;
    total_output_tokens: number;
  }>,
  metadata: {
    period: string;
    generatedAt: string;
  },
): string {
  const escapeCell = (value: string) => {
    if (/[",\n\r]/.test(value)) {
      return `"${value.replace(/"/g, '""')}"`;
    }
    return value;
  };

  const rows = [
    ["Schema", "Praviar analytics costs v1"],
    ["Period", metadata.period],
    ["Generated At", metadata.generatedAt],
    [],
    ["Date", "Cost (USD)", "Analyses", "Input Tokens", "Output Tokens"],
    ...dailyCosts.map((d) => [
      d.date,
      d.total_cost_usd.toFixed(4),
      String(d.analysis_count),
      String(d.total_input_tokens),
      String(d.total_output_tokens),
    ]),
  ];
  return rows.map((r) => r.map(escapeCell).join(",")).join("\n");
}
