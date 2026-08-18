"use client";

import Link from "next/link";
import {
  CheckCircle2,
  Clock3,
  ReceiptText,
  RotateCw,
  ShieldAlert,
  TriangleAlert,
} from "lucide-react";
import {
  CREDIT_PACK_DETAILS,
  formatReportCreditCount,
} from "@/components/billing/helpers";
import { Button } from "@/components/ui/button";
import {
  isStripeCheckoutSessionId,
  useCreditPackCheckoutReconciliation,
} from "@/hooks/use-billing";
import { WORKSPACE_SUPPORT_BOUNDARY_HREF } from "@/lib/support-boundary";

interface CreditPackReconciliationProps {
  capacityRefreshError?: boolean;
  currentConfirmedBalance: number;
  draftRestored?: boolean;
  isCapacityRefreshFetching?: boolean;
  onRefreshCapacity?: () => void;
  returnHref?: string;
  sessionId: string | null;
  surface: "analysis" | "billing";
  token: string | null;
}

function formatAppliedAt(value: string): string {
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) {
    return "timestamp unavailable";
  }

  return `${new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    hour: "2-digit",
    hour12: false,
    minute: "2-digit",
    month: "short",
    timeZone: "UTC",
    year: "numeric",
  }).format(new Date(timestamp))} UTC`;
}

function ReconciliationMetric({
  detail,
  label,
  value,
}: {
  detail?: string;
  label: string;
  value: string;
}) {
  return (
    <div className="praviar-account-metric-panel min-w-0 rounded-lg px-3 py-2">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-1 break-words text-sm font-semibold text-[var(--text-primary)]">
        {value}
      </p>
      {detail ? (
        <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
          {detail}
        </p>
      ) : null}
    </div>
  );
}

function LaunchDraftRecoveryWarning() {
  return (
    <div
      role="alert"
      className="mt-3 rounded-lg border border-warning/25 bg-warning/10 p-3"
      data-testid="credit-launch-draft-missing"
    >
      <div className="flex items-start gap-2">
        <TriangleAlert
          className="mt-0.5 h-4 w-4 shrink-0 text-warning"
          aria-hidden="true"
        />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            Launch packet was not restored
          </p>
          <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
            Credits may be confirmed, but the reviewed compound, product
            context, and reviewer handoff are no longer available on this
            device. Rebuild the launch packet before starting analysis; no run
            has been submitted from the missing draft.
          </p>
        </div>
      </div>
    </div>
  );
}

export function CreditPackCheckoutReconciliation({
  capacityRefreshError = false,
  currentConfirmedBalance,
  draftRestored = false,
  isCapacityRefreshFetching = false,
  onRefreshCapacity,
  returnHref,
  sessionId,
  surface,
  token,
}: CreditPackReconciliationProps) {
  const reconciliation = useCreditPackCheckoutReconciliation(token, sessionId);
  const validSession = isStripeCheckoutSessionId(sessionId);

  if (!validSession) {
    return (
      <section
        role="alert"
        aria-live="polite"
        className="rounded-lg border border-warning/25 bg-warning/10 p-4"
        data-testid="credit-reconciliation-unverified"
      >
        <div className="flex items-start gap-3">
          <ShieldAlert
            className="mt-0.5 h-5 w-5 shrink-0 text-warning"
            aria-hidden="true"
          />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              Checkout return cannot be verified
            </p>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              Praviar did not receive a valid Stripe session reference. No
              Report Credits are shown as applied. Refresh Billing, then use the
              operator-approved support path for your deployment if the issue
              remains.
            </p>
            <Button
              asChild
              variant="outline"
              size="sm"
              className="mt-3 min-h-11 w-full sm:w-auto"
            >
              <Link href={WORKSPACE_SUPPORT_BOUNDARY_HREF}>
                Review support path
              </Link>
            </Button>
          </div>
        </div>
      </section>
    );
  }

  if (reconciliation.error) {
    return (
      <section
        role="alert"
        aria-live="polite"
        className="rounded-lg border border-error/25 bg-error/10 p-4"
        data-testid="credit-reconciliation-error"
      >
        <div className="flex items-start gap-3">
          <TriangleAlert
            className="mt-0.5 h-5 w-5 shrink-0 text-error"
            aria-hidden="true"
          />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              Reconciliation status unavailable
            </p>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              Praviar could not verify this session against the organization
              ledger. Existing balance remains the only confirmed balance; no
              purchase is being claimed here.
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-3 min-h-11 w-full sm:w-auto"
              loading={reconciliation.isFetching}
              onClick={() => {
                void reconciliation.refetch();
              }}
            >
              <RotateCw className="h-4 w-4" aria-hidden="true" />
              Retry status check
            </Button>
          </div>
        </div>
      </section>
    );
  }

  const applied = reconciliation.data;
  if (applied?.status === "applied") {
    const pack = CREDIT_PACK_DETAILS[applied.credit_pack_id];
    const capacityRefreshPending =
      surface === "analysis" &&
      currentConfirmedBalance < applied.current_purchased_credits_balance;
    const capacityRefreshFailed =
      capacityRefreshPending && capacityRefreshError;

    return (
      <section
        role="status"
        aria-live="polite"
        className="praviar-account-control-card grid gap-4 overflow-hidden p-4 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.55fr)] lg:items-center"
        data-testid="credit-reconciliation-applied"
      >
        <div className="flex min-w-0 items-start gap-3">
          <CheckCircle2
            className="mt-0.5 h-5 w-5 shrink-0 text-success"
            aria-hidden="true"
          />
          <div className="min-w-0">
            <p className="type-label-sm text-success">
              Organization ledger confirmed
            </p>
            <p className="mt-1 type-heading-sm text-[var(--text-primary)]">
              {formatReportCreditCount(applied.credits_applied)} applied
            </p>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              This Stripe session is recorded in the append-only organization
              ledger.
              {surface === "analysis" && draftRestored
                ? " Your reviewed launch packet remains restored."
                : ""}
            </p>
            {surface === "analysis" && !draftRestored ? (
              <LaunchDraftRecoveryWarning />
            ) : null}
            {capacityRefreshPending ? (
              <div className="mt-2">
                <p className="text-sm font-semibold text-warning">
                  {capacityRefreshFailed
                    ? "Ledger confirmed; launch capacity refresh failed."
                    : "Ledger confirmed; refreshing launch capacity."}
                </p>
                {capacityRefreshFailed && onRefreshCapacity ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="mt-3 min-h-11 w-full sm:w-auto"
                    loading={isCapacityRefreshFetching}
                    onClick={onRefreshCapacity}
                  >
                    <RotateCw className="h-4 w-4" aria-hidden="true" />
                    Retry launch capacity
                  </Button>
                ) : null}
              </div>
            ) : null}
            {surface === "billing" && returnHref ? (
              <Button
                asChild
                variant="outline"
                size="sm"
                className="mt-3 min-h-11 w-full sm:w-auto"
              >
                <Link href={returnHref}>Return to analysis</Link>
              </Button>
            ) : null}
          </div>
        </div>
        <div className="grid min-w-0 gap-2 sm:grid-cols-3 lg:grid-cols-1">
          <ReconciliationMetric
            label="Pack"
            value={`${pack.label} · ${formatReportCreditCount(
              applied.credits_applied,
            )}`}
          />
          <ReconciliationMetric
            label="Current purchased balance"
            value={formatReportCreditCount(
              applied.current_purchased_credits_balance,
            )}
          />
          <ReconciliationMetric
            label="Audit"
            value={`Ledger ${applied.ledger_entry_id}`}
            detail={`Applied ${formatAppliedAt(applied.applied_at)}`}
          />
          <ReconciliationMetric
            label="Receipt"
            value="Stripe payment confirmation recorded"
            detail="Hosted invoice documents, if issued, appear in Invoice history."
          />
        </div>
      </section>
    );
  }

  const delayed = reconciliation.pollingTimedOut;
  return (
    <section
      role="status"
      aria-live="polite"
      className="rounded-lg border border-warning/25 bg-warning/10 p-4"
      data-testid={
        delayed
          ? "credit-reconciliation-delayed"
          : "credit-reconciliation-pending"
      }
    >
      <div className="flex items-start gap-3">
        <Clock3
          className="mt-0.5 h-5 w-5 shrink-0 text-warning"
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {delayed
              ? "Ledger confirmation is taking longer than expected"
              : "Checkout returned; Report Credits pending"}
          </p>
          <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
            {delayed
              ? "No matching organization-and-user ledger entry exists yet. This does not mean the payment failed. Do not launch work against these credits until confirmation appears."
              : "This browser returned with a Stripe-format session reference. The return URL alone does not verify payment or session ownership. Report Credits are unavailable until the signed webhook creates the matching organization ledger entry."}
          </p>
          {surface === "analysis" && draftRestored ? (
            <p className="mt-2 text-sm text-[var(--text-secondary)]">
              Your reviewed launch packet remains restored while confirmation is
              pending.
            </p>
          ) : null}
          {surface === "analysis" && !draftRestored ? (
            <LaunchDraftRecoveryWarning />
          ) : null}
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            <ReconciliationMetric
              label="Pack"
              value="Awaiting ledger confirmation"
            />
            <ReconciliationMetric
              label="Balance"
              value={formatReportCreditCount(currentConfirmedBalance)}
              detail="Existing confirmed balance only"
            />
            <ReconciliationMetric
              label="Receipt"
              value="Checked separately"
              detail="Hosted documents appear in Invoice history."
            />
          </div>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="min-h-11 w-full sm:w-auto"
              loading={reconciliation.isFetching}
              onClick={() => {
                void reconciliation.refetch();
              }}
            >
              <RotateCw className="h-4 w-4" aria-hidden="true" />
              Check status
            </Button>
            {delayed ? (
              <Button
                asChild
                variant="ghost"
                size="sm"
                className="min-h-11 w-full sm:w-auto"
              >
                <Link href={WORKSPACE_SUPPORT_BOUNDARY_HREF}>
                  <ReceiptText className="h-4 w-4" aria-hidden="true" />
                  Review support path
                </Link>
              </Button>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}
