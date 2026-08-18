import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  CHECKPOINT_DECISION_ERROR_MESSAGE,
  CheckpointOverlay,
} from "@/components/analysis-detail/checkpoint-overlay";

const apiMock = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: (...args: unknown[]) => apiMock(...args),
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "token-1",
}));

function Wrapped({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("CheckpointOverlay", () => {
  beforeEach(() => {
    apiMock.mockReset();
  });

  it("requires server success before clearing blocking checkpoints", async () => {
    const onClose = vi.fn();
    apiMock.mockResolvedValueOnce({
      id: "decision-1",
      checkpoint_id: "analysis_review",
      checkpoint_type: "analysis_review",
      decision: "approve",
    });

    render(
      <Wrapped>
        <CheckpointOverlay
          analysisId="analysis-1"
          onClose={onClose}
          activeCheckpoint={{
            checkpoint_type: "analysis_review",
            context: {},
            requires_response: true,
            timeout_minutes: 60,
            step: 4,
            step_name: "analyze",
            timestamp: "2026-06-06T00:00:00Z",
          }}
        />
      </Wrapped>,
    );

    const dialog = screen.getByRole("dialog", {
      name: "Human review checkpoint",
    });
    expect(
      screen.getByRole("button", { name: "Approve & Continue" }),
    ).toHaveClass("w-full", "min-h-11");
    expect(screen.getByRole("button", { name: "Reject" })).toHaveClass(
      "w-full",
      "min-h-11",
    );
    fireEvent.keyDown(dialog, { key: "Escape" });
    fireEvent.click(dialog);
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1));
    expect(apiMock).toHaveBeenCalledWith(
      "/analyses/analysis-1/checkpoints/analysis_review/decision",
      expect.objectContaining({
        method: "POST",
        token: "token-1",
      }),
    );
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it("persists the resolved-identity attestation before starting search", async () => {
    const onClose = vi.fn();
    apiMock.mockResolvedValueOnce({
      id: "decision-identity-1",
      checkpoint_id: "run-1:identity_review:fingerprint",
      checkpoint_type: "identity_review",
      decision: "approve",
    });

    render(
      <Wrapped>
        <CheckpointOverlay
          analysisId="analysis-1"
          onClose={onClose}
          activeCheckpoint={{
            checkpoint_id: "run-1:identity_review:fingerprint",
            checkpoint_type: "identity_review",
            context: {
              identity_fingerprint: "abcdef1234567890",
              comparison: {
                outcome: "exact_match",
                submitted_value: "aspirin",
                resolved_value: "aspirin",
                detail: "Exact identity.",
              },
              resolved_identity: {
                name: "Aspirin",
                source_authority: "PubChem",
                source_record_id: "CID 2244",
                authoritative_record_present: true,
              },
              search_envelope: [],
              variant_assessments: [],
              approval_attestation:
                "I verified the resolved identity and disclosed limitations.",
            },
            requires_response: true,
            timeout_minutes: 60,
            step: 0,
            step_name: "identity_review",
            timestamp: "2026-07-26T00:00:00Z",
          }}
        />
      </Wrapped>,
    );

    fireEvent.click(
      screen.getByRole("checkbox", {
        name: /verified the resolved identity/i,
      }),
    );
    fireEvent.click(
      screen.getByRole("button", {
        name: "Approve identity & start search",
      }),
    );

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1));
    expect(apiMock).toHaveBeenCalledWith(
      "/analyses/analysis-1/checkpoints/run-1%3Aidentity_review%3Afingerprint/decision",
      expect.objectContaining({
        body: expect.stringContaining(
          "Reviewer attested to the fingerprint-bound resolved identity",
        ),
        method: "POST",
        token: "token-1",
      }),
    );
    expect(apiMock.mock.calls[0][1].body).toContain(
      '"checkpoint_type":"identity_review"',
    );
    expect(apiMock.mock.calls[0][1].body).toContain('"decision":"approve"');
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it("persists the exact report-review payload fingerprint on approval", async () => {
    const onClose = vi.fn();
    const digest = "b".repeat(64);
    apiMock.mockResolvedValueOnce({
      id: "decision-report-1",
      checkpoint_id: `run-1:report_review:${digest.slice(0, 16)}`,
      checkpoint_type: "report_review",
      decision: "approve",
    });

    render(
      <Wrapped>
        <CheckpointOverlay
          analysisId="analysis-1"
          onClose={onClose}
          activeCheckpoint={{
            checkpoint_id: `run-1:report_review:${digest.slice(0, 16)}`,
            checkpoint_type: "report_review",
            context: {
              schema_version: "report-review/v1",
              checkpoint_id: `run-1:report_review:${digest.slice(0, 16)}`,
              run_id: "run-1",
              report_id: "report-1",
              overall_risk: "clear",
              patent_count: 1,
              analysis_failure_count: 0,
              executive_summary_excerpt: "A bounded fictional report summary.",
              executive_summary_truncated: false,
              claim_ledger: {
                assertion_count: 2,
                source_span_count: 3,
                needs_review_count: 0,
                unsupported_count: 0,
                attestation_key_ids: ["key-1"],
              },
              prompt_hash_count: 4,
              review_payload_sha256: digest,
            },
            requires_response: true,
            timeout_minutes: 60,
            step: 8,
            step_name: "report_review",
            timestamp: "2026-08-12T00:00:00Z",
          }}
        />
      </Wrapped>,
    );

    fireEvent.click(
      screen.getByRole("checkbox", {
        name: /reviewed the visible draft summary/i,
      }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Approve bound report" }),
    );

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1));
    const request = apiMock.mock.calls[0][1];
    expect(request.body).toContain(
      `claim-source ledger bound to review payload SHA-256 ${digest}`,
    );
    expect(request.body).toContain(`"review_payload_sha256":"${digest}"`);
    expect(apiMock.mock.calls[0][0]).toContain(
      encodeURIComponent(`run-1:report_review:${digest.slice(0, 16)}`),
    );
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it.each([
    ["approve", /approve/i],
    ["reject", /reject/i],
  ])(
    "keeps backend failure details out of the %s checkpoint error",
    async (_decision, buttonName) => {
      const onClose = vi.fn();
      const leakedBackendMessage =
        "postgres://secret-token SELECT * FROM checkpoint_decisions";
      apiMock.mockRejectedValueOnce(new Error(leakedBackendMessage));

      render(
        <Wrapped>
          <CheckpointOverlay
            analysisId="analysis-1"
            onClose={onClose}
            activeCheckpoint={{
              checkpoint_type: "analysis_review",
              context: {},
              requires_response: true,
              timeout_minutes: 60,
              step: 4,
              step_name: "analyze",
              timestamp: "2026-06-06T00:00:00Z",
            }}
          />
        </Wrapped>,
      );

      fireEvent.click(screen.getByRole("button", { name: buttonName }));

      expect(await screen.findByRole("alert")).toHaveTextContent(
        CHECKPOINT_DECISION_ERROR_MESSAGE,
      );
      expect(onClose).not.toHaveBeenCalled();
      expect(document.body).not.toHaveTextContent(leakedBackendMessage);
    },
  );
});
