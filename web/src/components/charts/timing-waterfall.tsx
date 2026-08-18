"use client";

import { useId } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  ResponsiveContainer,
  LabelList,
} from "recharts";
import {
  compactChartLabel,
  estimateAxisWidth,
  estimateTrailingLabelMargin,
  minimumReadableChartHeight,
} from "@/components/charts/chart-layout";
import { usePrefersReducedMotion } from "@/components/charts/use-prefers-reduced-motion";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TimingDatum {
  step: string;
  duration_seconds: number;
}

export interface TimingWaterfallProps {
  data: TimingDatum[];
  height?: number;
  ariaLabel?: string;
}

// ---------------------------------------------------------------------------
// Colors by step keyword — desaturated
// ---------------------------------------------------------------------------

// Forensic Teal + Clinical Copper pipeline phase colors.
const STEP_COLORS: [RegExp, string][] = [
  [/search/i, "var(--brand-teal)"], // Forensic teal — search/retrieval
  [/rank/i, "var(--brand-mint)"], // Clinical mint — ranking
  [/triage/i, "var(--brand-copper)"], // Copper — triage/judgment
  [/analy/i, "var(--brand-primary)"], // Adaptive primary — analysis
  [/equivalen/i, "var(--text-tertiary)"], // Neutralized evidence layer
  [/invalid/i, "var(--risk-high)"], // Semantic red — invalidity/high-risk
  [/report/i, "var(--brand-secondary)"], // Copper lift — report output
  [/resolve/i, "var(--brand-secondary-dim)"], // Copper depth — resolution
];

const DEFAULT_COLOR = "var(--text-disabled)";

function colorForStep(step: string): string {
  for (const [pattern, color] of STEP_COLORS) {
    if (pattern.test(step)) return color;
  }
  return DEFAULT_COLOR;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatSeconds(s: number): string {
  if (s < 1) return `${Math.round(s * 1000)}ms`;
  if (s < 60) return `${s.toFixed(1)}s`;
  const mins = Math.floor(s / 60);
  const secs = Math.round(s % 60);
  return `${mins}m ${secs}s`;
}

// ---------------------------------------------------------------------------
// Custom tooltip
// ---------------------------------------------------------------------------

function WaterfallTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: TimingDatum }>;
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div
      className="praviar-dialog-panel rounded-lg px-3 py-2 text-sm"
      role="status"
      aria-live="polite"
    >
      <p className="font-semibold text-[var(--text-primary)]">{d.step}</p>
      <p className="text-[var(--text-secondary)] tabular-nums">
        {formatSeconds(d.duration_seconds)}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

function buildTimingSummary(data: TimingDatum[]): string {
  if (data.length === 0) {
    return "No pipeline timing data available.";
  }

  const totalSeconds = data.reduce((sum, d) => sum + d.duration_seconds, 0);
  const slowest = data.reduce((current, item) =>
    item.duration_seconds > current.duration_seconds ? item : current,
  );

  return `Total runtime ${formatSeconds(
    totalSeconds,
  )}; slowest step ${slowest.step} at ${formatSeconds(
    slowest.duration_seconds,
  )}; ${data
    .map((d) => `${d.step} ${formatSeconds(d.duration_seconds)}`)
    .join(", ")}.`;
}

function buildTimingDescription(data: TimingDatum[]): string {
  if (data.length === 0) {
    return "No pipeline timing data available.";
  }

  return data
    .map((d) => `${d.step}: ${formatSeconds(d.duration_seconds)}`)
    .join("; ");
}

export function TimingWaterfall({
  data,
  height = 320,
  ariaLabel,
}: TimingWaterfallProps) {
  const descriptionId = useId();
  const prefersReducedMotion = usePrefersReducedMotion();
  const chartLabel = ariaLabel ?? "Timing waterfall chart";
  const chartDescription = buildTimingDescription(data);
  const chartSummary = buildTimingSummary(data);
  const chartHeight = minimumReadableChartHeight(height, data.length, 42);
  const stepAxisWidth = estimateAxisWidth(
    data.map((d) => d.step),
    128,
    188,
  );
  const durationLabelMargin = estimateTrailingLabelMargin(
    data.map((d) => formatSeconds(d.duration_seconds)),
    60,
    104,
  );

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
              No timing data
            </p>
            <p className="mt-1 text-xs text-[var(--text-tertiary)]">
              Pipeline timing appears after execution.
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
          height={chartHeight}
          minWidth={0}
          minHeight={Math.min(chartHeight, 220)}
          debounce={80}
        >
          <BarChart
            accessibilityLayer={false}
            data={data}
            layout="vertical"
            barCategoryGap="28%"
            margin={{ top: 6, right: durationLabelMargin, bottom: 8, left: 4 }}
          >
            <CartesianGrid
              horizontal={false}
              strokeDasharray="3 3"
              stroke="var(--chart-grid)"
            />
            <XAxis
              type="number"
              minTickGap={20}
              tick={{ fill: "var(--text-tertiary)", fontSize: 12 }}
              tickMargin={8}
              axisLine={{ stroke: "var(--chart-axis)" }}
              tickLine={false}
              tickFormatter={(v: number) => formatSeconds(v)}
            />
            <YAxis
              type="category"
              dataKey="step"
              width={stepAxisWidth}
              tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
              tickFormatter={(value: string) => compactChartLabel(value, 24)}
              tickMargin={8}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              content={<WaterfallTooltip />}
              cursor={{ fill: "var(--chart-cursor)" }}
              wrapperStyle={{ outline: "none" }}
            />
            <Bar
              dataKey="duration_seconds"
              radius={[0, 6, 6, 0]}
              maxBarSize={32}
              isAnimationActive={!prefersReducedMotion}
              animationDuration={prefersReducedMotion ? 0 : 800}
              animationEasing="ease-out"
              animationBegin={prefersReducedMotion ? 0 : 200}
            >
              {data.map((entry) => (
                <Cell
                  key={entry.step}
                  fill={colorForStep(entry.step)}
                  opacity={0.85}
                />
              ))}
              <LabelList
                dataKey="duration_seconds"
                position="right"
                offset={8}
                formatter={(v) =>
                  typeof v === "number" ? formatSeconds(v) : String(v ?? "")
                }
                style={{
                  fill: "var(--text-primary)",
                  fontSize: 12,
                  fontWeight: 600,
                }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p id={descriptionId} className="sr-only">
        {chartSummary} {chartDescription}
      </p>
    </div>
  );
}
