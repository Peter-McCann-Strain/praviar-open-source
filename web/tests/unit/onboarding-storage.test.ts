import { beforeEach, describe, expect, it } from "vitest";
import {
  clearLegacyOnboardingFlags,
  nonClerkOnboardingIdentity,
  onboardingStorageKey,
  onboardingStorageKeys,
  readOnboardingFlag,
  TEST_ONBOARDING_IDENTITY,
  WELCOME_MODAL_STORAGE_KEY,
  writeOnboardingFlag,
} from "@/lib/onboarding-storage";

describe("onboarding storage", () => {
  beforeEach(() => localStorage.clear());

  it("isolates completion by both user and organization", () => {
    const orgA = { userId: "user_1", orgId: "org_a" };
    const orgB = { userId: "user_1", orgId: "org_b" };
    const otherUser = { userId: "user_2", orgId: "org_a" };

    expect(writeOnboardingFlag(WELCOME_MODAL_STORAGE_KEY, orgA)).toBe(true);
    expect(readOnboardingFlag(WELCOME_MODAL_STORAGE_KEY, orgA)).toBe(true);
    expect(readOnboardingFlag(WELCOME_MODAL_STORAGE_KEY, orgB)).toBe(false);
    expect(readOnboardingFlag(WELCOME_MODAL_STORAGE_KEY, otherUser)).toBe(
      false,
    );
  });

  it("encodes identity values and refuses incomplete identities", () => {
    expect(
      onboardingStorageKey(WELCOME_MODAL_STORAGE_KEY, {
        userId: "user:1",
        orgId: "org/a",
      }),
    ).toBe("praviar_welcomed:v2:user=user%3A1:org=org%2Fa");
    expect(
      onboardingStorageKey(WELCOME_MODAL_STORAGE_KEY, {
        userId: "user_1",
        orgId: " ",
      }),
    ).toBeNull();
    expect(writeOnboardingFlag(WELCOME_MODAL_STORAGE_KEY, null)).toBe(false);
  });

  it("removes unscoped legacy flags without treating them as completion", () => {
    localStorage.setItem("praviar_welcomed", "true");
    localStorage.setItem("praviar_tour_complete", "true");

    clearLegacyOnboardingFlags();

    expect(localStorage.getItem("praviar_welcomed")).toBeNull();
    expect(localStorage.getItem("praviar_tour_complete")).toBeNull();
    expect(
      readOnboardingFlag(WELCOME_MODAL_STORAGE_KEY, TEST_ONBOARDING_IDENTITY),
    ).toBe(false);
  });

  it("uses explicit identities only for demo, dev bypass, and tests", () => {
    expect(
      nonClerkOnboardingIdentity({
        demoMode: false,
        devAuthBypass: false,
        nodeEnv: "production",
      }),
    ).toBeNull();
    expect(
      onboardingStorageKeys(
        nonClerkOnboardingIdentity({
          demoMode: false,
          devAuthBypass: false,
          nodeEnv: "test",
        }),
      ),
    ).not.toBeNull();
  });
});
