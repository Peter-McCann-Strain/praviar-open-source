import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MarketingNav } from "@/components/marketing/marketing-nav";
import {
  PRAVIAR_MARK_ID,
  PRAVIAR_MARK_TILE_PATH,
} from "@/components/icons/praviar-mark";
import { PUBLIC_PRIMARY_ACTION } from "@/marketing/public-readiness";

const currentPathname = "/sample-reports";

vi.mock("next/navigation", () => ({
  usePathname: () => currentPathname,
}));

describe("MarketingNav", () => {
  it("exposes the canonical Praviar brand link to assistive technology", () => {
    const { container } = render(<MarketingNav />);

    expect(screen.getByRole("link", { name: "Praviar home" })).toHaveAttribute(
      "href",
      "/",
    );
    expect(screen.getByRole("link", { name: "Praviar home" })).toHaveAttribute(
      "data-praviar-brand-lockup",
    );
    expect(
      container.querySelector('svg[data-praviar-mark="praviar-evidence-mark"]'),
    ).toBeInTheDocument();
    expect(
      container.querySelector("[data-praviar-lockup-tagline]"),
    ).not.toBeInTheDocument();
  });

  it("keeps the supplied evidence mark geometry in the marketing lockup", () => {
    render(<MarketingNav />);

    const homeLink = screen.getByRole("link", { name: "Praviar home" });
    const mark = homeLink.querySelector(
      `svg[data-praviar-mark="${PRAVIAR_MARK_ID}"]`,
    );

    expect(mark).toBeInTheDocument();
    expect(mark?.querySelector("path")).toHaveAttribute(
      "d",
      PRAVIAR_MARK_TILE_PATH,
    );
    expect(homeLink.querySelector("circle")).not.toBeInTheDocument();
    expect(homeLink.querySelector("line")).not.toBeInTheDocument();
  });

  it("announces the active desktop page", () => {
    const { container } = render(<MarketingNav />);
    const header = container.querySelector("header");

    expect(header).toHaveClass("h-14", "min-h-14");

    expect(screen.getByRole("link", { name: "Product" })).toHaveAttribute(
      "href",
      "/demo",
    );
    expect(screen.getByRole("link", { name: "Product" })).toHaveClass(
      "min-w-11",
      "px-2",
    );
    expect(
      screen.getByRole("link", { name: "Sample Dossier" }),
    ).toHaveAttribute("aria-current", "page");
    expect(container.querySelector('nav[aria-label="Primary"]')).toHaveClass(
      "hidden",
      "lg:flex",
    );
    expect(screen.getByRole("button", { name: "Open menu" })).toHaveClass(
      "lg:hidden",
    );
  });

  it("exposes an opaque modal mobile sheet and locks document scrolling", () => {
    render(<MarketingNav />);

    const menuButton = screen.getByRole("button", { name: "Open menu" });
    expect(menuButton).toHaveAttribute("aria-expanded", "false");
    expect(menuButton).toHaveAttribute("aria-controls");

    fireEvent.click(menuButton);

    const closeButton = screen.getByRole("button", { name: "Close menu" });
    const controlledId = closeButton.getAttribute("aria-controls");
    expect(closeButton).toHaveAttribute("aria-expanded", "true");
    expect(controlledId).toBeTruthy();
    expect(document.getElementById(controlledId ?? "")).toBeInTheDocument();
    const sheet = screen.getByRole("dialog", { name: "Primary navigation" });
    expect(sheet).toHaveClass(
      "fixed",
      "top-14",
      "overflow-y-auto",
      "bg-[var(--bg-base)]",
    );
    expect(
      screen.getByTestId("marketing-mobile-menu-scrim"),
    ).toBeInTheDocument();
    expect(document.body.style.overflow).toBe("hidden");
    expect(
      within(sheet).getByRole("link", { name: "Product" }),
    ).toHaveAttribute("href", "/demo");
    expect(
      within(sheet).getByRole("link", { name: "Sample Dossier" }),
    ).toHaveAttribute("aria-current", "page");
    expect(
      within(sheet).getByRole("link", {
        name: PUBLIC_PRIMARY_ACTION.label,
      }),
    ).toHaveAttribute("href", PUBLIC_PRIMARY_ACTION.href);
  });

  it("traps focus in the mobile sheet and restores it after Escape", async () => {
    render(<MarketingNav />);

    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));

    const closeButton = screen.getByRole("button", { name: "Close menu" });
    const sheet = screen.getByRole("dialog", { name: "Primary navigation" });
    const firstMobileLink = within(sheet).getByRole("link", {
      name: "Product",
    });
    const finalMobileLink = within(sheet).getByRole("link", {
      name: PUBLIC_PRIMARY_ACTION.label,
    });

    expect(firstMobileLink).toHaveFocus();

    finalMobileLink.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(closeButton).toHaveFocus();

    closeButton.focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(finalMobileLink).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.getByRole("button", { name: "Open menu" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(
      screen.queryByRole("dialog", { name: "Primary navigation" }),
    ).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe("");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Open menu" })).toHaveFocus(),
    );
  });
});
