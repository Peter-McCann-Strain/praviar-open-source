import {
  AlertTriangle,
  CheckCircle,
  Clock3,
  Layers,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { AnimatedCounter } from "@/components/shared/animated-counter";
import {
  StaggerContainer,
  StaggerItem,
} from "@/components/shared/stagger-container";
import type { BatchResponse } from "@/hooks/use-batch";
import { cn } from "@/lib/utils";

interface BatchSummaryCardsProps {
  data: {
    total: number;
    items: BatchResponse[];
  };
}

export function BatchSummaryCards({ data }: BatchSummaryCardsProps) {
  const totalCompounds = data.items.reduce(
    (sum: number, batch: BatchResponse) => sum + batch.total_compounds,
    0,
  );
  const completedCompounds = data.items.reduce(
    (sum: number, batch: BatchResponse) => sum + batch.completed_count,
    0,
  );
  const failedCompounds = data.items.reduce(
    (sum: number, batch: BatchResponse) => sum + batch.failed_count,
    0,
  );
  const activeRuns = data.items.filter((batch) =>
    ["running", "pending"].includes(batch.status),
  ).length;
  const handoffReady = data.items.filter((batch) =>
    ["completed", "partial"].includes(batch.status),
  ).length;
  const coveragePct =
    totalCompounds > 0
      ? Math.min(100, Math.round((completedCompounds / totalCompounds) * 100))
      : 0;
  const cards: Array<{
    icon: LucideIcon;
    label: string;
    value: number;
    suffix?: string;
    detail: string;
    tone: "brand" | "success" | "info" | "warning";
  }> = [
    {
      icon: failedCompounds > 0 ? AlertTriangle : Clock3,
      label: "Failure watch",
      value: failedCompounds,
      detail:
        failedCompounds > 0 ? "Needs operator review" : "No failures visible",
      tone: failedCompounds > 0 ? "warning" : "success",
    },
    {
      icon: Layers,
      label: "Portfolio runs",
      value: data.total,
      detail: `${activeRuns.toLocaleString()} active`,
      tone: "brand",
    },
    {
      icon: ShieldCheck,
      label: "Counsel handoff",
      value: handoffReady,
      detail: `${handoffReady.toLocaleString()} ready or partial`,
      tone: "success",
    },
    {
      icon: CheckCircle,
      label: "Source coverage",
      value: coveragePct,
      suffix: "%",
      detail: `${completedCompounds.toLocaleString()} of ${totalCompounds.toLocaleString()} screened`,
      tone: "info",
    },
  ];

  return (
    <StaggerContainer className="grid grid-cols-2 gap-2 sm:gap-3 min-[1440px]:grid-cols-4">
      {cards.map(({ icon: Icon, label, value, suffix, detail, tone }) => (
        <StaggerItem key={label}>
          <div className="praviar-surface-premium h-full min-h-28 rounded-lg border border-[var(--card-border)] p-3 sm:p-5">
            <div className="flex flex-col items-start gap-2.5 sm:flex-row sm:gap-3.5">
              <div
                className={cn(
                  "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border sm:h-10 sm:w-10",
                  tone === "warning"
                    ? "border-warning/20 bg-warning/10 text-warning"
                    : tone === "success"
                      ? "border-success/20 bg-success/10 text-success"
                      : tone === "info"
                        ? "border-info/20 bg-info/10 text-info"
                        : "border-brand-primary/20 bg-brand-primary/10 text-brand-primary",
                )}
              >
                <Icon className="h-5 w-5" aria-hidden="true" />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                  {label}
                </p>
                <p className="mt-1.5 text-2xl font-semibold leading-none tabular-nums text-[var(--text-primary)] sm:mt-2 sm:text-3xl">
                  <AnimatedCounter value={value} />
                  {suffix ? <span>{suffix}</span> : null}
                </p>
                <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                  {detail}
                </p>
              </div>
            </div>
          </div>
        </StaggerItem>
      ))}
    </StaggerContainer>
  );
}
