import { afterEach, describe, expect, it } from "vitest";
import {
  acceptAuthToken,
  authTokenMatchesIdentityBoundary,
  setCurrentAuthIdentityBoundary,
  type AuthIdentityBoundary,
} from "@/lib/auth-events";

function jwt(payload: Record<string, unknown>): string {
  const encoded = btoa(JSON.stringify(payload))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
  return `header.${encoded}.signature`;
}

const BOUNDARY: AuthIdentityBoundary = {
  userId: "user_buyer",
  sessionId: "sess_buyer",
  orgId: "org_current",
  orgRole: "org:admin",
};

describe("auth token identity binding", () => {
  afterEach(() => setCurrentAuthIdentityBoundary(null));

  it("accepts only the same Clerk v2 user, session, organization, and role", () => {
    const token = jwt({
      v: 2,
      sub: "user_buyer",
      sid: "sess_buyer",
      o: { id: "org_current", rol: "admin" },
    });
    expect(authTokenMatchesIdentityBoundary(token, BOUNDARY)).toBe(true);
  });

  it("rejects a cached token from the previously active organization", () => {
    const stale = jwt({
      v: 2,
      sub: "user_buyer",
      sid: "sess_buyer",
      o: { id: "org_previous", rol: "admin" },
    });
    setCurrentAuthIdentityBoundary(BOUNDARY);
    expect(acceptAuthToken(stale)).toBe(false);
  });

  it("requires an organization-free token at the selection boundary", () => {
    const selectionBoundary = { ...BOUNDARY, orgId: null, orgRole: null };
    const withoutOrganization = jwt({
      v: 2,
      sub: "user_buyer",
      sid: "sess_buyer",
    });
    const withOrganization = jwt({
      v: 2,
      sub: "user_buyer",
      sid: "sess_buyer",
      o: { id: "org_previous", rol: "member" },
    });

    expect(
      authTokenMatchesIdentityBoundary(withoutOrganization, selectionBoundary),
    ).toBe(true);
    expect(
      authTokenMatchesIdentityBoundary(withOrganization, selectionBoundary),
    ).toBe(false);
  });
});
