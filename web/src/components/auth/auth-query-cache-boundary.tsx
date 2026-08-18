"use client";

import { useAuth } from "@clerk/nextjs";
import type { QueryClient } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useRef } from "react";
import {
  AUTH_BOUNDARY_CHANGED_EVENT,
  emitAuthBoundaryChanged,
  setCurrentAuthBoundaryKey,
  setCurrentAuthIdentityBoundary,
} from "@/lib/auth-events";
import { authScopeKeyFromClaims } from "@/lib/query-keys";
import { clearAnalysisLaunchDraftStorage } from "@/lib/analysis-launch-draft-storage";
import { useConfigStore } from "@/stores/config-store";
import { usePipelineStore } from "@/stores/pipeline-store";
import { useReviewStore } from "@/stores/review-store";

export const PRIVATE_QUERY_ROOTS = [
  "admin",
  "analyses",
  "api-keys",
  "batches",
  "billing",
  "claimed-use-receipts",
  "comments",
  "compounds",
  "config-defaults",
  "config-presets",
  "export-jobs",
  "monitors",
  "notifications",
  "patents",
  "principal-capabilities",
  "reports",
  "review-queue",
  "reviewer-decisions",
  "setup-readiness",
] as const;

const CONFIG_AUTH_BOUNDARY_STORAGE_KEY = "praviar:config-auth-boundary";

function bindPersistedConfigToAuthBoundary(boundaryKey: string): boolean {
  if (typeof window === "undefined") return false;

  try {
    const storedBoundary = window.localStorage.getItem(
      CONFIG_AUTH_BOUNDARY_STORAGE_KEY,
    );
    const hasPersistedConfig =
      window.localStorage.getItem("praviar-config") !== null;
    const mustReset = hasPersistedConfig && storedBoundary !== boundaryKey;
    window.localStorage.setItem(CONFIG_AUTH_BOUNDARY_STORAGE_KEY, boundaryKey);
    return mustReset;
  } catch {
    // Storage may be unavailable in privacy-restricted contexts. The live
    // boundary transition still resets the in-memory store below.
    return false;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export interface AuthBoundarySnapshot {
  key: string;
  refreshToken: boolean;
}

export function buildAuthBoundarySnapshot({
  isLoaded,
  isSignedIn,
  userId,
  sessionId,
  orgId,
  orgRole,
  orgSlug,
  sessionClaims,
}: {
  isLoaded: boolean;
  isSignedIn: boolean | undefined;
  userId: string | null | undefined;
  sessionId: string | null | undefined;
  orgId: string | null | undefined;
  orgRole: string | null | undefined;
  orgSlug: string | null | undefined;
  sessionClaims: unknown;
}): AuthBoundarySnapshot {
  if (!isLoaded) {
    return { key: "auth:loading", refreshToken: false };
  }
  if (!isSignedIn) {
    return { key: "auth:signed-out", refreshToken: false };
  }

  const boundaryClaims = isRecord(sessionClaims) ? { ...sessionClaims } : {};
  if (userId) boundaryClaims.sub = userId;
  if (sessionId) boundaryClaims.sid = sessionId;
  if (orgId) boundaryClaims.org_id = orgId;
  if (orgRole) boundaryClaims.org_role = orgRole;
  if (orgSlug) boundaryClaims.org_slug = orgSlug;

  return {
    key: authScopeKeyFromClaims(boundaryClaims),
    refreshToken: true,
  };
}

export function purgePrivateAuthCache(queryClient: QueryClient): void {
  for (const root of PRIVATE_QUERY_ROOTS) {
    void queryClient.cancelQueries({ queryKey: [root] });
    queryClient.removeQueries({ queryKey: [root] });
  }
  queryClient.getMutationCache().clear();
}

export function resetPrivateClientState(): void {
  clearAnalysisLaunchDraftStorage();
  usePipelineStore.getState().reset();
  useReviewStore.getState().resetAll();
  useConfigStore.getState().clearAuthScope();
}

export function AuthBoundaryEventCacheReset({
  queryClient,
}: {
  queryClient: QueryClient;
}) {
  useEffect(() => {
    function handleAuthBoundaryChanged() {
      purgePrivateAuthCache(queryClient);
      resetPrivateClientState();
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
  }, [queryClient]);

  return null;
}

export function AuthQueryCacheBoundary({
  queryClient,
}: {
  queryClient: QueryClient;
}) {
  const previousBoundaryRef = useRef<string | null>(null);
  const auth = useAuth();
  const boundary = buildAuthBoundarySnapshot(auth);
  const { key: boundaryKey, refreshToken } = boundary;

  useLayoutEffect(
    () => () => {
      setCurrentAuthIdentityBoundary(null);
    },
    [],
  );

  useLayoutEffect(() => {
    setCurrentAuthIdentityBoundary(
      auth.isLoaded && auth.isSignedIn && auth.userId && auth.sessionId
        ? {
            userId: auth.userId,
            sessionId: auth.sessionId,
            orgId: auth.orgId ?? null,
            orgRole: auth.orgRole ?? null,
          }
        : null,
    );
    const previousBoundary = previousBoundaryRef.current;
    previousBoundaryRef.current = boundaryKey;

    if (previousBoundary === null) {
      setCurrentAuthBoundaryKey(boundaryKey);
      if (
        boundaryKey !== "auth:loading" &&
        bindPersistedConfigToAuthBoundary(boundaryKey)
      ) {
        resetPrivateClientState();
      }
      return;
    }

    if (previousBoundary === "auth:loading") {
      setCurrentAuthBoundaryKey(boundaryKey);
      if (bindPersistedConfigToAuthBoundary(boundaryKey)) {
        resetPrivateClientState();
      }
      // A token may have been read while Clerk's identity boundary was still
      // unresolved. Force one uncached, identity-validated token before any
      // private query can use the resolved user/session/organization context.
      emitAuthBoundaryChanged({ refreshToken, boundaryKey });
      return;
    }

    if (previousBoundary === boundaryKey) {
      return;
    }

    purgePrivateAuthCache(queryClient);
    resetPrivateClientState();
    bindPersistedConfigToAuthBoundary(boundaryKey);
    emitAuthBoundaryChanged({ refreshToken, boundaryKey });
  }, [
    auth.isLoaded,
    auth.isSignedIn,
    auth.orgId,
    auth.orgRole,
    auth.sessionId,
    auth.userId,
    boundaryKey,
    queryClient,
    refreshToken,
  ]);

  return null;
}
