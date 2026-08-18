"use client";

import { useId } from "react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { ChartSwatch } from "@/components/charts/chart-swatch";
import { usePrefersReducedMotion } from "@/components/charts/use-prefers-reduced-motion";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface RiskDatum {
  level: string;
  count: number;
}

export interface RiskDonutProps {
  /** Array of { level, count } entries. level should be HIGH | MEDIUM | LOW | CLEAR */
  data: RiskDatum[];
  /** Optional chart size in px (default 280) */
  size?: number;
  /** Center label for the counted unit. Defaults to patent-oriented report usage. */
  centerLabel?: string;
  /** Accessible chart name. Defaults to a stable chart label; counts live in the description. */
  ariaLabel?: string;
}

// ---------------------------------------------------------------------------
// Color map -- premium semantic tokens, resolved by the active theme.
// ---------------------------------------------------------------------------

const RISK_COLORS: Record<string, string> = {
  HIGH: "var(--risk-high)",
  MEDIUM: "var(--risk-medium)",
  LOW: "var(--risk-low)",
  CLEAR: "var(--risk-clear)",
};

const fallbackColor = "var(--text-disabled)";

function colorFor(level: string): string {
  return RISK_COLORS[level.toUpperCase()] ?? fallbackColor;
}

function formatLevel(level: string): string {
  const lower = level.toLowerCase();
  return `${lower.charAt(0).toUpperCase()}${lower.slice(1)}`;
}

function formatPercent(count: number, total: number): string {
  if (total <= 0) {
    return "0%";
  }

  const percent = (count / total) * 100;
  if (count > 0 && percent < 1) {
    return "<1%";
  }

  return `${Math.round(percent)}%`;
}

function formatUnit(count: number, label: string): string {
  if (count !== 1) {
    return label;
  }

  if (label === "analyses") return "analysis";
  if (label === "patents") return "patent";
  if (label === "reports") return "report";
  return label;
}

// ---------------------------------------------------------------------------
// Custom center label rendered via SVG
// ---------------------------------------------------------------------------

interface CenterLabelProps {
  cx: number;
  cy: number;
  label: string;
  total: number;
}

function CenterLabel({ cx, cy, label, total }: CenterLabelProps) {
  return (
    <g>
      <text
        x={cx}
        y={cy - 8}
        textAnchor="middle"
        dominantBaseline="central"
        fill="var(--text-primary)"
        fontSize={28}
        fontWeight={600}
      >
        {total}
      </text>
      <text
        x={cx}
        y={cy + 18}
        textAnchor="middle"
        dominantBaseline="central"
        fill="var(--text-tertiary)"
        fontSize={12}
      >
        {label}
      </text>
    </g>
  );
}

// ---------------------------------------------------------------------------
// Custom tooltip
// ---------------------------------------------------------------------------

function DonutTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: RiskDatum }>;
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div
      className="praviar-dialog-panel rounded-lg px-3 py-2 text-sm"
      role="status"
      aria-live="polite"
    >
      <span style={{ color: colorFor(d.level) }} className="font-semibold">
        {d.level}
      </span>
      <span className="ml-2 text-[var(--text-secondary)] tabular-nums">
        {d.count}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RiskDonut({
  data,
  size = 280,
  centerLabel = "patents",
  ariaLabel,
}: RiskDonutProps) {
  const descriptionId = useId();
  const prefersReducedMotion = usePrefersReducedMotion();
  const total = data.reduce((sum, d) => sum + d.count, 0);
  const generatedSummary =
    total > 0
      ? `${total} ${formatUnit(total, centerLabel)}: ${data
          .map((d) => `${d.count} ${d.level.toLowerCase()}`)
          .join(", ")}.`
      : `No ${centerLabel} risk data available.`;
  const chartLabel = ariaLabel ?? "Risk distribution chart";
  const chartDescription =
    total > 0
      ? `${generatedSummary} ${data
          .map(
            (d) =>
              `${d.level}: ${d.count} of ${total} ${formatUnit(
                total,
                centerLabel,
              )}`,
          )
          .join("; ")}`
      : generatedSummary;

  if (total === 0) {
    return (
      <div className="min-w-0">
        <div
          role="img"
          aria-label={chartLabel}
          aria-describedby={descriptionId}
          className="flex w-full items-center justify-center"
          style={{ height: size }}
        >
          <div className="flex h-32 w-32 flex-col items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-subtle)] text-center">
            <span className="type-heading-lg tabular-nums text-[var(--text-primary)]">
              0
            </span>
            <span className="text-xs text-[var(--text-tertiary)]">
              {centerLabel}
            </span>
          </div>
        </div>
        <p id={descriptionId} className="sr-only">
          {chartDescription}
        </p>
      </div>
    );
  }

  return (
    <div className="min-w-0">
      <div role="img" aria-label={chartLabel} aria-describedby={descriptionId}>
        <ResponsiveContainer
          width="100%"
          height={size}
          minWidth={0}
          minHeight={Math.min(size, 180)}
          debounce={80}
        >
          <PieChart accessibilityLayer={false}>
            <Pie
              rootTabIndex={-1}
              data={data}
              dataKey="count"
              nameKey="level"
              cx="50%"
              cy="50%"
              innerRadius="62%"
              outerRadius="85%"
              paddingAngle={3}
              stroke="none"
              isAnimationActive={!prefersReducedMotion}
              animationBegin={0}
              animationDuration={prefersReducedMotion ? 0 : 1000}
              animationEasing="ease-out"
            >
              {data.map((entry) => (
                <Cell
                  key={entry.level}
                  fill={colorFor(entry.level)}
                  opacity={0.85}
                />
              ))}
            </Pie>

            {/* Center total -- rendered as custom label on a hidden inner pie */}
            <Pie
              rootTabIndex={-1}
              data={[{ value: 1 }]}
              dataKey="value"
              cx="50%"
              cy="50%"
              outerRadius={0}
              fill="none"
              isAnimationActive={false}
              label={({ cx, cy }: { cx: number; cy: number }) => (
                <CenterLabel
                  cx={cx}
                  cy={cy}
                  label={centerLabel}
                  total={total}
                />
              )}
            />

            <Tooltip content={<DonutTooltip />} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul
        aria-hidden="true"
        className="mt-3 grid min-w-0 grid-cols-1 gap-2 min-[420px]:grid-cols-2"
        data-testid="risk-donut-legend"
      >
        {data.map((d) => (
          <li
            key={d.level}
            className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-2.5 py-2"
          >
            <span className="flex min-w-0 items-center gap-2">
              <ChartSwatch className="h-2.5 w-2.5" color={colorFor(d.level)} />
              <span className="min-w-0 break-words text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
                {formatLevel(d.level)}
              </span>
            </span>
            <span className="mt-1 flex items-baseline gap-1.5">
              <span className="text-sm font-semibold tabular-nums text-[var(--text-primary)]">
                {d.count.toLocaleString()}
              </span>
              <span className="text-xs tabular-nums text-[var(--text-tertiary)]">
                {formatPercent(d.count, total)}
              </span>
            </span>
          </li>
        ))}
      </ul>
      <p id={descriptionId} className="sr-only">
        {chartDescription}
      </p>
    </div>
  );
}
