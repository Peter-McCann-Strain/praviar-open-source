import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useExpandReportDetailsForPrint } from "@/hooks/use-expand-report-details-for-print";

function PrintDisclosureHarness() {
  useExpandReportDetailsForPrint();
  return (
    <div className="praviar-report-workspace">
      <details data-testid="closed">
        <summary>Closed</summary>
        <p>Hidden evidence</p>
      </details>
      <details data-testid="open" open>
        <summary>Open</summary>
        <p>Visible evidence</p>
      </details>
    </div>
  );
}

describe("useExpandReportDetailsForPrint", () => {
  it("expands closed report disclosures for print and restores their state", () => {
    const view = render(<PrintDisclosureHarness />);
    const closed = view.getByTestId("closed") as HTMLDetailsElement;
    const open = view.getByTestId("open") as HTMLDetailsElement;

    window.dispatchEvent(new Event("beforeprint"));

    expect(closed.open).toBe(true);
    expect(closed).toHaveAttribute("data-praviar-print-expanded", "true");
    expect(open.open).toBe(true);
    expect(open).not.toHaveAttribute("data-praviar-print-expanded");

    window.dispatchEvent(new Event("afterprint"));

    expect(closed.open).toBe(false);
    expect(closed).not.toHaveAttribute("data-praviar-print-expanded");
    expect(open.open).toBe(true);
  });
});
