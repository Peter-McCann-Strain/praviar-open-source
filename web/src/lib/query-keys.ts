"use client";

import type { QueryClient } from "@tanstack/react-query";

export const ANONYMOUS_AUTH_SCOPE = "auth:anonymous";

const SHA256_INITIAL_STATE: number[] = [
  0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c,
  0x1f83d9ab, 0x5be0cd19,
];

const SHA256_ROUND_CONSTANTS = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
  0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
  0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
  0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
  0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
  0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
] as const;

const VOLATILE_JWT_SCOPE_CLAIMS = new Set(["exp", "iat", "nbf"]);

function decodeBase64Url(value: string): string | null {
  try {
    const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(
      normalized.length + ((4 - (normalized.length % 4)) % 4),
      "=",
    );
    return globalThis.atob(padded);
  } catch {
    return null;
  }
}

function readStringClaim(
  claims: Record<string, unknown>,
  ...keys: string[]
): string | null {
  for (const key of keys) {
    const value = claims[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return null;
}

function rotateRight(value: number, bits: number): number {
  return (value >>> bits) | (value << (32 - bits));
}

function sha256Hex(value: string): string {
  const bytes = new TextEncoder().encode(value);
  const paddedLength = Math.ceil((bytes.length + 9) / 64) * 64;
  const padded = new Uint8Array(paddedLength);
  padded.set(bytes);
  padded[bytes.length] = 0x80;

  const bitLength = bytes.length * 8;
  const view = new DataView(padded.buffer);
  view.setUint32(paddedLength - 8, Math.floor(bitLength / 0x100000000));
  view.setUint32(paddedLength - 4, bitLength >>> 0);

  const state = [...SHA256_INITIAL_STATE];
  const words = new Uint32Array(64);

  for (let offset = 0; offset < padded.length; offset += 64) {
    for (let index = 0; index < 16; index += 1) {
      words[index] = view.getUint32(offset + index * 4);
    }

    for (let index = 16; index < 64; index += 1) {
      const s0 =
        rotateRight(words[index - 15], 7) ^
        rotateRight(words[index - 15], 18) ^
        (words[index - 15] >>> 3);
      const s1 =
        rotateRight(words[index - 2], 17) ^
        rotateRight(words[index - 2], 19) ^
        (words[index - 2] >>> 10);
      words[index] = (words[index - 16] + s0 + words[index - 7] + s1) >>> 0;
    }

    let [a, b, c, d, e, f, g, h] = state;

    for (let index = 0; index < 64; index += 1) {
      const s1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
      const ch = (e & f) ^ (~e & g);
      const temp1 =
        (h + s1 + ch + SHA256_ROUND_CONSTANTS[index] + words[index]) >>> 0;
      const s0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (s0 + maj) >>> 0;

      h = g;
      g = f;
      f = e;
      e = (d + temp1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) >>> 0;
    }

    state[0] = (state[0] + a) >>> 0;
    state[1] = (state[1] + b) >>> 0;
    state[2] = (state[2] + c) >>> 0;
    state[3] = (state[3] + d) >>> 0;
    state[4] = (state[4] + e) >>> 0;
    state[5] = (state[5] + f) >>> 0;
    state[6] = (state[6] + g) >>> 0;
    state[7] = (state[7] + h) >>> 0;
  }

  return state.map((word) => word.toString(16).padStart(8, "0")).join("");
}

function decodeJwtClaims(token: string): Record<string, unknown> | null {
  const [, payload] = token.split(".");
  if (!payload) return null;

  const decoded = decodeBase64Url(payload);
  if (!decoded) return null;

  try {
    const parsed = JSON.parse(decoded);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => canonicalize(item));
  }

  if (value && typeof value === "object") {
    const canonical: Record<string, unknown> = {};
    for (const key of Object.keys(value).sort()) {
      const canonicalValue = canonicalize(
        (value as Record<string, unknown>)[key],
      );
      if (canonicalValue !== undefined) {
        canonical[key] = canonicalValue;
      }
    }
    return canonical;
  }

  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }

  if (typeof value === "function" || typeof value === "symbol") {
    return undefined;
  }

  return value;
}

function authBoundaryClaims(
  claims: Record<string, unknown>,
): Record<string, unknown> {
  const boundaryClaims: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(claims)) {
    if (!VOLATILE_JWT_SCOPE_CLAIMS.has(key)) {
      boundaryClaims[key] = value;
    }
  }
  return boundaryClaims;
}

function hasBoundaryClaims(claims: Record<string, unknown>): boolean {
  return Object.keys(authBoundaryClaims(claims)).length > 0;
}

export function authScopeKeyFromClaims(
  claims: Record<string, unknown> | null | undefined,
): string {
  if (claims && Object.keys(claims).length > 0) {
    const boundaryClaims = authBoundaryClaims(claims);
    if (Object.keys(boundaryClaims).length === 0) {
      return `${ANONYMOUS_AUTH_SCOPE}:claims`;
    }
    const subject = readStringClaim(boundaryClaims, "sub", "sid");
    const organization = readStringClaim(
      boundaryClaims,
      "org_id",
      "orgId",
      "org_slug",
      "orgSlug",
    );
    const digestInput = JSON.stringify(canonicalize(boundaryClaims));
    const prefix = subject || organization ? "auth:scope" : "auth:jwt";
    return `${prefix}:${sha256Hex(digestInput)}`;
  }

  return `${ANONYMOUS_AUTH_SCOPE}:claims`;
}

export function authScopeKey(token: string | null | undefined): string {
  if (!token) return ANONYMOUS_AUTH_SCOPE;

  const claims = decodeJwtClaims(token);

  if (claims && Object.keys(claims).length > 0) {
    if (!hasBoundaryClaims(claims)) {
      return `auth:token:${sha256Hex(token)}`;
    }
    return authScopeKeyFromClaims(claims);
  }

  return `auth:token:${sha256Hex(token)}`;
}

export function authScopedQueryKey<const TKey extends readonly unknown[]>(
  baseKey: TKey,
  token: string | null | undefined,
): readonly [...TKey, string] {
  return [...baseKey, authScopeKey(token)] as readonly [...TKey, string];
}

export function authScopedMutationKey<const TKey extends readonly unknown[]>(
  baseKey: TKey,
  token: string | null | undefined,
): readonly [...TKey, string] {
  return authScopedQueryKey(baseKey, token);
}

type PreviousAuthScopedQuery = {
  queryKey?: readonly unknown[];
};

export function keepPreviousDataForAuthScope<TData>(
  currentAuthScope: string,
): (
  previousData: TData | undefined,
  previousQuery: PreviousAuthScopedQuery | undefined,
) => TData | undefined {
  return (previousData, previousQuery) => {
    const previousQueryKey = previousQuery?.queryKey;
    const previousAuthScope = previousQueryKey?.[previousQueryKey.length - 1];
    return previousAuthScope === currentAuthScope ? previousData : undefined;
  };
}

export function matchesAuthScopedQueryKey(
  queryKey: readonly unknown[],
  baseKey: readonly unknown[],
  token: string | null | undefined,
): boolean {
  if (queryKey.length < baseKey.length + 1) return false;
  if (queryKey[queryKey.length - 1] !== authScopeKey(token)) return false;
  return baseKey.every((segment, index) => Object.is(queryKey[index], segment));
}

export function matchesAuthScopedMutationKey(
  mutationKey: readonly unknown[],
  baseKey: readonly unknown[],
  token: string | null | undefined,
): boolean {
  return matchesAuthScopedQueryKey(mutationKey, baseKey, token);
}

export function invalidateAuthScopedQueries(
  queryClient: QueryClient,
  baseKey: readonly unknown[],
  token: string | null | undefined,
) {
  return queryClient.invalidateQueries({
    queryKey: baseKey,
    predicate: (query) =>
      matchesAuthScopedQueryKey(query.queryKey, baseKey, token),
  });
}
