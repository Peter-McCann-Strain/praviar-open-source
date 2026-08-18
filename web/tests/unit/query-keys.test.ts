import { describe, expect, it, vi } from "vitest";

import {
  authScopedMutationKey,
  authScopedQueryKey,
  authScopeKey,
  authScopeKeyFromClaims,
  invalidateAuthScopedQueries,
  matchesAuthScopedMutationKey,
  matchesAuthScopedQueryKey,
} from "@/lib/query-keys";

function jwt(claims: Record<string, unknown>) {
  const payload = btoa(JSON.stringify(claims))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
  return `header.${payload}.signature`;
}

describe("authScopeKey", () => {
  it("uses public JWT subject and org claims without exposing raw identifiers", () => {
    const scope = authScopeKey(jwt({ sub: "user_1", org_id: "org_1" }));

    expect(scope).toMatch(/^auth:scope:[a-f0-9]{64}$/);
    expect(scope).not.toContain("user_1");
    expect(scope).not.toContain("org_1");
  });

  it("changes when the active Clerk organization changes", () => {
    const userToken = jwt({ sub: "user_1", org_id: "org_1" });
    const switchedOrgToken = jwt({ sub: "user_1", org_id: "org_2" });

    expect(authScopeKey(userToken)).not.toBe(authScopeKey(switchedOrgToken));
  });

  it("changes when session or authorization claims change", () => {
    const adminToken = jwt({
      sub: "user_1",
      org_id: "org_1",
      sid: "sess_1",
      org_role: "org:admin",
      org_permissions: ["org:reports:read", "org:admin:read"],
    });
    const memberToken = jwt({
      sub: "user_1",
      org_id: "org_1",
      sid: "sess_2",
      org_role: "org:member",
      org_permissions: ["org:reports:read"],
    });

    expect(authScopeKey(adminToken)).not.toBe(authScopeKey(memberToken));
  });

  it("does not churn scope for volatile token time claims", () => {
    const firstToken = jwt({
      sub: "user_1",
      org_id: "org_1",
      sid: "sess_1",
      org_role: "org:admin",
      iat: 1780410000,
      exp: 1780413600,
      nbf: 1780410000,
    });
    const refreshedToken = jwt({
      sub: "user_1",
      org_id: "org_1",
      sid: "sess_1",
      org_role: "org:admin",
      iat: 1780413000,
      exp: 1780416600,
      nbf: 1780413000,
    });

    expect(authScopeKey(firstToken)).toBe(authScopeKey(refreshedToken));
  });

  it("does not collapse JWTs that only contain volatile time claims", () => {
    const firstToken = jwt({
      iat: 1780410000,
      exp: 1780413600,
      nbf: 1780410000,
    });
    const refreshedToken = jwt({
      iat: 1780413000,
      exp: 1780416600,
      nbf: 1780413000,
    });

    expect(authScopeKey(firstToken)).toMatch(/^auth:token:[a-f0-9]{64}$/);
    expect(authScopeKey(firstToken)).not.toBe(authScopeKey(refreshedToken));
  });

  it("does not collapse the previous 32-bit hash collision pair", () => {
    const firstToken = jwt({ sub: "user_1", org_id: "org_it0ufb9zkctp" });
    const secondToken = jwt({ sub: "user_1", org_id: "org_d10gf9035gap" });

    expect(authScopeKey(firstToken)).not.toBe(authScopeKey(secondToken));
  });

  it("does not put opaque bearer tokens into query keys", () => {
    const token = "opaque-secret-token";
    const scope = authScopeKey(token);

    expect(scope).toMatch(/^auth:token:[a-f0-9]{64}$/);
    expect(scope).not.toContain(token);
  });

  it("uses a SHA-256 digest for opaque token fallback scopes", () => {
    expect(authScopeKey("abc")).toBe(
      "auth:token:" +
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );
  });
});

describe("authScopeKeyFromClaims", () => {
  it("matches JWT-derived auth scopes for the same claims", () => {
    const claims = {
      sub: "user_1",
      org_id: "org_1",
      sid: "sess_1",
      org_role: "org:admin",
    };

    expect(authScopeKeyFromClaims(claims)).toBe(authScopeKey(jwt(claims)));
  });

  it("does not expose raw claim values", () => {
    const scope = authScopeKeyFromClaims({
      sub: "user_1",
      org_id: "org_1",
      sid: "sess_1",
      org_role: "org:admin",
    });

    expect(scope).toMatch(/^auth:scope:[a-f0-9]{64}$/);
    expect(scope).not.toContain("user_1");
    expect(scope).not.toContain("org_1");
    expect(scope).not.toContain("sess_1");
    expect(scope).not.toContain("admin");
  });

  it("does not manufacture a stable private scope from volatile-only claims", () => {
    expect(
      authScopeKeyFromClaims({
        iat: 1780410000,
        exp: 1780413600,
        nbf: 1780410000,
      }),
    ).toBe("auth:anonymous:claims");
  });
});

describe("authScopedQueryKey", () => {
  it("appends auth scope so prefix invalidations still match", () => {
    const token = jwt({ sub: "user_1", org_id: "org_1" });

    expect(
      authScopedQueryKey(["reports", "analysis-1"] as const, token),
    ).toEqual(["reports", "analysis-1", authScopeKey(token)]);
  });
});

describe("authScopedMutationKey", () => {
  it("appends the same auth scope used by private query keys", () => {
    const token = jwt({ sub: "user_1", org_id: "org_1" });

    expect(
      authScopedMutationKey(["reports", "analysis-1", "share"] as const, token),
    ).toEqual(["reports", "analysis-1", "share", authScopeKey(token)]);
  });
});

describe("matchesAuthScopedQueryKey", () => {
  it("matches scoped query keys for the current auth scope and base prefix", () => {
    const token = jwt({ sub: "user_1", org_id: "org_1" });
    const key = authScopedQueryKey(
      ["analyses", 1, 20, undefined, undefined] as const,
      token,
    );

    expect(matchesAuthScopedQueryKey(key, ["analyses"] as const, token)).toBe(
      true,
    );
  });

  it("rejects previous-scope and wrong-root query keys", () => {
    const currentToken = jwt({ sub: "user_1", org_id: "org_current" });
    const previousToken = jwt({ sub: "user_1", org_id: "org_previous" });
    const previousScopeKey = authScopedQueryKey(
      ["analyses", 1, 20] as const,
      previousToken,
    );
    const wrongRootKey = authScopedQueryKey(
      ["reports", "analysis-1"] as const,
      currentToken,
    );

    expect(
      matchesAuthScopedQueryKey(
        previousScopeKey,
        ["analyses"] as const,
        currentToken,
      ),
    ).toBe(false);
    expect(
      matchesAuthScopedQueryKey(
        wrongRootKey,
        ["analyses"] as const,
        currentToken,
      ),
    ).toBe(false);
  });
});

describe("matchesAuthScopedMutationKey", () => {
  it("matches mutation keys for the current auth scope and base prefix", () => {
    const token = jwt({ sub: "user_1", org_id: "org_1" });
    const previousToken = jwt({ sub: "user_1", org_id: "org_previous" });
    const key = authScopedMutationKey(
      ["billing", "checkout", "pro"] as const,
      token,
    );

    expect(matchesAuthScopedMutationKey(key, ["billing"] as const, token)).toBe(
      true,
    );
    expect(
      matchesAuthScopedMutationKey(key, ["billing"] as const, previousToken),
    ).toBe(false);
  });
});

describe("invalidateAuthScopedQueries", () => {
  it("invalidates only matching private keys for the current auth scope", () => {
    const token = jwt({ sub: "user_1", org_id: "org_1" });
    const invalidateQueries = vi.fn();
    const queryClient = { invalidateQueries };

    invalidateAuthScopedQueries(
      queryClient as never,
      ["reports", "analysis-1"],
      token,
    );

    const filters = invalidateQueries.mock.calls[0][0];
    expect(filters.queryKey).toEqual(["reports", "analysis-1"]);
    expect(
      filters.predicate({
        queryKey: authScopedQueryKey(["reports", "analysis-1"] as const, token),
      }),
    ).toBe(true);
    expect(
      filters.predicate({
        queryKey: authScopedQueryKey(
          ["reports", "analysis-1"] as const,
          jwt({ sub: "user_1", org_id: "org_2" }),
        ),
      }),
    ).toBe(false);
  });
});
