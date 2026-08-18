import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { createMotionMock } from "../helpers/mock-motion";

vi.mock("motion/react", () => createMotionMock());

import { EvidenceCard } from "@/components/report/evidence-card";

describe("EvidenceCard", () => {
  it("renders summary text", () => {
    render(
      <EvidenceCard summary="Claim 1: MET with 92% confidence" status="met">
        <p>Detail content</p>
      </EvidenceCard>,
    );
    expect(
      screen.getByText("Claim 1: MET with 92% confidence"),
    ).toBeInTheDocument();
  });

  it("shows status label", () => {
    render(
      <EvidenceCard summary="Test" status="met">
        <p>Detail</p>
      </EvidenceCard>,
    );
    expect(screen.getByText("Met (Risk)")).toBeInTheDocument();
  });

  it("shows Not Met (Safe) for not_met status", () => {
    render(
      <EvidenceCard summary="Test" status="not_met">
        <p>Detail</p>
      </EvidenceCard>,
    );
    expect(screen.getByText("Not Met (Safe)")).toBeInTheDocument();
  });

  it("shows confidence percentage", () => {
    render(
      <EvidenceCard summary="Test" status="met" confidence={0.92}>
        <p>Detail</p>
      </EvidenceCard>,
    );
    expect(screen.getByText("92%")).toBeInTheDocument();
  });

  it("starts collapsed by default", () => {
    render(
      <EvidenceCard summary="Test" status="met">
        <p>Hidden detail</p>
      </EvidenceCard>,
    );
    // Detail content should not be visible initially
    // The button should show collapsed state
    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("expands on click to show children", () => {
    render(
      <EvidenceCard summary="Test" status="met">
        <p>Detail content here</p>
      </EvidenceCard>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Detail content here")).toBeInTheDocument();
  });

  it("starts expanded when defaultExpanded is true", () => {
    render(
      <EvidenceCard summary="Test" status="met" defaultExpanded>
        <p>Visible detail</p>
      </EvidenceCard>,
    );
    expect(screen.getByRole("button")).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Visible detail")).toBeInTheDocument();
  });
});
