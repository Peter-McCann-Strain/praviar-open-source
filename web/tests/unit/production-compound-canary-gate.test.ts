import { describe, expect, it } from "vitest";
import { parseProductionCompoundCanaryEnvironment } from "../e2e/fixtures/production-compound-canary-gate";

const validEnvironment: NodeJS.ProcessEnv = {
  NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS: "false",
  NEXT_PUBLIC_DEMO_MODE: "false",
  PLAYWRIGHT_DEMO_MODE: "false",
  PLAYWRIGHT_PRODUCTION_API_PROBE_URL:
    "https://api.praviar.example/api/health/ready",
  PLAYWRIGHT_PRODUCTION_ALLOWED_ORIGIN: "https://app.praviar.example/",
  PLAYWRIGHT_PRODUCTION_BASE_URL: "https://app.praviar.example/",
  PLAYWRIGHT_PRODUCTION_CANDIDATE_API_PROBE_URL:
    "https://candidate-api.praviar.example/api/health/ready",
  PLAYWRIGHT_PRODUCTION_LAUNCH_COMPOUND: "tavaborole",
  PLAYWRIGHT_PRODUCTION_RELEASE_GIT_SHA: "a".repeat(40),
  PLAYWRIGHT_PRODUCTION_USER_EMAIL: "release-gate@praviar.example",
  PLAYWRIGHT_PRODUCTION_USER_PASSWORD: "protected-secret",
};

describe("production compound canary environment", () => {
  it("accepts an allowlisted origin, exact SHA, and inexpensive compound", () => {
    expect(
      parseProductionCompoundCanaryEnvironment(validEnvironment),
    ).toMatchObject({
      baseURL: "https://app.praviar.example/",
      candidateApiOrigin: "https://candidate-api.praviar.example/",
      launchCompound: "tavaborole",
      releaseGitSha: "a".repeat(40),
    });
  });

  it.each([
    "NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS",
    "NEXT_PUBLIC_DEMO_MODE",
    "PLAYWRIGHT_DEMO_MODE",
  ])("rejects %s", (name) => {
    expect(() =>
      parseProductionCompoundCanaryEnvironment({
        ...validEnvironment,
        [name]: "true",
      }),
    ).toThrow(name);
  });

  it.each([
    "http://app.praviar.example/",
    "https://localhost/",
    "https://user@app.praviar.example/",
    "https://app.praviar.example/path",
  ])("rejects unsafe target %s", (target) => {
    expect(() =>
      parseProductionCompoundCanaryEnvironment({
        ...validEnvironment,
        PLAYWRIGHT_PRODUCTION_BASE_URL: target,
      }),
    ).toThrow();
  });

  it("rejects an origin that differs from the protected allowlist", () => {
    expect(() =>
      parseProductionCompoundCanaryEnvironment({
        ...validEnvironment,
        PLAYWRIGHT_PRODUCTION_BASE_URL: "https://lookalike.praviar.example/",
      }),
    ).toThrow(/origin allowlist/u);
  });

  it.each([
    "http://api.praviar.example/api/health/ready",
    "https://api.praviar.example/api/health",
    "https://candidate---api-abc.run.app/api/health/ready",
  ])("rejects unsafe API probe %s", (probe) => {
    expect(() =>
      parseProductionCompoundCanaryEnvironment({
        ...validEnvironment,
        PLAYWRIGHT_PRODUCTION_API_PROBE_URL: probe,
      }),
    ).toThrow(/API_PROBE_URL/u);
  });

  it("requires a candidate API origin isolated from normal split traffic", () => {
    expect(() =>
      parseProductionCompoundCanaryEnvironment({
        ...validEnvironment,
        PLAYWRIGHT_PRODUCTION_CANDIDATE_API_PROBE_URL:
          "https://api.praviar.example/api/health/ready",
      }),
    ).toThrow(/isolated/u);
  });

  it.each(["aspirin", "large proprietary compound", ""])(
    "rejects unapproved compound %j",
    (compound) => {
      expect(() =>
        parseProductionCompoundCanaryEnvironment({
          ...validEnvironment,
          PLAYWRIGHT_PRODUCTION_LAUNCH_COMPOUND: compound,
        }),
      ).toThrow(/inexpensive|required/u);
    },
  );

  it.each(["abc", "A".repeat(40), "a".repeat(39), "a".repeat(41)])(
    "rejects unbound release SHA %j",
    (sha) => {
      expect(() =>
        parseProductionCompoundCanaryEnvironment({
          ...validEnvironment,
          PLAYWRIGHT_PRODUCTION_RELEASE_GIT_SHA: sha,
        }),
      ).toThrow(/exact 40-character release SHA/u);
    },
  );
});
