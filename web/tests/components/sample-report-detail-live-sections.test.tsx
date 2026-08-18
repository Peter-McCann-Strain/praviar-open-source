import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SampleReportDetailLiveSections } from "@/components/marketing/sample-report-detail-live-sections";
import type { DemoArtifactPayload } from "@/marketing/live-demo";

vi.mock("@/components/charts/search-funnel", () => ({
  SearchFunnel: () => <div>Search funnel chart</div>,
}));

vi.mock("@/components/charts/timing-waterfall", () => ({
  TimingWaterfall: () => <div>Timing profile chart</div>,
}));

const demoArtifact: DemoArtifactPayload = {
  compoundName: "succinic acid",
  canonicalSmiles: "OC(=O)CCC(O)=O",
  verdict: "high",
  blockingPatentsCount: 3,
  familiesFlaggedForReviewCount: 3,
  totalPatentsFound: 2417,
  patentsAfterTriage: 47,
  patentsAnalyzed: 5,
  runtimeLabel: "2 min 12 s",
  executiveSummary: "Two blocking families require counsel review.",
  keyFindings: ["Lead fermentation claim remains material."],
  searchFunnel: [
    { stage: "Discovered", count: 2417 },
    { stage: "Hard Filter", count: 312 },
    { stage: "Ranked", count: 88 },
    { stage: "Triaged", count: 47 },
    { stage: "Analyzed", count: 5 },
  ],
  timing: [{ step: "Claim analysis", duration_seconds: 48 }],
  claimSnapshot: {
    patentId: "US0000000001A1",
    patentTitle: "Fermentation process",
    claimNumber: 1,
    claimStatus: "partially_met",
    elements: [
      {
        label: "Element 1",
        elementText:
          "A method for producing a C4 dicarboxylic acid comprising culturing a recombinant prokaryotic microorganism",
        status: "met",
        reasoning: "The evaluated process uses recombinant E. coli.",
        confidence: 0.9,
        evidence:
          "The production process uses a recombinant prokaryotic microorganism.",
        traceId: "assertion-demo-meridian-claim-1-element-1",
        sourceCitation: "US0000000001A1 claim 1",
        sourceExcerpt:
          "Succinic acid is a C4 dicarboxylic acid and E. coli is prokaryotic.",
        supportStatus: "supported",
        reviewRequired: false,
      },
    ],
  },
  evidenceRows: [
    {
      patentId: "US0000000001A1",
      title: "Fermentation process",
      assignee: "Fictional Meridian Therapeutics",
      expiryDate: "2035-06-14",
      riskLevel: "high",
      claimReference: "Claim 1 · partially met",
      rationale: "Three of four elements are mapped in the fictional sample.",
      sourceLabel: "2 fixture sources",
      sourceUrl: "#sample-evidence-ledger",
      sourceTraceId: "fixture-trace-US0000000001A1",
      sourcePosture: "Synthetic fixture record",
      sourcesFoundIn: ["surechembl", "bigquery"],
      rank: 1,
      score: 0.89,
      filterReason: "",
      triageReason:
        "Claims directly cover microbial production of C4 dicarboxylic acids.",
      triageConfidence: 0.94,
      selectionReason:
        "Triage: relevant. Claims directly cover target production method.",
      selectedForAnalysis: true,
    },
  ],
  provenance: {
    reportId: "rpt_demo_succinic_001",
    generatedAt: "2026-07-01T14:22:13.100Z",
    pipelineVersion: "0.9.4",
    executionProfile: "world_class_adaptive",
    modelNames: ["claude-sonnet-4-20250514"],
    totalInputTokens: 126146,
    totalOutputTokens: 31563,
    estimatedCostUsd: 4.82,
  },
  verification: {
    checks: [
      {
        check_name: "citation_validity",
        passed: true,
        details: "All cited fixture records resolve inside the sample.",
        severity: "pass",
      },
      {
        check_name: "doe_consistency",
        passed: false,
        details: "Manual review recommended for prosecution history estoppel.",
        severity: "warning",
      },
    ],
    issues: ["Manual review recommended."],
    unsupportedVisibleClaims: 0,
    reviewNeededClaims: 1,
  },
  sourceHealth: [
    {
      source: "surechembl",
      status: "ok",
      patent_count: 1203,
      error_message: "",
    },
    {
      source: "patcid",
      status: "failed",
      patent_count: 0,
      error_message: "PatCID API returned HTTP 503 Service Unavailable.",
    },
  ],
  analysisFailures: [
    {
      patent_id: "US0000000008A1",
      step: "step5_doe",
      error_type: "TimeoutError",
      error_message: "USPTO file wrapper API timed out.",
      recoverable: true,
    },
  ],
  dataLimitations: [
    {
      category: "source_unavailable",
      description: "PatCID API returned 503 Service Unavailable.",
      impact: "Some relevant patents with Markush structures may be missed.",
    },
  ],
  designAround: "Use a downstream process outside the asserted claim scope.",
  invalidityTeaser: "A prior-art reference may support obviousness review.",
  disclaimer: "Synthetic fixture.",
  sourceReference: "Synthetic public fixture",
};

describe("SampleReportDetailLiveSections", () => {
  it("renders repeated limitation categories without a React identity error", () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => {});
    const repeatedCategoryArtifact: DemoArtifactPayload = {
      ...demoArtifact,
      dataLimitations: [
        {
          category: "synthetic_showcase",
          description: "First synthetic limitation.",
          impact: "First review boundary.",
        },
        {
          category: "synthetic_showcase",
          description: "Second synthetic limitation.",
          impact: "Second review boundary.",
        },
      ],
    };

    try {
      render(
        <SampleReportDetailLiveSections
          demoArtifact={repeatedCategoryArtifact}
        />,
      );

      expect(screen.getByText("First synthetic limitation.")).toBeVisible();
      expect(screen.getByText("Second synthetic limitation.")).toBeVisible();
      expect(
        consoleError.mock.calls.some((call) =>
          call.some(
            (value) =>
              typeof value === "string" &&
              /same key|keys should be unique/iu.test(value),
          ),
        ),
      ).toBe(false);
    } finally {
      consoleError.mockRestore();
    }
  });

  it("redacts diagnostic-looking source and analysis failure text", () => {
    const diagnosticArtifact: DemoArtifactPayload = {
      ...demoArtifact,
      sourceHealth: [
        {
          source: "patcid",
          status: "failed",
          patent_count: 0,
          error_message:
            "postgres://secret-host/praviar sk_live_secret SELECT * FROM analyses Traceback provider stack",
        },
      ],
      analysisFailures: [
        {
          patent_id: "US0000000008A1",
          step: "step5_doe",
          error_type: "TimeoutError",
          error_message:
            "Bearer abc123 /Users/example-user/private Traceback worker stack",
          recoverable: true,
        },
      ],
    };

    render(
      <SampleReportDetailLiveSections demoArtifact={diagnosticArtifact} />,
    );

    expect(document.body).not.toHaveTextContent("postgres://secret-host");
    expect(document.body).not.toHaveTextContent("sk_live_secret");
    expect(document.body).not.toHaveTextContent("SELECT * FROM analyses");
    expect(document.body).not.toHaveTextContent("Bearer abc123");
    expect(document.body).not.toHaveTextContent("/Users/example-user/private");
    expect(document.body).not.toHaveTextContent("Traceback provider stack");
    expect(document.body).toHaveTextContent(
      "Diagnostic details are available to support.",
    );
  });

  it("uses neutral public wording for internal execution profile enums", () => {
    render(<SampleReportDetailLiveSections demoArtifact={demoArtifact} />);

    expect(
      screen.getAllByText("Illustrative adaptive profile").length,
    ).toBeGreaterThan(0);
    expect(document.body).not.toHaveTextContent(/world[- ]class/i);
  });

  it("opens the first mobile report chapter without opening later chapters", () => {
    const originalMatchMedia = window.matchMedia;
    const mediaQuery = {
      addEventListener: vi.fn(),
      matches: false,
      media: "(min-width: 640px)",
      onchange: null,
      removeEventListener: vi.fn(),
    };

    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: vi.fn(() => mediaQuery),
      writable: true,
    });

    try {
      render(<SampleReportDetailLiveSections demoArtifact={demoArtifact} />);

      expect(
        screen.getByTestId("sample-trace-packet").closest("details"),
      ).toHaveAttribute("open");
      expect(
        screen.getByTestId("sample-verification-limits").closest("details"),
      ).not.toHaveAttribute("open");
    } finally {
      Object.defineProperty(window, "matchMedia", {
        configurable: true,
        value: originalMatchMedia,
        writable: true,
      });
    }
  });

  it("renders the sample as an auditable trace packet with source-linked claim evidence", () => {
    render(<SampleReportDetailLiveSections demoArtifact={demoArtifact} />);

    const tracePacket = screen.getByTestId("sample-trace-packet");
    expect(
      within(tracePacket).getByRole("heading", {
        name: "See how run metadata is presented in the sample",
      }),
    ).toBeInTheDocument();
    expect(
      within(tracePacket).getByText("rpt_demo_succinic_001"),
    ).toBeInTheDocument();
    expect(
      within(tracePacket).getByText("1 sample check warning"),
    ).toBeInTheDocument();
    expect(
      within(tracePacket).getByText("1 sample limitation"),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("table", { name: "Claim chart for US0000000001A1" }),
    ).toHaveAttribute("data-testid", "sample-claim-chart-table");
    expect(
      screen.getByRole("region", { name: "Claim chart table" }),
    ).not.toHaveAttribute("tabindex");
    for (const link of screen.getAllByRole("link", {
      name: "Inspect claim basis",
    })) {
      expect(link).toHaveClass("min-h-11");
    }
    expect(
      screen.getByRole("columnheader", { name: "Element" }),
    ).toHaveAttribute("scope", "col");
    expect(
      screen.getByRole("columnheader", { name: "Evidence excerpt" }),
    ).toHaveAttribute("scope", "col");
    expect(
      screen.getByRole("columnheader", { name: "Source trace" }),
    ).toHaveAttribute("scope", "col");
    expect(
      screen.getByRole("rowheader", { name: /Element 1 Claim 1/i }),
    ).toHaveAttribute("scope", "row");
    expect(screen.getAllByText("US0000000001A1").length).toBeGreaterThan(1);
    expect(
      screen.getAllByText("assertion-demo-meridian-claim-1-element-1").length,
    ).toBeGreaterThan(1);
    for (const traceIdentifier of screen.getAllByText(
      "assertion-demo-meridian-claim-1-element-1",
    )) {
      expect(traceIdentifier).toHaveClass("[overflow-wrap:anywhere]");
      expect(traceIdentifier).not.toHaveClass("break-all");
    }
    expect(
      screen.getAllByText("US0000000001A1 claim 1").length,
    ).toBeGreaterThan(1);
    expect(
      screen.getAllByText("Internal link present in fictional record").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        "The production process uses a recombinant prokaryotic microorganism.",
      ).length,
    ).toBeGreaterThan(1);

    const evidenceLedger = screen.getByTestId(
      "sample-evidence-traceability-ledger",
    );
    expect(
      within(evidenceLedger).getByRole("heading", {
        name: "Follow the sample finding back to its support",
      }),
    ).toBeInTheDocument();
    expect(
      within(evidenceLedger).getByRole("table", {
        name: "Evidence traceability ledger for the public sample report",
      }),
    ).toHaveAttribute("data-testid", "sample-evidence-ledger-table");
    expect(
      within(evidenceLedger).getByRole("region", {
        name: "Scrollable evidence traceability ledger",
      }),
    ).toHaveAttribute("tabindex", "0");
    expect(
      within(evidenceLedger).getByText("fixture-trace-US0000000001A1"),
    ).toBeInTheDocument();
    for (const sourceTraceIdentifier of within(evidenceLedger).getAllByText(
      "fixture-trace-US0000000001A1",
    )) {
      expect(sourceTraceIdentifier).toHaveClass("[overflow-wrap:anywhere]");
      expect(sourceTraceIdentifier).not.toHaveClass("break-all");
    }
    expect(within(evidenceLedger).getAllByText("#1")).toHaveLength(2);
    expect(
      within(evidenceLedger).getByText("Illustrative rank only"),
    ).toBeInTheDocument();

    const funnelAudit = screen.getByTestId("sample-funnel-audit-table");
    expect(
      within(funnelAudit).getByText("Illustrative funnel record"),
    ).toBeInTheDocument();
    const funnelAuditDesktopTable = within(funnelAudit).getByRole("table", {
      name: "Search funnel audit table for the sample report",
    });
    expect(funnelAuditDesktopTable).toHaveAttribute(
      "data-testid",
      "sample-funnel-audit-desktop-table",
    );
    expect(
      screen.getByTestId("sample-funnel-audit-desktop-table-wrap"),
    ).toHaveClass("hidden", "md:block");
    expect(
      screen.getByTestId("sample-funnel-audit-desktop-table-wrap"),
    ).toHaveAttribute("tabindex", "0");
    expect(
      screen.getByRole("region", {
        name: "Scrollable search funnel audit table",
      }),
    ).toHaveAttribute("data-testid", "sample-funnel-audit-desktop-table-wrap");
    expect(
      screen.getByTestId("sample-funnel-audit-desktop-table-wrap"),
    ).toHaveAccessibleName("Scrollable search funnel audit table");
    expect(
      within(funnelAuditDesktopTable).getByRole("columnheader", {
        name: "Stage",
      }),
    ).toBeInTheDocument();
    expect(
      within(funnelAuditDesktopTable).getByRole("columnheader", {
        name: "Retained",
      }),
    ).toBeInTheDocument();
    expect(
      within(funnelAuditDesktopTable).getByRole("columnheader", {
        name: "Removed",
      }),
    ).toBeInTheDocument();
    expect(
      within(funnelAuditDesktopTable).getByRole("columnheader", {
        name: "Audit note",
      }),
    ).toBeInTheDocument();
    expect(
      within(funnelAuditDesktopTable).getByRole("rowheader", {
        name: "Discovered",
      }),
    ).toBeInTheDocument();
    expect(
      within(funnelAuditDesktopTable).getByRole("rowheader", {
        name: "Analyzed",
      }),
    ).toBeInTheDocument();
    expect(
      within(funnelAuditDesktopTable).getByText("baseline"),
    ).toBeInTheDocument();
    expect(
      within(funnelAuditDesktopTable).getByText("2,105"),
    ).toBeInTheDocument();
    expect(
      within(funnelAuditDesktopTable).getByText("224"),
    ).toBeInTheDocument();
    expect(within(funnelAuditDesktopTable).getByText("41")).toBeInTheDocument();
    expect(within(funnelAuditDesktopTable).getByText("42")).toBeInTheDocument();
    const funnelAuditSummary = screen.getByTestId(
      "sample-funnel-audit-summary",
    );
    expect(funnelAuditSummary).toHaveClass("md:hidden");
    expect(
      within(funnelAuditSummary).getByText("2,412 records"),
    ).toBeInTheDocument();
    expect(within(funnelAuditSummary).getByText("99.8%")).toBeInTheDocument();
    expect(
      within(funnelAuditSummary).getByText("5 patents"),
    ).toBeInTheDocument();
    const funnelAuditCards = screen.getByTestId(
      "sample-funnel-audit-card-list",
    );
    expect(funnelAuditCards).toHaveClass("md:hidden");
    expect(within(funnelAuditCards).getByText("Stage 02")).toBeInTheDocument();
    expect(
      within(funnelAuditCards).getByText("Hard Filter"),
    ).toBeInTheDocument();
    expect(within(funnelAuditCards).getByText("2,105")).toBeInTheDocument();
    expect(
      within(funnelAuditCards).getByText(
        "Jurisdiction, family, publication, and scope filters remove records that cannot support the question.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Search funnel chart")).toBeInTheDocument();
    expect(screen.getByText("Timing profile chart")).toBeInTheDocument();
    expect(
      screen.getByText(
        /not evidence of production speed, cost, service level/i,
      ),
    ).toBeInTheDocument();

    const verificationLimits = screen.getByTestId("sample-verification-limits");
    expect(
      within(verificationLimits).getByRole("heading", {
        name: "What the fictional checks show and what counsel must still review",
      }),
    ).toBeInTheDocument();
    expect(
      within(verificationLimits).getByText("Internally consistent in sample"),
    ).toBeInTheDocument();
    expect(
      within(verificationLimits).getByText("Review warning in sample"),
    ).toBeInTheDocument();
    expect(
      within(verificationLimits).queryByText(/^pass$/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/^met$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^partially met$/i)).not.toBeInTheDocument();
    expect(
      screen.getAllByText(/Mapped in fictional sample/i).length,
    ).toBeGreaterThan(0);
    expect(
      within(verificationLimits).getByText(
        "Doctrine of equivalents consistency",
      ),
    ).toBeInTheDocument();
    expect(within(verificationLimits).getByText("patcid")).toBeInTheDocument();
    expect(
      within(verificationLimits).getByText(
        "PatCID API returned 503 Service Unavailable.",
      ),
    ).toBeInTheDocument();
  });
});
