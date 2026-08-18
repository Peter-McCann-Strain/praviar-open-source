import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ClaimedUseReceiptLedger } from "@/components/report/claimed-use-receipt-ledger";
import {
  buildClaimedUseReceipt,
  buildClaimedUseReceiptLedger,
  buildPriorClaimedUseReceipt,
  buildRevokedClaimedUseReceipt,
} from "../fixtures/claimed-use-receipts";

describe("ClaimedUseReceiptLedger", () => {
  it("shows the current signed overlay and server-derived references", () => {
    render(
      <ClaimedUseReceiptLedger
        state={{
          data: buildClaimedUseReceiptLedger(),
          isError: false,
          isLoading: false,
        }}
      />,
    );

    const ledger = screen.getByRole("region", {
      name: "Claimed-use receipt history",
    });
    expect(ledger).toHaveTextContent("Current counsel overlay");
    expect(ledger).toHaveTextContent("report-current");
    expect(ledger).toHaveTextContent("US12345678A1:grant-claims");
    expect(ledger).toHaveTextContent("source-span:label-use-17");
    expect(ledger).toHaveTextContent(
      "They do not rewrite or recertify the pipeline result",
    );
  });

  it("keeps prior and revoked records visible without presenting them as current", () => {
    render(
      <ClaimedUseReceiptLedger
        state={{
          data: buildClaimedUseReceiptLedger([
            buildPriorClaimedUseReceipt(),
            buildRevokedClaimedUseReceipt(),
          ]),
          isError: false,
          isLoading: false,
        }}
      />,
    );

    expect(
      screen.getByText(
        /No active receipt governs the current report fingerprint/i,
      ),
    ).toBeInTheDocument();
    const history = screen.getByText(
      "Review 2 prior, revoked, or flagged records",
    );
    fireEvent.click(history);

    expect(screen.getByText("Prior report")).toBeInTheDocument();
    expect(screen.getAllByText("Revoked")).toHaveLength(2);
    expect(
      screen.getByText(
        /The proposed label changed after the attorney completed review/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Current counsel overlay"),
    ).not.toBeInTheDocument();
  });

  it("expands complete history and integrity identifiers for export", () => {
    render(
      <ClaimedUseReceiptLedger
        variant="export"
        state={{
          data: buildClaimedUseReceiptLedger([
            buildClaimedUseReceipt(),
            buildPriorClaimedUseReceipt(),
            buildRevokedClaimedUseReceipt(),
          ]),
          isError: false,
          isLoading: false,
        }}
      />,
    );

    const ledger = screen.getByTestId("claimed-use-receipt-ledger-export");
    expect(ledger).toHaveTextContent("Prior and revoked records");
    expect(ledger).toHaveTextContent("Prior report");
    expect(ledger).toHaveTextContent(
      "The proposed label changed after the attorney completed review",
    );
    expect(ledger).toHaveTextContent("Receipt digest");
    expect(ledger).toHaveTextContent("Report fingerprint");
    expect(ledger.querySelector("details")).toBeNull();
  });

  it("fails closed when signed and persisted coordinates disagree", () => {
    const mismatched = buildClaimedUseReceipt();
    mismatched.receipt = {
      ...mismatched.receipt,
      report_fingerprint: "9".repeat(64),
    };

    render(
      <ClaimedUseReceiptLedger
        state={{
          data: buildClaimedUseReceiptLedger([mismatched]),
          isError: false,
          isLoading: false,
        }}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "conflicting signed and persisted coordinates",
    );
    fireEvent.click(
      screen.getByText("Review 1 prior, revoked, or flagged record"),
    );
    expect(screen.getByText("Integrity mismatch")).toBeInTheDocument();
    expect(
      screen.queryByText("Current counsel overlay"),
    ).not.toBeInTheDocument();
  });

  it("does not turn loading or error states into a false empty ledger", () => {
    const { rerender } = render(
      <ClaimedUseReceiptLedger state={{ isError: false, isLoading: true }} />,
    );

    expect(screen.getByRole("status")).toHaveTextContent(
      "do not infer that no counsel receipts exist",
    );

    rerender(
      <ClaimedUseReceiptLedger
        state={{
          error: new Error("network failed"),
          isError: true,
          isLoading: false,
        }}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Do not treat this state as evidence that no receipt exists",
    );
    expect(
      screen.queryByText(/No claimed-use counsel receipt is present/i),
    ).not.toBeInTheDocument();
  });

  it("uses mobile-safe semantic controls and breakable signed identifiers", () => {
    render(
      <ClaimedUseReceiptLedger
        state={{
          data: buildClaimedUseReceiptLedger([
            buildClaimedUseReceipt(),
            buildPriorClaimedUseReceipt(),
          ]),
          isError: false,
          isLoading: false,
        }}
      />,
    );

    const ledger = screen.getByRole("region", {
      name: "Claimed-use receipt history",
    });
    const stateSummary = within(ledger).getByRole("group", {
      name: "Claimed-use receipt state summary",
    });
    expect(stateSummary).toHaveClass("grid-cols-3");
    const historySummary = screen.getByText(
      "Review 1 prior, revoked, or flagged record",
    );
    expect(historySummary.tagName).toBe("SUMMARY");
    expect(historySummary).toHaveClass("min-h-11");
    expect(within(ledger).getByText("report-current").className).toContain(
      "break-all",
    );
  });
});
