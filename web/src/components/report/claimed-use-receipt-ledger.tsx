"use client";

import { useId, type ReactNode } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FileCheck2,
  History,
  ShieldX,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn, formatDate } from "@/lib/utils";
import type {
  ClaimedUseReceipt,
  ClaimedUseReceiptListResponse,
} from "@/types/api";

export interface ClaimedUseReceiptLedgerState {
  data?: ClaimedUseReceiptListResponse;
  error?: unknown;
  isError: boolean;
  isLoading: boolean;
}

interface ClaimedUseReceiptLedgerProps {
  state: ClaimedUseReceiptLedgerState;
  variant?: "screen" | "print" | "export";
  renderAction?: (item: ClaimedUseReceipt) => ReactNode;
}

type ReceiptDisplayState = "current" | "prior" | "revoked" | "invalid";

function getReceiptDisplayState(
  item: ClaimedUseReceipt,
  ledger: ClaimedUseReceiptListResponse,
): ReceiptDisplayState {
  const coordinatesMatch =
    item.analysis_id === item.receipt.analysis_id &&
    item.report_id === item.receipt.report_id &&
    item.report_fingerprint === item.receipt.report_fingerprint &&
    item.patent_id === item.receipt.patent_id &&
    item.claim_number === item.receipt.claim_number &&
    item.accused_act_index === item.receipt.accused_act_index &&
    item.accused_act_sha256 === item.receipt.accused_act_sha256 &&
    item.issuer_user_id === item.receipt.issuer_user_id &&
    item.reviewer_role === item.receipt.reviewer_role &&
    item.attestation_statement_version ===
      item.receipt.attestation_statement_version &&
    item.issued_at === item.receipt.verified_at;

  if (!coordinatesMatch) {
    return "invalid";
  }
  if (item.revoked_at) {
    return "revoked";
  }
  if (
    item.governs_current_report &&
    item.receipt.report_id === ledger.current_report_id &&
    item.receipt.report_fingerprint === ledger.current_report_fingerprint
  ) {
    return "current";
  }
  return "prior";
}

const STATE_META = {
  current: {
    badge: "success" as const,
    icon: CheckCircle2,
    label: "Current counsel overlay",
  },
  prior: {
    badge: "warning" as const,
    icon: History,
    label: "Prior report",
  },
  revoked: {
    badge: "destructive" as const,
    icon: ShieldX,
    label: "Revoked",
  },
  invalid: {
    badge: "destructive" as const,
    icon: AlertTriangle,
    label: "Integrity mismatch",
  },
};

export function ClaimedUseReceiptLedger({
  state,
  variant = "screen",
  renderAction,
}: ClaimedUseReceiptLedgerProps) {
  const headingId = useId();
  const isPrint = variant === "print";
  const isCompact = variant === "export";

  if (state.isLoading) {
    return (
      <section
        aria-labelledby={headingId}
        className={cn(
          "rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/35 p-4",
          isPrint && "print-claimed-use-receipts",
        )}
        role="status"
        aria-live="polite"
      >
        <h2
          id={headingId}
          className="text-sm font-semibold text-[var(--text-primary)]"
        >
          Claimed-use counsel record
        </h2>
        <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
          Verifying the attributable receipt ledger. Until this finishes, do not
          infer that no counsel receipts exist.
        </p>
      </section>
    );
  }

  if (state.isError || !state.data) {
    return (
      <section
        aria-labelledby={headingId}
        className={cn(
          "rounded-lg border border-error/30 bg-error/8 p-4",
          isPrint && "print-claimed-use-receipts",
        )}
        role="alert"
      >
        <div className="flex items-start gap-3">
          <AlertTriangle
            className="mt-0.5 h-4 w-4 shrink-0 text-error"
            aria-hidden="true"
          />
          <div className="min-w-0">
            <h2
              id={headingId}
              className="text-sm font-semibold text-[var(--text-primary)]"
            >
              Claimed-use receipt history unavailable
            </h2>
            <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
              This view could not verify the org-scoped counsel ledger. Do not
              treat this state as evidence that no receipt exists, and do not
              rely on this packet as a complete receipt history.
            </p>
          </div>
        </div>
      </section>
    );
  }

  const ledger = state.data;
  const classified = ledger.items.map((item) => ({
    item,
    state: getReceiptDisplayState(item, ledger),
  }));
  const current = classified.filter((entry) => entry.state === "current");
  const history = classified.filter((entry) => entry.state !== "current");
  const revokedCount = classified.filter(
    (entry) => entry.state === "revoked",
  ).length;
  const invalidCount = classified.filter(
    (entry) => entry.state === "invalid",
  ).length;

  return (
    <section
      aria-labelledby={headingId}
      className={cn(
        "rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 shadow-[var(--shadow-xs)]",
        isPrint && "print-claimed-use-receipts",
      )}
      data-testid={`claimed-use-receipt-ledger-${variant}`}
    >
      <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-brand-primary">
            <FileCheck2 className="h-4 w-4 shrink-0" aria-hidden="true" />
            Attributable counsel overlay
          </p>
          <h2
            id={headingId}
            className="mt-1 text-sm font-semibold text-[var(--text-primary)]"
          >
            Claimed-use receipt history
          </h2>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-[var(--text-secondary)]">
            These attorney-issued records are bound to an exact report, claim,
            proposed use, and governed source set. They do not rewrite or
            recertify the pipeline result.
          </p>
        </div>
        <dl
          className="grid shrink-0 grid-cols-3 gap-2 text-center"
          aria-label="Claimed-use receipt state summary"
          role="group"
        >
          <div className="min-w-[4.5rem] rounded-md bg-success/10 px-2 py-1.5">
            <dt className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
              Current
            </dt>
            <dd className="text-sm font-semibold text-[var(--text-primary)]">
              {current.length}
            </dd>
          </div>
          <div className="min-w-[4.5rem] rounded-md bg-[var(--surface-muted)] px-2 py-1.5">
            <dt className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
              Prior
            </dt>
            <dd className="text-sm font-semibold text-[var(--text-primary)]">
              {classified.filter((entry) => entry.state === "prior").length}
            </dd>
          </div>
          <div className="min-w-[4.5rem] rounded-md bg-error/8 px-2 py-1.5">
            <dt className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
              Revoked
            </dt>
            <dd className="text-sm font-semibold text-[var(--text-primary)]">
              {revokedCount}
            </dd>
          </div>
        </dl>
      </div>

      {invalidCount > 0 ? (
        <p
          className="mt-3 rounded-md border border-error/30 bg-error/8 p-3 text-xs leading-5 text-error"
          role="alert"
        >
          {invalidCount} stored{" "}
          {invalidCount === 1 ? "record has" : "records have"} conflicting
          signed and persisted coordinates. Those records are not presented as
          current.
        </p>
      ) : null}

      {classified.length === 0 ? (
        <p className="mt-3 rounded-md border border-dashed border-[var(--border-emphasis)] p-3 text-xs leading-5 text-[var(--text-secondary)]">
          No claimed-use counsel receipt is present in the verified ledger for
          this analysis. The certified report remains unchanged.
        </p>
      ) : (
        <div className="mt-4 space-y-3">
          {current.length === 0 ? (
            <p className="rounded-md border border-warning/30 bg-warning/10 p-3 text-xs leading-5 text-[var(--text-secondary)]">
              No active receipt governs the current report fingerprint. Prior or
              revoked records below must not be treated as current counsel
              confirmation.
            </p>
          ) : null}

          {current.map(({ item, state: displayState }) => (
            <ReceiptRecord
              key={item.id}
              displayState={displayState}
              item={item}
              renderAction={renderAction}
              compact={isCompact}
              expandAuditDetails={isPrint}
            />
          ))}

          {history.length > 0 ? (
            isPrint || isCompact ? (
              <div className="space-y-3">
                <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                  Prior and revoked records
                </h3>
                {history.map(({ item, state: displayState }) => (
                  <ReceiptRecord
                    key={item.id}
                    displayState={displayState}
                    item={item}
                    compact={isCompact}
                    expandAuditDetails={isPrint}
                  />
                ))}
              </div>
            ) : (
              <details className="group rounded-md border border-[var(--border-subtle)]">
                <summary className="min-h-11 cursor-pointer list-none px-3 py-3 text-xs font-semibold text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary">
                  Review {history.length} prior, revoked, or flagged{" "}
                  {history.length === 1 ? "record" : "records"}
                </summary>
                <div className="space-y-3 border-t border-[var(--border-subtle)] p-3">
                  {history.map(({ item, state: displayState }) => (
                    <ReceiptRecord
                      key={item.id}
                      displayState={displayState}
                      item={item}
                      renderAction={renderAction}
                      compact={isCompact}
                      expandAuditDetails={false}
                    />
                  ))}
                </div>
              </details>
            )
          ) : null}
        </div>
      )}
    </section>
  );
}

function ReceiptRecord({
  compact,
  displayState,
  expandAuditDetails,
  item,
  renderAction,
}: {
  compact: boolean;
  displayState: ReceiptDisplayState;
  expandAuditDetails: boolean;
  item: ClaimedUseReceipt;
  renderAction?: (item: ClaimedUseReceipt) => ReactNode;
}) {
  const titleId = useId();
  const meta = STATE_META[displayState];
  const StateIcon = meta.icon;

  return (
    <article
      aria-labelledby={titleId}
      className={cn(
        "min-w-0 rounded-md border p-3",
        displayState === "current" && "border-success/30 bg-success/8",
        displayState === "prior" && "border-warning/25 bg-warning/8",
        (displayState === "revoked" || displayState === "invalid") &&
          "border-error/25 bg-error/8",
      )}
      data-receipt-state={displayState}
      data-print-keep-together
    >
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h3
            id={titleId}
            className="break-words font-mono text-xs font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]"
          >
            {item.patent_id} · claim {item.claim_number}
          </h3>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            Attorney record issued {formatDate(item.issued_at)} · proposed use{" "}
            {item.accused_act_index + 1}
          </p>
        </div>
        <Badge variant={meta.badge} className="w-fit shrink-0">
          <StateIcon className="mr-1 h-3 w-3" aria-hidden="true" />
          {meta.label}
        </Badge>
      </div>

      <dl className="mt-3 grid min-w-0 gap-2 text-xs sm:grid-cols-2">
        <div className="min-w-0">
          <dt className="text-[var(--text-tertiary)]">Signed report</dt>
          <dd className="mt-0.5 break-all font-mono text-[var(--text-primary)]">
            {item.receipt.report_id}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-[var(--text-tertiary)]">Issuing attorney ID</dt>
          <dd className="mt-0.5 break-all font-mono text-[var(--text-primary)]">
            {item.receipt.issuer_user_id}
          </dd>
        </div>
        <Digest label="Receipt digest" value={item.receipt.receipt_sha256} />
        <Digest label="Report fingerprint" value={item.report_fingerprint} />
      </dl>

      {item.receipt.evidence_references.length > 0 ? (
        <div className="mt-3">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
            Server-derived governed references
          </p>
          <ul className="mt-1 space-y-1 text-xs leading-5 text-[var(--text-secondary)]">
            {item.receipt.evidence_references.map((reference) => (
              <li
                key={reference}
                className="break-words font-mono [overflow-wrap:anywhere]"
              >
                {reference}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="mt-3 text-xs font-semibold text-error" role="alert">
          Governed evidence references are missing; do not rely on this record.
        </p>
      )}

      {item.revoked_at ? (
        <p className="mt-3 rounded-md border border-error/20 bg-[var(--bg-surface)]/70 p-2 text-xs leading-5 text-[var(--text-secondary)]">
          <span className="font-semibold text-error">
            Revoked {formatDate(item.revoked_at)}
            {item.revoked_by_user_id ? ` by ${item.revoked_by_user_id}` : ""}:
          </span>{" "}
          {item.revocation_reason}
        </p>
      ) : null}

      {!compact && expandAuditDetails ? (
        <div className="mt-3">
          <p className="py-2 text-xs font-semibold text-[var(--text-primary)]">
            Signed coordinates and attestation
          </p>
          <SignedAuditDetails item={item} />
        </div>
      ) : !compact ? (
        <details className="mt-3">
          <summary className="min-h-11 cursor-pointer py-2 text-xs font-semibold text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary">
            Inspect signed coordinates and digests
          </summary>
          <SignedAuditDetails item={item} />
        </details>
      ) : null}

      {renderAction ? (
        <div className="mt-3" data-no-print>
          {renderAction(item)}
        </div>
      ) : null}
    </article>
  );
}

function SignedAuditDetails({ item }: { item: ClaimedUseReceipt }) {
  return (
    <dl className="grid min-w-0 gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/75 p-2 text-xs sm:grid-cols-2">
      <Digest label="Accused-use snapshot" value={item.accused_act_sha256} />
      <Digest
        label="Current-claim receipt"
        value={item.receipt.current_claim_receipt_sha256}
      />
      <Digest
        label="Attestation statement"
        value={item.attestation_statement_version}
      />
      <Digest label="Attestation key" value={item.receipt.attestation_key_id} />
    </dl>
  );
}

function Digest({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="font-semibold uppercase tracking-[0.08em] text-[var(--text-tertiary)]">
        {label}
      </dt>
      <dd className="mt-0.5 break-all font-mono text-[var(--text-primary)]">
        {value}
      </dd>
    </div>
  );
}
