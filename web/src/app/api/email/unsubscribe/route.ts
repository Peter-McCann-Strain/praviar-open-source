import { createHash } from "node:crypto";

import { NextRequest, NextResponse } from "next/server";

import {
  DIGEST_UNSUBSCRIBE_COOKIE,
  hasUsableDigestUnsubscribeToken,
} from "@/lib/digest-unsubscribe";
import { resolvePublicApiOrigin } from "@/lib/production-env";

const ONE_CLICK_VALUE = "One-Click";

function resultRedirect(request: NextRequest, result: string) {
  const destination = new URL("/unsubscribe/digest", request.url);
  destination.searchParams.set("result", result);
  const response = NextResponse.redirect(destination, {
    status: 303,
    headers: {
      "Cache-Control": "no-store",
      "Referrer-Policy": "no-referrer",
      "X-Robots-Tag": "noindex, nofollow",
    },
  });
  response.cookies.delete(DIGEST_UNSUBSCRIBE_COOKIE);
  return response;
}

function oneClickResponse(status = 204) {
  return new NextResponse(null, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "Referrer-Policy": "no-referrer",
      "X-Robots-Tag": "noindex, nofollow",
    },
  });
}

export async function POST(request: NextRequest) {
  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return oneClickResponse();
  }
  const isFooterConfirmation = formData.get("source") === "footer";
  if (formData.get("List-Unsubscribe") !== ONE_CLICK_VALUE) {
    return isFooterConfirmation
      ? resultRedirect(request, "processed")
      : oneClickResponse();
  }
  const bodyToken = formData.get("token");
  const token =
    typeof bodyToken === "string" && bodyToken
      ? bodyToken
      : (request.cookies.get(DIGEST_UNSUBSCRIBE_COOKIE)?.value ??
        request.nextUrl.searchParams.get("token") ??
        "");
  if (!hasUsableDigestUnsubscribeToken(token)) {
    return isFooterConfirmation
      ? resultRedirect(request, "processed")
      : oneClickResponse();
  }
  const tokenLocator = createHash("sha256")
    .update(token, "ascii")
    .digest("hex");

  const apiUrl = resolvePublicApiOrigin({
    apiUrl: process.env.NEXT_PUBLIC_API_URL,
    nodeEnv: process.env.NODE_ENV,
  });
  if (!apiUrl) {
    return isFooterConfirmation
      ? resultRedirect(request, "retry")
      : oneClickResponse(503);
  }

  let upstream: Response;
  try {
    upstream = await fetch(
      `${apiUrl}/api/v1/notifications/unsubscribe/digest/${tokenLocator}`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ token }),
        cache: "no-store",
        signal: AbortSignal.timeout(10_000),
      },
    );
  } catch {
    if (isFooterConfirmation) {
      return resultRedirect(request, "retry");
    }
    return oneClickResponse(503);
  }

  if (isFooterConfirmation) {
    return resultRedirect(
      request,
      upstream.status < 500 ? "processed" : "retry",
    );
  }

  return upstream.status < 500
    ? oneClickResponse()
    : oneClickResponse(upstream.status);
}
