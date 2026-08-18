import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TrustPageContent } from "@/components/marketing/trust-page";

describe("TrustPageContent", () => {
  it("renders implemented product controls beside explicit assurance limits", () => {
    render(<TrustPageContent />);

    expect(
      screen.getByRole("heading", {
        name: "Know what Praviar can protect and prove before you use it.",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Keep each workspace separate"),
    ).toBeInTheDocument();
    expect(screen.getByText("Trace the evidence")).toBeInTheDocument();
    expect(screen.getByText("Record the review")).toBeInTheDocument();
    expect(
      screen.getByText(/research-preview portfolio project/i),
    ).toBeInTheDocument();
    expect(screen.getByTestId("trust-control-visual")).toHaveTextContent(
      "The work stays visible",
    );
    expect(screen.getByTestId("trust-boundary-artifact")).toHaveTextContent(
      "Qualified counsel review",
    );
    expect(screen.getByTestId("trust-boundary-artifact")).toHaveClass(
      "praviar-ink-frame",
    );
    expect(
      screen.getAllByRole("link", { name: /review the methodology/i })[0],
    ).toHaveAttribute("href", "/methodology");
    expect(
      screen.getByRole("link", { name: /open the fictional sample/i }),
    ).toHaveAttribute("href", "/sample-reports/example-molecule-alpha");
    expect(screen.getAllByText("Code capability only").length).toBeGreaterThan(
      0,
    );
    expect(
      screen.getAllByText(/not an offered enterprise service/i).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("Repository policy published").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/private GitHub security-advisory reporting path/i)
        .length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/SOC 2 certified/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Provider training, retention/i),
    ).toBeInTheDocument();
  });

  it("keeps public trust copy inside the customer-claims boundaries", () => {
    const { container } = render(<TrustPageContent />);
    const text = container.textContent ?? "";

    expect(text).toMatch(/does not issue a legal clearance opinion/i);
    expect(text).toMatch(/identified deployment operator/i);
    expect(text).not.toMatch(/\bworld[- ]class\b/i);
    expect(text).not.toMatch(/\bguarantee(?:d|s)?\b/i);
    expect(text).not.toMatch(/Praviar is SOC 2 certified/i);
    expect(text).not.toMatch(/\bproduction[- ]ready\b/i);
    expect(text).not.toMatch(/(?:guaranteed|included|published) SLA/i);
    expect(text).not.toMatch(/hosted checkout/i);
    expect(text).not.toMatch(/manage billing/i);
    expect(container.querySelectorAll('a[href^="mailto:"]')).toHaveLength(0);

    for (const link of Array.from(container.querySelectorAll("a"))) {
      expect(link.getAttribute("href") ?? "").not.toMatch(
        /(?:sign-up|billing|checkout)/i,
      );
    }
  });

  it("gives each mobile assurance group an accessible name", () => {
    const { container } = render(<TrustPageContent />);
    const groups = Array.from(
      container.querySelectorAll("details[data-assurance-group]"),
    );

    expect(groups).toHaveLength(3);
    for (const group of groups) {
      expect(group).toHaveAccessibleName();
      expect(group).toHaveTextContent(/records/i);
    }
  });
});
