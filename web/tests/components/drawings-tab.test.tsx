import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { DrawingsTab } from "@/components/report/drawings-tab";
import type { FTOReport } from "@praviar/shared-types";

import { TEST_REPORT } from "../fixtures/report-fixture";

// MoleculeViewer2D is heavy (RDKit-WASM); mock per the established pattern in
// summary-tab-data.test.tsx so test wall-time stays under 100ms per case.
vi.mock("@/components/chemistry/molecule-viewer-2d", () => ({
  MoleculeViewer2D: ({ smiles, isMarkush, label }: any) => (
    <div
      data-testid="molecule-viewer"
      data-smiles={smiles}
      data-is-markush={String(isMarkush ?? false)}
    >
      {label ?? "viewer"}
    </div>
  ),
}));

describe("DrawingsTab", () => {
  it("renders the empty state when no drawings analyses exist", () => {
    const empty: FTOReport = { ...TEST_REPORT, drawing_analyses: [] };
    render(<DrawingsTab report={empty} />);
    expect(
      screen.getByText(/No governed drawing extracts/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/evidence gap/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/drawing_analysis_enabled/),
    ).not.toBeInTheDocument();
    expect(screen.queryAllByTestId("molecule-viewer")).toHaveLength(0);
  });

  it("renders the empty state when drawing_analyses is undefined", () => {
    const undef: FTOReport = { ...TEST_REPORT, drawing_analyses: undefined };
    render(<DrawingsTab report={undef} />);
    expect(
      screen.getByText(/No governed drawing extracts/i),
    ).toBeInTheDocument();
  });

  it("renders one card per structure across all patents in the fixture", () => {
    render(<DrawingsTab report={TEST_REPORT} />);
    // Fixture has 3 structures total: 2 in US0000000018A1 + 1 in US0000000019A1
    expect(screen.getAllByTestId("molecule-viewer")).toHaveLength(3);
    expect(
      screen.getByText("Governance provenance missing"),
    ).toBeInTheDocument();
    expect(screen.getByText("Do not rely")).toBeInTheDocument();
  });

  it("distinguishes governed live evidence from missing provenance", () => {
    const live = {
      schema_version: "praviar.drawing-governance.v1" as const,
      rollout_state: "production" as const,
      influence_permitted: true,
      evidence_gate_passed: true,
      runtime_roster_sha256: "a".repeat(64),
      ml_bom_sha256: "b".repeat(64),
      calibration_artifact_id: "vision-calibration-2026-07",
      calibration_artifact_revision: 3,
      calibration_artifact_sha256: "c".repeat(64),
      worker_image_digest: `sha256:${"d".repeat(64)}`,
      jurisdictions: ["US", "EP"],
      verified_at: "2026-07-30T12:00:00Z",
    };
    const report: FTOReport = {
      ...TEST_REPORT,
      drawing_analyses: TEST_REPORT.drawing_analyses?.map((analysis) => ({
        ...analysis,
        governance_provenance: live,
      })),
    };

    render(<DrawingsTab report={report} />);

    expect(screen.getByTestId("drawing-governance-live")).toBeInTheDocument();
    expect(screen.getByText("Governed live evidence")).toBeInTheDocument();
    expect(screen.getAllByText("Verified")).toHaveLength(2);
    expect(screen.getByText("US, EP")).toBeInTheDocument();
    expect(screen.getByText("sha256:aaaaaaaaaaaa…")).toBeInTheDocument();
  });

  it("blocks mixed drawing runtime identities", () => {
    const report: FTOReport = {
      ...TEST_REPORT,
      drawing_analyses: TEST_REPORT.drawing_analyses?.map(
        (analysis, index) => ({
          ...analysis,
          governance_provenance: {
            rollout_state: "shadow",
            influence_permitted: false,
            evidence_gate_passed: false,
            jurisdictions: index === 0 ? ["US"] : ["EP"],
          },
        }),
      ),
    };

    render(<DrawingsTab report={report} />);

    expect(
      screen.getByText("Mixed drawing evidence identities"),
    ).toBeInTheDocument();
    expect(screen.getByText("Do not rely")).toBeInTheDocument();
  });

  it("renders summary stats with correct counts", () => {
    render(<DrawingsTab report={TEST_REPORT} />);
    // 2 patents, 3 structures, 1 markush, 33% markush rate
    expect(screen.getByText(/Patents with drawings/i)).toBeInTheDocument();
    expect(screen.getByText(/Total structures/i)).toBeInTheDocument();
    expect(screen.getByText(/Markush templates/i)).toBeInTheDocument();
    // Spot-check numeric values render somewhere on the page
    const html = document.body.innerHTML;
    expect(html).toMatch(/\b3\b/); // total structures
    expect(html).toMatch(/\b2\b/); // patents
    expect(html).toMatch(/\b1\b/); // markush
    expect(html).toMatch(/33%/); // markush rate
  });

  it("counts only patents that actually contain drawing structures", () => {
    const report: FTOReport = {
      ...TEST_REPORT,
      drawing_analyses: [
        ...(TEST_REPORT.drawing_analyses ?? []),
        {
          patent_id: "US_EMPTY_DRAWING_RECORD",
          structures_found: 0,
          structures: [],
        },
      ],
    };

    render(<DrawingsTab report={report} />);

    const patentMetric = screen
      .getByText("Patents with drawings")
      .closest("div");
    expect(patentMetric).toHaveTextContent("2");
    expect(
      screen.queryByText("US_EMPTY_DRAWING_RECORD"),
    ).not.toBeInTheDocument();
  });

  it("groups structures by patent_id with section headers", () => {
    render(<DrawingsTab report={TEST_REPORT} />);
    expect(screen.getByText("US0000000018A1")).toBeInTheDocument();
    expect(screen.getByText("US0000000019A1")).toBeInTheDocument();
  });

  it("passes isMarkush=true for the Markush structure and false for regulars", () => {
    render(<DrawingsTab report={TEST_REPORT} />);
    const viewers = screen.getAllByTestId("molecule-viewer");
    const markushFlags = viewers.map((v) => v.getAttribute("data-is-markush"));
    // Exactly one markush in the fixture
    expect(markushFlags.filter((f) => f === "true")).toHaveLength(1);
    expect(markushFlags.filter((f) => f === "false")).toHaveLength(2);
  });
});
