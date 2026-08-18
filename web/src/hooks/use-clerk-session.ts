"use client";

/**
 * Clerk session token extraction hook. Coordinates with Clerk's window
 * global to fetch the bearer token, refresh it on an interval, and surface
 * fatal failures via toast + console.
 *
 * In production with no Clerk configured this returns `null` and surfaces
 * an error toast — there is no silent fallback.
 *
 * Use directly when you only care about the Clerk path; otherwise compose
 * via `useAuthToken`, which can use explicit demo mode or the local
 * dev-token bypass when `NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS=true`.
 */
import { useEffect, useRef, useState } from "react";
import {
  AUTH_GIVE_UP_MS,
  AUTH_INITIAL_POLL_MS,
  AUTH_MAX_POLL_MS,
  TOKEN_REFRESH_INTERVAL_MS,
} from "@/lib/constants";
import {
  type AuthBoundaryChangedDetail,
  AUTH_BOUNDARY_CHANGED_EVENT,
  acceptAuthToken,
  getAuthBoundaryVersion,
} from "@/lib/auth-events";
import { hasValidClerkPublishableKey } from "@/lib/production-env";
import { useToastStore } from "@/stores/toast-store";
import { logError } from "@/lib/error-logger";

const CLERK_KEY = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
const IS_PRODUCTION = process.env.NODE_ENV === "production";

export const AUTH_SERVICE_NOT_CONFIGURED_MESSAGE =
  "Authentication service not configured. Contact your administrator.";
export const AUTH_SESSION_REFRESH_ERROR_MESSAGE =
  "Authentication failed. Refresh the page or sign in again.";
export const AUTH_SESSION_UNAVAILABLE_ERROR_MESSAGE =
  "Authentication service unavailable. Refresh the page or sign in again.";

/** True when a usable Clerk publishable key is present at build time. */
export const hasClerk = hasValidClerkPublishableKey(CLERK_KEY);

declare global {
  interface Window {
    Clerk?: {
      loaded?: boolean;
      session?: {
        getToken: (options?: { skipCache?: boolean }) => Promise<string | null>;
      };
    };
  }
}

interface ClerkSessionState {
  /** Bearer token, or null while pending / on error. */
  token: string | null;
  /** Human-readable error if Clerk failed to initialise. */
  error: string | null;
  /** True if Clerk is configured for this build. */
  hasClerk: boolean;
}

/**
 * Returns the Clerk session token. Polls window.Clerk with exponential
 * backoff until ready, then refreshes on a fixed interval.
 */
export function useClerkSession(): ClerkSessionState {
  const addToast = useToastStore((s) => s.addToast);
  const addToastRef = useRef(addToast);
  const refreshSuspendedRef = useRef(false);
  const refreshInFlightRef = useRef(false);
  const refreshSequenceRef = useRef(0);
  useEffect(() => {
    addToastRef.current = addToast;
  }, [addToast]);

  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(() => {
    if (!hasClerk && IS_PRODUCTION) {
      return AUTH_SERVICE_NOT_CONFIGURED_MESSAGE;
    }
    return null;
  });

  useEffect(() => {
    if (!hasClerk) {
      if (IS_PRODUCTION) {
        addToastRef.current(
          "Authentication not configured — API requests will fail. Check NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY.",
          "error",
        );
        console.error(
          "[useClerkSession] PRODUCTION: Clerk publishable key missing or invalid. " +
            "Configure NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY.",
        );
      }
      return;
    }

    let cancelled = false;
    let refreshInterval: ReturnType<typeof setInterval> | undefined = undefined;

    async function refresh(
      expectedBoundaryVersion = getAuthBoundaryVersion(),
      forceFresh = false,
    ) {
      if (refreshSuspendedRef.current) {
        return;
      }
      if (refreshInFlightRef.current) {
        return;
      }
      refreshInFlightRef.current = true;
      const refreshSequence = ++refreshSequenceRef.current;

      try {
        const t = await window.Clerk?.session?.getToken(
          forceFresh ? { skipCache: true } : undefined,
        );
        if (
          cancelled ||
          expectedBoundaryVersion !== getAuthBoundaryVersion() ||
          refreshSequence !== refreshSequenceRef.current
        ) {
          return;
        }
        if (t) {
          if (!acceptAuthToken(t)) {
            setToken(null);
            setError(AUTH_SESSION_REFRESH_ERROR_MESSAGE);
            return;
          }
          setToken(t);
          setError(null);
        } else {
          console.error(
            "[useClerkSession] Clerk session returned null token — session may have expired.",
          );
          acceptAuthToken(null);
          setToken(null);
        }
      } catch {
        if (
          cancelled ||
          expectedBoundaryVersion !== getAuthBoundaryVersion() ||
          refreshSequence !== refreshSequenceRef.current
        ) {
          return;
        }
        logError(new Error("Clerk token refresh failed"), {
          source: "useClerkSession",
          extra: {
            action: "refresh_clerk_token",
            clerkLoaded: window.Clerk?.loaded,
            hasSession: Boolean(window.Clerk?.session),
          },
        });
        addToastRef.current(
          "Authentication failed — please refresh the page",
          "error",
        );
        acceptAuthToken(null);
        setToken(null);
        setError(AUTH_SESSION_REFRESH_ERROR_MESSAGE);
      } finally {
        if (refreshSequence === refreshSequenceRef.current) {
          refreshInFlightRef.current = false;
        }
      }
    }

    // Poll until Clerk initializes with exponential backoff (500ms -> 1s -> 2s)
    // Give up after AUTH_GIVE_UP_MS total elapsed time.
    const GIVE_UP_MS = AUTH_GIVE_UP_MS;
    let pollDelay = AUTH_INITIAL_POLL_MS;
    let elapsed = 0;
    let initTimeout: ReturnType<typeof setTimeout>;

    function pollClerk() {
      if (cancelled) return;
      if (window.Clerk?.session) {
        refresh(getAuthBoundaryVersion(), true);
        refreshInterval = setInterval(refresh, TOKEN_REFRESH_INTERVAL_MS);
        return;
      }
      elapsed += pollDelay;
      if (elapsed < GIVE_UP_MS) {
        pollDelay = Math.min(pollDelay * 2, AUTH_MAX_POLL_MS);
        initTimeout = setTimeout(pollClerk, pollDelay);
      } else {
        setToken((prev) => {
          if (prev) return prev;
          const timeoutMsg = `Clerk session did not initialize within ${GIVE_UP_MS}ms.`;
          console.error("[useClerkSession]", timeoutMsg, {
            clerkOnWindow: !!window.Clerk,
            clerkLoaded: window.Clerk?.loaded,
            hasSession: !!window.Clerk?.session,
          });
          addToastRef.current(
            "Authentication service unavailable — please refresh",
            "error",
          );
          setError(AUTH_SESSION_UNAVAILABLE_ERROR_MESSAGE);
          return null;
        });
      }
    }
    function handleAuthBoundaryChanged(event: Event) {
      acceptAuthToken(null);
      refreshSequenceRef.current += 1;
      refreshInFlightRef.current = false;
      setToken(null);
      const shouldRefresh =
        (event as CustomEvent<AuthBoundaryChangedDetail>).detail
          ?.refreshToken ?? true;
      refreshSuspendedRef.current = !shouldRefresh;
      if (shouldRefresh) {
        void refresh(getAuthBoundaryVersion(), true);
      }
    }

    initTimeout = setTimeout(pollClerk, pollDelay);
    window.addEventListener(
      AUTH_BOUNDARY_CHANGED_EVENT,
      handleAuthBoundaryChanged,
    );

    return () => {
      cancelled = true;
      refreshSequenceRef.current += 1;
      refreshInFlightRef.current = false;
      window.removeEventListener(
        AUTH_BOUNDARY_CHANGED_EVENT,
        handleAuthBoundaryChanged,
      );
      clearTimeout(initTimeout);
      if (refreshInterval !== undefined) {
        clearInterval(refreshInterval);
      }
    };
  }, []);

  return { token, error, hasClerk };
}
