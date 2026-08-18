import type { ComponentType } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  KeyRound,
  Loader2,
  ShieldCheck,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";

interface SettingsAccessPostureStripProps {
  activeCount: number;
  createOpen: boolean;
  expiredCount?: number;
  expiringSoonCount?: number;
  neverUsedCount: number;
  refreshWarning?: boolean;
  revokePending: boolean;
  total: number;
}

type PostureTone = "success" | "warning";

export function SettingsAccessPostureStrip({
  activeCount,
  createOpen,
  expiredCount = 0,
  expiringSoonCount = 0,
  neverUsedCount,
  refreshWarning = false,
  revokePending,
  total,
}: SettingsAccessPostureStripProps) {
  const reviewNeeded =
    neverUsedCount > 0 ||
    expiredCount > 0 ||
    expiringSoonCount > 0 ||
    refreshWarning;
  const postureTone: PostureTone =
    revokePending || createOpen || reviewNeeded ? "warning" : "success";
  const postureLabel = revokePending
    ? "Revocation pending"
    : createOpen
      ? "Credential draft open"
      : reviewNeeded
        ? "Review needed"
        : "Access clear";
  const postureDetail = revokePending
    ? "Credential changes are locked until the revocation request settles."
    : createOpen
      ? "Finish or close the new-key flow before starting another credential change."
      : refreshWarning
        ? "Existing key data is still visible, but the latest refresh needs retry."
        : expiredCount > 0
          ? "Expired credentials remain visible for revocation and audit closure."
          : expiringSoonCount > 0
            ? "Rotate expiring keys before automation reaches its access deadline."
            : neverUsedCount > 0
              ? "Review never-used keys before they become forgotten access paths."
              : "Active credentials have explicit scopes and bounded expiry.";

  return (
    <section
      aria-labelledby="settings-access-posture-heading"
      className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 p-4 shadow-[var(--shadow-xs)]"
      data-settings-access-posture
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border ${
              postureTone === "success"
                ? "border-success/25 bg-success/10 text-success"
                : "border-warning/25 bg-warning/10 text-warning"
            }`}
          >
            {revokePending ? (
              <Loader2
                className="h-4 w-4 animate-spin motion-reduce:animate-none"
                aria-hidden="true"
              />
            ) : postureTone === "success" ? (
              <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            ) : (
              <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            )}
          </span>
          <div className="min-w-0">
            <div
              className="flex min-w-0 flex-wrap items-center gap-2"
              role="status"
              aria-live="polite"
            >
              <h2
                id="settings-access-posture-heading"
                className="text-sm font-semibold text-[var(--text-primary)]"
              >
                Access posture
              </h2>
              <Badge variant={postureTone}>{postureLabel}</Badge>
            </div>
            <p className="mt-1 max-w-3xl text-sm leading-5 text-[var(--text-secondary)]">
              {postureDetail}
            </p>
            <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
              API key posture only; SSO status is governed in the identity panel
              below.
            </p>
          </div>
        </div>

        <dl className="grid min-w-0 gap-2 sm:grid-cols-3 lg:w-[30rem]">
          <PostureMetric
            icon={KeyRound}
            label="Issued ledger"
            value={`${total.toLocaleString()} total`}
            detail="Includes revoked audit records"
          />
          <PostureMetric
            icon={CheckCircle2}
            label="Active access"
            value={`${activeCount.toLocaleString()} active`}
            detail="Unrevoked and not expired"
            tone="success"
          />
          <PostureMetric
            icon={
              expiredCount > 0 || expiringSoonCount > 0
                ? AlertTriangle
                : ShieldCheck
            }
            label="Needs review"
            value={`${(expiredCount + expiringSoonCount + neverUsedCount).toLocaleString()} flagged`}
            detail="Expired, expiring, or unused"
            tone={
              expiredCount > 0 || expiringSoonCount > 0 || neverUsedCount > 0
                ? "warning"
                : "success"
            }
          />
        </dl>
      </div>
    </section>
  );
}

function PostureMetric({
  detail,
  icon: Icon,
  label,
  tone = "default",
  value,
}: {
  detail: string;
  icon: ComponentType<{ className?: string }>;
  label: string;
  tone?: "default" | "success" | "warning";
  value: string;
}) {
  const iconClass =
    tone === "success"
      ? "border-success/20 bg-success/10 text-success"
      : tone === "warning"
        ? "border-warning/20 bg-warning/10 text-warning"
        : "border-brand-primary/20 bg-brand-primary/10 text-brand-primary";

  return (
    <div className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/72 px-3 py-2">
      <dt className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
        <span
          className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md border ${iconClass}`}
        >
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
        </span>
        {label}
      </dt>
      <dd className="mt-1 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
        {value}
      </dd>
      <dd className="mt-0.5 text-xs leading-5 text-[var(--text-secondary)]">
        {detail}
      </dd>
    </div>
  );
}
