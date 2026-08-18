"use client";

import { useEffect, useId, useRef, useState } from "react";
import { KeyRound, Loader2, MailCheck, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { logError } from "@/lib/error-logger";
import {
  requestSharedReportVerification,
  verifySharedReportRecipient,
} from "./actions";
import { ShareAccessBody, ShareAccessPanel } from "./share-access-panel";
import type { SharedReportResult } from "./shared-report-types";

export function ShareVerificationPrompt({
  token,
  initialInvalid = false,
  onResultChange,
  showBrand = true,
}: {
  token: string;
  initialInvalid?: boolean;
  onResultChange?: (result: SharedReportResult) => void;
  showBrand?: boolean;
}) {
  const [code, setCode] = useState("");
  const [codeSent, setCodeSent] = useState(initialInvalid);
  const [syntheticDemoCode, setSyntheticDemoCode] = useState<string | null>(
    null,
  );
  const [message, setMessage] = useState<string | null>(null);
  const [verificationError, setVerificationError] = useState<string | null>(
    initialInvalid ? "That code is invalid, expired, or already used." : null,
  );
  const [pendingAction, setPendingAction] = useState<
    "request" | "verify" | null
  >(null);
  const isPending = pendingAction !== null;
  const inputId = useId();
  const verificationErrorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!verificationError || isPending) return;
    verificationErrorRef.current?.focus({ preventScroll: true });
  }, [isPending, verificationError]);

  const requestCode = async () => {
    if (isPending) return;
    setMessage(null);
    setVerificationError(null);
    setPendingAction("request");
    try {
      const result = await requestSharedReportVerification(token);
      if (result.status === "sent") {
        setCodeSent(true);
        setSyntheticDemoCode(result.syntheticDemoCode ?? null);
        setMessage(
          "The email provider accepted a one-time code for the mailbox selected by the sender.",
        );
        return;
      }
      if (result.status === "rate-limited") {
        // A recipient may already have a still-valid code from another tab
        // or an earlier request. Rate limiting another send must not hide the
        // verification form and strand that legitimate recipient.
        setCodeSent(true);
        setSyntheticDemoCode(null);
        setMessage(
          "A code was recently sent. Enter the code you already received, or wait before requesting another.",
        );
        return;
      }
      onResultChange?.({
        status:
          result.status === "expired"
            ? "expired"
            : result.status === "not-found"
              ? "not-found"
              : "error",
      });
    } catch (error) {
      logError(error, {
        source: "ShareVerificationPrompt",
        extra: { action: "request_code" },
      });
      setMessage(
        "The verification email could not be sent. Try again shortly.",
      );
    } finally {
      setPendingAction(null);
    }
  };

  const verifyCode = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!/^\d{8}$/.test(code) || isPending) return;
    setMessage(null);
    setVerificationError(null);
    setPendingAction("verify");
    try {
      const result = await verifySharedReportRecipient(token, code);
      setCode("");
      if (result.status === "verification-required") {
        setVerificationError("That code is invalid, expired, or already used.");
        return;
      }
      onResultChange?.(result);
    } catch (error) {
      logError(error, {
        source: "ShareVerificationPrompt",
        extra: { action: "verify_code" },
      });
      setVerificationError("Verification did not complete. Try again shortly.");
    } finally {
      setPendingAction(null);
    }
  };

  return (
    <ShareAccessPanel
      variant="verification"
      title="Verify intended recipient"
      description="This report is bound to one mailbox. Praviar will send a one-time code there without revealing the address on this page."
      contentFirstOnMobile
      showBrand={showBrand}
    >
      <ShareAccessBody>
        <div className="space-y-4 text-left">
          <div className="rounded-lg border border-brand-primary/20 bg-brand-primary/5 p-3 text-xs leading-5 text-[var(--text-secondary)]">
            <p className="flex items-center gap-2 font-semibold text-[var(--text-primary)]">
              <ShieldCheck
                className="h-4 w-4 text-brand-primary"
                aria-hidden="true"
              />
              Recipient-bound access
            </p>
            <p className="mt-1">
              Forwarding this link alone cannot open the report. Every
              successful view is attributed and visible to the sender.
            </p>
          </div>

          {!codeSent ? (
            <Button
              type="button"
              size="lg"
              className="w-full gap-2 rounded-lg"
              onClick={requestCode}
              disabled={isPending}
            >
              {pendingAction === "request" ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <MailCheck className="h-4 w-4" aria-hidden="true" />
              )}
              {pendingAction === "request"
                ? "Sending secure code…"
                : "Send verification code"}
            </Button>
          ) : (
            <form onSubmit={verifyCode} className="space-y-3">
              {syntheticDemoCode ? (
                <div
                  className="rounded-lg border border-info/30 bg-info/10 p-3 text-xs leading-5 text-[var(--text-secondary)]"
                  role="note"
                >
                  <p className="font-bold uppercase tracking-[0.12em] text-info">
                    Synthetic demo only
                  </p>
                  <p className="mt-1">
                    No email is sent in demo mode. Use code{" "}
                    <span className="font-mono font-bold text-[var(--text-primary)]">
                      {syntheticDemoCode}
                    </span>
                    .
                  </p>
                </div>
              ) : null}
              <label
                htmlFor={inputId}
                className="block text-sm font-medium text-[var(--text-secondary)]"
              >
                8-digit verification code
              </label>
              <Input
                id={inputId}
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                maxLength={8}
                value={code}
                onChange={(event) => {
                  setCode(event.target.value.replace(/\D/g, "").slice(0, 8));
                  setVerificationError(null);
                }}
                placeholder="00000000"
                className="h-12 font-mono text-lg tracking-[0.24em]"
                disabled={isPending}
              />
              {verificationError && !isPending ? (
                <div
                  ref={verificationErrorRef}
                  role="alert"
                  tabIndex={-1}
                  className="rounded-lg border border-error/30 bg-error/10 px-3 py-2.5 text-xs font-medium leading-5 text-error"
                >
                  {verificationError}
                </div>
              ) : null}
              <Button
                type="submit"
                size="lg"
                className="w-full gap-2 rounded-lg"
                disabled={code.length !== 8 || isPending}
              >
                {pendingAction === "verify" ? (
                  <Loader2
                    className="h-4 w-4 animate-spin"
                    aria-hidden="true"
                  />
                ) : (
                  <KeyRound className="h-4 w-4" aria-hidden="true" />
                )}
                {pendingAction === "verify"
                  ? "Verifying…"
                  : "Verify and view report"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                className="min-h-11 w-full"
                onClick={requestCode}
                disabled={isPending}
              >
                Send a new code
              </Button>
            </form>
          )}

          {message && !isPending ? (
            <p
              role="status"
              aria-live="polite"
              className="text-xs leading-5 text-[var(--text-secondary)]"
            >
              {message}
            </p>
          ) : null}
        </div>
      </ShareAccessBody>
    </ShareAccessPanel>
  );
}
