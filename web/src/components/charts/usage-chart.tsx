"use client";

import { useId } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { ChartSwatch } from "@/components/charts/chart-swatch";
import { compactChartLabel } from "@/components/charts/chart-layout";
import { usePrefersReducedMotion } from "@/components/charts/use-prefers-reduced-motion";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UsageDatum {
  step: string;
  input_tokens: number;
  output_tokens: number;
}

export interface UsageChartProps {
  data: UsageDatum[];
  height?: number;
  ariaLabel?: string;
  emptyDescription?: string;
  emptyTitle?: string;
  inputLabel?: string;
  outputLabel?: string;
}

// ---------------------------------------------------------------------------
// Colors — desaturated
// ---------------------------------------------------------------------------

const INPUT_COLOR = "var(--brand-primary)";
const OUTPUT_COLOR = "var(--brand-secondary)";
const USAGE_SWATCH_COLORS: Record<string, string> = {
  input_tokens: INPUT_COLOR,
  "Input Tokens": INPUT_COLOR,
  output_tokens: OUTPUT_COLOR,
  "Output Tokens": OUTPUT_COLOR,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function usageSwatchColor(entry: {
  color?: string;
  dataKey?: string;
  name?: string;
  value?: number | string;
}) {
  const valueKey = typeof entry.value === "string" ? entry.value : undefined;

  return (
    (entry.dataKey ? USAGE_SWATCH_COLORS[entry.dataKey] : undefined) ??
    (entry.name ? USAGE_SWATCH_COLORS[entry.name] : undefined) ??
    (valueKey ? USAGE_SWATCH_COLORS[valueKey] : undefined) ??
    entry.color ??
    "var(--text-disabled)"
  );
}

// ---------------------------------------------------------------------------
// Custom tooltip
// ---------------------------------------------------------------------------

function UsageTooltip({
  active,
  inputLabel = "Input Tokens",
  outputLabel = "Output Tokens",
  payload,
  label,
}: {
  active?: boolean;
  inputLabel?: string;
  outputLabel?: string;
  payload?: Array<{
    color?: string;
    dataKey?: string;
    name: string;
    value: number;
  }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="praviar-dialog-panel rounded-lg px-3 py-2 text-sm"
      role="status"
      aria-live="polite"
    >
      <p className="mb-1 font-semibold text-[var(--text-primary)]">{label}</p>
      {payload.map((entry) => (
        <p
          key={entry.name}
          className="text-[var(--text-secondary)] tabular-nums"
        >
          <ChartSwatch
            className="mr-2 h-2 w-2"
            color={usageSwatchColor(entry)}
          />
          {entry.dataKey === "input_tokens"
            ? inputLabel
            : entry.dataKey === "output_tokens"
              ? outputLabel
              : entry.name}
          : {formatTokens(entry.value)}
        </p>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Custom legend
// ---------------------------------------------------------------------------

function UsageLegend({
  inputLabel = "Input Tokens",
  outputLabel = "Output Tokens",
  payload,
}: {
  inputLabel?: string;
  outputLabel?: string;
  payload?: Array<{ color?: string; dataKey?: string; value: string }>;
}) {
  if (!payload?.length) return null;
  return (
    <div className="flex flex-wrap justify-center gap-x-6 gap-y-2 pt-1">
      {payload.map((entry) => (
        <span
          key={entry.value}
          className="flex items-center gap-1.5 text-xs text-[var(--text-secondary)]"
        >
          <ChartSwatch
            className="h-2.5 w-2.5"
            color={usageSwatchColor(entry)}
            shape="square"
          />
          {entry.dataKey === "input_tokens"
            ? inputLabel
            : entry.dataKey === "output_tokens"
              ? outputLabel
              : entry.value}
        </span>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

function buildUsageSummary(
  data: UsageDatum[],
  inputLabel: string,
  outputLabel: string,
): string {
  if (data.length === 0) {
    return `No ${inputLabel.toLowerCase()} or ${outputLabel.toLowerCase()} data available.`;
  }

  const inputTotal = data.reduce((sum, d) => sum + d.input_tokens, 0);
  const outputTotal = data.reduce((sum, d) => sum + d.output_tokens, 0);

  return `${formatTokens(
    inputTotal,
  )} ${inputLabel.toLowerCase()} and ${formatTokens(outputTotal)} ${outputLabel.toLowerCase()} across ${
    data.length
  } step${data.length === 1 ? "" : "s"}; ${data
    .map(
      (d) =>
        `${d.step} ${formatTokens(d.input_tokens)} ${inputLabel.toLowerCase()} and ${formatTokens(
          d.output_tokens,
        )} ${outputLabel.toLowerCase()}`,
    )
    .join(", ")}.`;
}

function buildUsageDescription(
  data: UsageDatum[],
  inputLabel: string,
  outputLabel: string,
): string {
  if (data.length === 0) {
    return `No ${inputLabel.toLowerCase()} or ${outputLabel.toLowerCase()} data available.`;
  }

  return data
    .map(
      (d) =>
        `${d.step}: ${formatTokens(d.input_tokens)} ${inputLabel.toLowerCase()}, ${formatTokens(
          d.output_tokens,
        )} ${outputLabel.toLowerCase()}`,
    )
    .join("; ");
}

export function UsageChart({
  ariaLabel,
  data,
  emptyDescription = "Model usage appears after execution.",
  emptyTitle = "No token usage",
  height = 320,
  inputLabel = "Input Tokens",
  outputLabel = "Output Tokens",
}: UsageChartProps) {
  const reactId = useId().replace(/:/g, "");
  const descriptionId = `usage-chart-description-${reactId}`;
  const inputGradientId = `usage-chart-input-${reactId}`;
  const outputGradientId = `usage-chart-output-${reactId}`;
  const prefersReducedMotion = usePrefersReducedMotion();
  const chartLabel = ariaLabel ?? "Token usage chart";
  const chartDescription = buildUsageDescription(data, inputLabel, outputLabel);
  const chartSummary = buildUsageSummary(data, inputLabel, outputLabel);

  if (data.length === 0) {
    return (
      <div className="min-w-0">
        <div
          role="img"
          aria-label={chartLabel}
          aria-describedby={descriptionId}
          className="flex items-center justify-center rounded-md border border-[var(--border-subtle)] bg-[var(--surface-subtle)] text-center"
          style={{ height }}
        >
          <div>
            <p className="type-label text-[var(--text-secondary)]">
              {emptyTitle}
            </p>
            <p className="mt-1 text-xs text-[var(--text-tertiary)]">
              {emptyDescription}
            </p>
          </div>
        </div>
        <p id={descriptionId} className="sr-only">
          {chartSummary}
        </p>
      </div>
    );
  }

  return (
    <div className="min-w-0">
      <div role="img" aria-label={chartLabel} aria-describedby={descriptionId}>
        <ResponsiveContainer
          width="100%"
          height={height}
          minWidth={0}
          minHeight={Math.min(height, 220)}
          debounce={80}
        >
          <BarChart
            accessibilityLayer={false}
            data={data}
            barCategoryGap="22%"
            margin={{ top: 6, right: 16, bottom: 10, left: 6 }}
          >
            <defs>
              <linearGradient id={inputGradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={INPUT_COLOR} stopOpacity={0.8} />
                <stop offset="100%" stopColor={INPUT_COLOR} stopOpacity={0.3} />
              </linearGradient>
              <linearGradient id={outputGradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={OUTPUT_COLOR} stopOpacity={0.8} />
                <stop
                  offset="100%"
                  stopColor={OUTPUT_COLOR}
                  stopOpacity={0.3}
                />
              </linearGradient>
            </defs>
            <CartesianGrid
              vertical={false}
              strokeDasharray="3 3"
              stroke="var(--chart-grid)"
            />
            <XAxis
              dataKey="step"
              tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
              tickFormatter={(value: string) => compactChartLabel(value, 16)}
              tickMargin={10}
              axisLine={{ stroke: "var(--chart-axis)" }}
              tickLine={false}
              interval={0}
              minTickGap={8}
              angle={-35}
              textAnchor="end"
              height={84}
            />
            <YAxis
              width={48}
              tick={{ fill: "var(--text-tertiary)", fontSize: 12 }}
              tickMargin={8}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => formatTokens(v)}
            />
            <Tooltip
              content={
                <UsageTooltip
                  inputLabel={inputLabel}
                  outputLabel={outputLabel}
                />
              }
              cursor={{ fill: "var(--chart-cursor)" }}
              wrapperStyle={{ outline: "none" }}
            />
            <Legend
              content={
                <UsageLegend
                  inputLabel={inputLabel}
                  outputLabel={outputLabel}
                />
              }
            />
            <Bar
              dataKey="input_tokens"
              name={inputLabel}
              fill={`url(#${inputGradientId})`}
              radius={[4, 4, 0, 0]}
              maxBarSize={40}
              isAnimationActive={!prefersReducedMotion}
              animationDuration={prefersReducedMotion ? 0 : 800}
              animationEasing="ease-out"
              animationBegin={prefersReducedMotion ? 0 : 200}
            />
            <Bar
              dataKey="output_tokens"
              name={outputLabel}
              fill={`url(#${outputGradientId})`}
              radius={[4, 4, 0, 0]}
              maxBarSize={40}
              isAnimationActive={!prefersReducedMotion}
              animationDuration={prefersReducedMotion ? 0 : 800}
              animationEasing="ease-out"
              animationBegin={prefersReducedMotion ? 0 : 400}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p id={descriptionId} className="sr-only">
        {chartSummary} {chartDescription}
      </p>
    </div>
  );
}
