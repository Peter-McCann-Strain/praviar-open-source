"use client";

/**
 * Auth token hook. The canonical entry point used across the app.
 *
 * The implementation is intentionally kept inline here (rather than
 * delegating to the split sub-hooks) so that all log messages share the
 * stable `[useAuthToken]` namespace that downstream tooling and tests
 * depend on. The split sub-hooks (`useClerkSession`, `useDemoAuth`,
 * `useAuthPolling`) are re-exported below for callers that want a
 * narrower slice of the auth pipeline.
 */
import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  TOKEN_REFRESH_INTERVAL_MS,
  AUTH_GIVE_UP_MS,
  AUTH_INITIAL_POLL_MS,
  AUTH_MAX_POLL_MS,
  DEV_AUTH_BYPASS_ENABLED,
} from "@/lib/constants";
import {
  type AuthBoundaryChangedDetail,
  AUTH_BOUNDARY_CHANGED_EVENT,
  acceptAuthToken,
  getAuthBoundaryVersion,
} from "@/lib/auth-events";
import {
  type AuthSessionRecoveryTestDetail,
  AUTH_SESSION_RECOVERY_TEST_EVENT,
  isAuthBoundaryTestBridgeEnabled,
  isAuthSessionRecoveryTestReason,
} from "@/lib/auth-boundary-test-bridge";
import { useToastStore } from "@/stores/toast-store";
import { logError } from "@/lib/error-logger";

import {
  AUTH_SERVICE_NOT_CONFIGURED_MESSAGE,
  AUTH_SESSION_REFRESH_ERROR_MESSAGE,
  AUTH_SESSION_UNAVAILABLE_ERROR_MESSAGE,
  hasClerk,
  useClerkSession,
} from "@/hooks/use-clerk-session";
import { useDemoAuth } from "@/hooks/use-demo-auth";
import { useAuthPolling } from "@/hooks/use-auth-polling";

export { hasClerk, useClerkSession, useDemoAuth, useAuthPolling };

const IS_PRODUCTION = process.env.NODE_ENV === "production";

let _warnedNoClerk = false;

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

/**
 * Returns a bearer token for API requests plus an error state.
 *
 * When Clerk is configured, extracts the session token from window.Clerk.
 * In development without Clerk, returns "dev-token" only when the explicit
 * NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS flag is enabled for backend dev-mode bypass.
 * In production without Clerk, sets error state -- NO silent fallback.
 */
export type AuthSessionRecoveryReason = "expired" | "refresh_failed";

export interface AuthSessionRecoveryState {
  reason: AuthSessionRecoveryReason | null;
  isRefreshing: boolean;
  retrySession: () => void;
}

interface AuthTokenControllerState {
  token: string | null;
  recovery: AuthSessionRecoveryState;
}

const AuthTokenContext = createContext<AuthTokenControllerState | undefined>(
  undefined,
);

function useAuthTokenController(enabled: boolean): AuthTokenControllerState {
  const demoToken = useDemoAuth();
  const addToast = useToastStore((s) => s.addToast);
  const addToastRef = useRef(addToast);
  const refreshSuspendedRef = useRef(false);
  const hadAcceptedTokenRef = useRef(
    enabled &&
      Boolean(
        demoToken || (!hasClerk && !IS_PRODUCTION && DEV_AUTH_BYPASS_ENABLED),
      ),
  );
  const manualRetryInFlightRef = useRef(false);
  const automaticRefreshInFlightRef = useRef(false);
  const refreshSequenceRef = useRef(0);
  const retrySessionRef = useRef<() => Promise<void>>(async () => {});
  const recoveryReasonRef = useRef<AuthSessionRecoveryReason | null>(null);
  useEffect(() => {
    addToastRef.current = addToast;
  }, [addToast]);

  const [recoveryReason, setRecoveryReasonState] =
    useState<AuthSessionRecoveryReason | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const setRecoveryReason = useCallback(
    (reason: AuthSessionRecoveryReason | null) => {
      recoveryReasonRef.current = reason;
      setRecoveryReasonState(reason);
    },
    [],
  );
  const retrySession = useCallback(() => {
    if (!enabled) return;
    void retrySessionRef.current();
  }, [enabled]);

  const [token, setToken] = useState<string | null>(() => {
    if (!enabled) return null;
    if (demoToken) {
      acceptAuthToken(demoToken);
      return demoToken;
    }

    if (hasClerk) return null;

    // No Clerk configured
    if (IS_PRODUCTION) {
      // FAIL LOUD: In production, refusing to use dev-token
      console.error(
        "[useAuthToken] PRODUCTION ERROR: Clerk is not configured (NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is missing or invalid). " +
          "Authentication will not work. Set a valid Clerk publishable key for production deployment.",
      );
      return null;
    }

    if (!DEV_AUTH_BYPASS_ENABLED) {
      console.warn(
        "[useAuthToken] DEV MODE: Clerk not configured and dev auth bypass disabled. " +
          "Set NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY or explicit NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS=true.",
      );
      return null;
    }

    // Explicit development bypass only: use dev-token
    if (!_warnedNoClerk) {
      _warnedNoClerk = true;
      console.info(
        "[useAuthToken] DEV MODE: Clerk not configured — using explicit dev-token bypass. " +
          "API calls will bypass authentication. This is only acceptable in local development.",
      );
    }
    acceptAuthToken("dev-token");
    return "dev-token";
  });

  const [, setError] = useState<string | null>(() => {
    if (!enabled) return null;
    if (demoToken) {
      return null;
    }

    if (!hasClerk && IS_PRODUCTION) {
      return AUTH_SERVICE_NOT_CONFIGURED_MESSAGE;
    }
    return null;
  });

  useEffect(() => {
    if (!enabled || !isAuthBoundaryTestBridgeEnabled()) return;

    function handleTestRecoveryChange(event: Event) {
      const reason = (
        event as CustomEvent<Partial<AuthSessionRecoveryTestDetail>>
      ).detail?.reason;
      if (!isAuthSessionRecoveryTestReason(reason)) return;

      if (reason === null) {
        acceptAuthToken("dev-token");
        hadAcceptedTokenRef.current = true;
        setToken("dev-token");
        setError(null);
      } else {
        acceptAuthToken(null);
        setToken(null);
      }
      setRecoveryReason(reason);
      setIsRefreshing(false);
    }

    window.addEventListener(
      AUTH_SESSION_RECOVERY_TEST_EVENT,
      handleTestRecoveryChange,
    );
    return () => {
      window.removeEventListener(
        AUTH_SESSION_RECOVERY_TEST_EVENT,
        handleTestRecoveryChange,
      );
    };
  }, [enabled, setRecoveryReason]);

  useEffect(() => {
    if (!enabled) return;

    if (demoToken) {
      acceptAuthToken(demoToken);
      hadAcceptedTokenRef.current = true;

      function handleAuthBoundaryChanged(event: Event) {
        const shouldRefresh =
          (event as CustomEvent<AuthBoundaryChangedDetail>).detail
            ?.refreshToken ?? true;

        acceptAuthToken(demoToken);
        hadAcceptedTokenRef.current = true;
        setRecoveryReason(null);
        setIsRefreshing(false);

        if (!shouldRefresh) return;
      }

      window.addEventListener(
        AUTH_BOUNDARY_CHANGED_EVENT,
        handleAuthBoundaryChanged,
      );
      return () => {
        window.removeEventListener(
          AUTH_BOUNDARY_CHANGED_EVENT,
          handleAuthBoundaryChanged,
        );
      };
    }

    if (!hasClerk) {
      retrySessionRef.current = async () => {
        if (manualRetryInFlightRef.current) return;
        manualRetryInFlightRef.current = true;
        setIsRefreshing(true);
        try {
          if (!IS_PRODUCTION && DEV_AUTH_BYPASS_ENABLED) {
            acceptAuthToken("dev-token");
            hadAcceptedTokenRef.current = true;
            setToken("dev-token");
            setError(null);
            setRecoveryReason(null);
          }
        } finally {
          manualRetryInFlightRef.current = false;
          setIsRefreshing(false);
        }
      };
      if (IS_PRODUCTION) {
        // Surface the error to the user via toast
        addToastRef.current(
          "Authentication not configured — API requests will fail. Check NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY.",
          "error",
        );
        console.error(
          "[useAuthToken] PRODUCTION: Clerk publishable key missing or invalid. " +
            "Configure NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY.",
        );
      }
      function handleAuthBoundaryChanged(event: Event) {
        acceptAuthToken(null);
        hadAcceptedTokenRef.current = false;
        setRecoveryReason(null);
        setIsRefreshing(false);
        const shouldRefresh =
          (event as CustomEvent<AuthBoundaryChangedDetail>).detail
            ?.refreshToken ?? true;
        if (shouldRefresh && !IS_PRODUCTION && DEV_AUTH_BYPASS_ENABLED) {
          acceptAuthToken("dev-token");
          hadAcceptedTokenRef.current = true;
          setToken("dev-token");
          setError(null);
          return;
        }
        setToken(null);
      }

      window.addEventListener(
        AUTH_BOUNDARY_CHANGED_EVENT,
        handleAuthBoundaryChanged,
      );
      return () => {
        retrySessionRef.current = async () => {};
        window.removeEventListener(
          AUTH_BOUNDARY_CHANGED_EVENT,
          handleAuthBoundaryChanged,
        );
      };
    }

    let cancelled = false;
    // FIX 7: Initialize to undefined so clearInterval doesn't error on uninitialized value
    let refreshInterval: ReturnType<typeof setInterval> | undefined = undefined;

    async function refresh(
      expectedBoundaryVersion = getAuthBoundaryVersion(),
      forceFresh = false,
      trigger: "automatic" | "manual" = "automatic",
    ) {
      if (refreshSuspendedRef.current) {
        return;
      }

      const isManual = trigger === "manual";
      if (isManual) {
        if (manualRetryInFlightRef.current) return;
        // A manual fresh-token request supersedes any slower automatic refresh.
        // The request sequence below prevents that older result from committing.
        automaticRefreshInFlightRef.current = false;
        manualRetryInFlightRef.current = true;
        setIsRefreshing(true);
      } else {
        if (
          manualRetryInFlightRef.current ||
          automaticRefreshInFlightRef.current
        ) {
          return;
        }
        automaticRefreshInFlightRef.current = true;
      }
      const refreshSequence = ++refreshSequenceRef.current;

      const requestsFreshToken =
        forceFresh || isManual || recoveryReasonRef.current !== null;

      try {
        const t = await window.Clerk?.session?.getToken(
          requestsFreshToken ? { skipCache: true } : undefined,
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
            console.warn(
              "[useAuthToken] Clerk returned a token for a stale authentication boundary.",
            );
            setToken(null);
            setError(AUTH_SESSION_REFRESH_ERROR_MESSAGE);
            return;
          }
          hadAcceptedTokenRef.current = true;
          setToken(t);
          setError(null);
          if (requestsFreshToken) {
            setRecoveryReason(null);
          }
        } else {
          console.error(
            "[useAuthToken] Clerk session returned null token — session may have expired.",
          );
          const hadAcceptedToken = hadAcceptedTokenRef.current;
          acceptAuthToken(null);
          setToken(null);
          if (hadAcceptedToken) {
            setRecoveryReason("expired");
          }
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
          source: "useAuthToken",
          extra: {
            action: "refresh_clerk_token",
            clerkLoaded: window.Clerk?.loaded,
            hasSession: Boolean(window.Clerk?.session),
          },
        });
        const hadAcceptedToken = hadAcceptedTokenRef.current;
        if (hadAcceptedToken) {
          setRecoveryReason("refresh_failed");
        } else {
          addToastRef.current(
            "Authentication failed — please refresh the page",
            "error",
          );
        }
        acceptAuthToken(null);
        setToken(null);
        setError(AUTH_SESSION_REFRESH_ERROR_MESSAGE);
      } finally {
        if (isManual) {
          if (
            !cancelled &&
            expectedBoundaryVersion === getAuthBoundaryVersion() &&
            refreshSequence === refreshSequenceRef.current
          ) {
            manualRetryInFlightRef.current = false;
            setIsRefreshing(false);
          }
        } else if (refreshSequence === refreshSequenceRef.current) {
          automaticRefreshInFlightRef.current = false;
        }
      }
    }

    retrySessionRef.current = () =>
      refresh(getAuthBoundaryVersion(), true, "manual");

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
          console.error("[useAuthToken]", timeoutMsg, {
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
      hadAcceptedTokenRef.current = false;
      manualRetryInFlightRef.current = false;
      automaticRefreshInFlightRef.current = false;
      refreshSequenceRef.current += 1;
      setRecoveryReason(null);
      setIsRefreshing(false);
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
      manualRetryInFlightRef.current = false;
      automaticRefreshInFlightRef.current = false;
      retrySessionRef.current = async () => {};
      window.removeEventListener(
        AUTH_BOUNDARY_CHANGED_EVENT,
        handleAuthBoundaryChanged,
      );
      clearTimeout(initTimeout);
      if (refreshInterval !== undefined) {
        clearInterval(refreshInterval);
      }
    };
  }, [demoToken, enabled, setRecoveryReason]);

  const recovery = useMemo<AuthSessionRecoveryState>(
    () => ({
      reason: recoveryReason,
      isRefreshing,
      retrySession,
    }),
    [isRefreshing, recoveryReason, retrySession],
  );

  return useMemo(
    () => ({
      token: demoToken ?? token,
      recovery,
    }),
    [demoToken, recovery, token],
  );
}

/**
 * Own the single Clerk polling/refresh loop for the application. Consumers use
 * `useAuthToken()` below, so dozens of data hooks do not create duplicate
 * intervals or race one another during an organization switch.
 */
export function AuthTokenProvider({ children }: { children: ReactNode }) {
  const authState = useAuthTokenController(true);
  return createElement(
    AuthTokenContext.Provider,
    { value: authState },
    children,
  );
}

/** Return the shared bearer token, with a standalone controller for hook tests. */
export function useAuthToken(): string | null {
  const sharedAuthState = useContext(AuthTokenContext);
  const standaloneAuthState = useAuthTokenController(
    sharedAuthState === undefined,
  );
  return sharedAuthState === undefined
    ? standaloneAuthState.token
    : sharedAuthState.token;
}

/**
 * Return durable recovery controls for an established session that can no
 * longer produce a token. Initial auth loading, signed-out state, and auth
 * boundary changes intentionally remain outside this state.
 */
export function useAuthSessionRecovery(): AuthSessionRecoveryState {
  const sharedAuthState = useContext(AuthTokenContext);
  const standaloneAuthState = useAuthTokenController(
    sharedAuthState === undefined,
  );
  return sharedAuthState === undefined
    ? standaloneAuthState.recovery
    : sharedAuthState.recovery;
}
