"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  ChevronDown,
  CircleDashed,
  LockKeyhole,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import type {
  SetupReadinessItem,
  SetupReadinessItemStatus,
} from "@/hooks/use-setup-readiness";
import { useSetupReadiness } from "@/hooks/use-setup-readiness";
import { cn } from "@/lib/utils";

const STATUS_PRESENTATION: Record<
  SetupReadinessItemStatus,
  {
    label: string;
    icon: typeof Check;
    badge: "success" | "warning" | "secondary" | "outline";
    iconClassName: string;
  }
> = {
  complete: {
    label: "Verified",
    icon: Check,
    badge: "success",
    iconClassName: "bg-success/10 text-success",
  },
  action_required: {
    label: "Action required",
    icon: AlertTriangle,
    badge: "warning",
    iconClassName: "bg-warning/10 text-warning",
  },
  blocked: {
    label: "Blocked",
    icon: LockKeyhole,
    badge: "secondary",
    iconClassName: "bg-[var(--surface-active)] text-[var(--text-tertiary)]",
  },
  not_required: {
    label: "Not required",
    icon: CircleDashed,
    badge: "outline",
    iconClassName: "bg-[var(--surface-active)] text-[var(--text-secondary)]",
  },
};

function ReadinessItem({ item }: { item: SetupReadinessItem }) {
  const presentation = STATUS_PRESENTATION[item.status];
  const Icon = presentation.icon;

  return (
    <li className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
            presentation.iconClassName,
          )}
          aria-hidden="true"
        >
          <Icon className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <h3 className="text-sm font-semibold text-[var(--text-primary)]">
              {item.label}
            </h3>
            <Badge variant={presentation.badge}>{presentation.label}</Badge>
          </div>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            {item.description}
          </p>
          <p className="mt-2 break-words text-xs leading-5 text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
            <span className="font-semibold text-[var(--text-secondary)]">
              Evidence:
            </span>{" "}
            {item.evidence}
          </p>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-[var(--border-subtle)] pt-3 text-xs">
            <span className="text-[var(--text-tertiary)]">
              Owner: {item.owner}
            </span>
            {item.recovery_href ? (
              <Link
                href={item.recovery_href}
                className="inline-flex min-h-11 items-center gap-1 font-semibold text-brand-primary hover:underline"
              >
                {item.recovery_label}
                <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
              </Link>
            ) : (
              <span className="font-semibold text-[var(--text-secondary)]">
                {item.recovery_label}
              </span>
            )}
          </div>
        </div>
      </div>
    </li>
  );
}

function formatObservedAt(value: string): string {
  const observedAt = new Date(value);
  if (Number.isNaN(observedAt.getTime())) return "Timestamp unavailable";

  return `${observedAt.getUTCFullYear()}-${String(observedAt.getUTCMonth() + 1).padStart(2, "0")}-${String(observedAt.getUTCDate()).padStart(2, "0")} ${String(observedAt.getUTCHours()).padStart(2, "0")}:${String(observedAt.getUTCMinutes()).padStart(2, "0")} UTC`;
}

export function SetupReadinessPanel({
  token,
  compact = false,
}: {
  token: string | null;
  compact?: boolean;
}) {
  const readiness = useSetupReadiness(token);

  if (readiness.isLoading) {
    return (
      <Card
        role="region"
        aria-labelledby="setup-readiness-loading-title"
        aria-busy="true"
        data-testid="setup-readiness-loading"
      >
        <CardHeader>
          <h2
            id="setup-readiness-loading-title"
            className="type-heading-md text-base text-[var(--text-primary)]"
          >
            Workspace launch checklist
          </h2>
          <CardDescription>
            Verifying organization-scoped setup evidence…
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  if (readiness.isError || !readiness.data) {
    return (
      <Card
        role="alert"
        aria-labelledby="setup-readiness-error-title"
        data-testid="setup-readiness-error"
      >
        <CardHeader>
          <h2
            id="setup-readiness-error-title"
            className="type-heading-md text-base text-[var(--text-primary)]"
          >
            Setup verification unavailable
          </h2>
          <CardDescription>
            No checklist item is marked complete while the authoritative
            workspace snapshot is unavailable. Existing settings remain
            unchanged.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            variant="outline"
            className="min-h-11"
            onClick={() => void readiness.refetch()}
          >
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            Retry setup verification
          </Button>
        </CardContent>
      </Card>
    );
  }

  const { data } = readiness;
  const isReady = data.overall_status === "ready";
  const remaining = Math.max(0, data.applicable_items - data.completed_items);
  const checklist = (
    <ol className="grid gap-3 lg:grid-cols-2">
      {data.items.map((item) => (
        <ReadinessItem key={item.id} item={item} />
      ))}
    </ol>
  );

  return (
    <Card
      role="region"
      aria-labelledby="setup-readiness-title"
      className="overflow-hidden border-brand-primary/20"
      data-testid="setup-readiness-panel"
    >
      <CardHeader className="border-b border-[var(--border-subtle)] bg-[linear-gradient(120deg,var(--bg-surface),color-mix(in_srgb,var(--brand-primary)_6%,var(--bg-surface)))]">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-primary/10 text-brand-primary">
              <ShieldCheck className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <h2
                id="setup-readiness-title"
                className="type-heading-md text-base text-[var(--text-primary)]"
              >
                Workspace launch checklist
              </h2>
              <CardDescription className="mt-1 max-w-2xl">
                Server-verified setup evidence, ownership, and the next safe
                action. Browser tour progress is not used as proof.
              </CardDescription>
            </div>
          </div>
          <Badge variant={isReady ? "success" : "warning"}>
            {isReady ? "Ready" : `${remaining} remaining`}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2 text-sm">
          <p className="font-semibold text-[var(--text-primary)]">
            {data.completed_items} of {data.applicable_items} applicable checks
            verified
          </p>
          <p className="text-xs text-[var(--text-tertiary)]">
            Snapshot:{" "}
            <time dateTime={data.observed_at}>
              {formatObservedAt(data.observed_at)}
            </time>
          </p>
        </div>
        <div
          className="mb-5 h-2 overflow-hidden rounded-full bg-[var(--surface-active)]"
          role="progressbar"
          aria-label="Workspace setup readiness"
          aria-valuemin={0}
          aria-valuemax={data.applicable_items}
          aria-valuenow={data.completed_items}
        >
          <div
            className="h-full rounded-full bg-brand-primary transition-[width] motion-reduce:transition-none"
            style={{
              width: `${data.applicable_items > 0 ? (data.completed_items / data.applicable_items) * 100 : 100}%`,
            }}
          />
        </div>
        {compact ? (
          <details data-testid="setup-readiness-details" className="group">
            <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between rounded-lg border border-[var(--border-default)] px-3 text-sm font-semibold text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 [&::-webkit-details-marker]:hidden">
              Review setup evidence and recovery actions
              <ChevronDown
                className="h-4 w-4 transition-transform group-open:rotate-180 motion-reduce:transition-none"
                aria-hidden="true"
              />
            </summary>
            <div className="pt-3">{checklist}</div>
          </details>
        ) : (
          checklist
        )}
      </CardContent>
    </Card>
  );
}
