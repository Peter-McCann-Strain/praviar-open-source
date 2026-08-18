import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TEST_REPORT } from "../fixtures/report-fixture";
import { buildClaimedUseReceiptLedger } from "../fixtures/claimed-use-receipts";

const mocks = vi.hoisted(() => ({
  issue: vi.fn(),
  revoke: vi.fn(),
}));

vi.mock("@/lib/constants", () => ({
  DEMO_MODE_ENABLED: false,
}));

vi.mock("@/hooks/use-claimed-use-receipts", () => ({
  useIssueClaimedUseReceipt: vi.fn(() => ({
    error: null,
    isError: false,
    isPending: false,
    mutateAsync: mocks.issue,
  })),
  useRevokeClaimedUseReceipt: vi.fn(() => ({
    error: null,
    isError: false,
    isPending: false,
    mutateAsync: mocks.revoke,
  })),
}));

import { ClaimedUseReceiptWorkbench } from "@/components/report/claimed-use-receipt-workbench";

describe("ClaimedUseReceiptWorkbench", () => {
  const receiptState = {
    data: {
      ...buildClaimedUseReceiptLedger([]),
      current_report_id: "report-123",
      current_report_fingerprint: "a".repeat(64),
      eligible_uses: [
        {
          accused_act_index: 2,
          jurisdiction: "US",
          actor: "Example Pharma Inc.",
          start_date: "2027-01-20",
          regulatory_path: "anda" as const,
          target_product_identity: "Example 10 mg tablet",
          proposed_indication: "Treatment of example disease",
          proposed_label_use: "One tablet once daily.",
          label_carve_out_state: "partial" as const,
        },
      ],
    },
    error: null,
    isError: false,
    isLoading: false,
  };

  beforeEach(() => {
    mocks.issue.mockReset();
    mocks.issue.mockResolvedValue({});
    mocks.revoke.mockReset();
  });

  it("requires attorney affirmation while keeping evidence server-derived", async () => {
    render(
      <ClaimedUseReceiptWorkbench
        analysisId="analysis-123"
        canIssueReceipts
        canReviewFindings
        receiptState={receiptState}
        report={TEST_REPORT}
        token="token-123"
      />,
    );

    const issueButton = screen.getByRole("button", {
      name: "Issue counsel receipt",
    });
    expect(issueButton).toBeDisabled();

    expect(
      screen.queryByLabelText("Evidence references"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(
        /Governed evidence references are resolved by the server/i,
      ),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: /I am the issuing attorney/i,
      }),
    );
    expect(issueButton).toBeEnabled();
    fireEvent.click(issueButton);

    await waitFor(() => expect(mocks.issue).toHaveBeenCalledTimes(1));
    expect(mocks.issue).toHaveBeenCalledWith(
      expect.objectContaining({
        expected_report_id: "report-123",
        expected_report_fingerprint: "a".repeat(64),
        accused_act_index: 2,
        claimed_use_match: true,
        product_identity_match: true,
      }),
    );
  });

  it("does not query or expose receipt contents without counsel capability", () => {
    render(
      <ClaimedUseReceiptWorkbench
        analysisId="analysis-123"
        canIssueReceipts={false}
        canReviewFindings={false}
        receiptState={receiptState}
        report={TEST_REPORT}
        token="token-123"
      />,
    );

    expect(
      screen.getByText(
        /Attorney or administrator permission is required to inspect/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Issue counsel receipt" }),
    ).not.toBeInTheDocument();
  });

  it("states that issuance is an overlay rather than a report rewrite", () => {
    render(
      <ClaimedUseReceiptWorkbench
        analysisId="analysis-123"
        canIssueReceipts
        canReviewFindings
        receiptState={receiptState}
        report={TEST_REPORT}
        token="token-123"
      />,
    );

    expect(
      screen.getByText(/Issuance does not rewrite the certified report/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/They do not rewrite or recertify the pipeline result/i),
    ).toBeInTheDocument();
  });

  it("lets an administrator inspect the ledger without showing issuance controls", () => {
    render(
      <ClaimedUseReceiptWorkbench
        analysisId="analysis-123"
        canIssueReceipts={false}
        canReviewFindings
        receiptState={receiptState}
        report={TEST_REPORT}
        token="token-123"
      />,
    );

    expect(
      screen.getByText(
        /Issuance is restricted to a currently authorized attorney/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Issue counsel receipt" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Claimed-use receipt history" }),
    ).toBeInTheDocument();
  });
});
