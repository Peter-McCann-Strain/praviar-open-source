// k6 load test on the real auth path — W6-D exit criterion.
//
// Replaces the existing locustfile.py path that authenticates with `dev-token`
// (per 02-production-readiness.md, the load test currently bypasses real auth
// so capacity is unmeasured).
//
// This test:
//   1. Authenticates as 5 simulated orgs with real Clerk JWTs (provided via env).
//   2. Saturates POST /api/v1/analyses at 100 concurrent VUs for 5 minutes.
//   3. Asserts SLOs from 10-gcp-architecture.md §8:
//        - p95 latency on GET /api/v1/analyses < 800ms
//        - error rate < 0.5%
//        - 99.5% availability
//
// Run:
//   k6 run \
//     --env API_URL=https://api.example.invalid \
//     --env ORG_TOKEN_1=... \
//     --env ORG_TOKEN_2=... \
//     --env ORG_TOKEN_3=... \
//     --env ORG_TOKEN_4=... \
//     --env ORG_TOKEN_5=... \
//     api/load_tests/k6_authenticated.js
//
// Replace the reserved example origin with the deployment's verified API
// origin. Per the load-test contract: pass under 100 concurrent users across
// five organisations.

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const errorRate = new Rate("api_errors");
const analysisCreateDuration = new Trend("analysis_create_duration_ms");
const analysisListDuration = new Trend("analysis_list_duration_ms");

const API_URL = __ENV.API_URL || "http://localhost:8000";
const ORG_TOKENS = [
  __ENV.ORG_TOKEN_1,
  __ENV.ORG_TOKEN_2,
  __ENV.ORG_TOKEN_3,
  __ENV.ORG_TOKEN_4,
  __ENV.ORG_TOKEN_5,
].filter((t) => t && t.length > 0);

if (ORG_TOKENS.length === 0) {
  throw new Error(
    "No ORG_TOKEN_N env vars provided — at least one Clerk JWT is required. " +
      "Get one via: clerk dashboard → sign in as test user → copy session token.",
  );
}

const SAMPLE_COMPOUNDS = [
  "CC(=O)Oc1ccccc1C(=O)O", // aspirin
  "CN1CCN(CC1)c1nc(N)c2cc(OC)c(OC)cc2n1", // imatinib core
  "CC(C)Cc1ccc(cc1)[C@@H](C)C(=O)O", // ibuprofen
  "Nc1nc2c(ncn2[C@@H]2C[C@H](O)[C@@H](CO)O2)c(=O)[nH]1", // acyclovir
  "Cc1cnc(N[C@@H](Cc2ccccc2)C(=O)O)c(N)c1", // representative
];

export const options = {
  scenarios: {
    saturation_5min: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 25 }, // warm-up
        { duration: "1m", target: 100 }, // ramp to 100 VUs
        { duration: "3m", target: 100 }, // hold for 3 min
        { duration: "30s", target: 0 }, // ramp down
      ],
      gracefulRampDown: "30s",
    },
  },
  thresholds: {
    // SLO: p95 < 800ms on GET /api/v1/analyses (10-gcp-architecture.md §8).
    analysis_list_duration_ms: ["p(95)<800"],
    // Loose threshold on POST (pipeline triggers are slower).
    analysis_create_duration_ms: ["p(95)<3000"],
    // SLO: 99.5% availability => error rate < 0.5%.
    api_errors: ["rate<0.005"],
    // Built-in HTTP fail rate < 1% to surface infrastructure outages.
    http_req_failed: ["rate<0.01"],
  },
};

function authHeaders() {
  // Each VU rotates through the 5 org tokens to simulate cross-tenant load.
  const token = ORG_TOKENS[__VU % ORG_TOKENS.length];
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

export default function () {
  const headers = authHeaders();

  // ── 1. Read: list recent analyses (cheap path, exercises RLS + Postgres) ──
  const listResp = http.get(`${API_URL}/api/v1/analyses?page=1&page_size=20`, {
    headers,
    tags: { name: "list_analyses" },
  });
  analysisListDuration.add(listResp.timings.duration);
  errorRate.add(listResp.status >= 400);
  check(listResp, {
    "GET /analyses status 200": (r) => r.status === 200,
    "GET /analyses returns items array": (r) => {
      try {
        return Array.isArray(r.json("items"));
      } catch {
        return false;
      }
    },
  });

  sleep(0.5);

  // ── 2. Write: create an analysis (heavier path, triggers Cloud Tasks) ──
  // Note: real pipeline runs are slow; we exercise the API + queue dispatch only.
  const compound =
    SAMPLE_COMPOUNDS[Math.floor(Math.random() * SAMPLE_COMPOUNDS.length)];
  const createResp = http.post(
    `${API_URL}/api/v1/analyses`,
    JSON.stringify({
      compound_smiles: compound,
      jurisdictions: ["US", "EP"],
      tier: "triage",
    }),
    {
      headers,
      tags: { name: "create_analysis" },
    },
  );
  analysisCreateDuration.add(createResp.timings.duration);
  errorRate.add(createResp.status >= 400);
  check(createResp, {
    "POST /analyses status 201 or 202": (r) =>
      r.status === 201 || r.status === 202,
    "POST /analyses returns analysis id": (r) => {
      try {
        return Boolean(r.json("id"));
      } catch {
        return false;
      }
    },
  });

  sleep(1.0);
}

export function handleSummary(data) {
  return {
    stdout: JSON.stringify(
      {
        slo_results: {
          p95_list_ms: data.metrics.analysis_list_duration_ms.values["p(95)"],
          p95_create_ms:
            data.metrics.analysis_create_duration_ms.values["p(95)"],
          error_rate: data.metrics.api_errors.values.rate,
          total_requests: data.metrics.http_reqs.values.count,
        },
      },
      null,
      2,
    ),
  };
}
