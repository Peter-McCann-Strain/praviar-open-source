import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/marketing/page-event-beacon", () => ({
  PageEventBeacon: () => null,
}));

import MethodologyPage from "@/app/(marketing)/methodology/page";

describe("methodology public claims", () => {
  it("states the limits of internal checks and keeps actions informational", () => {
    const { container } = render(<MethodologyPage />);

    expect(
      screen.getByText(/These are internal controls, not external validation/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/candidate patent families can be prioritised/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/working open-source research system/i),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "Open the fictional sample" })[0],
    ).toHaveAttribute("href", "/sample-reports/example-molecule-alpha");
    expect(
      screen.getByRole("link", { name: "Review current assurance status" }),
    ).toHaveAttribute("href", "/trust#assurance-heading");

    for (const link of Array.from(container.querySelectorAll("a"))) {
      expect(link.getAttribute("href") ?? "").not.toMatch(
        /(?:sign-up|billing|checkout|pricing)/i,
      );
    }
  });

  it("opens the first mobile pipeline chapter by default", () => {
    render(<MethodologyPage />);

    const firstMobileChapter = screen
      .getAllByText("Define the matter")
      .map((element) => element.closest("details"))
      .find((element): element is HTMLDetailsElement => element !== null);
    const secondMobileChapter = screen
      .getAllByText("Reduce the noise")
      .map((element) => element.closest("details"))
      .find((element): element is HTMLDetailsElement => element !== null);

    expect(firstMobileChapter).toHaveAttribute("open");
    expect(secondMobileChapter).not.toHaveAttribute("open");
  });
});
