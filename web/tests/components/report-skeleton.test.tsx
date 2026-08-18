import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReportSkeleton } from "@/components/report/report-skeleton";

describe("ReportSkeleton", () => {
  it("uses the current responsive report preview contract", () => {
    const { container } = render(<ReportSkeleton />);

    const preview = container.querySelector(
      "[data-praviar-report-preview-skeleton]",
    );
    expect(preview).toBeTruthy();
    expect(preview).toHaveClass("praviar-report-workspace", "overflow-hidden");
    expect(container.querySelector("[data-praviar-mark-frame]")).toBeTruthy();
    expect(
      container.querySelector('svg[data-praviar-mark="praviar-evidence-mark"]'),
    ).toBeTruthy();

    for (const label of [
      "Outcome loading tab",
      "Patents loading tab",
      "Claims loading tab",
      "Validity loading tab",
    ]) {
      expect(screen.getByLabelText(label)).toHaveClass("flex-1", "rounded-lg");
    }

    const classNames = Array.from(container.querySelectorAll("[class]")).map(
      (element) => element.getAttribute("class") ?? "",
    );
    const classTokens = classNames.flatMap((className) =>
      className.split(/\s+/u),
    );
    expect(classTokens).not.toContain("w-80");
    expect(container.innerHTML).not.toContain("rounded-t-md");
  });
});
