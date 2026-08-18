"use server";

import { API_BASE_URL, DEMO_MODE_ENABLED } from "@/lib/constants";
import {
  DEMO_SHARE_VERIFICATION_CODE,
  getDemoSharedReport,
} from "@/lib/demo-data";
import { resolveDemoShareVerificationClock } from "@/lib/demo-share-clock";
import { logError } from "@/lib/error-logger";
import type { SharedReportResult } from "./shared-report-types";
import {
  isSharedReportExpired,
  isSharedReportVerificationSessionExpired,
  parseSharedReportPayload,
} from "./shared-report-validation";

const ACCESS_SECRET_HEADER = "X-Praviar-Grant-Access";
const TOKEN_PATTERN = /^[A-Za-z0-9_-]{40,64}$/;
const CODE_PATTERN = /^\d{8}$/;

export type VerificationRequestResult =
  | { status: "sent"; syntheticDemoCode?: string }
  | { status: "not-found" | "expired" | "rate-limited" | "error" };

export async function requestSharedReportVerification(
  token: string,
): Promise<VerificationRequestResult> {
  if (!TOKEN_PATTERN.test(token)) return { status: "not-found" };
  if (DEMO_MODE_ENABLED) {
    return {
      status: "sent",
      syntheticDemoCode: DEMO_SHARE_VERIFICATION_CODE,
    };
  }
  if (!API_BASE_URL) return { status: "error" };

  try {
    const response = await fetch(
      `${API_BASE_URL}/share/${encodeURIComponent(token)}/challenge`,
      {
        method: "POST",
        cache: "no-store",
      },
    );
    if (response.status === 404) return { status: "not-found" };
    if (response.status === 410) return { status: "expired" };
    if (response.status === 429) return { status: "rate-limited" };
    return response.ok ? { status: "sent" } : { status: "error" };
  } catch (error) {
    logError(error, {
      source: "SharedReport",
      extra: { action: "request_verification" },
    });
    return { status: "error" };
  }
}

export async function verifySharedReportRecipient(
  token: string,
  code: string,
): Promise<SharedReportResult> {
  if (!TOKEN_PATTERN.test(token)) return { status: "not-found" };
  if (!CODE_PATTERN.test(code)) {
    return { status: "verification-required", invalid: true };
  }

  if (DEMO_MODE_ENABLED) {
    if (code !== DEMO_SHARE_VERIFICATION_CODE) {
      return { status: "verification-required", invalid: true };
    }
    const report = getDemoSharedReport(token);
    if (!report) return { status: "not-found" };
    const verificationClock = resolveDemoShareVerificationClock();
    const attributedReport = {
      ...report,
      verified_recipient_email: "recipient@demo.praviar.invalid",
      attributable_view_number: 1,
      verified_session_expires_at: new Date(
        verificationClock.getTime() + 30 * 60 * 1000,
      ).toISOString(),
    };
    if (isSharedReportExpired(attributedReport, verificationClock)) {
      return { status: "expired" };
    }
    return isSharedReportVerificationSessionExpired(
      attributedReport,
      verificationClock,
    )
      ? { status: "verification-required", invalid: false }
      : { status: "ok", report: attributedReport };
  }

  if (!API_BASE_URL) return { status: "error" };

  try {
    const verificationResponse = await fetch(
      `${API_BASE_URL}/share/${encodeURIComponent(token)}/verify`,
      {
        method: "POST",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ code }),
      },
    );
    if (verificationResponse.status === 404) return { status: "not-found" };
    if (verificationResponse.status === 410) return { status: "expired" };
    if (
      verificationResponse.status === 401 ||
      verificationResponse.status === 429
    ) {
      return { status: "verification-required", invalid: true };
    }
    if (!verificationResponse.ok) return { status: "error" };

    const verificationPayload: unknown = await verificationResponse.json();
    if (!isVerificationPayload(verificationPayload)) return { status: "error" };

    // The proof is used immediately in this server action and is never returned
    // to the browser, written to storage, placed in a cookie, or added to a URL.
    const reportResponse = await fetch(
      `${API_BASE_URL}/share/${encodeURIComponent(token)}`,
      {
        cache: "no-store",
        headers: {
          [ACCESS_SECRET_HEADER]: verificationPayload.access_secret,
        },
      },
    );
    if (reportResponse.status === 404) return { status: "not-found" };
    if (reportResponse.status === 410) return { status: "expired" };
    if (reportResponse.status === 401) {
      return { status: "verification-required", invalid: true };
    }
    if (!reportResponse.ok) return { status: "error" };

    const report = parseSharedReportPayload(await reportResponse.json());
    if (!report) return { status: "error" };
    if (isSharedReportExpired(report)) {
      return { status: "expired" };
    }
    return isSharedReportVerificationSessionExpired(report)
      ? { status: "verification-required", invalid: false }
      : { status: "ok", report };
  } catch (error) {
    logError(error, {
      source: "SharedReport",
      extra: { action: "verify_recipient" },
    });
    return { status: "error" };
  }
}

function isVerificationPayload(
  value: unknown,
): value is { access_secret: string; access_expires_at: string } {
  if (typeof value !== "object" || value === null) return false;
  const payload = value as Record<string, unknown>;
  return (
    typeof payload.access_secret === "string" &&
    TOKEN_PATTERN.test(payload.access_secret) &&
    typeof payload.access_expires_at === "string" &&
    !Number.isNaN(Date.parse(payload.access_expires_at))
  );
}
