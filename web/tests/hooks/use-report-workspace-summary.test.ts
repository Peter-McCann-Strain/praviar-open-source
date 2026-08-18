import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api-client", () => ({ apiClient: vi.fn() }));
vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "test-token",
}));
vi.mock("@/lib/constants", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/constants")>("@/lib/constants");

  return {
    ...actual,
    DEMO_MODE_ENABLED: true,
    DEV_AUTH_BYPASS_ENABLED: true,
  };
});

import { useReportWorkspaceSummary } from "@/hooks/use-report-workspace-summary";
import { apiClient } from "@/lib/api-client";

const mockApiClient = vi.mocked(apiClient);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children,
    );
  };
}

describe("useReportWorkspaceSummary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches the workspace summary with auth token", async () => {
    const providerCapabilities = [
      {
        provider_name: "Report-derived evidence layer",
        provider_class: "report_derived",
        provider_status: "active",
        live_retrieval_supported: false,
        modality_coverage: ["small_molecule"],
        jurisdiction_coverage: ["US", "EP"],
        governance_note:
          "Search runs against evidence already captured in this report.",
      },
    ];
    const mockSummary = {
      analysis_id: "analysis-1",
      report_id: "report-1",
      trust_mode: "counsel",
      report_summary: {
        overall_risk: "high",
        blocking_patents_count: 3,
        total_patents_found: 12,
        executive_summary: "Summary text",
      },
      capability_metadata: {
        trust_mode: "counsel",
        capability_profile: "report_grounded",
      },
      suggested_evidence_queries: [
        {
          kind: "compound",
          query: "aspirin patent",
          rationale: "Baseline query",
          source: "compound.name",
        },
      ],
      monitor_seed_defaults: {
        analysis_id: "analysis-1",
        compound_name: "Aspirin",
        compound_smiles: "CC(=O)Oc1ccccc1C(=O)O",
        schedule: "weekly",
        source_report_id: "report-1",
        source_trust_mode: "counsel",
        requires_manual_input: false,
        missing_fields: [],
      },
      routing_profile: {
        modality: "small_molecule",
      },
      opinion_readiness: {
        export_ready: true,
      },
      data_coverage: {
        sources: 4,
      },
      source_convergence: {
        score: 0.9,
      },
      uncertainty_register: [],
      evidence_scope: {
        mode: "report_evidence",
        external_live_retrieval: false,
        comment_routing_available: true,
        sources_considered: ["patentsview", "pubchem_sdq"],
        governed_note: "Report-derived evidence only.",
        provider_capabilities: providerCapabilities,
        providers: providerCapabilities,
        hybrid_evidence_ready: false,
      },
    };
    mockApiClient.mockResolvedValueOnce(mockSummary);

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useReportWorkspaceSummary("analysis-1"),
      {
        wrapper,
      },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(mockSummary);
    expect(result.current.data).toMatchObject({
      evidence_scope: {
        provider_capabilities: providerCapabilities,
        providers: providerCapabilities,
        hybrid_evidence_ready: false,
      },
    });
    expect(result.current.error).toBeNull();
    expect(result.current.refetch).toEqual(expect.any(Function));
    expect(mockApiClient).toHaveBeenCalledWith(
      "/reports/analysis-1/workspace-summary",
      expect.objectContaining({
        token: "test-token",
      }),
    );
  });

  it("serves local demo workspace summaries without an API request", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useReportWorkspaceSummary("ana_demo_001"),
      {
        wrapper,
      },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toMatchObject({
      analysis_id: "ana_demo_001",
      report_id: "rpt_ana_demo_001",
      trust_mode: "counsel",
      evidence_scope: {
        mode: "report_evidence",
        external_live_retrieval: false,
      },
      opinion_readiness: {
        export_ready: false,
      },
    });
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("preserves the providers alias in evidence_scope when canonical provider_capabilities is absent", async () => {
    const providers = [
      {
        provider_name: "Licensed overlay placeholder",
        provider_class: "licensed_overlay",
        provider_status: "declared_only",
        live_retrieval_supported: false,
        modality_coverage: ["small_molecule", "markush_candidate"],
        jurisdiction_coverage: ["US", "EP", "JP"],
        governance_note:
          "Declared for future governed retrieval, not active in this workspace.",
      },
    ];
    mockApiClient.mockResolvedValueOnce({
      analysis_id: "analysis-1",
      report_id: "report-1",
      trust_mode: "counsel",
      report_summary: {
        overall_risk: "medium",
        blocking_patents_count: 1,
        total_patents_found: 5,
        executive_summary: "Summary text",
      },
      capability_metadata: {
        trust_mode: "counsel",
        capability_profile: "report_grounded",
      },
      suggested_evidence_queries: [],
      monitor_seed_defaults: {
        analysis_id: "analysis-1",
        compound_name: "Aspirin",
        compound_smiles: "CC(=O)Oc1ccccc1C(=O)O",
        schedule: "weekly",
        source_report_id: "report-1",
        source_trust_mode: "counsel",
        requires_manual_input: false,
        missing_fields: [],
      },
      routing_profile: {
        modality: "small_molecule",
      },
      opinion_readiness: {
        export_ready: true,
      },
      data_coverage: {
        sources: 4,
      },
      source_convergence: {
        score: 0.9,
      },
      uncertainty_register: [],
      evidence_scope: {
        mode: "hybrid_evidence",
        providers,
        hybrid_evidence_ready: true,
      },
    });

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useReportWorkspaceSummary("analysis-1"),
      {
        wrapper,
      },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toMatchObject({
      evidence_scope: {
        providers,
        hybrid_evidence_ready: true,
      },
    });
    expect(
      result.current.data?.evidence_scope.providers[0]?.provider_status,
    ).toBe("declared_only");
  });

  it("surfaces an error when the workspace summary request fails", async () => {
    mockApiClient.mockRejectedValueOnce(
      new Error("Workspace summary unavailable"),
    );

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useReportWorkspaceSummary("analysis-1"),
      {
        wrapper,
      },
    );

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.data).toBeUndefined();
    expect(result.current.error?.message).toBe("Workspace summary unavailable");
    expect(result.current.refetch).toEqual(expect.any(Function));
  });
});
