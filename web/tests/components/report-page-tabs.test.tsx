import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReportPageTabs } from "@/components/report-page/report-page-tabs";
import {
  getOverflowTabs,
  resolveReportTab,
} from "@/components/report-page/tabs";

describe("ReportPageTabs", () => {
  it("resolves product-language validity deep links to the invalidity tab", () => {
    expect(resolveReportTab("validity", getOverflowTabs(false))).toBe(
      "invalidity",
    );
    expect(resolveReportTab("summary", getOverflowTabs(false))).toBe(
      "overview",
    );
  });

  it("renders a labeled primary tablist with stable primary tab ids", () => {
    const { container } = render(
      <ReportPageTabs
        tab="overview"
        overflowTabs={getOverflowTabs(false)}
        tabCounts={{ patents: 2, evidence: 5 }}
        onTabChange={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("tablist", { name: "Report sections" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("combobox", { name: "Report section" }),
    ).toHaveValue("overview");
    const overview = screen.getByRole("tab", { name: /outcome/i });
    const patents = screen.getByRole("tab", { name: /patents, 2 records/i });

    expect(overview).toHaveAttribute("id", "tab-overview");
    expect(overview).toHaveAttribute("aria-controls", "tabpanel-overview");
    expect(patents).toHaveAttribute("id", "tab-patents");
    expect(
      screen.getByRole("tab", { name: /evidence, 5 records/i }),
    ).toHaveAttribute("id", "tab-evidence");
    expect(screen.getByText("(2)")).toHaveClass("lg:inline");
    expect(screen.getByText("(2)")).not.toHaveClass("sm:inline");
    expect(
      screen.queryByRole("tab", { name: /structures/i }),
    ).not.toBeInTheDocument();
    const tablist = screen.getByRole("tablist", { name: "Report sections" });
    expect(tablist).toHaveClass("grid", "grid-cols-5", "gap-1");
    expect(tablist).not.toHaveAttribute("tabindex");
    expect(tablist).toHaveAttribute("data-praviar-report-tabs-stable-shell");
    expect(overview).toHaveAttribute("tabindex", "0");
    expect(patents).toHaveAttribute("tabindex", "-1");
    expect(container.firstElementChild).toHaveClass(
      "scroll-mb-[calc(6.75rem+env(safe-area-inset-bottom))]",
    );
    expect(container.firstElementChild).toHaveAttribute("data-no-print");
    expect(container.querySelector("#tab-claims")).toHaveClass(
      "min-w-[6.5rem]",
      "min-h-11",
      "text-xs",
      "sm:gap-1",
      "sm:px-2",
      "lg:gap-2",
    );
    expect(container.querySelector("#tab-claims")).not.toHaveClass(
      "sm:min-h-10",
    );
    expect(container.querySelector("#tab-claims svg")).toHaveClass("h-3.5");
  });

  it("offers every report section in one compact mobile picker", () => {
    const onTabChange = vi.fn();

    render(
      <ReportPageTabs
        tab="overview"
        overflowTabs={getOverflowTabs(false)}
        tabCounts={{ claims: 12, comments: 3 }}
        onTabChange={onTabChange}
      />,
    );

    const picker = screen.getByRole("combobox", { name: "Report section" });
    expect(picker).toHaveClass("min-h-11", "w-full", "appearance-none");
    expect(
      screen.getByRole("option", { name: "Claims, 12 records" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Comments, 3 records" }),
    ).toBeInTheDocument();

    fireEvent.change(picker, { target: { value: "comments" } });
    expect(onTabChange).toHaveBeenCalledWith("comments");
  });

  it("moves secondary sections into the More menu", () => {
    const onTabChange = vi.fn();

    render(
      <ReportPageTabs
        tab="overview"
        overflowTabs={getOverflowTabs(false)}
        tabCounts={{ evidence: 5, comments: 3 }}
        onTabChange={onTabChange}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "More report sections" }),
    );

    const menu = screen.getByRole("menu", {
      name: "Secondary report sections",
    });
    expect(menu).toBeInTheDocument();
    expect(
      screen.queryByRole("menuitem", { name: /Evidence/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: /Comments 3/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: /Comments 3/ }),
    ).toHaveAttribute("id", "overflow-tab-comments");

    fireEvent.click(screen.getByRole("menuitem", { name: /Comments 3/ }));

    expect(onTabChange).toHaveBeenCalledWith("comments");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("reflects an active secondary section on the More trigger", () => {
    render(
      <ReportPageTabs
        tab="meta"
        overflowTabs={getOverflowTabs(false)}
        tabCounts={{}}
        onTabChange={vi.fn()}
      />,
    );

    const moreButton = screen.getByRole("button", {
      name: "More report sections, current secondary section Coverage & quality",
    });
    expect(moreButton).toHaveAttribute("aria-expanded", "false");
    expect(moreButton).toHaveClass("min-h-11");
    expect(moreButton).toHaveClass("sm:w-36", "lg:w-44");
    expect(moreButton).not.toHaveClass("sm:min-h-10");
    expect(document.getElementById("overflow-tab-meta")).toHaveTextContent(
      "Coverage & quality",
    );
    expect(moreButton).toHaveTextContent("Coverage & quality");
    expect(moreButton).toHaveTextContent("Coverage");
    expect(screen.getByRole("tab", { name: "Outcome" })).toHaveAttribute(
      "tabindex",
      "0",
    );
    expect(screen.getByRole("tab", { name: "Patents" })).toHaveAttribute(
      "tabindex",
      "-1",
    );

    fireEvent.click(moreButton);
    expect(
      screen.getByRole("menuitem", { name: /Coverage & quality/ }),
    ).toHaveAttribute("aria-current", "page");
    expect(
      screen.getByRole("menuitem", { name: /Coverage & quality/ }),
    ).not.toHaveAttribute("id");
  });

  it("restores focus to the More trigger when Escape closes the secondary menu", async () => {
    render(
      <ReportPageTabs
        tab="overview"
        overflowTabs={getOverflowTabs(false)}
        tabCounts={{ evidence: 5, comments: 3 }}
        onTabChange={vi.fn()}
      />,
    );

    const moreButton = screen.getByRole("button", {
      name: "More report sections",
    });
    fireEvent.click(moreButton);

    const firstMenuItem = screen.getByRole("menuitem", { name: /Comments 3/ });

    await waitFor(() => expect(firstMenuItem).toHaveFocus());
    fireEvent.keyDown(firstMenuItem, { key: "Escape" });

    await waitFor(() => expect(moreButton).toHaveFocus());
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("supports Home, End, and arrow navigation inside the secondary menu", async () => {
    render(
      <ReportPageTabs
        tab="overview"
        overflowTabs={getOverflowTabs(false)}
        tabCounts={{}}
        onTabChange={vi.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "More report sections" }),
    );

    const comments = screen.getByRole("menuitem", { name: /Comments/ });
    const coverageQuality = screen.getByRole("menuitem", {
      name: /Coverage & quality/,
    });

    await waitFor(() => expect(comments).toHaveFocus());
    fireEvent.keyDown(comments, { key: "End" });
    expect(coverageQuality).toHaveFocus();
    fireEvent.keyDown(coverageQuality, { key: "Home" });
    expect(comments).toHaveFocus();
    fireEvent.keyDown(comments, { key: "ArrowUp" });
    expect(coverageQuality).toHaveFocus();
    fireEvent.keyDown(coverageQuality, { key: "ArrowDown" });
    expect(comments).toHaveFocus();
  });

  it("keeps primary report sections stable instead of moving them after hydration", () => {
    const originalMatchMedia = window.matchMedia;
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query === "(max-width: 479px)",
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    try {
      render(
        <ReportPageTabs
          tab="claims"
          overflowTabs={getOverflowTabs(false)}
          tabCounts={{ claims: 12 }}
          onTabChange={vi.fn()}
        />,
      );

      expect(
        screen.getByRole("tab", { name: /claims, 12 records/i }),
      ).toHaveAttribute("id", "tab-claims");
      expect(
        screen.getByRole("button", { name: "More report sections" }),
      ).toHaveAttribute("data-state", "inactive");

      fireEvent.click(
        screen.getByRole("button", { name: "More report sections" }),
      );

      expect(
        screen.queryByRole("menuitem", { name: /Claims/ }),
      ).not.toBeInTheDocument();
      expect(
        screen.getByRole("menuitem", { name: /Coverage & quality/ }),
      ).toBeInTheDocument();
    } finally {
      window.matchMedia = originalMatchMedia;
    }
  });
});
