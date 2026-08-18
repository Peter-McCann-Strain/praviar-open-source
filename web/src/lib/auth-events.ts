"use client";

import { authScopeKey } from "@/lib/query-keys";

export const AUTH_BOUNDARY_CHANGED_EVENT = "praviar:auth-boundary-changed";

export interface AuthBoundaryChangedDetail {
  refreshToken: boolean;
}

export interface AuthIdentityBoundary {
  userId: string;
  sessionId: string;
  orgId: string | null;
  orgRole: string | null;
}

let authBoundaryVersion = 0;
let authBoundaryAbortController = new AbortController();
let currentAuthBoundaryKey: string | null = null;
let currentAuthIdentityBoundary: AuthIdentityBoundary | null = null;
let authTokenValidationRequired = true;
let acceptedAuthTokenScope: string | null = null;
let acceptedAuthBoundaryKey: string | null = null;
let acceptedAuthBoundaryVersion: number | null = null;

export function getAuthBoundaryVersion(): number {
  return authBoundaryVersion;
}

export function getCurrentAuthBoundaryKey(): string | null {
  return currentAuthBoundaryKey;
}

export function setCurrentAuthBoundaryKey(boundaryKey: string | null): void {
  currentAuthBoundaryKey = boundaryKey;
}

export function setCurrentAuthIdentityBoundary(
  boundary: AuthIdentityBoundary | null,
): void {
  currentAuthIdentityBoundary = boundary;
}

export function getAuthBoundarySignal(): AbortSignal {
  return authBoundaryAbortController.signal;
}

export function acceptAuthToken(token: string | null): boolean {
  if (
    token &&
    currentAuthIdentityBoundary &&
    !authTokenMatchesIdentityBoundary(token, currentAuthIdentityBoundary)
  ) {
    acceptedAuthTokenScope = null;
    acceptedAuthBoundaryKey = null;
    acceptedAuthBoundaryVersion = null;
    return false;
  }
  acceptedAuthTokenScope = token ? authScopeKey(token) : null;
  acceptedAuthBoundaryKey = token ? currentAuthBoundaryKey : null;
  acceptedAuthBoundaryVersion = token ? authBoundaryVersion : null;
  authTokenValidationRequired = true;
  return Boolean(token);
}

function decodeJwtClaims(token: string): Record<string, unknown> | null {
  const parts = token.split(".");
  if (parts.length !== 3 || !parts[1]) return null;
  try {
    const normalized = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(
      normalized.length + ((4 - (normalized.length % 4)) % 4),
      "=",
    );
    const parsed = JSON.parse(globalThis.atob(padded));
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

function normalizedOrgRole(value: string | null): string | null {
  if (!value) return null;
  return value.startsWith("org:") ? value.slice(4) : value;
}

export function authTokenMatchesIdentityBoundary(
  token: string,
  boundary: AuthIdentityBoundary,
): boolean {
  const claims = decodeJwtClaims(token);
  if (!claims || claims.v !== 2) return false;
  if (claims.sub !== boundary.userId || claims.sid !== boundary.sessionId) {
    return false;
  }

  const orgClaim = claims.o;
  if (boundary.orgId === null) {
    return orgClaim === undefined || orgClaim === null;
  }
  if (!orgClaim || typeof orgClaim !== "object" || Array.isArray(orgClaim)) {
    return false;
  }
  const organization = orgClaim as Record<string, unknown>;
  return (
    organization.id === boundary.orgId &&
    organization.rol === normalizedOrgRole(boundary.orgRole)
  );
}

export function isAuthTokenAccepted(token: string): boolean {
  if (!authTokenValidationRequired) return true;
  return (
    acceptedAuthTokenScope === authScopeKey(token) &&
    acceptedAuthBoundaryKey === currentAuthBoundaryKey &&
    acceptedAuthBoundaryVersion === authBoundaryVersion
  );
}

export function emitAuthBoundaryChanged({
  refreshToken = true,
  boundaryKey = currentAuthBoundaryKey,
}: Partial<AuthBoundaryChangedDetail> & {
  boundaryKey?: string | null;
} = {}): void {
  authBoundaryVersion += 1;
  currentAuthBoundaryKey = boundaryKey;
  authTokenValidationRequired = true;
  acceptedAuthTokenScope = null;
  acceptedAuthBoundaryKey = null;
  acceptedAuthBoundaryVersion = null;
  authBoundaryAbortController.abort(
    new Error("Authentication boundary changed"),
  );
  authBoundaryAbortController = new AbortController();
  window.dispatchEvent(
    new CustomEvent<AuthBoundaryChangedDetail>(AUTH_BOUNDARY_CHANGED_EVENT, {
      detail: { refreshToken },
    }),
  );
}
