"use client";

import type { ComponentType } from "react";
import {
  AlertTriangle,
  BarChart3,
  Building2,
  CheckCircle,
  Cog,
  Loader2,
  RotateCcw,
  ScrollText,
  Shield,
  ShieldCheck,
  Users,
  XCircle,
} from "lucide-react";
import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export type AdminTab =
  | "overview"
  | "organizations"
  | "users"
  | "metrics"
  | "audit-logs"
  | "tasks";

export const TABS: {
  id: AdminTab;
  label: string;
  icon: ComponentType<{ className?: string }>;
}[] = [
  { id: "overview", label: "Overview", icon: Shield },
  { id: "organizations", label: "Organizations", icon: Building2 },
  { id: "users", label: "Users", icon: Users },
  { id: "metrics", label: "Ops Snapshot", icon: BarChart3 },
  { id: "audit-logs", label: "Audit Logs", icon: ScrollText },
  { id: "tasks", label: "Tasks", icon: Cog },
];

export function resolveAdminTab(value: string | null): AdminTab {
  return TABS.some((tab) => tab.id === value)
    ? (value as AdminTab)
    : "overview";
}

export const ROLE_OPTIONS = ["admin", "attorney", "scientist", "client"];
export const INVITE_ROLE_OPTIONS = ["attorney", "scientist", "client"];
export const PLAN_OPTIONS = ["free", "starter", "pro", "enterprise"];
export const ADMIN_FIELD_CLASS =
  "h-11 rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-muted)] px-3 text-sm transition-colors focus-visible:border-brand-primary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)] disabled:cursor-not-allowed disabled:opacity-50";
export const ADMIN_BUTTON_TARGET_CLASS = "min-h-11";

export function relativeTime(date: string): string {
  const timestamp = new Date(date).getTime();
  if (Number.isNaN(timestamp)) {
    return "Unknown";
  }

  const diff = Date.now() - timestamp;
  if (diff < 0) {
    return "Scheduled";
  }

  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function ServiceStatusIcon({ status }: { status: string }) {
  if (status === "healthy" || status === "ok") {
    return <CheckCircle className="h-4 w-4 text-success" />;
  }
  if (status === "degraded" || status === "warning") {
    return <AlertTriangle className="h-4 w-4 text-warning" />;
  }
  return <XCircle className="h-4 w-4 text-error" />;
}

type AdminSurface = AdminTab;
type AdminStatusVariant = "auth" | "loading" | "restricted" | "temporary";

interface AdminStatusCopy {
  title: string;
  description: string;
  contextItems: string[];
  recoveryTitle: string;
  recoveryBody: string;
}

const ADMIN_SURFACE_LABEL: Record<AdminSurface, string> = {
  overview: "system overview",
  organizations: "organization controls",
  users: "user controls",
  metrics: "platform metrics",
  "audit-logs": "audit log",
  tasks: "task queue",
};

function getAdminStatusCopy(
  surface: AdminSurface,
  variant: AdminStatusVariant,
): AdminStatusCopy {
  const label = ADMIN_SURFACE_LABEL[surface];

  if (variant === "auth") {
    return {
      title: `Checking ${label} access`,
      description:
        "Confirming administrator access before Praviar requests tenant-scoped operational records.",
      contextItems: [
        "Admin session check in progress",
        "No tenant data exposed",
        "Controls unlock after access",
      ],
      recoveryTitle: "Preparing a governed admin view",
      recoveryBody:
        "Praviar only requests administrative records after an authenticated administrator token is available.",
    };
  }

  if (variant === "loading") {
    return {
      title: `Loading ${label}`,
      description:
        "Retrieving operational state, tenant controls, and audit context for administrator review.",
      contextItems: [
        "Admin records requested",
        "Existing state unchanged",
        "Actions wait for a fresh view",
      ],
      recoveryTitle: "Opening the current admin view",
      recoveryBody:
        "Role, tenant, and queue controls remain unavailable until the latest admin data is loaded.",
    };
  }

  if (variant === "restricted") {
    return {
      title: `${capitalizeFirst(label)} access restricted`,
      description:
        "Your current session is not authorized to view this administrator-scoped surface. Cached records are hidden until access is confirmed again.",
      contextItems: [
        "Cached admin data hidden",
        "No tenant records exposed",
        "Retry after access changes",
      ],
      recoveryTitle: "Confirm admin access",
      recoveryBody:
        "A retry requests a fresh authorization check before any administrator-scoped records are shown.",
    };
  }

  return {
    title: `${capitalizeFirst(label)} temporarily unavailable`,
    description:
      "The service did not return a usable admin view. Existing organizations, users, audit records, and queue state are unchanged.",
    contextItems: [
      "No admin data changed",
      "Retry requests a fresh view",
      "Tenant records withheld",
    ],
    recoveryTitle: "Retry the admin request",
    recoveryBody:
      "A retry asks for the latest administrator-scoped view without changing roles, plans, users, or queued work.",
  };
}

export function AdminStatusState({
  surface,
  variant,
  onRetry,
}: {
  surface: AdminSurface;
  variant: AdminStatusVariant;
  onRetry?: () => void;
}) {
  const copy = getAdminStatusCopy(surface, variant);
  const isPending = variant === "auth" || variant === "loading";
  const titleId = `admin-${surface}-${variant}-title`;
  const summaryId = `${titleId}-summary`;

  return (
    <section
      aria-labelledby={titleId}
      aria-describedby={summaryId}
      className="praviar-operational-field scroll-mt-20 overflow-hidden rounded-lg"
      data-praviar-status-frame
      data-testid={`admin-${surface}-status-${variant}`}
    >
      <div className="border-b border-[var(--border-subtle)] bg-[var(--surface-muted)]/40 px-4 py-3 sm:px-6 sm:py-5">
        <div className="flex min-w-0 items-start gap-3 sm:gap-4">
          <PraviarMarkFrame size="dialog" />
          <div
            role={isPending ? "status" : "alert"}
            aria-live={isPending ? "polite" : "assertive"}
            aria-busy={isPending ? true : undefined}
            aria-atomic="true"
            aria-labelledby={titleId}
            aria-describedby={summaryId}
            className="min-w-0"
          >
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
              Admin control plane
            </p>
            <h2
              id={titleId}
              className="mt-1 break-words text-2xl font-semibold leading-tight text-[var(--text-primary)] [overflow-wrap:anywhere] sm:type-heading-xl"
            >
              {copy.title}
            </h2>
            <p
              id={summaryId}
              className="mt-2 max-w-2xl text-sm leading-5 text-[var(--text-secondary)] sm:leading-6"
            >
              {copy.description}
            </p>
          </div>
        </div>
      </div>

      <div className="grid min-w-0 gap-0 lg:grid-cols-[0.82fr_1.18fr]">
        <div className="border-b border-[var(--border-subtle)] bg-[var(--surface-muted)]/30 p-3 sm:p-6 lg:border-b-0 lg:border-r">
          <div
            className={cn(
              "flex h-10 w-10 items-center justify-center rounded-lg border sm:h-14 sm:w-14",
              variant === "temporary" || variant === "restricted"
                ? "border-error/25 bg-error/10 text-error"
                : "border-info/25 bg-info/10 text-info",
            )}
          >
            {variant === "loading" ? (
              <Loader2
                className="h-5 w-5 animate-spin motion-reduce:animate-none sm:h-6 sm:w-6"
                aria-hidden="true"
              />
            ) : variant === "temporary" || variant === "restricted" ? (
              <AlertTriangle
                className="h-5 w-5 sm:h-6 sm:w-6"
                aria-hidden="true"
              />
            ) : (
              <Shield className="h-5 w-5 sm:h-6 sm:w-6" aria-hidden="true" />
            )}
          </div>

          <div className="mt-3 grid gap-2 sm:mt-5 sm:gap-3">
            {copy.contextItems.map((item) => (
              <div
                key={item}
                className="praviar-glass-chip flex min-w-0 items-center gap-3 rounded-lg px-3 py-2"
              >
                <ShieldCheck
                  className="h-4 w-4 shrink-0 text-[var(--brand-primary)]"
                  aria-hidden="true"
                />
                <span className="min-w-0 text-sm text-[var(--text-secondary)]">
                  {item}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="min-w-0 p-3 sm:p-6">
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 p-3 sm:p-4">
            <p className="font-semibold text-[var(--text-primary)]">
              {copy.recoveryTitle}
            </p>
            <p className="mt-1 text-sm leading-5 text-[var(--text-secondary)] sm:leading-6">
              {copy.recoveryBody}
            </p>
            {onRetry ? (
              <Button
                type="button"
                variant="outline"
                className="mt-3 min-h-11 w-full gap-2 sm:mt-4 sm:w-auto"
                onClick={onRetry}
              >
                <RotateCcw className="h-4 w-4" aria-hidden="true" />
                Retry admin load
              </Button>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}

export function AdminRefreshWarning({ label }: { label: string }) {
  return (
    <div
      role="status"
      aria-atomic="true"
      className="rounded-lg border border-warning/20 bg-warning/10 px-4 py-3"
    >
      <div className="flex items-start gap-2">
        <AlertTriangle
          className="mt-0.5 h-4 w-4 shrink-0 text-warning"
          aria-hidden="true"
        />
        <p className="text-sm leading-6 text-[var(--text-secondary)]">
          {label} refresh failed. Existing admin data is still shown, and no
          tenant or user changes were made.
        </p>
      </div>
    </div>
  );
}

export function AdminPagedEmptyState({
  title,
  description,
  actionLabel,
  onAction,
}: {
  title: string;
  description: string;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <Card>
      <CardContent className="p-5 sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-[var(--text-primary)]">
              {title}
            </h3>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              {description}
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            className="min-h-11 w-full gap-2 sm:w-auto"
            onClick={onAction}
          >
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            {actionLabel}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function capitalizeFirst(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}
