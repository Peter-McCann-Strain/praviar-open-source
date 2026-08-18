import type { StepCost } from "@/hooks/use-admin-analytics";
import {
  type ModelDonutDatum,
  formatCurrency,
  formatTokens,
} from "@/components/admin-analytics/helpers";
import { ChartSwatch } from "@/components/charts/chart-swatch";

export function CostTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="praviar-dialog-panel rounded-lg px-3 py-2 text-sm">
      <p className="mb-1 font-semibold text-[var(--text-primary)]">{label}</p>
      {payload.map((entry) => (
        <p
          key={entry.name}
          className="text-[var(--text-secondary)] tabular-nums"
        >
          <ChartSwatch className="mr-2 h-2 w-2" color={entry.color} />
          {entry.name}:{" "}
          {entry.name.includes("Token")
            ? formatTokens(entry.value)
            : formatCurrency(entry.value)}
        </p>
      ))}
    </div>
  );
}

export function StepTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: StepCost }>;
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="praviar-dialog-panel rounded-lg px-3 py-2 text-sm">
      <p className="mb-1 font-semibold text-[var(--text-primary)]">
        {d.step_name}
      </p>
      <p className="text-[var(--text-secondary)] tabular-nums">
        Cost: {formatCurrency(d.total_cost_usd)}
      </p>
      <p className="text-[var(--text-secondary)] tabular-nums">
        Avg: {formatCurrency(d.avg_cost_usd)}/analysis
      </p>
      <p className="text-[var(--text-secondary)] tabular-nums">
        Analyses: {d.analysis_count}
      </p>
    </div>
  );
}

export function ModelTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: ModelDonutDatum }>;
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="praviar-dialog-panel rounded-lg px-3 py-2 text-sm">
      <p className="mb-1 font-semibold text-[var(--text-primary)]">
        {d.fullName}
      </p>
      <p className="text-[var(--text-secondary)] tabular-nums">
        Cost: {formatCurrency(d.cost)}
      </p>
      <p className="text-[var(--text-secondary)] tabular-nums">
        Tokens: {d.tokens}
      </p>
    </div>
  );
}
