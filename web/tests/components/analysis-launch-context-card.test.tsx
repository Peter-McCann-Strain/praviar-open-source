import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnalysisLaunchContextCard } from "@/components/analysis-detail/analysis-launch-context-card";
import type { AnalysisListItem } from "@/types/api";

const baseAnalysis: AnalysisListItem = {
  id: "ana-1",
  compound_input: "ibuprofen",
  compound_name: "Ibuprofen",
  compound_smiles: "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
  status: "running",
  current_step: 4,
  progress_pct: 52,
  overall_risk: null,
  blocking_patents_count: 0,
  total_patents_found: 189,
  executive_summary: "",
  estimated_cost_usd: 1.34,
  pipeline_duration_seconds: null,
  flagged_for_review: false,
  created_at: "2026-06-30T09:15:00.000Z",
  updated_at: "2026-07-01T17:21:00.000Z",
};

describe("AnalysisLaunchContextCard", () => {
  it("renders launch product context, assumptions, open gaps, and known art", () => {
    render(
      <AnalysisLaunchContextCard
        analysis={{
          ...baseAnalysis,
          launch_context: {
            trust_mode: "counsel",
            jurisdiction_bundle: "custom",
            target_jurisdictions: ["US", "EP"],
            development_stage: "clinical",
            asset_type_hint: "formulation",
            matter_type: "formulation",
            intended_actions: ["formulation_review", "commercial_launch"],
            product_context: {
              product_name: "PRV-142 oral tablet",
              dosage_form: "Film-coated tablet",
              route_of_administration: "Oral",
              strength: "200 mg",
              known_patents_or_assignees: ["US12345678", "Fictional Meridian"],
              owned_or_licensed_ip:
                "Internal option to use PRV-142 formulation estate",
            },
          },
        }}
      />,
    );

    expect(
      screen.getByRole("region", { name: "Launch context" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Product and evidence assumptions"),
    ).toBeInTheDocument();
    expect(screen.getByText("Report Credit used")).toBeInTheDocument();
    expect(
      screen.getByTestId("launch-context-mobile-summary"),
    ).toHaveTextContent("Review launch assumptions");
    expect(screen.getAllByText("6 product facts").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Formulation; Clinical").length).toBeGreaterThan(
      0,
    );
    expect(screen.getAllByText("US, EP").length).toBeGreaterThan(0);
    expect(screen.getByText("PRV-142 oral tablet")).toBeInTheDocument();
    expect(screen.getByText("Film-coated tablet")).toBeInTheDocument();
    expect(screen.getByText("Owned or licensed IP")).toBeInTheDocument();
    expect(
      screen.getByText("Internal option to use PRV-142 formulation estate"),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("US12345678, Fictional Meridian").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/Open context:/)).toBeInTheDocument();
    expect(screen.getByText(/Indication/)).toBeInTheDocument();
  });

  it("renders nothing when an older analysis has no launch context", () => {
    const { container } = render(
      <AnalysisLaunchContextCard analysis={baseAnalysis} />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
