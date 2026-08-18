import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PraviarLockup } from "@/components/brand/praviar-lockup";
import {
  PRAVIAR_MARK_ID,
  PRAVIAR_MARK_ON_LIGHT_OUTLINE,
} from "@/components/icons/praviar-mark";

describe("PraviarLockup", () => {
  it("renders the canonical mark and wordmark as one reusable lockup", () => {
    const { container } = render(
      <PraviarLockup size="marketing" tagline="FTO Screening" />,
    );

    expect(
      container.querySelector(`svg[data-praviar-mark="${PRAVIAR_MARK_ID}"]`),
    ).toBeInTheDocument();
    expect(
      container.querySelector("[data-praviar-wordmark]"),
    ).toHaveTextContent("Praviar");
    expect(
      container.querySelector("[data-praviar-lockup-tagline]"),
    ).toHaveTextContent("FTO Screening");
    expect(screen.getByText("Praviar")).toBeInTheDocument();
    expect(screen.getByText("FTO Screening")).toBeInTheDocument();
    expect(screen.getByText("Praviar")).not.toHaveAttribute(
      "aria-hidden",
      "true",
    );
    expect(screen.getByText("FTO Screening")).not.toHaveAttribute(
      "aria-hidden",
      "true",
    );
    expect(container.querySelector("path")).toHaveAttribute(
      "stroke",
      PRAVIAR_MARK_ON_LIGHT_OUTLINE,
    );
  });

  it("can collapse to mark-only without leaving duplicate wordmark text", () => {
    render(<PraviarLockup size="sidebar" showWordmark={false} />);

    expect(screen.getByRole("img", { name: "Praviar" })).toBeInTheDocument();
    expect(screen.queryByText("Praviar")).not.toBeInTheDocument();
  });

  it("can mark collapsed lockup usage as decorative inside a labelled parent", () => {
    const { container } = render(
      <a href="/dashboard" aria-label="Praviar dashboard">
        <PraviarLockup size="sidebar" showWordmark={false} decorative />
      </a>,
    );

    expect(
      screen.getByRole("link", { name: "Praviar dashboard" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("img", { name: "Praviar" }),
    ).not.toBeInTheDocument();
    expect(
      container.querySelector("[data-praviar-lockup='canonical']"),
    ).toHaveAttribute("aria-hidden", "true");
  });

  it("uses the approved dark-surface treatment for app navigation", () => {
    const { container } = render(
      <PraviarLockup size="sidebar" surface="dark" />,
    );

    const svg = container.querySelector(
      `svg[data-praviar-mark="${PRAVIAR_MARK_ID}"]`,
    );

    expect(svg).toBeInTheDocument();
    expect(svg).toHaveAttribute("viewBox", "0 0 230 230");
    expect(container.firstElementChild).toHaveClass("gap-3");
    expect(
      container.querySelector(".praviar-lockup-mark-shell"),
    ).not.toHaveClass("praviar-brand-mark-shell");
    expect(
      container.querySelector(".praviar-lockup-mark-shell"),
    ).not.toHaveClass("praviar-brand-mark-shell-dark");
  });
});
