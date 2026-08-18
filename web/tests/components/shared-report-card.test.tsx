import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SharedReportCard } from "@/app/share/[token]/shared-report-card";

describe("SharedReportCard", () => {
  it("renders the public share as a read-only FTO dossier", () => {
    render(
      <SharedReportCard
        report={{
          report_id: "rpt_demo_succinic_001",
          share_id: "shr_demo_succinic_001",
          packet_version: "public-share-v1",
          source_snapshot_at: "2026-04-09T11:00:00.000Z",
          pipeline_version: "pipeline-2026.06",
          model_version: "agentic-report-2026.06",
          integrity_digest: "sha256:share-demo-001",
          compound_name: "Succinic acid",
          overall_risk: "high",
          blocking_patents_count: 2,
          total_patents_found: 2417,
          executive_summary:
            "Two high-risk patent families require qualified counsel review.",
          key_findings: [
            "US0000000001A1 overlaps the fermentation route.",
            "US0000000002A1 overlaps purification conditions.",
          ],
          generated_at: "2026-04-09T11:24:00.000Z",
          source_coverage: ["pubchem_sdq", "patentsview"],
          jurisdiction_scope: ["US", "EP"],
          evidence_limitations: ["EP family context incomplete"],
          review_status: "approved",
          share_expires_at: "2027-05-09T11:24:00.000Z",
          key_patents: [
            {
              patent_number: "US0000000001A1",
              risk_level: "high",
              assignee: "Example Pharma",
              expiry: "2037-04-09",
              patent_url: "https://patents.google.com/patent/US0000000001A1",
              source_reference: "Google Patents",
            },
            {
              patent_number: "US0000000002A1",
              risk_level: "high",
              assignee: "GenericCo",
              expiry: "2034-11-21",
              patent_url: "https://patents.google.com/patent/US0000000002A1",
              source_reference: "Google Patents",
            },
          ],
        }}
      />,
    );

    const dossierPreview = screen.getByLabelText(
      "Succinic acid FTO dossier preview",
    );
    expect(dossierPreview).toHaveAttribute(
      "data-praviar-visual",
      "fto-dossier",
    );
    expect(
      screen.getByLabelText("Shared report trust summary"),
    ).toHaveAttribute("data-praviar-share-trust-bar");
    expect(
      screen
        .getByLabelText("Verified recipient session")
        .compareDocumentPosition(dossierPreview) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    const decisionSnapshot = screen.getByRole("region", {
      name: "Shared decision snapshot",
    });
    expect(decisionSnapshot).toHaveAttribute(
      "data-praviar-share-decision-snapshot",
    );
    expect(decisionSnapshot).toHaveTextContent(
      "Start with the business answer",
    );
    expect(decisionSnapshot).toHaveTextContent("Risk answer");
    expect(decisionSnapshot).toHaveTextContent("HIGH");
    expect(decisionSnapshot).toHaveTextContent("Blocking patents");
    expect(decisionSnapshot).toHaveTextContent("2");
    expect(decisionSnapshot).toHaveTextContent("Top evidence");
    expect(decisionSnapshot).toHaveTextContent("US0000000001A1");
    expect(decisionSnapshot).toHaveTextContent("Validity window");
    expect(decisionSnapshot).toHaveTextContent("May 9, 2027, UTC");
    const packetReceipt = screen.getByRole("region", {
      name: "Shared packet receipt",
    });
    expect(packetReceipt).toHaveAttribute("data-praviar-share-packet-receipt");
    expect(
      dossierPreview.compareDocumentPosition(packetReceipt) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    const packetProvenance = screen.getByRole("region", {
      name: "Shared packet provenance",
    });
    expect(packetProvenance).toHaveTextContent("Preserve with diligence notes");
    expect(screen.getByText("Packet reference")).toBeInTheDocument();
    expect(screen.getByText("rpt_demo_succinic_001")).toBeInTheDocument();
    expect(screen.getByText("Packet version")).toBeInTheDocument();
    expect(screen.getByText("public-share-v1")).toBeInTheDocument();
    expect(screen.getByText("Source snapshot")).toBeInTheDocument();
    expect(packetProvenance).toHaveTextContent("Apr 9, 2026, UTC");
    expect(screen.getByText("Pipeline/model")).toBeInTheDocument();
    expect(
      screen.getByText("pipeline-2026.06 / agentic-report-2026.06"),
    ).toBeInTheDocument();
    expect(screen.getByText("Integrity digest")).toBeInTheDocument();
    expect(screen.getByText("sha256:share-demo-001")).toBeInTheDocument();
    expect(screen.getByText("Packet receipt")).toBeInTheDocument();
    expect(
      screen.getByText("Sender-controlled evidence record"),
    ).toBeInTheDocument();
    expect(screen.getByText("Share expiry")).toBeInTheDocument();
    expect(screen.getByText("Review status")).toBeInTheDocument();
    expect(screen.getByText("Evidence shown")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: "Succinic acid shared FTO report",
        level: 1,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Succinic acid", level: 2 }),
    ).toBeInTheDocument();
    expect(screen.queryByText("External FTO handoff")).not.toBeInTheDocument();
    expect(
      screen.getByRole("region", {
        name: "Shared report access and evidence scope",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/preliminary patent risk posture/i),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Generated").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Access")).toBeInTheDocument();
    expect(screen.getByText("Read-only view")).toBeInTheDocument();
    expect(screen.getByText("Workspace review")).toBeInTheDocument();
    expect(
      screen.getAllByText("Workspace review complete").length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Jurisdictions").length).toBeGreaterThanOrEqual(
      1,
    );
    expect(screen.getAllByText("US, EP").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Sources").length).toBeGreaterThanOrEqual(1);
    expect(
      screen.getAllByText("PubChem SDQ, PatentsView").length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Link expires").length).toBeGreaterThanOrEqual(
      1,
    );
    expect(
      screen.getAllByText("May 9, 2027, UTC").length,
    ).toBeGreaterThanOrEqual(1);
    expect(
      screen.getAllByText("EP family context incomplete").length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Example Pharma")).toBeInTheDocument();
    expect(screen.getByText("Exp. 2037-04-09")).toBeInTheDocument();
    expect(
      screen.getByRole("link", {
        name: "Open source record for US0000000001A1",
      }),
    ).toHaveAttribute(
      "href",
      "https://patents.google.com/patent/US0000000001A1",
    );
    expect(screen.getAllByText("Google Patents").length).toBeGreaterThan(0);
    expect(screen.getByText("Shared preliminary report")).toBeInTheDocument();
    expect(screen.getByText("Read-only FTO view")).toBeInTheDocument();
    expect(screen.getByText("Evidence included")).toBeInTheDocument();
    expect(screen.getAllByText("2 key patents").length).toBeGreaterThanOrEqual(
      1,
    );
    expect(screen.getAllByText("US0000000001A1").length).toBeGreaterThan(1);
    expect(
      screen.getAllByText("External reliance status").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Reliance review")).toBeInTheDocument();
    expect(screen.getByText("Required")).toBeInTheDocument();
    expect(screen.queryByText("Counsel review")).not.toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Recipient review workflow" }),
    ).toHaveAttribute("data-praviar-share-review-workflow");
    expect(screen.getByText("Counsel triage")).toBeInTheDocument();
    expect(
      screen.getByText("Decision path before reliance"),
    ).toBeInTheDocument();
    expect(screen.getByText("Confirm evidence scope")).toBeInTheDocument();
    expect(screen.getByText("Prioritize counsel review")).toBeInTheDocument();
    expect(screen.getByText("Carry forward caveats")).toBeInTheDocument();
    expect(screen.getByText("Request governed follow-up")).toBeInTheDocument();
    expect(screen.getByText("Counsel first")).toBeInTheDocument();
    expect(screen.getByText("Caveats active")).toBeInTheDocument();
    expect(screen.getByText("No edits here")).toBeInTheDocument();
    expect(
      screen.getAllByText("Partial evidence: counsel verification required")
        .length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText("Counsel verification required"),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("Apr 9, 2026, UTC").length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Not a legal opinion")).toBeInTheDocument();
    expect(
      screen.getByText(/does not provide a legal clearance opinion/i),
    ).toBeInTheDocument();
  });

  it("keeps a long verified recipient address readable on narrow screens", () => {
    const recipient =
      "patent.counsel.with.a.long.mailbox@international-biotech.example";

    render(
      <SharedReportCard
        report={{
          compound_name: "Recipient-bound compound",
          overall_risk: "medium",
          blocking_patents_count: 0,
          total_patents_found: 1,
          executive_summary:
            "One patent family requires qualified counsel review.",
          key_findings: ["US1234567A1 requires claim review."],
          generated_at: "2026-04-09T11:24:00.000Z",
          source_coverage: ["PatentsView"],
          jurisdiction_scope: ["US"],
          verified_recipient_email: recipient,
        }}
      />,
    );

    const recipientLabel = screen.getByText(recipient);
    expect(recipientLabel).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
    expect(recipientLabel).not.toHaveClass("break-all");
    expect(recipientLabel).toHaveAttribute("title", recipient);
  });

  it("renders the attributable session expiry with an exact UTC time", () => {
    render(
      <SharedReportCard
        report={{
          compound_name: "Example Molecule Alpha",
          overall_risk: "medium",
          blocking_patents_count: 0,
          total_patents_found: 2,
          executive_summary: "A fictional report for recipient review.",
          key_findings: ["One synthetic finding requires review."],
          generated_at: "2026-01-15T10:30:00.000Z",
          verified_recipient_email: "recipient@demo.praviar.invalid",
          attributable_view_number: 1,
          verified_session_expires_at: "2026-01-15T11:00:00.000Z",
        }}
      />,
    );

    expect(
      screen.getByRole("region", { name: "Verified recipient session" }),
    ).toHaveTextContent("Session expires Jan 15, 2026, 11:00 UTC");
  });

  it("does not render unsafe public source URLs", () => {
    render(
      <SharedReportCard
        report={{
          compound_name: "Unsafe source compound",
          overall_risk: "high",
          blocking_patents_count: 1,
          total_patents_found: 12,
          executive_summary:
            "A material patent family requires qualified counsel review.",
          key_findings: ["US-UNSAFE-1 overlaps the proposed product scope."],
          generated_at: "2026-04-09T11:24:00.000Z",
          source_coverage: ["PatentsView"],
          jurisdiction_scope: ["US"],
          share_expires_at: "2027-05-09T11:24:00.000Z",
          key_patents: [
            {
              patent_number: "US-UNSAFE-1",
              risk_level: "high",
              assignee: "Example Pharma",
              patent_url: "https://127.0.0.1/admin",
              source_reference: "USPTO PPUBS",
            },
          ],
        }}
      />,
    );

    expect(
      screen.queryByRole("link", {
        name: "Open source record for US-UNSAFE-1",
      }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("USPTO PPUBS")).toBeInTheDocument();
  });

  it("frames low-risk shared reports without implying legal clearance", () => {
    render(
      <SharedReportCard
        report={{
          compound_name: "Caffeine",
          overall_risk: "clear",
          blocking_patents_count: 0,
          total_patents_found: 12,
          executive_summary:
            "No material blockers were identified in the current source set.",
          key_findings: ["Current source set did not surface blocking claims."],
          generated_at: "not-a-date",
          key_patents: [],
          jurisdiction_scope: ["US"],
          source_coverage: ["report evidence"],
          integrity_summary: {
            affected_patents_count: 0,
            recoverable_failures_count: 0,
            needs_review_count: 0,
            data_limitations_count: 0,
            source_caveats_count: 0,
            evidence_sufficient_for_clearance: true,
            metadata_inconsistent: false,
          },
        }}
      />,
    );

    expect(screen.getByText(/risk posture, review scope/i)).toBeInTheDocument();
    const clearPostureLabels = screen.getAllByText("NO BLOCKERS SURFACED");
    const clearPostureMetric = clearPostureLabels.find((element) =>
      element.className.includes("leading-tight"),
    );
    expect(clearPostureLabels.length).toBeGreaterThan(1);
    expect(clearPostureMetric).toBeInTheDocument();
    expect(clearPostureMetric).toHaveClass("break-words", "leading-tight");
    expect(clearPostureMetric).not.toHaveClass("whitespace-nowrap");
    expect(screen.queryByText("CLEAR")).not.toBeInTheDocument();
    expect(
      screen.getAllByText("Generated date unavailable").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText(
        /No key patents were included in this shared view for US/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/Not a legal opinion/i).length).toBeGreaterThan(
      0,
    );
    expect(
      screen.getByText(/does not provide a legal clearance opinion/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Screening only: no legal clearance opinion"),
    ).toBeInTheDocument();
    expect(screen.getByText("Document screening basis")).toBeInTheDocument();
    expect(screen.getByText("Screening record")).toBeInTheDocument();
    expect(screen.getByText("Boundary active")).toBeInTheDocument();
  });

  it("fails closed when public integrity metadata is unavailable", () => {
    render(
      <SharedReportCard
        report={{
          compound_name: "Sparse clear packet",
          overall_risk: "clear",
          blocking_patents_count: 0,
          total_patents_found: 12,
          executive_summary:
            "No material blockers were identified in the current source set.",
          key_findings: ["Current source set did not surface blocking claims."],
          generated_at: "2026-04-09T11:24:00.000Z",
          key_patents: [],
          jurisdiction_scope: ["US"],
          source_coverage: ["report evidence"],
        }}
      />,
    );

    expect(
      screen.getAllByText("Partial evidence: counsel verification required")
        .length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText("Counsel verification required"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Screening only: no legal clearance opinion"),
    ).not.toBeInTheDocument();
  });

  it("marks high-risk public packets as requiring reliance review without misleading zero counts", () => {
    render(
      <SharedReportCard
        report={{
          compound_name: "Clean high-risk compound",
          overall_risk: "high",
          blocking_patents_count: 1,
          total_patents_found: 12,
          executive_summary:
            "A material patent family requires qualified counsel review.",
          key_findings: ["US-HIGH-1 overlaps the proposed product scope."],
          generated_at: "2026-04-09T11:24:00.000Z",
          source_coverage: ["PubChem SDQ"],
          jurisdiction_scope: ["US"],
          evidence_limitations: [],
          integrity_summary: {
            affected_patents_count: 0,
            recoverable_failures_count: 0,
            needs_review_count: 0,
            data_limitations_count: 0,
            source_caveats_count: 0,
            evidence_sufficient_for_clearance: true,
            metadata_inconsistent: false,
          },
          key_patents: [
            {
              patent_number: "US-HIGH-1",
              risk_level: "high",
              assignee: "Example Pharma",
              expiry: "2037-04-09",
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("Reliance review")).toBeInTheDocument();
    expect(screen.getByText("Required")).toBeInTheDocument();
    expect(screen.queryByText("Counsel review")).not.toBeInTheDocument();
  });

  it("can demote its internal heading when the page chrome owns the visible h1", () => {
    render(
      <SharedReportCard
        headingLevel={2}
        report={{
          compound_name: "Caffeine",
          overall_risk: "clear",
          blocking_patents_count: 0,
          total_patents_found: 12,
          executive_summary:
            "No material blockers were identified in the current source set.",
          key_findings: ["Current source set did not surface blocking claims."],
          generated_at: "2026-04-10T09:15:00.000Z",
          key_patents: [],
          jurisdiction_scope: ["US"],
          source_coverage: ["report evidence"],
        }}
      />,
    );

    expect(
      screen.queryByRole("heading", {
        name: "Caffeine shared FTO report",
        level: 1,
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: "Caffeine shared FTO report",
        level: 2,
      }),
    ).toBeInTheDocument();
  });

  it("formats public source labels without leaking provider ids", () => {
    render(
      <SharedReportCard
        report={{
          compound_name: "Source label compound",
          overall_risk: "low",
          blocking_patents_count: 0,
          total_patents_found: 8,
          executive_summary: "Source labels should be customer-readable.",
          key_findings: ["No material blockers in the current public sources."],
          generated_at: "2026-04-09T11:24:00.000Z",
          source_coverage: [
            "google_patents_public_datasets",
            "epo_ops",
            "uspto",
          ],
          jurisdiction_scope: ["US", "EP"],
          key_patents: [],
        }}
      />,
    );

    expect(
      screen.getAllByText(/Google patent datasets/i).length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText(/EPO OPS/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/USPTO/i).length).toBeGreaterThan(0);
    expect(
      screen.queryByText(/google_patents_public_datasets/i),
    ).not.toBeInTheDocument();
  });

  it("renders duplicate evidence limitations without dropping rows", () => {
    render(
      <SharedReportCard
        report={{
          compound_name: "Duplicate limitation compound",
          overall_risk: "medium",
          blocking_patents_count: 1,
          total_patents_found: 18,
          executive_summary: "One medium-risk patent family needs review.",
          key_findings: ["A method claim may overlap the proposed process."],
          generated_at: "2026-04-09T11:24:00.000Z",
          source_coverage: ["patentsview"],
          jurisdiction_scope: ["US"],
          evidence_limitations: [
            "Coverage caveat requires counsel review",
            "Coverage caveat requires counsel review",
          ],
          review_status: "pending_review",
          key_patents: [],
        }}
      />,
    );

    expect(
      screen.getAllByText("Coverage caveat requires counsel review"),
    ).toHaveLength(4);
  });

  it("surfaces integrity metadata and redacts raw diagnostics in public caveats", () => {
    render(
      <SharedReportCard
        report={{
          compound_name: "Integrity compound",
          overall_risk: "low",
          blocking_patents_count: 0,
          total_patents_found: 108,
          executive_summary:
            "No material blockers were found, but partial evidence needs review.",
          key_findings: [
            "US-A-111 overlaps a backup process route.",
            "Portfolio-level source coverage needs counsel review.",
          ],
          generated_at: "2026-04-09T11:24:00.000Z",
          source_coverage: ["PubChem SDQ", "PatentsView"],
          jurisdiction_scope: ["US"],
          evidence_limitations: [
            "postgres://secret-host/praviar sk_live_secret SELECT * FROM analyses Traceback",
            "2 patent analyses require review",
            "Source coverage caveat 3 requires reviewer confirmation.",
            "Source coverage caveat 4 requires reviewer confirmation.",
            "Source coverage caveat 5 must remain visible to recipients.",
          ],
          integrity_summary: {
            affected_patents_count: 2,
            recoverable_failures_count: 1,
            needs_review_count: 1,
            data_limitations_count: 1,
            source_caveats_count: 3,
            evidence_sufficient_for_clearance: false,
            metadata_inconsistent: true,
          },
          total_material_patents: 6,
          omitted_key_patents_count: 4,
          omitted_limitations_count: 2,
          standard_limitations: [
            "Markush and generic claim coverage may require manual claim construction.",
            "Prior-art exhaustiveness and validity opinions are outside this shared screening artifact.",
            "Standard limitation 3 must stay attached to downstream review.",
            "Standard limitation 4 must stay attached to downstream review.",
            "Standard limitation 5 must stay attached to downstream review.",
            "Standard limitation 6 must not be hidden in the public packet.",
            "postgres://standard-secret/praviar sk_live_standard SELECT * FROM public_reports Traceback",
          ],
          intended_use:
            "Read-only external FTO screening packet for qualified patent counsel review.",
          ai_system_notice:
            "AI-assisted patent landscape analysis; outputs require human review before reliance.",
          reliance_boundary:
            "Not a legal clearance opinion or freedom-to-operate opinion.",
          key_patents: [
            {
              patent_number: "US-B-222",
              risk_level: "low",
              assignee: "Example Pharma",
              expiry: "2038-01-01",
            },
            {
              patent_number: "US-A-111",
              risk_level: "medium",
              assignee: "GenericCo",
              expiry: "2034-11-21",
            },
          ],
        }}
      />,
    );

    expect(
      screen.getAllByText("Partial evidence: counsel verification required")
        .length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("2 affected")).toBeInTheDocument();
    expect(screen.getByText("Reliance review")).toBeInTheDocument();
    expect(screen.getByText("Required")).toBeInTheDocument();
    expect(screen.getAllByText("1").length).toBeGreaterThanOrEqual(1);
    expect(
      screen.getByText(
        "2 additional caveats omitted from this compact public view.",
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Evidence shown").length).toBeGreaterThanOrEqual(
      1,
    );
    expect(
      screen.getByText(
        /4 reviewed patents are omitted from this compact view/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("2 of 6 reviewed patents shown").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText(/AI-assisted patent landscape analysis/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Markush and generic claim coverage/i),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(
        "Source coverage caveat 5 must remain visible to recipients.",
      ).length,
    ).toBeGreaterThan(1);
    expect(
      screen.getByText(
        "Standard limitation 6 must not be hidden in the public packet.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/standard-secret/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/sk_live_standard/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/public_reports/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret-host/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/sk_live/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/SELECT \*/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Traceback/i)).not.toBeInTheDocument();
    expect(screen.getAllByText("US-A-111").length).toBeGreaterThan(1);
    expect(screen.getByText("Shared finding")).toBeInTheDocument();
  });

  it("treats omitted public evidence as partial even without integrity flags", () => {
    render(
      <SharedReportCard
        report={{
          compound_name: "Omitted evidence compound",
          overall_risk: "low",
          blocking_patents_count: 0,
          total_patents_found: 42,
          executive_summary:
            "The compact packet omits some reviewed patent context.",
          key_findings: [
            "No displayed patent is blocking in the compact view.",
          ],
          generated_at: "2026-04-09T11:24:00.000Z",
          source_coverage: ["PatentsView"],
          jurisdiction_scope: ["US"],
          evidence_limitations: [],
          integrity_summary: {
            affected_patents_count: 0,
            recoverable_failures_count: 0,
            needs_review_count: 0,
            data_limitations_count: 0,
            source_caveats_count: 0,
            evidence_sufficient_for_clearance: true,
            metadata_inconsistent: false,
          },
          total_material_patents: 5,
          omitted_key_patents_count: 3,
          omitted_limitations_count: 0,
          key_patents: [
            {
              patent_number: "US-OMIT-1",
              risk_level: "low",
              assignee: "Example Pharma",
            },
            {
              patent_number: "US-OMIT-2",
              risk_level: "low",
              assignee: "GenericCo",
            },
          ],
        }}
      />,
    );

    expect(
      screen.getAllByText("Partial evidence: counsel verification required")
        .length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("3 omitted")).toBeInTheDocument();
    expect(
      screen.queryByText("Screening only: no legal clearance opinion"),
    ).not.toBeInTheDocument();
  });

  it("keeps sticky trust metadata visually separated and resilient to long tokens", () => {
    const longJurisdiction = `US-${"GLOBAL".repeat(48)}`;
    const longSource = `patentsview-${"continuation".repeat(42)}`;
    const longLimitation = `machine-readable-caveat-${"claimscope".repeat(36)}`;

    render(
      <SharedReportCard
        report={{
          compound_name: "Long token compound",
          overall_risk: "medium",
          blocking_patents_count: 0,
          total_patents_found: 7,
          executive_summary:
            "A long-source shared report should remain readable on mobile.",
          key_findings: ["Review the long jurisdiction and source labels."],
          generated_at: "2026-04-09T11:24:00.000Z",
          source_coverage: [longSource],
          jurisdiction_scope: [longJurisdiction],
          evidence_limitations: [longLimitation],
          key_patents: [],
        }}
      />,
    );

    const trustBar = screen.getByLabelText("Shared report trust summary");
    expect(trustBar).toHaveClass(
      "md:sticky",
      "md:top-3",
      "shadow-[var(--shadow-md)]",
      "backdrop-blur-xl",
    );

    expect(
      screen
        .getAllByText(longJurisdiction)
        .some((element) =>
          element.className.includes("[overflow-wrap:anywhere]"),
        ),
    ).toBe(true);
    expect(
      screen
        .getAllByText(longSource)
        .some((element) =>
          element.className.includes("[overflow-wrap:anywhere]"),
        ),
    ).toBe(true);
    const renderedLongLimitation = screen
      .getAllByText(/machine-readable-caveat-claimscope/)
      .find((element) => element.className.includes("break-words"));
    expect(renderedLongLimitation).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
  });
});
