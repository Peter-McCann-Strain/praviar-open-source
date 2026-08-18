"use client";

import type { ComponentType } from "react";
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  KeyRound,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface SettingsGovernanceRailProps {
  activeCount: number;
  expiredCount?: number;
  expiringSoonCount?: number;
  neverUsedCount: number;
  revokePending: boolean;
  createOpen: boolean;
}

export function SettingsGovernanceRail({
  activeCount,
  expiredCount = 0,
  expiringSoonCount = 0,
  neverUsedCount,
  revokePending,
  createOpen,
}: SettingsGovernanceRailProps) {
  const reviewNeeded =
    neverUsedCount > 0 ||
    expiredCount > 0 ||
    expiringSoonCount > 0 ||
    revokePending ||
    createOpen;

  return (
    <aside
      className="space-y-4 lg:sticky lg:top-24 lg:self-start"
      aria-labelledby="settings-governance-heading"
    >
      <Card className="overflow-hidden">
        <CardHeader className="border-b border-[var(--border-default)]">
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle
                id="settings-governance-heading"
                className="text-base"
                role="heading"
                aria-level={2}
              >
                Access governance
              </CardTitle>
              <p className="mt-1 text-sm leading-5 text-[var(--text-secondary)]">
                Credential, identity, and audit controls for organization data.
              </p>
            </div>
            <Badge variant={reviewNeeded ? "warning" : "success"}>
              {reviewNeeded ? "Review" : "Clear"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 pt-6">
          <div className="grid gap-3">
            <RailItem
              icon={KeyRound}
              title={`${activeCount} active API key${activeCount === 1 ? "" : "s"}`}
              detail="Rotate keys on a schedule and revoke unused automation credentials."
            />
            <RailItem
              icon={
                expiredCount > 0 || expiringSoonCount > 0
                  ? AlertTriangle
                  : CheckCircle2
              }
              title={
                expiredCount > 0
                  ? `${expiredCount} expired key${expiredCount === 1 ? "" : "s"}`
                  : expiringSoonCount > 0
                    ? `${expiringSoonCount} key${expiringSoonCount === 1 ? "" : "s"} expiring soon`
                    : "No expiring keys"
              }
              detail={
                expiredCount > 0
                  ? "Revoke or replace expired automation credentials."
                  : expiringSoonCount > 0
                    ? "Rotate these credentials before scheduled expiry."
                    : "Active credentials have bounded lifetimes."
              }
              warning={expiredCount > 0 || expiringSoonCount > 0}
            />
            <RailItem
              icon={neverUsedCount > 0 ? AlertTriangle : CheckCircle2}
              title={
                neverUsedCount > 0
                  ? `${neverUsedCount} key${neverUsedCount === 1 ? "" : "s"} never used`
                  : "No never-used keys"
              }
              detail={
                neverUsedCount > 0
                  ? "Review unused keys before they become forgotten access paths."
                  : "Issued credentials show expected usage or are revoked."
              }
              warning={neverUsedCount > 0}
            />
            <RailItem
              icon={ShieldCheck}
              title="SSO managed through Clerk"
              detail="Configuration changes require IdP and Clerk dashboard completion."
            />
            <RailItem
              icon={CalendarClock}
              title="Bounded credential lifetime"
              detail="New API keys must declare scopes and an expiry date."
            />
          </div>

          {revokePending ? (
            <div className="rounded-lg border border-warning/25 bg-warning/10 p-3 text-xs leading-5 text-warning">
              Revocation is in progress. Other revoke actions are locked until
              the request settles.
            </div>
          ) : null}

          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-subtle)] p-3">
            <div className="flex items-center gap-2">
              <Workflow
                className="h-4 w-4 text-brand-primary"
                aria-hidden="true"
              />
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                Admin review path
              </p>
            </div>
            <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
              Issue keys for approved automations, monitor first use, then close
              unused paths with retained audit context.
            </p>
          </div>
        </CardContent>
      </Card>
    </aside>
  );
}

function RailItem({
  icon: Icon,
  title,
  detail,
  warning = false,
}: {
  icon: ComponentType<{ className?: string }>;
  title: string;
  detail: string;
  warning?: boolean;
}) {
  return (
    <div className="flex items-start gap-3">
      <span
        className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border ${
          warning
            ? "border-warning/25 bg-warning/10 text-warning"
            : "border-brand-primary/20 bg-brand-primary/10 text-brand-primary"
        }`}
      >
        <Icon className="h-4 w-4" aria-hidden="true" />
      </span>
      <div>
        <p className="text-sm font-medium text-[var(--text-primary)]">
          {title}
        </p>
        <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
          {detail}
        </p>
      </div>
    </div>
  );
}
