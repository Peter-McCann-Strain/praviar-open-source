import { useId } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { ModelUsageResponse } from "@/hooks/use-admin-analytics";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  MODEL_COLORS,
  type ModelDonutDatum,
  formatCurrency,
  formatPercentLike,
  formatTokens,
} from "@/components/admin-analytics/helpers";
import { AnalyticsPanelStatus } from "@/components/admin-analytics/status-state";
import { ModelTooltip } from "@/components/admin-analytics/tooltips";
import { ChartSwatch } from "@/components/charts/chart-swatch";
import { usePrefersReducedMotion } from "@/components/charts/use-prefers-reduced-motion";

interface ModelsTabProps {
  modelData: ModelUsageResponse | undefined;
  modelLoading: boolean;
  modelError?: unknown;
  modelDonutData: ModelDonutDatum[];
  onRetry: () => void;
}

function buildModelChartSummary(modelDonutData: ModelDonutDatum[]) {
  if (modelDonutData.length === 0) {
    return "No model token usage data available.";
  }

  const totalTokens = modelDonutData.reduce(
    (sum, model) => sum + model.value,
    0,
  );
  const totalCost = modelDonutData.reduce((sum, model) => sum + model.cost, 0);

  return `${formatTokens(totalTokens)} tokens and ${formatCurrency(
    totalCost,
  )} across ${modelDonutData.length} model${
    modelDonutData.length === 1 ? "" : "s"
  }; ${modelDonutData
    .map(
      (model) =>
        `${model.fullName} ${model.tokens} tokens at ${formatCurrency(
          model.cost,
        )}`,
    )
    .join("; ")}.`;
}

export function ModelsTab({
  modelData,
  modelLoading,
  modelError,
  modelDonutData,
  onRetry,
}: ModelsTabProps) {
  const descriptionId = `model-usage-chart-${useId().replace(/:/g, "")}`;
  const prefersReducedMotion = usePrefersReducedMotion();
  const modelChartSummary = buildModelChartSummary(modelDonutData);

  if (modelError && !modelData) {
    return (
      <AnalyticsPanelStatus
        title="Model telemetry unavailable"
        description="Model usage could not be loaded. Existing model settings and report state are unchanged."
        onRetry={onRetry}
      />
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Card>
        <CardHeader>
          <CardTitle aria-level={2} className="text-sm">
            Token Usage by Model
          </CardTitle>
        </CardHeader>
        <CardContent>
          {modelLoading ? (
            <div className="flex h-[280px] items-center justify-center">
              <div className="skeleton-shimmer h-full w-full rounded-md bg-[var(--skeleton-base)]" />
            </div>
          ) : modelDonutData.length === 0 ? (
            <div className="flex h-[280px] items-center justify-center">
              <p className="text-sm text-[var(--text-tertiary)]">
                No model data
              </p>
            </div>
          ) : (
            <div>
              <div
                role="img"
                aria-label="Token usage by model chart"
                aria-describedby={descriptionId}
              >
                <ResponsiveContainer width="100%" height={240} minWidth={0}>
                  <PieChart accessibilityLayer={false}>
                    <Pie
                      data={modelDonutData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      innerRadius="55%"
                      outerRadius="85%"
                      paddingAngle={3}
                      stroke="none"
                      isAnimationActive={!prefersReducedMotion}
                      animationDuration={prefersReducedMotion ? 0 : 800}
                    >
                      {modelDonutData.map((model, i) => (
                        <Cell
                          key={model.id}
                          fill={MODEL_COLORS[i % MODEL_COLORS.length]}
                          opacity={0.85}
                        />
                      ))}
                    </Pie>
                    <Tooltip content={<ModelTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <p id={descriptionId} className="sr-only">
                {modelChartSummary}
              </p>
              <div className="mt-2 flex flex-wrap justify-center gap-3">
                {modelDonutData.map((m, i) => (
                  <span
                    key={m.id}
                    className="flex max-w-full items-center gap-1.5 break-all text-xs text-[var(--text-secondary)]"
                    title={m.fullName}
                    aria-label={`${m.fullName}: ${m.tokens} tokens`}
                  >
                    <ChartSwatch
                      className="h-2 w-2"
                      color={MODEL_COLORS[i % MODEL_COLORS.length]}
                    />
                    {m.name}
                  </span>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle aria-level={2} className="text-sm">
            Model Details
          </CardTitle>
        </CardHeader>
        <CardContent>
          {modelLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <div
                  key={i}
                  className="skeleton-shimmer h-12 rounded-md bg-[var(--skeleton-base)]"
                />
              ))}
            </div>
          ) : (
            <div
              aria-label="Admin analytics model detail table"
              className="overflow-x-auto [scrollbar-gutter:stable] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
              role="region"
              tabIndex={0}
            >
              <table className="min-w-[44rem] w-full text-sm">
                <caption className="sr-only">
                  Admin analytics model detail table with model name, input
                  tokens, output tokens, estimated cost, and request count.
                </caption>
                <thead>
                  <tr className="border-b border-[var(--border-default)]">
                    <th
                      scope="col"
                      className="py-2 pr-4 text-left text-xs font-medium text-[var(--text-tertiary)]"
                    >
                      Model
                    </th>
                    <th
                      scope="col"
                      className="px-4 py-2 text-right text-xs font-medium text-[var(--text-tertiary)]"
                    >
                      Input Tokens
                    </th>
                    <th
                      scope="col"
                      className="px-4 py-2 text-right text-xs font-medium text-[var(--text-tertiary)]"
                    >
                      Output Tokens
                    </th>
                    <th
                      scope="col"
                      className="px-4 py-2 text-right text-xs font-medium text-[var(--text-tertiary)]"
                    >
                      Cost
                    </th>
                    <th
                      scope="col"
                      className="py-2 pl-4 text-right text-xs font-medium text-[var(--text-tertiary)]"
                    >
                      Requests
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-subtle)]">
                  {(modelData?.models ?? []).map((m) => (
                    <tr
                      key={m.model_name}
                      className="transition-colors hover:bg-[var(--surface-hover)]"
                    >
                      <td className="py-2.5 pr-4 font-mono text-xs text-[var(--text-primary)]">
                        <span className="min-w-0 break-all">
                          {m.model_name}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right text-[var(--text-secondary)] tabular-nums">
                        <span>{formatTokens(m.total_input_tokens)}</span>
                      </td>
                      <td className="px-4 py-2.5 text-right text-[var(--text-secondary)] tabular-nums">
                        <span>{formatTokens(m.total_output_tokens)}</span>
                      </td>
                      <td className="px-4 py-2.5 text-right font-medium text-[var(--text-primary)] tabular-nums">
                        <span>{formatCurrency(m.estimated_cost_usd)}</span>
                      </td>
                      <td className="py-2.5 pl-4 text-right text-[var(--text-secondary)] tabular-nums">
                        <span>{m.request_count}</span>
                      </td>
                    </tr>
                  ))}
                  {(modelData?.models ?? []).length === 0 && (
                    <tr>
                      <td
                        colSpan={5}
                        className="py-8 text-center text-[var(--text-tertiary)]"
                      >
                        No model data for this period
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {modelData?.overall_cache_hit_rate != null && (
            <div className="mt-4 flex flex-col gap-2 rounded-lg border border-[var(--border-default)] bg-[var(--surface-subtle)] p-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm text-[var(--text-secondary)]">
                  Prompt Cache Hit Rate
                </span>
              </div>
              <Badge
                variant={
                  modelData.overall_cache_hit_rate > 50 ? "success" : "warning"
                }
              >
                {formatPercentLike(modelData.overall_cache_hit_rate)}
              </Badge>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
