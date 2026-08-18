import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { BarChart3 } from "lucide-react";
import type { CostBreakdownResponse } from "@/hooks/use-admin-analytics";
import { usePrefersReducedMotion } from "@/components/charts/use-prefers-reduced-motion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  STEP_COLORS,
  formatCurrency,
} from "@/components/admin-analytics/helpers";
import {
  CostTooltip,
  StepTooltip,
} from "@/components/admin-analytics/tooltips";
import { AnalyticsPanelStatus } from "@/components/admin-analytics/status-state";

interface CostsTabProps {
  costData: CostBreakdownResponse | undefined;
  costLoading: boolean;
  costError?: unknown;
  onRetry: () => void;
}

export function CostsTab({
  costData,
  costLoading,
  costError,
  onRetry,
}: CostsTabProps) {
  const prefersReducedMotion = usePrefersReducedMotion();
  const dailyCosts = costData?.daily_costs ?? [];
  const stepCosts = costData?.step_costs ?? [];

  if (costError && !costData) {
    return (
      <AnalyticsPanelStatus
        title="Cost telemetry unavailable"
        description="Cost charts could not be loaded. Existing cost controls and tenant records are unchanged."
        onRetry={onRetry}
      />
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle aria-level={2} className="text-sm">
            Cost Over Time
          </CardTitle>
        </CardHeader>
        <CardContent>
          {costLoading ? (
            <div className="flex h-[320px] items-center justify-center">
              <div className="skeleton-shimmer h-full w-full rounded-md bg-[var(--skeleton-base)]" />
            </div>
          ) : dailyCosts.length === 0 ? (
            <CostChartEmptyState
              title="No daily spend in this period"
              description="Praviar received cost telemetry, but no dated spend rows matched the selected range."
            />
          ) : (
            <div
              role="img"
              aria-labelledby="cost-over-time-title"
              aria-describedby="cost-over-time-summary"
            >
              <p id="cost-over-time-title" className="sr-only">
                Cost over time chart
              </p>
              <div className="sm:hidden">
                <MobileCostRows
                  items={dailyCosts.map((item) => ({
                    label: item.date,
                    value: formatCurrency(item.total_cost_usd),
                    detail: `${item.analysis_count.toLocaleString()} analyses`,
                  }))}
                />
              </div>
              <div className="hidden sm:block">
                <ResponsiveContainer width="100%" height={320} minWidth={0}>
                  <LineChart
                    accessibilityLayer
                    data={dailyCosts}
                    margin={{ top: 4, right: 12, bottom: 8, left: 8 }}
                  >
                    <defs>
                      <linearGradient
                        id="costGradient"
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                      >
                        <stop
                          offset="0%"
                          stopColor="var(--brand-primary)"
                          stopOpacity={0.3}
                        />
                        <stop
                          offset="100%"
                          stopColor="var(--brand-primary)"
                          stopOpacity={0}
                        />
                      </linearGradient>
                    </defs>
                    <CartesianGrid
                      vertical={false}
                      strokeDasharray="3 3"
                      stroke="var(--chart-grid)"
                    />
                    <XAxis
                      dataKey="date"
                      tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
                      axisLine={{ stroke: "var(--chart-axis)" }}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fill: "var(--text-tertiary)", fontSize: 12 }}
                      axisLine={false}
                      tickLine={false}
                      tickFormatter={(v: number) => formatCurrency(v)}
                    />
                    <Tooltip content={<CostTooltip />} />
                    <Line
                      type="monotone"
                      dataKey="total_cost_usd"
                      name="Cost"
                      stroke="var(--brand-primary)"
                      strokeWidth={2}
                      dot={false}
                      activeDot={{ r: 4, fill: "var(--brand-primary)" }}
                      fill="url(#costGradient)"
                      fillOpacity={1}
                      isAnimationActive={!prefersReducedMotion}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <CostChartSummary
                id="cost-over-time-summary"
                items={dailyCosts.map((item) => ({
                  label: item.date,
                  value: `${formatCurrency(item.total_cost_usd)} across ${item.analysis_count.toLocaleString()} analyses`,
                }))}
              />
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle aria-level={2} className="text-sm">
            Cost by Pipeline Step
          </CardTitle>
        </CardHeader>
        <CardContent>
          {costLoading ? (
            <div className="flex h-[320px] items-center justify-center">
              <div className="skeleton-shimmer h-full w-full rounded-md bg-[var(--skeleton-base)]" />
            </div>
          ) : stepCosts.length === 0 ? (
            <CostChartEmptyState
              title="No pipeline step spend in this period"
              description="Praviar received cost telemetry, but no step-level spend rows matched the selected range."
            />
          ) : (
            <div
              role="img"
              aria-labelledby="step-cost-title"
              aria-describedby="step-cost-summary"
            >
              <p id="step-cost-title" className="sr-only">
                Cost by pipeline step chart
              </p>
              <div className="sm:hidden">
                <MobileCostRows
                  items={stepCosts.map((item) => ({
                    label: item.step_name.replaceAll("_", " "),
                    value: formatCurrency(item.total_cost_usd),
                    detail: `${item.analysis_count.toLocaleString()} analyses`,
                  }))}
                />
              </div>
              <div className="hidden sm:block">
                <ResponsiveContainer width="100%" height={320} minWidth={0}>
                  <BarChart
                    accessibilityLayer
                    data={stepCosts}
                    layout="vertical"
                    margin={{ top: 4, right: 12, bottom: 8, left: 80 }}
                  >
                    <CartesianGrid
                      horizontal={false}
                      strokeDasharray="3 3"
                      stroke="var(--chart-grid)"
                    />
                    <XAxis
                      type="number"
                      tick={{ fill: "var(--text-tertiary)", fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                      tickFormatter={(v: number) => formatCurrency(v)}
                    />
                    <YAxis
                      type="category"
                      dataKey="step_name"
                      tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                      width={75}
                    />
                    <Tooltip content={<StepTooltip />} />
                    <Bar
                      dataKey="total_cost_usd"
                      name="Cost"
                      radius={[0, 4, 4, 0]}
                      maxBarSize={24}
                      isAnimationActive={!prefersReducedMotion}
                      animationDuration={800}
                    >
                      {stepCosts.map((_, i) => (
                        <Cell
                          key={i}
                          fill={STEP_COLORS[i % STEP_COLORS.length]}
                          opacity={0.8}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <CostChartSummary
                id="step-cost-summary"
                items={stepCosts.map((item) => ({
                  label: item.step_name,
                  value: `${formatCurrency(item.total_cost_usd)} across ${item.analysis_count.toLocaleString()} analyses`,
                }))}
              />
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function MobileCostRows({
  items,
}: {
  items: Array<{ label: string; value: string; detail: string }>;
}) {
  return (
    <ul className="divide-y divide-[var(--border-subtle)] rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/45">
      {items.slice(0, 8).map((item) => (
        <li
          key={`${item.label}-${item.value}`}
          className="flex items-center justify-between gap-3 px-3 py-3"
        >
          <span className="min-w-0">
            <span className="block truncate text-xs font-semibold capitalize text-[var(--text-primary)]">
              {item.label}
            </span>
            <span className="mt-0.5 block text-xs text-[var(--text-tertiary)]">
              {item.detail}
            </span>
          </span>
          <span className="shrink-0 font-mono text-sm font-semibold tabular-nums text-[var(--brand-primary)]">
            {item.value}
          </span>
        </li>
      ))}
    </ul>
  );
}

function CostChartEmptyState({
  description,
  title,
}: {
  description: string;
  title: string;
}) {
  return (
    <div
      role="status"
      className="flex min-h-[320px] flex-col items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 px-6 py-10 text-center"
    >
      <span className="flex h-11 w-11 items-center justify-center rounded-lg border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
        <BarChart3 className="h-5 w-5" aria-hidden="true" />
      </span>
      <p className="mt-4 text-sm font-semibold text-[var(--text-primary)]">
        {title}
      </p>
      <p className="mt-1 max-w-md text-sm leading-6 text-[var(--text-secondary)]">
        {description}
      </p>
    </div>
  );
}

function CostChartSummary({
  id,
  items,
}: {
  id: string;
  items: Array<{ label: string; value: string }>;
}) {
  return (
    <ul id={id} className="sr-only">
      {items.slice(0, 12).map((item) => (
        <li key={`${item.label}-${item.value}`}>
          {item.label}: {item.value}
        </li>
      ))}
      {items.length > 12 ? (
        <li>{items.length - 12} more rows omitted.</li>
      ) : null}
    </ul>
  );
}
