import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MarketingSiteShell } from "@/components/marketing/site-shell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

describe("MarketingSiteShell", () => {
  it("keeps the mobile footer compact and uses the stronger marketing label", () => {
    render(
      <MarketingSiteShell>
        <p>Page content</p>
      </MarketingSiteShell>,
    );

    const footer = screen.getByRole("contentinfo");
    expect(footer).toHaveAttribute("data-marketing-footer");
    expect(footer).toHaveClass("px-4", "py-8", "sm:py-12");

    const exploreHeading = within(footer).getByRole("heading", {
      name: "Explore",
    });
    const companyHeading = within(footer).getByRole("heading", {
      name: "Company",
    });

    expect(exploreHeading).toHaveClass("type-marketing-label");
    expect(companyHeading).toHaveClass("type-marketing-label");
    expect(exploreHeading.parentElement?.parentElement).toHaveClass(
      "grid-cols-2",
    );
  });
});
