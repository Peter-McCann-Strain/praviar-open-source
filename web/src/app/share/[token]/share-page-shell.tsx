"use client";

import type { ReactNode } from "react";
import { useCallback, useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import {
  CalendarClock,
  CheckCircle2,
  FileLock2,
  Scale,
  ShieldCheck,
} from "lucide-react";
import { PraviarLockup } from "@/components/brand/praviar-lockup";
import { BRAND } from "@/marketing/content";
import { SharedReportCard } from "./shared-report-card";
import { ShareVerificationPrompt } from "./share-verification-prompt";
import { ShareStatusState } from "./share-status-state";
import type { SharedReportResult } from "./shared-report-types";
import { isSharedReportVerificationSessionExpired } from "./shared-report-validation";

interface SharePageShellProps {
  initialResult: SharedReportResult;
  token: string;
}

export function SharePageShell({ initialResult, token }: SharePageShellProps) {
  const [unlockedResult, setUnlockedResult] =
    useState<SharedReportResult | null>(null);
  const [isRetrying, startRetryTransition] = useTransition();
  const router = useRouter();
  const result = unlockedResult ?? initialResult;
  const chrome = getShareChrome(result);

  useEffect(() => {
    if (result.status !== "ok") {
      return undefined;
    }

    let expiryTimer: number | undefined;
    const checkExpiry = () => {
      if (isSharedReportVerificationSessionExpired(result.report)) {
        setUnlockedResult({
          status: "verification-required",
          invalid: false,
        });
        return;
      }

      const remainingMs =
        Date.parse(result.report.verified_session_expires_at) - Date.now();
      expiryTimer = window.setTimeout(
        checkExpiry,
        Math.min(Math.max(remainingMs, 1), 60_000),
      );
    };

    // Always cross an asynchronous boundary before a state update so this
    // effect remains React-safe even if an already-expired result is supplied.
    expiryTimer = window.setTimeout(checkExpiry, 0);
    return () => {
      if (expiryTimer !== undefined) {
        window.clearTimeout(expiryTimer);
      }
    };
  }, [result]);

  const handleResultChange = useCallback((nextResult: SharedReportResult) => {
    // Verification starts near the bottom of a deliberately explanatory access
    // panel. Reset the reading position before swapping in the result so a
    // successful recipient never lands halfway through an unlocked report and
    // an error never appears outside the viewport.
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    setUnlockedResult(nextResult);
    requestAnimationFrame(() => {
      document.getElementById("main-content")?.focus({ preventScroll: true });
      window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    });
  }, []);

  const retryAccessCheck = () => {
    setUnlockedResult(null);
    startRetryTransition(() => {
      router.refresh();
    });
  };

  return (
    <main
      id="main-content"
      tabIndex={-1}
      className="light praviar-share-access-field relative isolate min-h-screen overflow-x-clip px-4 py-8 sm:px-6 sm:py-10"
    >
      <div
        aria-hidden="true"
        className="praviar-share-evidence-grid pointer-events-none absolute inset-0 -z-10 opacity-70"
      />
      <div className="mx-auto max-w-6xl space-y-5">
        <header className="light praviar-glass-panel overflow-hidden rounded-lg border border-[var(--border-default)] shadow-[var(--shadow-lg)]">
          <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_24rem]">
            <div className="min-w-0">
              <div className="praviar-glass-strip flex min-w-0 flex-col gap-4 border-b border-[var(--border-default)] p-5 sm:flex-row sm:items-start sm:p-6 lg:border-b-0 lg:border-r">
                <PraviarLockup
                  size="marketing"
                  wordmark="Praviar"
                  tagline="Shared FTO packet"
                  className="w-full sm:w-auto sm:shrink-0"
                />
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                    External shared FTO packet
                  </p>
                  {result.status === "ok" ? (
                    <h1 className="mt-1 break-words type-heading-xl text-[var(--text-primary)] [overflow-wrap:anywhere]">
                      {chrome.title}
                    </h1>
                  ) : (
                    <p className="mt-1 break-words type-heading-xl text-[var(--text-primary)] [overflow-wrap:anywhere]">
                      {chrome.title}
                    </p>
                  )}
                  <p className="mt-3 max-w-2xl text-sm leading-6 text-[var(--text-secondary)]">
                    {chrome.description}
                  </p>
                </div>
              </div>
            </div>

            <dl className="praviar-glass-strip grid gap-2 p-5 sm:grid-cols-2 sm:p-6 lg:grid-cols-1">
              <ShareChromeFact
                icon={<CalendarClock className="h-4 w-4" aria-hidden="true" />}
                label="Status"
                value={chrome.status}
              />
              <ShareChromeFact
                icon={<FileLock2 className="h-4 w-4" aria-hidden="true" />}
                label="Access"
                value="Read-only external view"
              />
              <ShareChromeFact
                icon={<ShieldCheck className="h-4 w-4" aria-hidden="true" />}
                label="Actions"
                value="No workspace edits"
              />
              <ShareChromeFact
                icon={<Scale className="h-4 w-4" aria-hidden="true" />}
                label="Boundary"
                value="No legal clearance opinion"
              />
            </dl>
          </div>
        </header>

        {result.status === "error" ? (
          <ShareStatusState
            variant="error"
            showBrand={false}
            onRetry={retryAccessCheck}
            retrying={isRetrying}
          />
        ) : result.status === "verification-required" ? (
          <ShareVerificationPrompt
            token={token}
            initialInvalid={result.invalid}
            onResultChange={handleResultChange}
            showBrand={false}
          />
        ) : result.status === "expired" ? (
          <ShareStatusState variant="expired" showBrand={false} />
        ) : result.status === "ok" ? (
          <div className="space-y-4">
            {unlockedResult?.status === "ok" ? (
              <div
                role="status"
                data-testid="share-verification-success"
                className="flex items-start gap-3 rounded-lg border border-success/30 bg-success/10 px-4 py-3 text-sm text-[var(--text-secondary)]"
              >
                <CheckCircle2
                  className="mt-0.5 h-5 w-5 shrink-0 text-success"
                  aria-hidden="true"
                />
                <div>
                  <p className="font-semibold text-[var(--text-primary)]">
                    Recipient verified · read-only report opened
                  </p>
                  <p className="mt-0.5 text-xs leading-5">
                    This attributable view cannot edit the source workspace or
                    export privileged material.
                  </p>
                </div>
              </div>
            ) : null}
            <SharedReportCard report={result.report} headingLevel={2} />
          </div>
        ) : (
          <ShareStatusState variant="not-found" showBrand={false} />
        )}

        <footer className="light praviar-glass-panel-soft rounded-lg p-4 text-center text-xs leading-5 text-[var(--text-tertiary)]">
          Read-only shared views do not grant workspace access, report editing,
          PDF export, or a legal clearance opinion. Full workspace actions stay
          behind authenticated {BRAND.name} access.
        </footer>
      </div>
    </main>
  );
}

function getShareChrome(result: SharedReportResult): {
  title: string;
  description: string;
  status: string;
} {
  if (result.status === "ok") {
    return {
      title: result.report.compound_name,
      description:
        "A sender-controlled report package for patent-risk review. The evidence is visible for recipient triage while workspace actions remain gated.",
      status: "Report ready",
    };
  }

  if (result.status === "verification-required") {
    return {
      title: BRAND.name,
      description:
        "A recipient-bound report package is waiting behind mailbox verification. Request a one-time code to open the attributable read-only view.",
      status: "Recipient verification required",
    };
  }

  if (result.status === "expired") {
    return {
      title: BRAND.name,
      description:
        "This sender-managed report link is no longer active. Ask the sender to issue a fresh read-only share from the workspace.",
      status: "Link expired",
    };
  }

  if (result.status === "not-found") {
    return {
      title: BRAND.name,
      description:
        "This shared report could not be matched to an active link. Confirm the URL with the sender before retrying.",
      status: "Link unavailable",
    };
  }

  return {
    title: BRAND.name,
    description:
      "The report access check did not complete. Retry shortly, or ask the sender to confirm the shared link.",
    status: "Access check failed",
  };
}

function ShareChromeFact({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="praviar-glass-chip rounded-lg px-3 py-2">
      <dt className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
        <span className="text-[var(--brand-primary)]">{icon}</span>
        {label}
      </dt>
      <dd className="mt-1 text-xs font-semibold leading-5 text-[var(--text-primary)]">
        {value}
      </dd>
    </div>
  );
}
