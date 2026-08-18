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

export interface FunnelDatum {
  stage: string;
  count: number;
}

export interface SearchFunnelProps {
  data: FunnelDatum[];
  height?: number;
  ariaLabel?: string;
}

// ---------------------------------------------------------------------------
// Forensic Teal + Clinical Copper funnel gradient
// ---------------------------------------------------------------------------

const FUNNEL_GRADIENT = [
  "var(--brand-mint)",
  "var(--brand-teal)",
  "var(--brand-primary-dim)",
  "var(--brand-ink)",
  "var(--brand-copper)",
  "var(--brand-secondary-dim)",
];

function barColor(index: number, total: number): string {
  const ratio = total <= 1 ? 0 : index / (total - 1);
  const gradientIndex = Math.min(
    Math.round(ratio * (FUNNEL_GRADIENT.length - 1)),
    FUNNEL_GRADIENT.length - 1,
  );
  return FUNNEL_GRADIENT[gradientIndex];
}

// ---------------------------------------------------------------------------
// Custom tooltip
// ---------------------------------------------------------------------------

function FunnelTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: FunnelDatum }>;
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div
      className="praviar-dialog-panel rounded-lg px-3 py-2 text-sm"
      role="status"
      aria-live="polite"
    >
      <p className="font-semibold text-[var(--text-primary)]">{d.stage}</p>
      <p className="text-[var(--text-secondary)] tabular-nums">
        {d.count.toLocaleString()} patents
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

function formatPatents(count: number): string {
  return `${count.toLocaleString()} patent${count === 1 ? "" : "s"}`;
}

function buildFunnelSummary(data: FunnelDatum[]): string {
  if (data.length === 0) {
    return "No patent funnel data available.";
  }

  return `${data
    .map((d) => `${d.stage} ${formatPatents(d.count)}`)
    .join(", ")}.`;
}

function buildFunnelDescription(data: FunnelDatum[]): string {
  if (data.length === 0) {
    return "No search funnel data available.";
  }

  return data.map((d) => `${d.stage}: ${formatPatents(d.count)}`).join("; ");
}

export function SearchFunnel({
  data,
  height = 320,
  ariaLabel,
}: SearchFunnelProps) {
  const descriptionId = useId();
  const prefersReducedMotion = usePrefersReducedMotion();
  const chartLabel = ariaLabel ?? "Search funnel chart";
  const chartDescription = buildFunnelDescription(data);
  const chartSummary = buildFunnelSummary(data);
  const chartHeight = minimumReadableChartHeight(height, data.length, 42);
  const stageAxisWidth = estimateAxisWidth(
    data.map((d) => d.stage),
    104,
    156,
  );
  const valueLabelMargin = estimateTrailingLabelMargin(
    data.map((d) => d.count.toLocaleString()),
    54,
    96,
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
              No funnel data
            </p>
            <p className="mt-1 text-xs text-[var(--text-tertiary)]">
              Search stages will appear after retrieval.
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
            margin={{ top: 6, right: valueLabelMargin, bottom: 8, left: 4 }}
          >
            <CartesianGrid
              horizontal={false}
              strokeDasharray="3 3"
              stroke="var(--chart-grid)"
            />
            <XAxis
              type="number"
              allowDecimals={false}
              minTickGap={24}
              tick={{ fill: "var(--text-tertiary)", fontSize: 12 }}
              tickMargin={8}
              axisLine={{ stroke: "var(--chart-axis)" }}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey="stage"
              width={stageAxisWidth}
              tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
              tickFormatter={(value: string) => compactChartLabel(value, 20)}
              tickMargin={8}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              content={<FunnelTooltip />}
              cursor={{ fill: "var(--chart-cursor)" }}
              wrapperStyle={{ outline: "none" }}
            />
            <Bar
              dataKey="count"
              radius={[0, 6, 6, 0]}
              maxBarSize={34}
              isAnimationActive={!prefersReducedMotion}
              animationDuration={prefersReducedMotion ? 0 : 800}
              animationEasing="ease-out"
              animationBegin={prefersReducedMotion ? 0 : 200}
            >
              {data.map((_, index) => (
                <Cell
                  key={index}
                  fill={barColor(index, data.length)}
                  opacity={0.85}
                />
              ))}
              <LabelList
                dataKey="count"
                position="right"
                offset={8}
                formatter={(v) =>
                  typeof v === "number" ? v.toLocaleString() : String(v ?? "")
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
