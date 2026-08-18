import type { ComponentType } from "react";
import { AlertTriangle, Clock, KeyRound, ShieldCheck } from "lucide-react";
import { AnimatedCounter } from "@/components/shared/animated-counter";
import { Card, CardContent } from "@/components/ui/card";

interface SettingsSummaryCardsProps {
  total: number;
  activeCount: number;
  expiringSoonCount?: number;
  revokedCount: number;
}

export function SettingsSummaryCards({
  total,
  activeCount,
  expiringSoonCount = 0,
  revokedCount,
}: SettingsSummaryCardsProps) {
  const cards = [
    {
      label: "Issued keys",
      value: total,
      detail: "Credentials in the audit ledger",
      icon: KeyRound,
      tone: "brand" as const,
    },
    {
      label: "Active access",
      value: activeCount,
      detail: "Able to request organization data",
      icon: ShieldCheck,
      tone: "success" as const,
    },
    {
      label: "Expiring soon",
      value: expiringSoonCount,
      detail: "Within the next 14 days",
      icon: AlertTriangle,
      tone: expiringSoonCount > 0 ? ("warning" as const) : ("muted" as const),
    },
    {
      label: "Revoked audit",
      value: revokedCount,
      detail: "Closed credentials retained",
      icon: Clock,
      tone: "muted" as const,
    },
  ];

  return (
    <section
      aria-label="Settings access summary"
      className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4"
    >
      {cards.map((card) => (
        <SummaryCard key={card.label} {...card} />
      ))}
    </section>
  );
}

function SummaryCard({
  label,
  value,
  detail,
  icon: Icon,
  tone,
}: {
  label: string;
  value: number;
  detail: string;
  icon: ComponentType<{ className?: string }>;
  tone: "brand" | "success" | "warning" | "muted";
}) {
  const iconClass =
    tone === "success"
      ? "bg-success/10 text-success"
      : tone === "warning"
        ? "bg-warning/10 text-warning"
        : tone === "brand"
          ? "bg-brand-primary/10 text-brand-primary"
          : "bg-[var(--surface-active)] text-[var(--text-tertiary)]";

  return (
    <Card className="min-h-[8.5rem]">
      <CardContent className="p-5">
        <div className="flex items-start gap-3.5">
          <div
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${iconClass}`}
          >
            <Icon className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <p className="type-label-sm text-[var(--text-secondary)]">
              {label}
            </p>
            <p className="mt-1 type-heading-xl tabular-nums text-[var(--text-primary)]">
              <AnimatedCounter value={value} />
            </p>
            <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
              {detail}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
