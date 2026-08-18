import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ReportSectionContextStrip } from "@/components/report-page/report-section-context-strip";

describe("ReportSectionContextStrip", () => {
  it("shows active section context, precise evidence counts, guardrail, search, and AI action", () => {
    const onAskAi = vi.fn();
    const onSearch = vi.fn();

    render(
      <ReportSectionContextStrip
        tab="patents"
        tabCounts={{ patents: 5, claims: 18, drawings: 2 }}
        hasReasoningTraces={false}
        onAskAi={onAskAi}
        onSearch={onSearch}
      />,
    );

    expect(
      screen.getByRole("region", { name: "Report section context" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Report section context" }),
    ).toHaveAttribute("data-no-print");
    expect(screen.getByText("Current section")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Patents" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Material patents, claim-level risk/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Review focus")).toBeInTheDocument();
    expect(
      screen.getByText(/Claim evidence, active blockers, expiry/i),
    ).toBeInTheDocument();
    expect(screen.getByText("5 records")).toBeInTheDocument();
    expect(screen.getByText("18 analyzed")).toBeInTheDocument();
    expect(screen.getByText("2 extracted")).toBeInTheDocument();
    expect(screen.getByText("Counsel review required")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Decision support only; verify before commercial reliance.",
      ),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", {
        name: "AI-assisted section critique: patents evidence",
      }),
    );
    expect(onAskAi).toHaveBeenCalledWith(
      expect.objectContaining({
        intent: "section",
        title: "Patents section",
        description: expect.stringContaining("Material patents"),
        actionLabel: "Check section gaps",
        prompt: expect.stringContaining(
          "Critique the Patents section of this FTO report for gaps",
        ),
        metadata: expect.arrayContaining([
          { label: "Patents", value: "5 records" },
          { label: "Claims", value: "18 analyzed" },
          { label: "Structures", value: "2 extracted" },
          {
            label: "Review focus",
            value:
              "Claim evidence, active blockers, expiry, legal status, and family risk.",
          },
          { label: "Grounding", value: "Report packet only" },
          { label: "Reliance", value: "Counsel review required" },
        ]),
      }),
    );
    expect(onAskAi.mock.calls[0][0].prompt).toContain(
      "call out unsupported or missing evidence",
    );

    fireEvent.click(screen.getByRole("button", { name: "Search evidence" }));
    expect(onSearch).toHaveBeenCalledTimes(1);
  });

  it("labels secondary sections without relying on source readiness", () => {
    render(
      <ReportSectionContextStrip
        tab="meta"
        tabCounts={{ patents: 0, claims: 0, drawings: 0 }}
        hasReasoningTraces={false}
        onSearch={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Coverage & quality" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Source coverage, evidence quality/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Source coverage, verification checks/i),
    ).toBeInTheDocument();
    expect(screen.getByText("0 records")).toBeInTheDocument();
  });

  it("gives the Evidence section a source-workbench label without duplicated wording", () => {
    const onAskAi = vi.fn();

    render(
      <ReportSectionContextStrip
        tab="evidence"
        tabCounts={{ patents: 5, claims: 18, drawings: 2 }}
        hasReasoningTraces={false}
        onAskAi={onAskAi}
        onSearch={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Evidence" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Governed evidence search, provenance scope/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Source authority, provenance gaps/i),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", {
        name: "AI-assisted section critique: evidence workspace",
      }),
    );
    expect(onAskAi).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "Evidence section",
        prompt: expect.stringContaining(
          "Critique the Evidence section of this FTO report for gaps",
        ),
      }),
    );
    expect(
      screen.queryByRole("button", {
        name: "AI-assisted section critique: evidence evidence",
      }),
    ).not.toBeInTheDocument();
  });
});
