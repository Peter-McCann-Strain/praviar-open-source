import { describe, expect, it } from "vitest";
import {
  CRITICAL_STAGING_JOURNEY_ACTIONS,
  classifyStagingAnalysisStatus,
  createCriticalJourneyLedger,
  parseStagingJourneyEnvironment,
} from "../e2e/fixtures/staging-journey-gate";

const validEnvironment = {
  PLAYWRIGHT_STAGING_ALLOWED_ORIGIN: "https://staging.praviar.example",
  PLAYWRIGHT_STAGING_BASE_URL: "https://staging.praviar.example",
  PLAYWRIGHT_STAGING_LAUNCH_COMPOUND: "tavaborole",
  PLAYWRIGHT_STAGING_SHARE_RECIPIENT_EMAIL: "recipient@example.test",
  PLAYWRIGHT_STAGING_STRIPE_BOUNDARY_MODE: "mock-return",
  PLAYWRIGHT_STAGING_USER_EMAIL: "release-gate@example.test",
  PLAYWRIGHT_STAGING_USER_PASSWORD: "not-a-real-secret",
};

describe("staging critical-journey gate", () => {
  it.each(Object.keys(validEnvironment))(
    "fails closed when %s is missing",
    (name) => {
      const environment = { ...validEnvironment };
      delete environment[name as keyof typeof environment];
      expect(() => parseStagingJourneyEnvironment(environment)).toThrow(name);
    },
  );

  it.each([
    "NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS",
    "NEXT_PUBLIC_DEMO_MODE",
    "PLAYWRIGHT_DEMO_MODE",
  ])("rejects the non-production runtime flag %s", (flag) => {
    expect(() =>
      parseStagingJourneyEnvironment({ ...validEnvironment, [flag]: "true" }),
    ).toThrow(`${flag}=true is forbidden`);
  });

  it("rejects localhost, plaintext, and non-explicit Stripe modes", () => {
    expect(() =>
      parseStagingJourneyEnvironment({
        ...validEnvironment,
        PLAYWRIGHT_STAGING_BASE_URL: "http://localhost:3100",
      }),
    ).toThrow("must use https");
    expect(() =>
      parseStagingJourneyEnvironment({
        ...validEnvironment,
        PLAYWRIGHT_STAGING_BASE_URL: "https://localhost:3100",
      }),
    ).toThrow("remote production-shaped deployment");
    expect(() =>
      parseStagingJourneyEnvironment({
        ...validEnvironment,
        PLAYWRIGHT_STAGING_STRIPE_BOUNDARY_MODE: "live",
      }),
    ).toThrow("must be mock-return");
  });

  it("requires an approved inexpensive ground-truthed compound", () => {
    expect(() =>
      parseStagingJourneyEnvironment({
        ...validEnvironment,
        PLAYWRIGHT_STAGING_LAUNCH_COMPOUND: "client-secret-compound",
      }),
    ).toThrow("approved inexpensive, ground-truthed release-gate compounds");
  });

  it("rejects caller-controlled origins and URL data that could receive credentials", () => {
    expect(() =>
      parseStagingJourneyEnvironment({
        ...validEnvironment,
        PLAYWRIGHT_STAGING_BASE_URL: "https://attacker.example",
      }),
    ).toThrow("protected staging origin allowlist");
    expect(() =>
      parseStagingJourneyEnvironment({
        ...validEnvironment,
        PLAYWRIGHT_STAGING_BASE_URL:
          "https://staging.praviar.example/path?capture=true",
      }),
    ).toThrow("without a path, query, or fragment");
    expect(() =>
      parseStagingJourneyEnvironment({
        ...validEnvironment,
        PLAYWRIGHT_STAGING_BASE_URL:
          "https://user:password@staging.praviar.example",
      }),
    ).toThrow("credential-free origin");
  });

  it("fails if even one critical action was not executed", () => {
    for (const omitted of CRITICAL_STAGING_JOURNEY_ACTIONS) {
      const ledger = createCriticalJourneyLedger();
      for (const action of CRITICAL_STAGING_JOURNEY_ACTIONS) {
        if (action !== omitted) ledger.mark(action);
      }
      expect(() => ledger.assertComplete()).toThrow(omitted);
    }
  });

  it("accepts every action exactly once and rejects duplicate receipts", () => {
    const ledger = createCriticalJourneyLedger();
    for (const action of CRITICAL_STAGING_JOURNEY_ACTIONS) ledger.mark(action);
    expect(() => ledger.assertComplete()).not.toThrow();
    expect(ledger.snapshot()).toEqual(CRITICAL_STAGING_JOURNEY_ACTIONS);
    expect(() => ledger.mark("sign_in")).toThrow("recorded twice");
  });

  it("classifies a newly completed analysis as report-ready", () => {
    expect(classifyStagingAnalysisStatus("completed")).toBe("complete");
  });

  it.each(["pending", "running"])(
    "continues polling a newly launched analysis in %s",
    (status) => {
      expect(classifyStagingAnalysisStatus(status)).toBe("wait");
    },
  );

  it.each(["failed", "cancelled", "deleted"])(
    "fails immediately when the newly launched analysis reaches %s",
    (status) => {
      expect(() => classifyStagingAnalysisStatus(status)).toThrow(
        `terminal status ${status}`,
      );
    },
  );

  it("rejects malformed or unknown analysis statuses", () => {
    expect(() => classifyStagingAnalysisStatus("queued")).toThrow(
      "unsupported status queued",
    );
    expect(() => classifyStagingAnalysisStatus(null)).toThrow(
      "unsupported status invalid",
    );
  });
});
