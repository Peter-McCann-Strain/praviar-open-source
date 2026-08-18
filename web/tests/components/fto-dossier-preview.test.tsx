import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FtoDossierPreview } from "@/components/brand";

describe("FtoDossierPreview", () => {
  it("renders a decision-first dossier with risk drivers, evidence rows, and provenance", () => {
    const { container } = render(
      <FtoDossierPreview
        compoundName="Succinic acid"
        risk="high"
        summary="Two high-risk patent families require counsel review."
        metrics={[
          { label: "Blocking", value: "2" },
          { label: "Found", value: "2,417" },
          { label: "Runtime", value: "2 min" },
        ]}
        riskDrivers={[
          {
            label: "Driver 1",
            reference: "US0000000001A1",
            detail: "Independent claim 1 overlaps fermentation route.",
            severity: "high",
          },
        ]}
        evidenceRows={[
          {
            reference: "US0000000001A1",
            assignee: "Fictional Meridian Therapeutics",
            claimReference: "Claim 1 · partially met",
            expiry: "2035-06-14",
            rationale: "Three of four elements are met.",
            risk: "high",
            sourceLabel: "Google Patents",
            sourceUrl: "https://patents.google.com/patent/US0000000001A1",
          },
        ]}
        claimPreview={{
          title: "Fermentation process",
          reference: "US0000000001A1 · claim 1",
          text: "Process records show anaerobic production phase.",
          rationale: "Counsel should review yield and host-organism scope.",
        }}
        visual={<div aria-label="Molecule evidence panel" />}
        provenanceItems={["Synthetic fixture data", "Not a legal opinion"]}
      />,
    );

    expect(
      screen.getByLabelText("Succinic acid FTO dossier preview"),
    ).toHaveAttribute("data-praviar-visual", "fto-dossier");
    expect(screen.getByTestId("fto-dossier-preview")).toHaveClass("rounded-lg");
    expect(screen.getByText("US patent landscape")).toBeInTheDocument();
    expect(screen.getByText("FTO dossier")).toHaveClass("type-marketing-label");
    expect(screen.getByText("Read-only preview")).toHaveClass("text-xs");
    expect(screen.getByText("2,417")).toBeInTheDocument();
    expect(
      screen.getByText("Independent claim 1 overlaps fermentation route."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Fictional Meridian Therapeutics"),
    ).toBeInTheDocument();
    expect(screen.getByText("Claim 1 · partially met")).toBeInTheDocument();
    expect(
      screen.getByRole("link", {
        name: "Open source record for US0000000001A1",
      }),
    ).toHaveClass("min-h-11");
    expect(
      screen.getByRole("link", {
        name: "Open source record for US0000000001A1",
      }),
    ).toHaveAttribute(
      "href",
      "https://patents.google.com/patent/US0000000001A1",
    );
    expect(screen.getByText("Fermentation process")).toBeInTheDocument();
    expect(screen.getByText("Synthetic fixture data")).toBeInTheDocument();
    expect(screen.getByText("Synthetic fixture data")).toHaveClass("text-xs");
    expect(
      screen.getByLabelText("Molecule evidence panel"),
    ).toBeInTheDocument();
    expect(
      container.querySelector("[data-praviar-mark-frame='light']"),
    ).toBeInTheDocument();
    expect(
      container.querySelector('svg[data-praviar-mark="praviar-evidence-mark"]'),
    ).toBeInTheDocument();
  });

  it("puts lead evidence before the molecule visual in compact mobile dossiers", () => {
    render(
      <FtoDossierPreview
        compact
        compoundName="Succinic acid"
        risk="high"
        summary="Two high-risk patent families require counsel review."
        metrics={[
          { label: "Blocking", value: "2" },
          { label: "Found", value: "2,417" },
          { label: "Runtime", value: "2 min" },
        ]}
        evidenceRows={[
          {
            reference: "US0000000001A1",
            assignee: "Fictional Meridian Therapeutics",
            claimReference: "Claim 1 · partially met",
            rationale: "Three of four elements are met.",
            risk: "high",
          },
        ]}
        visual={<div aria-label="Molecule evidence panel" />}
      />,
    );

    const preview = screen.getByTestId("fto-dossier-preview");
    const leadEvidence = screen.getByTestId("fto-dossier-lead-evidence");
    const visual = screen.getByTestId("fto-dossier-visual");

    expect(preview).toHaveAttribute("data-praviar-visual", "fto-dossier");
    expect(preview).toHaveClass("rounded-lg");
    expect(leadEvidence).toHaveClass("rounded-lg");
    expect(leadEvidence).toHaveTextContent("US0000000001A1");
    expect(leadEvidence).toHaveTextContent("Claim 1 · partially met");
    expect(leadEvidence).toHaveTextContent("Three of four elements are met.");
    expect(
      leadEvidence.compareDocumentPosition(visual) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("can keep compact sales previews concise on mobile", () => {
    render(
      <FtoDossierPreview
        compact
        mobileSummaryOnly
        mobileVisualHidden
        compoundName="Succinic acid"
        risk="high"
        summary="A concise fictional screening summary."
        metrics={[{ label: "Families flagged", value: "3" }]}
        visual={<div aria-label="Sample molecule" />}
      />,
    );

    expect(screen.getByTestId("fto-dossier-detail")).toHaveClass(
      "hidden",
      "md:block",
    );
    expect(screen.getByTestId("fto-dossier-visual")).toHaveClass(
      "hidden",
      "md:block",
    );
    expect(screen.getByTestId("fto-dossier-metrics")).toHaveClass(
      "grid-cols-2",
    );
    expect(
      screen.getByText("A concise fictional screening summary."),
    ).toHaveClass("line-clamp-4", "md:line-clamp-none");
  });

  it("can limit compact index previews to one driver and evidence row", () => {
    render(
      <FtoDossierPreview
        compact
        compactItemLimit={1}
        compoundName="Succinic acid"
        risk="high"
        summary="A concise fictional screening summary."
        metrics={[{ label: "Families flagged", value: "3" }]}
        riskDrivers={[
          {
            label: "Driver 1",
            reference: "US111",
            detail: "First driver",
          },
          {
            label: "Driver 2",
            reference: "US222",
            detail: "Second driver",
          },
        ]}
        evidenceRows={[
          {
            reference: "US111",
            rationale: "First evidence",
            risk: "high",
          },
          {
            reference: "US222",
            rationale: "Second evidence",
            risk: "high",
          },
        ]}
      />,
    );

    expect(screen.getByText("First driver")).toBeInTheDocument();
    expect(screen.queryByText("Second driver")).not.toBeInTheDocument();
    expect(screen.getAllByText("First evidence")).toHaveLength(2);
    expect(screen.queryByText("Second evidence")).not.toBeInTheDocument();
  });

  it("renders source labels as text when evidence rows are read-only", () => {
    render(
      <FtoDossierPreview
        compoundName="Succinic acid"
        risk="medium"
        summary="A shared packet keeps source labels visible without links."
        metrics={[{ label: "Found", value: "12" }]}
        evidenceRows={[
          {
            reference: "US0000000001A1",
            assignee: "Fictional Meridian Therapeutics",
            claimReference: "Claim 1",
            rationale: "Included for counsel review.",
            risk: "medium",
            sourceLabel: "Google Patents",
          },
        ]}
      />,
    );

    expect(screen.getByText("Google Patents")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", {
        name: "Open source record for US0000000001A1",
      }),
    ).not.toBeInTheDocument();
  });

  it("wraps long pharma and patent metadata inside the dossier preview", () => {
    const longCompound =
      "N-(4-((7-chloro-6-(longsubstituentchainwithnoobviousbreakpoints)quinazolin-4-yl)oxy)phenyl)-3-hydroxypropanamide";
    const longAssignee =
      "AcmeGlobalBiopharmaceuticalHoldingsInternationalTherapeuticsResearchSubsidiaryLLC";
    const longClaim =
      "Claim 128 element iii.a.2 fermentation-neutralization-crystallization-isolation-with-continuous-pH-control";
    const longSourceLabel =
      "InternalDocketEvidenceRecordWithUnbrokenIdentifierUS20260345678A1ClaimScopeAppendix";

    render(
      <FtoDossierPreview
        compoundName={longCompound}
        risk="medium"
        summary="This dossier summary includesaverylongunspacedpharmacologyphraseandpatentidentifierthatmustwrapinsidepaper."
        metrics={[
          {
            label: "Longest unbroken metric label",
            value: "US20260345678A1/WO2026123456A1/EP4567890B1",
          },
        ]}
        riskDrivers={[
          {
            label: "Primaryclaimscopewithnospaces",
            reference: "US20260345678A1",
            detail:
              "Independent claim language includesaverylongunspacedtechnicalphraseforstress.",
            severity: "medium",
          },
        ]}
        evidenceRows={[
          {
            reference: "US20260345678A1",
            assignee: longAssignee,
            claimReference: longClaim,
            rationale:
              "Counsel should review the entire claim ladder includingaverylongunspacedmanufacturingconditionbeforehandoff.",
            risk: "medium",
            sourceLabel: longSourceLabel,
          },
        ]}
        claimPreview={{
          title:
            "VeryLongClaimPreviewTitleWithoutNaturalBreakpointsForPatentCounselReview",
          reference: "US20260345678A1 · claim 128",
          text: "Acompositioncomprisingaverylongunspacedchemicaldescriptorandcontinuousprocessingcondition.",
          rationale:
            "The claim rationale includesaverylongunspacedphraseandshouldwrapwithoutclipping.",
        }}
      />,
    );

    expect(screen.getByRole("heading", { name: longCompound })).toHaveClass(
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText(longAssignee).parentElement).toHaveClass(
      "min-w-0",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText(longClaim).parentElement).toHaveClass(
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText(longSourceLabel)).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
  });

  it("keeps compact lead evidence readable instead of visually clipping the rationale", () => {
    render(
      <FtoDossierPreview
        compact
        compoundName="Succinic acid"
        risk="high"
        summary="Two high-risk patent families require counsel review."
        metrics={[
          { label: "Blocking", value: "2" },
          { label: "Found", value: "2,417" },
          { label: "Runtime", value: "2 min" },
        ]}
        evidenceRows={[
          {
            reference: "US0000000001A1",
            assignee: "Fictional Meridian Therapeutics",
            claimReference: "Claim 1 · partially met",
            rationale:
              "Three of four elements are met, including anaerobic production, neutralization, and downstream isolation. The evidence also notes strain lineage, pH control, downstream crystallization, and batch-level yield thresholds so the final counsel handoff note remains visible.",
            risk: "high",
          },
        ]}
      />,
    );

    const leadEvidence = screen.getByTestId("fto-dossier-lead-evidence");

    expect(leadEvidence).toHaveTextContent(
      "final counsel handoff note remains visible.",
    );
    expect(leadEvidence.querySelector(".line-clamp-2")).not.toBeInTheDocument();
  });
});
