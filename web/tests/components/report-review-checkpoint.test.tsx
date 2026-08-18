import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReportReviewCheckpoint } from "@/components/pipeline/report-review-checkpoint";

const DIGEST = "a".repeat(64);
const REPORT_CONTEXT: Record<string, unknown> = {
  schema_version: "report-review/v1",
  checkpoint_id: `run-1:report_review:${DIGEST.slice(0, 16)}`,
  run_id: "run-1",
  report_id: "report-1",
  overall_risk: "medium",
  patent_count: 7,
  analysis_failure_count: 1,
  executive_summary_excerpt:
    "The fictional Example Molecule Alpha landscape contains one family requiring counsel review.",
  executive_summary_truncated: true,
  claim_ledger: {
    assertion_count: 18,
    source_span_count: 24,
    needs_review_count: 2,
    unsupported_count: 0,
    attestation_key_ids: ["evidence-key-2026-01"],
  },
  prompt_hash_count: 8,
  review_payload_sha256: DIGEST,
};

describe("ReportReviewCheckpoint", () => {
  it("shows the bounded draft, risk, ledger, and fingerprint before approval", () => {
    render(
      <ReportReviewCheckpoint
        data={REPORT_CONTEXT}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Review the bounded report draft" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("medium risk", { exact: false }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Example Molecule Alpha landscape/),
    ).toBeInTheDocument();
    expect(screen.getByText("18")).toBeInTheDocument();
    expect(screen.getByText("24")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText(/8 prompt hashes bound/)).toBeInTheDocument();
    expect(screen.getByText(/SHA-256 a{16}/)).toBeInTheDocument();
    expect(screen.getByText(/bounded excerpt/)).toBeInTheDocument();
  });

  it("requires explicit attestation before approving the bound payload", () => {
    const onApprove = vi.fn();
    render(
      <ReportReviewCheckpoint
        data={REPORT_CONTEXT}
        onApprove={onApprove}
        onReject={vi.fn()}
      />,
    );

    const approve = screen.getByRole("button", {
      name: "Approve bound report",
    });
    expect(approve).toBeDisabled();

    fireEvent.click(
      screen.getByRole("checkbox", {
        name: /reviewed the visible draft summary/i,
      }),
    );
    expect(approve).toBeEnabled();
    fireEvent.click(approve);
    expect(onApprove).toHaveBeenCalledTimes(1);
  });

  it("uses Unicode code points for the shared 1,200-character boundary", () => {
    render(
      <ReportReviewCheckpoint
        data={{
          ...REPORT_CONTEXT,
          executive_summary_excerpt: "😀".repeat(1_200),
          executive_summary_truncated: false,
        }}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />,
    );

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Approve bound report" }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: /reviewed the visible draft summary/i,
      }),
    );
    expect(
      screen.getByRole("button", { name: "Approve bound report" }),
    ).toBeEnabled();
  });

  it.each([
    ["missing digest", { review_payload_sha256: "" }],
    ["missing run ID", { run_id: "" }],
    ["missing checkpoint ID", { checkpoint_id: "" }],
    [
      "mismatched checkpoint ID",
      { checkpoint_id: "run-1:report_review:bbbbbbbbbbbbbbbb" },
    ],
    [
      "unsupported claim",
      {
        claim_ledger: {
          ...(REPORT_CONTEXT.claim_ledger as object),
          unsupported_count: 1,
        },
      },
    ],
    ["oversized excerpt", { executive_summary_excerpt: "x".repeat(1_201) }],
  ])("fails closed for a %s", (_label, override) => {
    render(
      <ReportReviewCheckpoint
        data={{ ...REPORT_CONTEXT, ...override }}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "failed integrity validation",
    );
    expect(
      screen.getByRole("button", { name: "Approve bound report" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reject report" })).toBeEnabled();
  });
});
