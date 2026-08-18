"use client";

import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FileCheck2,
  RotateCcw,
  ShieldX,
} from "lucide-react";

import {
  ClaimedUseReceiptLedger,
  type ClaimedUseReceiptLedgerState,
} from "@/components/report/claimed-use-receipt-ledger";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  useIssueClaimedUseReceipt,
  useRevokeClaimedUseReceipt,
} from "@/hooks/use-claimed-use-receipts";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import { formatDate } from "@/lib/utils";
import type { FTOReport } from "@praviar/shared-types";
import type { ClaimedUseReceipt } from "@/types/api";

interface ClaimedUseReceiptWorkbenchProps {
  analysisId: string;
  canIssueReceipts: boolean;
  canReviewFindings: boolean;
  onRetryLedger?: () => void;
  receiptState: ClaimedUseReceiptLedgerState;
  report: FTOReport;
  token: string | null;
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return "The receipt workflow could not complete. Refresh the governed report and try again.";
}

function claimOptionValue(patentId: string, claimNumber: number): string {
  return `${patentId}::${claimNumber}`;
}

export function ClaimedUseReceiptWorkbench({
  analysisId,
  canIssueReceipts,
  canReviewFindings,
  onRetryLedger,
  receiptState,
  report,
  token,
}: ClaimedUseReceiptWorkbenchProps) {
  const issueReceipt = useIssueClaimedUseReceipt(analysisId, token);
  const revokeReceipt = useRevokeClaimedUseReceipt(analysisId, token);
  const [selectedUse, setSelectedUse] = useState("");
  const [selectedClaim, setSelectedClaim] = useState("");
  const [affirmed, setAffirmed] = useState(false);
  const [revokeTargetId, setRevokeTargetId] = useState<string | null>(null);
  const [revocationReason, setRevocationReason] = useState("");

  const claimOptions = report.patent_analyses.flatMap((patent) =>
    (patent.claims_analyzed ?? []).map((claim) => ({
      claimNumber: claim.claim_number,
      patentId: patent.patent_id,
      value: claimOptionValue(patent.patent_id, claim.claim_number),
    })),
  );
  const effectiveUse =
    selectedUse ||
    (receiptState.data?.eligible_uses[0]
      ? String(receiptState.data.eligible_uses[0].accused_act_index)
      : "");
  const effectiveClaim = selectedClaim || (claimOptions[0]?.value ?? "");
  const selectedUseRecord = receiptState.data?.eligible_uses.find(
    (item) => String(item.accused_act_index) === effectiveUse,
  );
  const selectedClaimRecord = claimOptions.find(
    (item) => item.value === effectiveClaim,
  );
  const canIssue = Boolean(
    canIssueReceipts &&
    token &&
    receiptState.data &&
    selectedUseRecord &&
    selectedClaimRecord &&
    affirmed &&
    !issueReceipt.isPending,
  );

  const handleIssue = async () => {
    if (
      !canIssue ||
      !receiptState.data ||
      !selectedUseRecord ||
      !selectedClaimRecord
    ) {
      return;
    }
    try {
      await issueReceipt.mutateAsync({
        expected_report_id: receiptState.data.current_report_id,
        expected_report_fingerprint:
          receiptState.data.current_report_fingerprint,
        patent_id: selectedClaimRecord.patentId,
        claim_number: selectedClaimRecord.claimNumber,
        accused_act_index: selectedUseRecord.accused_act_index,
        claimed_use_match: true,
        product_identity_match: true,
      });
      setAffirmed(false);
    } catch {
      // React Query retains and renders the mutation error below.
    }
  };

  const handleRevoke = async () => {
    if (!revokeTargetId || revocationReason.trim().length < 10) {
      return;
    }
    try {
      await revokeReceipt.mutateAsync({
        receiptId: revokeTargetId,
        reason: revocationReason.trim(),
      });
      setRevokeTargetId(null);
      setRevocationReason("");
    } catch {
      // React Query retains and renders the mutation error beside the action.
    }
  };

  const renderReceiptAction = (item: ClaimedUseReceipt) => {
    if (!item.can_revoke || item.revoked_at) {
      return null;
    }

    if (revokeTargetId !== item.id) {
      return (
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => {
            setRevokeTargetId(item.id);
            setRevocationReason("");
          }}
        >
          Revoke receipt
        </Button>
      );
    }

    return (
      <div className="space-y-2 rounded-md border border-warning/30 bg-warning/10 p-3">
        <label
          className="block text-xs font-semibold text-[var(--text-primary)]"
          htmlFor={`revoke-reason-${item.id}`}
        >
          Revocation reason
        </label>
        <Textarea
          id={`revoke-reason-${item.id}`}
          value={revocationReason}
          onChange={(event) => setRevocationReason(event.target.value)}
          maxLength={1000}
          rows={2}
          placeholder="Explain the changed product, label, claim record, or review conclusion."
        />
        {revokeReceipt.isError ? (
          <p className="text-xs text-error" role="alert">
            {errorMessage(revokeReceipt.error)}
          </p>
        ) : null}
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          <Button
            type="button"
            size="sm"
            variant="destructive"
            disabled={
              revocationReason.trim().length < 10 || revokeReceipt.isPending
            }
            onClick={() => void handleRevoke()}
          >
            <ShieldX className="mr-2 h-3.5 w-3.5" aria-hidden="true" />
            Confirm revocation
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => {
              setRevokeTargetId(null);
              setRevocationReason("");
            }}
          >
            Cancel
          </Button>
        </div>
      </div>
    );
  };

  if (DEMO_MODE_ENABLED) {
    return (
      <Card data-testid="claimed-use-receipt-workbench">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileCheck2 className="h-4 w-4 text-brand-primary" />
            Claimed-use counsel receipts
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm leading-6 text-[var(--text-secondary)]">
            Receipt issuance is disabled in the public demo because it requires
            an authenticated attorney, a tenant-bound report, and fresh
            primary-authority claim records.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4" data-testid="claimed-use-receipt-workbench">
      <Card>
        <CardHeader className="gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <FileCheck2 className="h-4 w-4 text-brand-primary" />
              Issue a claimed-use counsel receipt
            </CardTitle>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
              Attest one proposed US regulatory use against the exact current
              report, controlling claim text, and signed legal-status record.
              Issuance does not rewrite the certified report.
            </p>
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          {!canReviewFindings ? (
            <p className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)]/40 p-3 text-xs leading-5 text-[var(--text-secondary)]">
              Attorney or administrator permission is required to inspect or
              revoke claimed-use receipts. Only an attorney may issue one.
            </p>
          ) : receiptState.isLoading ? (
            <p
              className="text-sm text-[var(--text-secondary)]"
              role="status"
              aria-live="polite"
            >
              Verifying current receipt eligibility…
            </p>
          ) : receiptState.isError || !receiptState.data ? (
            <div
              className="rounded-lg border border-error/30 bg-error/10 p-4"
              role="alert"
            >
              <div className="flex items-start gap-3">
                <AlertTriangle
                  className="mt-0.5 h-4 w-4 shrink-0 text-error"
                  aria-hidden="true"
                />
                <div>
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    Receipt eligibility could not be verified
                  </p>
                  <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                    {errorMessage(receiptState.error)}
                  </p>
                  {onRetryLedger ? (
                    <Button
                      className="mt-3"
                      size="sm"
                      variant="outline"
                      onClick={onRetryLedger}
                    >
                      <RotateCcw
                        className="mr-2 h-3.5 w-3.5"
                        aria-hidden="true"
                      />
                      Recheck evidence
                    </Button>
                  ) : null}
                </div>
              </div>
            </div>
          ) : !canIssueReceipts ? (
            <p className="rounded-md border border-info/25 bg-info/8 p-3 text-xs leading-5 text-[var(--text-secondary)]">
              You can review and, where authorized, revoke the ledger below.
              Issuance is restricted to a currently authorized attorney.
            </p>
          ) : (
            <>
              {receiptState.data.eligible_uses.length === 0 ? (
                <p className="rounded-md border border-warning/30 bg-warning/10 p-3 text-xs leading-5 text-[var(--text-secondary)]">
                  No current US regulatory-submission use is eligible. Update
                  and rerun the analysis with complete product, indication,
                  proposed-label, carve-out, and timing facts.
                </p>
              ) : (
                <div className="grid gap-4 lg:grid-cols-2">
                  <div>
                    <label
                      className="mb-1.5 block text-xs font-semibold text-[var(--text-secondary)]"
                      htmlFor="claimed-use-use-select"
                    >
                      Proposed regulatory use
                    </label>
                    <Select value={effectiveUse} onValueChange={setSelectedUse}>
                      <SelectTrigger id="claimed-use-use-select">
                        <SelectValue placeholder="Select proposed use" />
                      </SelectTrigger>
                      <SelectContent>
                        {receiptState.data.eligible_uses.map((use) => (
                          <SelectItem
                            key={use.accused_act_index}
                            value={String(use.accused_act_index)}
                          >
                            {use.regulatory_path.toUpperCase()} ·{" "}
                            {use.target_product_identity}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <label
                      className="mb-1.5 block text-xs font-semibold text-[var(--text-secondary)]"
                      htmlFor="claimed-use-claim-select"
                    >
                      Current report claim
                    </label>
                    <Select
                      value={effectiveClaim}
                      onValueChange={setSelectedClaim}
                    >
                      <SelectTrigger id="claimed-use-claim-select">
                        <SelectValue placeholder="Select claim" />
                      </SelectTrigger>
                      <SelectContent>
                        {claimOptions.map((claim) => (
                          <SelectItem key={claim.value} value={claim.value}>
                            {claim.patentId} · claim {claim.claimNumber}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              )}

              {selectedUseRecord ? (
                <dl className="grid gap-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/75 p-3 text-xs sm:grid-cols-3">
                  <div>
                    <dt className="font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">
                      Actor and date
                    </dt>
                    <dd className="mt-1 text-[var(--text-primary)]">
                      {selectedUseRecord.actor} ·{" "}
                      {formatDate(selectedUseRecord.start_date)}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">
                      Indication
                    </dt>
                    <dd className="mt-1 text-[var(--text-primary)]">
                      {selectedUseRecord.proposed_indication}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">
                      Label carve-out
                    </dt>
                    <dd className="mt-1 capitalize text-[var(--text-primary)]">
                      {selectedUseRecord.label_carve_out_state}
                    </dd>
                  </div>
                </dl>
              ) : null}

              <p className="rounded-md border border-brand-primary/20 bg-brand-primary/8 p-3 text-xs leading-5 text-[var(--text-secondary)]">
                Governed evidence references are resolved by the server from the
                current claim record and source-span ledger. They cannot be
                typed or substituted in this form.
              </p>

              <label className="flex items-start gap-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/70 p-3 text-xs leading-5 text-[var(--text-secondary)]">
                <input
                  type="checkbox"
                  checked={affirmed}
                  onChange={(event) => setAffirmed(event.target.checked)}
                  className="mt-0.5 h-4 w-4 shrink-0 rounded border-[var(--border-emphasis)] accent-brand-primary"
                />
                <span>
                  I am the issuing attorney. I affirm that the proposed use and
                  product identity match the selected current claim after
                  reviewing the governed evidence that the server will bind to
                  this attributable, revocable record.
                </span>
              </label>

              {issueReceipt.isError ? (
                <p className="text-xs leading-5 text-error" role="alert">
                  {errorMessage(issueReceipt.error)}
                </p>
              ) : null}
              <Button
                type="button"
                className="w-full sm:w-auto"
                disabled={!canIssue}
                onClick={() => void handleIssue()}
              >
                <CheckCircle2 className="mr-2 h-4 w-4" aria-hidden="true" />
                {issueReceipt.isPending
                  ? "Issuing governed receipt…"
                  : "Issue counsel receipt"}
              </Button>
            </>
          )}
        </CardContent>
      </Card>

      {canReviewFindings ? (
        <ClaimedUseReceiptLedger
          state={receiptState}
          renderAction={renderReceiptAction}
        />
      ) : null}
    </div>
  );
}
