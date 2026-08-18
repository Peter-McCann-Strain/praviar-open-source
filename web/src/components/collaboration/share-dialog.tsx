"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  Check,
  ChevronDown,
  ChevronUp,
  Clock3,
  Copy,
  Eye,
  MailCheck,
  RefreshCw,
  ShieldCheck,
  Trash2,
  UserRoundCheck,
} from "lucide-react";
import type { FTOReport, RiskLevel } from "@praviar/shared-types";
import { ShareDialogBackdrop } from "@/components/collaboration/share-dialog-backdrop";
import { ShareDialogHeader } from "@/components/collaboration/share-dialog-header";
import { useExportDialogFocusTrap } from "@/components/collaboration/use-export-dialog-focus-trap";
import {
  copyTextToClipboard,
  formatRelativeTime,
} from "@/components/report/share-analytics-helpers";
import {
  formatReportRiskLabel,
  getReportReference,
} from "@/components/report-page/report-command-summary";
import { RiskBadge } from "@/components/shared/risk-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuthToken } from "@/hooks/use-auth-token";
import { apiClient, isAuthBoundaryError } from "@/lib/api-client";
import { getCurrentAuthBoundaryKey } from "@/lib/auth-events";
import { logError } from "@/lib/error-logger";
import { authScopeKey } from "@/lib/query-keys";
import {
  externalReportGrantActivityResponseSchema,
  externalReportGrantCreatedResponseSchema,
  externalReportGrantListResponseSchema,
  externalReportGrantRevokedResponseSchema,
  validateApiResponse,
  type ExternalReportGrant,
  type ExternalReportGrantActivity,
  type ExternalReportGrantActivityResponse,
  type ExternalReportGrantCreatedResponse,
  type ExternalReportGrantListResponse,
  type ExternalReportGrantRevokedResponse,
} from "@/lib/validators";
import { useToastStore } from "@/stores/toast-store";

interface ShareDialogProps {
  reportId: string;
  report?: FTOReport;
  open: boolean;
  onClose: () => void;
  onShareStateRefresh?: () => void;
}

export function ShareDialog({
  report,
  reportId,
  open,
  onClose,
  onShareStateRefresh,
}: ShareDialogProps) {
  const token = useAuthToken();
  const stableAuthBoundaryKey = token
    ? (getCurrentAuthBoundaryKey() ?? authScopeKey(token))
    : authScopeKey(null);
  if (!open || typeof document === "undefined") return null;
  return createPortal(
    <OpenShareDialog
      key={`${reportId}:${stableAuthBoundaryKey}`}
      report={report}
      reportId={reportId}
      token={token}
      onClose={onClose}
      onShareStateRefresh={onShareStateRefresh}
    />,
    document.body,
  );
}

function OpenShareDialog({
  report,
  reportId,
  token,
  onClose,
  onShareStateRefresh,
}: Pick<ShareDialogProps, "report" | "reportId" | "onClose"> & {
  token: string | null;
  onShareStateRefresh?: () => void;
}) {
  const toast = useToastStore();
  const scopeAbortControllerRef = useRef(new AbortController());
  const listRequestRef = useRef<{
    key: string;
    promise: Promise<ExternalReportGrantListResponse>;
  } | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const recipientLedgerRef = useRef<HTMLElement>(null);
  const newShareReceiptRef = useRef<HTMLDivElement>(null);
  const scrollLedgerAfterRefreshRef = useRef(false);
  const [recipientEmail, setRecipientEmail] = useState("");
  const [expiresInDays, setExpiresInDays] = useState("7");
  const [maxViews, setMaxViews] = useState("25");
  const [grants, setGrants] = useState<ExternalReportGrant[]>([]);
  const [newShareUrl, setNewShareUrl] = useState<string | null>(null);
  const [newShareRecipient, setNewShareRecipient] = useState<string | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [restricted, setRestricted] = useState(false);
  const [listLoadError, setListLoadError] = useState(false);
  const [listReloadKey, setListReloadKey] = useState(0);
  const [ledgerRevision, setLedgerRevision] = useState(0);
  const shareStateRefreshPendingForLedgerRef = useRef(false);
  const onShareStateRefreshRef = useRef(onShareStateRefresh);
  const [createIdempotencyKey, setCreateIdempotencyKey] = useState(() =>
    crypto.randomUUID(),
  );
  const parsedMaxViews = Number(maxViews);
  const maxViewsValid =
    /^\d+$/.test(maxViews) &&
    Number.isInteger(parsedMaxViews) &&
    parsedMaxViews >= 1 &&
    parsedMaxViews <= 100;

  useExportDialogFocusTrap(true, onClose, dialogRef);

  useEffect(() => {
    onShareStateRefreshRef.current = onShareStateRefresh;
  }, [onShareStateRefresh]);

  useEffect(() => {
    if (scopeAbortControllerRef.current.signal.aborted) {
      scopeAbortControllerRef.current = new AbortController();
    }
    const controller = scopeAbortControllerRef.current;
    return () => {
      controller.abort(new Error("Share dialog scope changed"));
    };
  }, []);

  useEffect(() => {
    if (!token) {
      return;
    }
    let active = true;
    const requestKey = `${reportId}:${token}:${listReloadKey}`;
    const load = async () => {
      setLoading(true);
      try {
        let request = listRequestRef.current;
        if (!request || request.key !== requestKey) {
          const controller = new AbortController();
          request = {
            key: requestKey,
            promise: apiClient<ExternalReportGrantListResponse>(
              `/reports/${reportId}/share`,
              {
                token,
                signal: controller.signal,
                validate: (data) =>
                  validateApiResponse(
                    externalReportGrantListResponseSchema,
                    data,
                    "/reports/:analysis_id/share",
                  ),
              },
            ),
          };
          listRequestRef.current = request;
        }
        const response = await request.promise;
        if (active) {
          setGrants(response.items);
          setLedgerRevision((revision) => revision + 1);
          setRestricted(false);
          setListLoadError(false);
          if (shareStateRefreshPendingForLedgerRef.current) {
            shareStateRefreshPendingForLedgerRef.current = false;
            onShareStateRefreshRef.current?.();
          }
        }
      } catch (error) {
        if (!active) return;
        if (isAuthBoundaryError(error)) {
          setRestricted(true);
          setListLoadError(false);
        } else {
          setRestricted(false);
          setListLoadError(true);
          logError(error, {
            source: "ShareDialog",
            extra: { action: "list_grants" },
          });
        }
      } finally {
        if (listRequestRef.current?.key === requestKey) {
          listRequestRef.current = null;
        }
        if (active) setLoading(false);
      }
    };
    // React Strict Mode performs a throwaway setup/cleanup cycle in
    // development. Both setups share this scope-keyed, idempotent read so the
    // probe neither duplicates nor aborts an application request. A stale
    // response is still ignored after a genuine scope change.
    void load();
    return () => {
      active = false;
    };
  }, [listReloadKey, reportId, token]);

  const reloadRecipientLedger = () => {
    shareStateRefreshPendingForLedgerRef.current = true;
    scrollLedgerAfterRefreshRef.current = true;
    setListReloadKey((value) => value + 1);
  };

  const createGrant = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (creating || !token || !recipientEmail.trim() || !maxViewsValid) return;
    setCreating(true);
    setNewShareUrl(null);
    try {
      const created = await apiClient<ExternalReportGrantCreatedResponse>(
        `/reports/${reportId}/share`,
        {
          method: "POST",
          token,
          signal: scopeAbortControllerRef.current.signal,
          headers: { "Idempotency-Key": createIdempotencyKey },
          body: JSON.stringify({
            recipient_email: recipientEmail.trim(),
            expires_in_days: Number(expiresInDays),
            max_views: parsedMaxViews,
          }),
          validate: (data) =>
            validateApiResponse(
              externalReportGrantCreatedResponseSchema,
              data,
              "/reports/:analysis_id/share",
            ),
        },
      );
      if (created.share_token) {
        const origin =
          typeof window === "undefined" ? "" : window.location.origin;
        setNewShareUrl(`${origin}/share/${created.share_token}`);
      }
      setNewShareRecipient(created.recipient_email);
      setGrants((current) => [
        created,
        ...current.filter((grant) => grant.id !== created.id),
      ]);
      // Reissue rotates older same-mailbox grants server-side. Refresh the
      // authoritative ledger so every historical row reflects that mutation.
      setListReloadKey((value) => value + 1);
      setRecipientEmail("");
      setCreateIdempotencyKey(crypto.randomUUID());
      toast.addToast(
        created.replayed
          ? "This invitation was already accepted for delivery"
          : "Recipient invitation accepted for delivery",
        "success",
      );
    } catch (error) {
      const authorizationLost = isAuthBoundaryError(error);
      if (authorizationLost) setRestricted(true);
      setGrants([]);
      setLoading(true);
      setListLoadError(false);
      if (!authorizationLost) setListReloadKey((value) => value + 1);
      logError(error, {
        source: "ShareDialog",
        extra: { action: "create_grant" },
      });
      toast.addToast(
        "Invitation outcome could not be confirmed. The authoritative recipient ledger is being reloaded.",
        "error",
      );
    } finally {
      onShareStateRefreshRef.current?.();
      setCreating(false);
    }
  };

  const revokeGrant = async (grantId: string) => {
    if (revokingId || !token) return;
    setRevokingId(grantId);
    try {
      await apiClient<ExternalReportGrantRevokedResponse>(
        `/reports/${reportId}/share/${grantId}`,
        {
          method: "DELETE",
          token,
          signal: scopeAbortControllerRef.current.signal,
          validate: (data) =>
            validateApiResponse(
              externalReportGrantRevokedResponseSchema,
              data,
              "/reports/:analysis_id/share/:grant_id",
            ),
        },
      );
      setGrants((current) =>
        current.map((grant) =>
          grant.id === grantId
            ? {
                ...grant,
                revoked_at: new Date().toISOString(),
                status: "revoked" as const,
              }
            : grant,
        ),
      );
      toast.addToast("Recipient access revoked", "success");
    } catch (error) {
      const authorizationLost = isAuthBoundaryError(error);
      if (authorizationLost) setRestricted(true);
      setGrants([]);
      setLoading(true);
      setListLoadError(false);
      if (!authorizationLost) setListReloadKey((value) => value + 1);
      logError(error, {
        source: "ShareDialog",
        extra: { action: "revoke_grant" },
      });
      toast.addToast(
        "Revocation outcome could not be confirmed. The authoritative recipient ledger is being reloaded.",
        "error",
      );
    } finally {
      onShareStateRefreshRef.current?.();
      setRevokingId(null);
    }
  };

  const copyLink = async () => {
    if (!newShareUrl || !token) return;
    try {
      await copyTextToClipboard(newShareUrl);
      setCopied(true);
      toast.addToast("Recipient-bound link copied", "success");
    } catch (error) {
      logError(error, {
        source: "ShareDialog",
        extra: { action: "copy_link" },
      });
      toast.addToast("Link could not be copied", "error");
    }
  };

  const startNewInvitationAttempt = (grant: ExternalReportGrant) => {
    setRecipientEmail(grant.recipient_email);
    setCreateIdempotencyKey(crypto.randomUUID());
    setNewShareUrl(null);
    setNewShareRecipient(null);
    setCopied(false);
    window.setTimeout(
      () => document.getElementById("share-recipient-email")?.focus(),
      0,
    );
    toast.addToast("A new invitation attempt is ready to review", "info");
  };

  const reportReference = report ? getReportReference(report) : reportId;
  const compoundName = report?.compound?.name ?? "Report packet";
  const risk = report?.risk_summary.overall_risk as RiskLevel | undefined;
  const ledgerLoading = !token || (loading && grants.length === 0);

  useEffect(() => {
    if (!newShareUrl) return;
    const timer = window.setTimeout(() => {
      newShareReceiptRef.current?.scrollIntoView?.({
        behavior: "auto",
        block: "start",
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [newShareUrl]);

  useEffect(() => {
    if (!scrollLedgerAfterRefreshRef.current || loading) return;
    scrollLedgerAfterRefreshRef.current = false;
    const timer = window.setTimeout(() => {
      recipientLedgerRef.current?.scrollIntoView?.({
        behavior: "auto",
        block: "nearest",
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [ledgerRevision, loading]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <ShareDialogBackdrop onClose={onClose} />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="share-dialog-title"
        className="praviar-dialog-panel relative mx-3 flex max-h-[min(94dvh,880px)] w-full max-w-[62rem] flex-col overflow-hidden rounded-lg shadow-[0_24px_80px_rgba(11,31,36,0.24)]"
      >
        <div className="min-h-0 overflow-y-auto">
          <div
            className="praviar-share-handoff-field sticky top-0 z-20 border-b border-[var(--border-default)] px-3 pb-3 pt-3 shadow-[var(--shadow-xs)] sm:px-6 sm:pb-4 sm:pt-5"
            data-testid="share-dialog-sticky-header"
          >
            <ShareDialogHeader onClose={onClose} />
          </div>
          <div className="praviar-share-handoff-field border-b border-[var(--border-default)] px-3 pb-3 pt-2 sm:px-6 sm:pb-5 sm:pt-3">
            <div className="grid grid-cols-2 gap-x-3 gap-y-2 rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] p-2.5 sm:grid-cols-3 sm:gap-3 sm:p-3">
              <Identity label="Report" value={reportReference} />
              <Identity label="Compound" value={compoundName} />
              <div className="col-span-2 flex items-center gap-2 sm:col-span-1">
                {risk ? (
                  <RiskBadge
                    risk={risk}
                    label={formatReportRiskLabel(risk)}
                    size="sm"
                  />
                ) : null}
                <span className="text-xs font-semibold text-[var(--text-secondary)]">
                  Read-only external packet
                </span>
              </div>
            </div>
          </div>

          {restricted ? (
            <div
              className="m-6 rounded-lg border border-error/25 bg-error/10 p-5"
              role="alert"
            >
              <h3 className="font-semibold text-[var(--text-primary)]">
                Share access restricted
              </h3>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                Your session cannot manage recipients for this report.
              </p>
            </div>
          ) : (
            <div className="grid gap-4 px-3 py-4 sm:px-6 sm:py-6 lg:grid-cols-[minmax(19rem,0.8fr)_minmax(0,1.2fr)] lg:gap-6">
              <section
                aria-labelledby="recipient-grant-heading"
                className="order-2 lg:order-1"
              >
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-brand-primary">
                  Governed delivery
                </p>
                <h3
                  id="recipient-grant-heading"
                  className="mt-1 text-lg font-semibold text-[var(--text-primary)]"
                >
                  Invite one intended recipient
                </h3>
                <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                  The link is bound to the named mailbox. The recipient must
                  enter a fresh one-time code, and every report view is
                  attributable.
                </p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={reloadRecipientLedger}
                  disabled={ledgerLoading}
                  className="mt-3 min-h-11 gap-2"
                >
                  <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                  Refresh recipient ledger
                </Button>

                {!token ? (
                  <p
                    className="mt-4 rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)] px-3 py-2 text-xs font-medium text-[var(--text-secondary)]"
                    role="status"
                  >
                    Preparing your authenticated sharing session…
                  </p>
                ) : null}

                <form onSubmit={createGrant} className="mt-5 space-y-4">
                  <div>
                    <label
                      htmlFor="share-recipient-email"
                      className="mb-1.5 block text-sm font-medium text-[var(--text-primary)]"
                    >
                      Recipient email
                    </label>
                    <Input
                      id="share-recipient-email"
                      type="email"
                      autoComplete="email"
                      required
                      disabled={!token || creating}
                      value={recipientEmail}
                      onChange={(event) =>
                        setRecipientEmail(event.target.value)
                      }
                      placeholder="counsel@recipient.com"
                      className="h-11"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <label className="text-xs font-medium text-[var(--text-secondary)]">
                      Expires after
                      <select
                        value={expiresInDays}
                        disabled={!token || creating}
                        onChange={(event) =>
                          setExpiresInDays(event.target.value)
                        }
                        className="mt-1.5 h-11 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-sm text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <option value="1">1 day</option>
                        <option value="3">3 days</option>
                        <option value="7">7 days</option>
                        <option value="14">14 days</option>
                        <option value="30">30 days</option>
                      </select>
                    </label>
                    <label className="text-xs font-medium text-[var(--text-secondary)]">
                      Maximum views
                      <Input
                        type="number"
                        min={1}
                        max={100}
                        step={1}
                        required
                        disabled={!token || creating}
                        value={maxViews}
                        onChange={(event) => setMaxViews(event.target.value)}
                        error={!maxViewsValid}
                        errorMessage="Enter a whole number from 1 to 100."
                        errorId="share-max-views-error"
                        className="mt-1.5 h-11"
                      />
                    </label>
                  </div>
                  <Button
                    type="submit"
                    className="min-h-11 w-full gap-2"
                    loading={creating}
                    disabled={
                      creating ||
                      !token ||
                      !recipientEmail.trim() ||
                      !maxViewsValid
                    }
                  >
                    <MailCheck className="h-4 w-4" aria-hidden="true" />
                    Send verification invitation
                  </Button>
                </form>

                {newShareUrl ? (
                  <div
                    ref={newShareReceiptRef}
                    className="mt-5 scroll-mt-32 rounded-lg border border-success/30 bg-success/10 p-3 sm:p-4"
                    role="status"
                  >
                    <p className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
                      <Check
                        className="h-4 w-4 text-success"
                        aria-hidden="true"
                      />
                      Invitation accepted for delivery to {newShareRecipient}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                      This link is shown once. Copying it is safe for handoff
                      because mailbox verification is still required.
                    </p>
                    <div
                      role="textbox"
                      aria-label="Recipient link (read only)"
                      aria-readonly="true"
                      tabIndex={0}
                      className="mt-3 min-h-11 select-all break-all rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2 font-mono text-xs leading-5 text-[var(--text-primary)]"
                    >
                      {newShareUrl}
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={copyLink}
                      disabled={!token}
                      className="mt-3 min-h-11 w-full gap-2"
                    >
                      <Copy className="h-4 w-4" aria-hidden="true" />
                      {copied ? "Copied" : "Copy recipient link"}
                    </Button>
                  </div>
                ) : null}

                <div className="mt-5 grid gap-2 text-xs text-[var(--text-secondary)]">
                  <Policy
                    icon={UserRoundCheck}
                    text="Mailbox-bound; forwarded links alone cannot open the report"
                  />
                  <Policy
                    icon={Eye}
                    text="Named access history, view limits, and immediate revocation"
                  />
                  <Policy
                    icon={ShieldCheck}
                    text="No downloads, exports, edits, or workspace access"
                  />
                </div>
              </section>

              <section
                ref={recipientLedgerRef}
                aria-labelledby="access-history-heading"
                className="order-1 min-w-0 scroll-mt-28 lg:order-2"
                data-testid="share-recipient-ledger"
              >
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-brand-primary">
                  Recipient ledger
                </p>
                <h3
                  id="access-history-heading"
                  className="mt-1 text-lg font-semibold text-[var(--text-primary)]"
                >
                  Named access history
                </h3>
                <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                  Each invitation has independent expiry, view limits,
                  verification, and revocation.
                </p>
                <div className="mt-4 space-y-3">
                  {ledgerLoading ? (
                    <p className="rounded-lg border border-[var(--border-default)] p-4 text-sm text-[var(--text-secondary)]">
                      Loading recipient ledger…
                    </p>
                  ) : listLoadError ? (
                    <div
                      className="rounded-lg border border-error/25 bg-error/10 p-4"
                      role="alert"
                    >
                      <p className="text-sm font-semibold text-[var(--text-primary)]">
                        Recipient ledger unavailable
                      </p>
                      <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                        We could not load the recipient history. No access state
                        has been inferred.
                      </p>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={reloadRecipientLedger}
                        className="mt-3 min-h-11"
                      >
                        Retry
                      </Button>
                    </div>
                  ) : grants.length === 0 ? (
                    <p className="rounded-lg border border-dashed border-[var(--border-default)] p-5 text-sm text-[var(--text-secondary)]">
                      No recipient grants yet.
                    </p>
                  ) : (
                    grants.map((grant) => (
                      <GrantRow
                        key={grant.id}
                        grant={grant}
                        reportId={reportId}
                        ledgerRevision={ledgerRevision}
                        token={token}
                        revoking={revokingId === grant.id}
                        disabled={!token}
                        onRestricted={setRestricted}
                        onStartNewAttempt={() =>
                          startNewInvitationAttempt(grant)
                        }
                        onRevoke={() => revokeGrant(grant.id)}
                      />
                    ))
                  )}
                </div>
              </section>
            </div>
          )}
        </div>
        <footer className="flex shrink-0 justify-end border-t border-[var(--border-default)] bg-[var(--bg-surface)] px-5 py-4 sm:px-6">
          <Button variant="outline" onClick={onClose} className="min-h-11">
            Done
          </Button>
        </footer>
      </div>
    </div>
  );
}

function GrantRow({
  grant,
  reportId,
  ledgerRevision,
  token,
  revoking,
  disabled,
  onRestricted,
  onStartNewAttempt,
  onRevoke,
}: {
  grant: ExternalReportGrant;
  reportId: string;
  ledgerRevision: number;
  token: string | null;
  revoking: boolean;
  disabled: boolean;
  onRestricted: (restricted: boolean) => void;
  onStartNewAttempt: () => void;
  onRevoke: () => Promise<void>;
}) {
  const [activityExpanded, setActivityExpanded] = useState(false);
  const [activity, setActivity] = useState<
    ExternalReportGrantActivity[] | null
  >(null);
  const [activityLoading, setActivityLoading] = useState(false);
  const [activityError, setActivityError] = useState(false);
  const [activityReloadKey, setActivityReloadKey] = useState(0);
  const [confirmingRevoke, setConfirmingRevoke] = useState(false);
  const revokeTriggerRef = useRef<HTMLButtonElement>(null);
  const cancelRevokeRef = useRef<HTMLButtonElement>(null);
  const revokeConfirmationRef = useRef<HTMLDivElement>(null);
  const activityPanelRef = useRef<HTMLDivElement>(null);
  const active = grant.status === "active";
  const outcomeUnknown = grant.status === "delivery_outcome_unknown";
  const retryableTerminal = [
    "delivery_rejected",
    "delivery_cancelled_by_policy",
    "delivery_cancelled_expired",
    "delivery_cancelled_retention_expired",
    "revoked",
  ].includes(grant.status);
  const revocable =
    active || grant.status === "delivery_pending" || outcomeUnknown;
  const statusPresentation = grantStatusPresentation(grant.status);

  useEffect(() => {
    if (!confirmingRevoke) return;
    cancelRevokeRef.current?.focus({ preventScroll: true });
    const timer = window.setTimeout(() => {
      revokeConfirmationRef.current?.scrollIntoView?.({
        behavior: "auto",
        block: "center",
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [confirmingRevoke]);

  const cancelRevoke = () => {
    setConfirmingRevoke(false);
    window.setTimeout(() => revokeTriggerRef.current?.focus(), 0);
  };

  const confirmRevoke = async () => {
    await onRevoke();
    setConfirmingRevoke(false);
  };

  useEffect(() => {
    if (!activityExpanded || !token) return;
    let current = true;
    const controller = new AbortController();
    const loadActivity = async () => {
      setActivityLoading(true);
      setActivityError(false);
      try {
        const response = await apiClient<ExternalReportGrantActivityResponse>(
          `/reports/${reportId}/share/${grant.id}/activity`,
          {
            token,
            signal: controller.signal,
            validate: (data) =>
              validateApiResponse(
                externalReportGrantActivityResponseSchema,
                data,
                "/reports/:analysis_id/share/:grant_id/activity",
              ),
          },
        );
        if (current) setActivity(response.items);
      } catch (error) {
        if (!current) return;
        if (isAuthBoundaryError(error)) onRestricted(true);
        setActivity(null);
        setActivityError(true);
        logError(error, {
          source: "ShareDialog",
          extra: { action: "load_grant_activity" },
        });
      } finally {
        if (current) setActivityLoading(false);
      }
    };
    void loadActivity();
    return () => {
      current = false;
      controller.abort();
    };
  }, [
    activityExpanded,
    activityReloadKey,
    grant.id,
    grant.revoked_at,
    ledgerRevision,
    onRestricted,
    reportId,
    token,
  ]);

  useEffect(() => {
    if (!activityExpanded || activityLoading || activity === null) return;
    const timer = window.setTimeout(() => {
      activityPanelRef.current?.scrollIntoView?.({
        behavior: "auto",
        block: "start",
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [activity, activityExpanded, activityLoading]);

  return (
    <article className="flex flex-col rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] p-3 shadow-[var(--shadow-xs)] sm:p-4">
      <div className="flex flex-col items-start gap-2 sm:flex-row sm:justify-between sm:gap-3">
        <div className="min-w-0 w-full sm:flex-1">
          <p
            className="block max-w-full overflow-hidden text-ellipsis whitespace-nowrap text-[13px] font-semibold tracking-normal text-[var(--text-primary)] sm:whitespace-normal sm:text-sm sm:[overflow-wrap:anywhere]"
            title={grant.recipient_email}
          >
            {grant.recipient_email}
          </p>
          <p className="mt-1 text-xs text-[var(--text-tertiary)]">
            {statusPresentation.label} · {grant.view_count} of {grant.max_views}{" "}
            views
          </p>
        </div>
        <span
          className={`inline-flex max-w-full shrink-0 rounded-full px-2 py-1 text-xs font-bold uppercase tracking-wide ${active ? "bg-success/10 text-success" : "bg-[var(--surface-muted)] text-[var(--text-tertiary)]"}`}
        >
          {active ? "Active invitation" : statusPresentation.label}
        </span>
      </div>
      {statusPresentation.detail ? (
        <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
          {statusPresentation.detail}
        </p>
      ) : null}
      <div className="mt-3 grid gap-2 text-xs text-[var(--text-secondary)] sm:grid-cols-2">
        <p className="flex items-center gap-1.5">
          <Clock3 className="h-3.5 w-3.5" aria-hidden="true" />
          Expires {formatRelativeTime(grant.expires_at)}
        </p>
        <p className="flex items-center gap-1.5">
          <Eye className="h-3.5 w-3.5" aria-hidden="true" />
          {grant.last_accessed_at
            ? `Last viewed ${formatRelativeTime(grant.last_accessed_at)}`
            : "Not yet viewed"}
        </p>
      </div>
      <Button
        type="button"
        variant="ghost"
        onClick={() => setActivityExpanded((current) => !current)}
        disabled={!token}
        aria-expanded={activityExpanded}
        aria-controls={`grant-activity-${grant.id}`}
        aria-label={`${activityExpanded ? "Hide" : "Show"} activity for ${grant.recipient_email}`}
        className="order-2 mt-3 min-h-11 w-full gap-2"
      >
        {activityExpanded ? (
          <ChevronUp className="h-4 w-4" aria-hidden="true" />
        ) : (
          <ChevronDown className="h-4 w-4" aria-hidden="true" />
        )}
        {activityExpanded ? "Hide activity" : "Show activity"}
      </Button>
      {activityExpanded ? (
        <div
          ref={activityPanelRef}
          id={`grant-activity-${grant.id}`}
          className="order-3 mt-3 scroll-mt-32 border-t border-[var(--border-subtle)] pt-3"
        >
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mb-3 min-h-11 gap-2"
            disabled={activityLoading || !token}
            onClick={() => setActivityReloadKey((current) => current + 1)}
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            Refresh activity
          </Button>
          {activityLoading ? (
            <p className="text-xs text-[var(--text-secondary)]" role="status">
              Loading immutable activity…
            </p>
          ) : activityError ? (
            <div
              className="rounded-lg border border-error/20 bg-error/10 p-3"
              role="alert"
            >
              <p className="text-xs font-semibold text-[var(--text-primary)]">
                Grant activity unavailable
              </p>
              <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                No timeline state has been inferred. Recipient access remains
                unchanged.
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-2 min-h-11 gap-2"
                onClick={() => setActivityReloadKey((current) => current + 1)}
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                Retry activity
              </Button>
            </div>
          ) : activity?.length ? (
            <ol
              className="space-y-2"
              aria-label={`Immutable activity for ${grant.recipient_email}`}
            >
              {activity.map((item) => (
                <li
                  key={item.id}
                  className="flex items-start justify-between gap-3 rounded-md bg-[var(--surface-muted)] px-3 py-2 text-xs"
                >
                  <span className="font-medium text-[var(--text-primary)]">
                    {grantActivityLabel(item)}
                  </span>
                  <time
                    dateTime={item.occurred_at}
                    className="shrink-0 text-right text-[var(--text-tertiary)]"
                  >
                    <span className="block">
                      {formatRelativeTime(item.occurred_at)}
                    </span>
                    <span className="mt-0.5 block font-mono text-xs">
                      {formatExactUtc(item.occurred_at)}
                    </span>
                  </time>
                </li>
              ))}
            </ol>
          ) : (
            <p className="rounded-md bg-[var(--surface-muted)] px-3 py-2 text-xs text-[var(--text-secondary)]">
              No recorded recipient activity yet.
            </p>
          )}
        </div>
      ) : null}
      {retryableTerminal ? (
        <Button
          type="button"
          variant="outline"
          onClick={onStartNewAttempt}
          className="order-4 mt-3 min-h-11 w-full gap-2"
          aria-label={`Start new invitation attempt for ${grant.recipient_email}`}
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          Start new invitation attempt
        </Button>
      ) : null}
      {revocable ? (
        confirmingRevoke ? (
          <div
            ref={revokeConfirmationRef}
            role="alertdialog"
            aria-modal="false"
            aria-labelledby={`revoke-grant-title-${grant.id}`}
            aria-describedby={`revoke-grant-description-${grant.id}`}
            className="order-1 mt-3 scroll-m-32 rounded-lg border border-error/25 bg-error/10 p-3"
          >
            <p
              id={`revoke-grant-title-${grant.id}`}
              className="text-sm font-semibold text-[var(--text-primary)]"
            >
              {outcomeUnknown
                ? "Cancel this unresolved invitation?"
                : "Revoke this recipient?"}
            </p>
            <p
              id={`revoke-grant-description-${grant.id}`}
              className="mt-1 text-xs leading-5 text-[var(--text-secondary)]"
            >
              {outcomeUnknown ? (
                <>
                  Cancelling prevents any later provider recovery from
                  activating the invitation for{" "}
                  <span className="break-all [overflow-wrap:anywhere]">
                    {grant.recipient_email}.
                  </span>{" "}
                  You can then issue a new invitation with a new operation key.
                </>
              ) : (
                <>
                  This immediately invalidates access for{" "}
                  <span className="break-all [overflow-wrap:anywhere]">
                    {grant.recipient_email}.
                  </span>{" "}
                  The invitation must be reissued to restore access.
                </>
              )}
            </p>
            <div className="mt-3 flex flex-nowrap gap-2 sm:justify-end">
              <Button
                ref={cancelRevokeRef}
                type="button"
                variant="ghost"
                aria-label={
                  outcomeUnknown
                    ? "Keep recovery active"
                    : "Keep recipient access"
                }
                className="min-h-11 min-w-0 flex-1 px-2 text-xs sm:flex-none sm:px-4 sm:text-sm"
                onClick={cancelRevoke}
                disabled={revoking}
              >
                <span className="sm:hidden">
                  {outcomeUnknown ? "Keep recovery" : "Keep access"}
                </span>
                <span className="hidden sm:inline">
                  {outcomeUnknown
                    ? "Keep recovery active"
                    : "Keep recipient access"}
                </span>
              </Button>
              <Button
                type="button"
                variant="destructive"
                aria-label={
                  outcomeUnknown ? "Cancel invitation" : "Confirm revocation"
                }
                className="min-h-11 min-w-0 flex-1 px-2 text-xs sm:flex-none sm:px-4 sm:text-sm"
                onClick={() => void confirmRevoke()}
                loading={revoking}
                disabled={revoking || disabled}
              >
                <span className="sm:hidden">
                  {outcomeUnknown ? "Cancel invite" : "Revoke access"}
                </span>
                <span className="hidden sm:inline">
                  {outcomeUnknown ? "Cancel invitation" : "Confirm revocation"}
                </span>
              </Button>
            </div>
          </div>
        ) : (
          <Button
            ref={revokeTriggerRef}
            type="button"
            variant="ghost"
            onClick={() => setConfirmingRevoke(true)}
            disabled={revoking || disabled}
            className="order-1 mt-3 min-h-11 w-full gap-2 text-error hover:bg-error/10"
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
            {outcomeUnknown
              ? "Cancel unresolved invitation"
              : "Revoke recipient"}
          </Button>
        )
      ) : null}
    </article>
  );
}

function grantStatusPresentation(status: ExternalReportGrant["status"]): {
  label: string;
  detail?: string;
} {
  switch (status) {
    case "delivery_cancelled_by_policy":
      return {
        label: "Cancelled by policy",
        detail: "Cancelled after workspace policy changed.",
      };
    case "delivery_cancelled_expired":
      return {
        label: "Cancelled after expiry",
        detail: "Cancelled after its access window expired.",
      };
    case "delivery_cancelled_retention_expired":
      return {
        label: "Cancelled after retention",
        detail: "Cancelled when provider lookup retention ended.",
      };
    case "delivery_reconciliation_alert":
      return {
        label: "Operator review required",
        detail: "Delivery reconciliation requires operator review.",
      };
    case "delivery_outcome_unknown":
      return { label: "Delivery outcome unknown" };
    case "delivery_rejected":
      return { label: "Delivery rejected" };
    case "delivery_pending":
      return { label: "Delivery pending" };
    case "view_limit_reached":
      return { label: "View limit reached" };
    case "active":
      return { label: "Active" };
    case "expired":
      return { label: "Expired" };
    case "revoked":
      return { label: "Revoked" };
    default:
      return {
        label: "Delivery status unavailable",
        detail:
          "Refresh the recipient ledger to retrieve authoritative delivery state.",
      };
  }
}

function grantActivityLabel(item: ExternalReportGrantActivity): string {
  switch (item.event) {
    case "delivery_dispatch_started":
      return "Invitation submitted to delivery provider";
    case "delivery_provider_accepted":
      return "Delivery provider accepted invitation";
    case "delivery_rejected":
      return "Delivery provider rejected invitation";
    case "delivery_outcome_unknown":
      return "Delivery outcome unknown; no resubmission attempted";
    case "delivery_cancelled_by_policy":
      return "Invitation cancelled after workspace policy changed";
    case "delivery_cancelled_expired":
      return "Invitation cancelled after its access window expired";
    case "delivery_cancelled_retention_expired":
      return "Invitation cancelled when provider lookup retention ended";
    case "delivery_reconciliation_alert":
      return "Delivery reconciliation requires operator review";
    case "invitation_sent":
      return "Invitation accepted for delivery";
    case "recipient_verified":
      return "Recipient mailbox verified";
    case "report_viewed":
      return item.view_number
        ? `Report view ${item.view_number}`
        : "Report viewed";
    case "revoked_by_policy":
      return "Revoked by workspace domain policy";
    case "revoked_by_reissue":
      return "Revoked when a new invitation replaced this one";
    case "revoked":
      return "Recipient access revoked";
  }
}

function formatExactUtc(value: string): string {
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return "Invalid UTC timestamp";
  return `${timestamp.toISOString().replace(".000Z", "Z")} UTC`;
}

function Identity({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-xs font-bold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p
        className="mt-0.5 break-words text-xs font-semibold leading-4 tracking-normal text-[var(--text-primary)] [overflow-wrap:anywhere] sm:mt-1 sm:text-sm sm:leading-normal"
        title={value}
      >
        {value}
      </p>
    </div>
  );
}

function Policy({
  icon: Icon,
  text,
}: {
  icon: typeof ShieldCheck;
  text: string;
}) {
  return (
    <p className="flex items-start gap-2 rounded-md bg-[var(--surface-muted)] px-3 py-2">
      <Icon
        className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-primary"
        aria-hidden="true"
      />
      {text}
    </p>
  );
}
