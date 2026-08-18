"use client";

/**
 * Explicit dev-mode auth bypass. Returns "dev-token" only when Clerk is not
 * configured, we are not in production, demo mode is off, and
 * NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS=true. Returns `null` otherwise so callers
 * can choose another path.
 *
 * The name "polling" reflects the role of this hook in the auth pipeline:
 * it's the dev-time stand-in that sits next to the Clerk poller in
 * `useClerkSession`. There is no real polling here — by design — because
 * the dev token is static.
 */
import { DEMO_MODE_ENABLED, DEV_AUTH_BYPASS_ENABLED } from "@/lib/constants";
import { hasClerk } from "@/hooks/use-clerk-session";

const IS_PRODUCTION = process.env.NODE_ENV === "production";

let _warnedNoClerk = false;

export function useAuthPolling(): string | null {
  if (hasClerk || DEMO_MODE_ENABLED) return null;
  if (IS_PRODUCTION) return null;
  if (!DEV_AUTH_BYPASS_ENABLED) return null;

  if (!_warnedNoClerk) {
    _warnedNoClerk = true;
    console.info(
      "[useAuthPolling] DEV MODE: Clerk not configured — using explicit dev-token bypass. " +
        "API calls will bypass authentication. This is only acceptable in local development.",
    );
  }
  return "dev-token";
}
