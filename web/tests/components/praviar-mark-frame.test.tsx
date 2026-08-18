import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import {
  PRAVIAR_MARK_ID,
  PRAVIAR_MARK_ON_LIGHT_OUTLINE,
} from "@/components/icons/praviar-mark";

describe("PraviarMarkFrame", () => {
  it("renders the outlined canonical mark in the shared light frame", () => {
    const { container } = render(<PraviarMarkFrame />);

    const frame = container.querySelector("[data-praviar-mark-frame='light']");
    const mark = container.querySelector(
      `svg[data-praviar-mark="${PRAVIAR_MARK_ID}"]`,
    );

    expect(frame).toBeInTheDocument();
    expect(frame).toHaveClass(
      "h-12",
      "w-12",
      "rounded-lg",
      "praviar-brand-mark-shell",
    );
    expect(mark).toBeInTheDocument();
    expect(container.querySelector("path")).toHaveAttribute(
      "stroke",
      PRAVIAR_MARK_ON_LIGHT_OUTLINE,
    );
  });

  it("can expose an accessible mark-only label when needed", () => {
    render(<PraviarMarkFrame decorative={false} label="Praviar workspace" />);

    expect(
      screen.getByRole("img", { name: "Praviar workspace" }),
    ).toBeInTheDocument();
  });

  it("uses governed optical size tokens for compact, dialog, and hero marks", () => {
    const { container } = render(
      <div>
        <PraviarMarkFrame size="xs" />
        <PraviarMarkFrame size="dialog" />
        <PraviarMarkFrame size="hero" />
      </div>,
    );

    const frames = container.querySelectorAll("[data-praviar-mark-frame]");
    const heroMark = frames[2]?.querySelector(
      `svg[data-praviar-mark="${PRAVIAR_MARK_ID}"]`,
    );

    expect(frames[0]).toHaveClass("h-9", "w-9");
    expect(frames[1]).toHaveClass("h-11", "w-11");
    expect(frames[2]).toHaveClass("h-10", "w-10", "sm:h-14", "sm:w-14");
    expect(heroMark).toHaveClass("h-8", "w-8", "sm:h-11", "sm:w-11");
  });
});
