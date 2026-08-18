import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api-client", () => ({ apiClient: vi.fn() }));
vi.mock("@/lib/constants", () => ({
  DEMO_MODE_ENABLED: true,
  DEV_AUTH_BYPASS_ENABLED: false,
}));
vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "test-token",
}));

import { apiClient } from "@/lib/api-client";
import { emitAuthBoundaryChanged } from "@/lib/auth-events";
import { useReportEvidenceSearch } from "@/hooks/use-report-evidence-search";
import { REPORT_EVIDENCE_SEARCH_ERROR_MESSAGE } from "@/hooks/report-interaction-copy";

const mockApiClient = vi.mocked(apiClient);

describe("useReportEvidenceSearch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("starts empty", () => {
    const { result } = renderHook(() => useReportEvidenceSearch("analysis-1"));

    expect(result.current.data).toBeUndefined();
    expect(result.current.interpretedQuery).toBe("");
    expect(result.current.totalResults).toBe(0);
    expect(result.current.resultQuery).toBe("");
    expect(result.current.failedQuery).toBeNull();
    expect(result.current.isShowingPreviousResults).toBe(false);
    expect(result.current.isSearching).toBe(false);
    expect(result.current.error).toBeNull();
    expect(typeof result.current.search).toBe("function");
    expect(typeof result.current.clear).toBe("function");
  });

  it("posts report-grounded evidence searches with the auth token by default", async () => {
    mockApiClient.mockResolvedValueOnce({
      query: "aspirin",
      interpreted_query: "aspirin evidence search",
      scope: {
        mode: "report_evidence",
        external_live_retrieval: false,
        comment_routing_available: true,
        sources_considered: ["evidence_artifacts", "prosecution_dossiers"],
        governed_note: "Report-derived only",
        provider_capabilities: [
          {
            provider_id: "report_derived",
            provider_name: "Report-derived evidence layer",
            provider_class: "report_derived",
            provider_status: "active",
            live_retrieval_supported: false,
            configured: true,
            configured_for_org: true,
            materialized_in_report: true,
            execution_mode: "report_materialized",
            modality_coverage: ["small_molecule"],
            jurisdiction_coverage: ["US", "EPC"],
            governance_note: "Uses report-collected evidence only.",
            source_as_of: "Completed report snapshot",
            dataset_version: "report_record",
          },
        ],
        hybrid_evidence_ready: false,
      },
      results: [
        {
          result_id: "res-1",
          title: "Claim coverage note",
          summary: "Supports the claim interpretation.",
          source_name: "evidence_artifacts",
          authority_tier: "supporting",
          freshness: "current",
          artifact_type: "claim_summary",
          section: "claims",
          patent_id: "US123",
          relevance: 0.92,
          provenance: [
            { label: "artifact_id", value: "art-1" },
            { label: "family_id", value: "fam-1" },
          ],
          follow_up_target: {
            target_type: "analysis",
            target_id: "analysis-1",
            suggested_note: "Review this claim support in context.",
          },
        },
      ],
      total: 1,
    });

    const { result } = renderHook(() => useReportEvidenceSearch("analysis-1"));

    await act(async () => {
      await result.current.search("aspirin");
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/reports/analysis-1/evidence-search",
      expect.objectContaining({
        method: "POST",
        token: "test-token",
      }),
    );

    const [, options] = mockApiClient.mock.calls[0];
    expect(JSON.parse(String(options?.body))).toEqual({
      query: "aspirin",
      retrieval_mode: "report_evidence",
    });
    expect(result.current.data?.results).toHaveLength(1);
    expect(result.current.interpretedQuery).toBe("aspirin evidence search");
    expect(result.current.resultQuery).toBe("aspirin");
    expect(result.current.failedQuery).toBeNull();
    expect(result.current.isShowingPreviousResults).toBe(false);
    expect(result.current.totalResults).toBe(1);
    expect(result.current.data?.scope.provider_capabilities).toEqual([
      {
        provider_id: "report_derived",
        provider_name: "Report-derived evidence layer",
        provider_class: "report_derived",
        provider_status: "active",
        live_retrieval_supported: false,
        configured: true,
        configured_for_org: true,
        materialized_in_report: true,
        execution_mode: "report_materialized",
        modality_coverage: ["small_molecule"],
        jurisdiction_coverage: ["US", "EPC"],
        governance_note: "Uses report-collected evidence only.",
        source_as_of: "Completed report snapshot",
        dataset_version: "report_record",
      },
    ]);
    expect(result.current.data?.scope.hybrid_evidence_ready).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.isSearching).toBe(false);
  });

  it("serves demo evidence searches locally without an API request", async () => {
    const { result } = renderHook(() =>
      useReportEvidenceSearch("ana_demo_001", null),
    );

    await act(async () => {
      await result.current.search("blocking claim", {
        retrievalMode: "report_evidence",
      });
    });

    expect(mockApiClient).not.toHaveBeenCalled();
    expect(result.current.error).toBeNull();
    expect(result.current.failedQuery).toBeNull();
    expect(result.current.data?.query).toBe("blocking claim");
    expect(result.current.data?.scope.external_live_retrieval).toBe(false);
    expect(result.current.data?.scope.comment_routing_available).toBe(true);
    expect(result.current.data?.results.length).toBeGreaterThan(0);
    expect(result.current.data?.results[0]?.patent_id).toBe(
      "XX-FICTION-0001-A1",
    );
    expect(result.current.interpretedQuery).toContain(
      "governed demo evidence snapshot",
    );
    expect(result.current.resultQuery).toBe("blocking claim");
    expect(result.current.totalResults).toBe(
      result.current.data?.results.length,
    );
    expect(result.current.isSearching).toBe(false);
  });

  it("posts governed external expansion requests when requested", async () => {
    mockApiClient.mockResolvedValueOnce({
      query: "celecoxib formulation",
      interpreted_query: "celecoxib formulation external evidence",
      scope: {
        mode: "external_evidence",
        external_live_retrieval: true,
        comment_routing_available: true,
        sources_considered: ["pubchem_sdq", "patentsview"],
        governed_note:
          "External expansion remained inside declared provider policy.",
        provider_capabilities: [
          {
            provider_name: "PubChem SDQ",
            provider_class: "public_open",
            live_retrieval_supported: true,
            modality_coverage: ["small_molecule"],
            jurisdiction_coverage: ["global"],
            governance_note: "Public chemical evidence only.",
          },
        ],
        hybrid_evidence_ready: true,
      },
      results: [],
      total: 0,
    });

    const { result } = renderHook(() => useReportEvidenceSearch("analysis-1"));

    await act(async () => {
      await result.current.search("celecoxib formulation", {
        retrievalMode: "external_evidence",
      });
    });

    const [, options] = mockApiClient.mock.calls[0];
    expect(JSON.parse(String(options?.body))).toEqual({
      query: "celecoxib formulation",
      retrieval_mode: "external_evidence",
    });
    expect(result.current.data?.scope.mode).toBe("external_evidence");
    expect(result.current.data?.scope.external_live_retrieval).toBe(true);
  });

  it("clears state on empty or whitespace-only queries without calling the API", async () => {
    mockApiClient.mockResolvedValueOnce({
      query: "aspirin",
      interpreted_query: "aspirin evidence search",
      scope: {
        mode: "report_evidence",
        external_live_retrieval: false,
        comment_routing_available: true,
        sources_considered: [],
        governed_note: "Report-derived only",
      },
      results: [
        {
          result_id: "res-1",
          title: "Claim coverage note",
          summary: "Supports the claim interpretation.",
          source_name: "evidence_artifacts",
          authority_tier: "supporting",
          freshness: "current",
          artifact_type: "claim_summary",
          section: "claims",
          patent_id: "US123",
          relevance: 0.92,
          provenance: [],
          follow_up_target: null,
        },
      ],
      total: 1,
    });

    const { result } = renderHook(() => useReportEvidenceSearch("analysis-1"));

    await act(async () => {
      await result.current.search("aspirin");
    });

    await act(async () => {
      await result.current.search("   ");
    });

    expect(mockApiClient).toHaveBeenCalledTimes(1);
    expect(result.current.data).toBeUndefined();
    expect(result.current.interpretedQuery).toBe("");
    expect(result.current.totalResults).toBe(0);
    expect(result.current.resultQuery).toBe("");
    expect(result.current.failedQuery).toBeNull();
    expect(result.current.isShowingPreviousResults).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.isSearching).toBe(false);
  });

  it("clear resets all state", async () => {
    mockApiClient.mockResolvedValueOnce({
      query: "aspirin",
      interpreted_query: "aspirin evidence search",
      scope: {
        mode: "report_evidence",
        external_live_retrieval: false,
        comment_routing_available: true,
        sources_considered: [],
        governed_note: "Report-derived only",
      },
      results: [],
      total: 0,
    });

    const { result } = renderHook(() => useReportEvidenceSearch("analysis-1"));

    await act(async () => {
      await result.current.search("aspirin");
    });

    act(() => {
      result.current.clear();
    });

    expect(result.current.data).toBeUndefined();
    expect(result.current.interpretedQuery).toBe("");
    expect(result.current.totalResults).toBe(0);
    expect(result.current.resultQuery).toBe("");
    expect(result.current.failedQuery).toBeNull();
    expect(result.current.isShowingPreviousResults).toBe(false);
    expect(result.current.isSearching).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("surfaces safe errors and preserves prior results when the search fails", async () => {
    const priorResponse = {
      query: "aspirin",
      interpreted_query: "aspirin evidence search",
      scope: {
        mode: "report_evidence",
        external_live_retrieval: false,
        comment_routing_available: true,
        sources_considered: [],
        governed_note: "Report-derived only",
      },
      results: [
        {
          result_id: "res-1",
          title: "Claim coverage note",
          summary: "Supports the claim interpretation.",
          source_name: "evidence_artifacts",
          authority_tier: "supporting",
          freshness: "current",
          artifact_type: "claim_summary",
          section: "claims",
          patent_id: "US123",
          relevance: 0.92,
          provenance: [],
          follow_up_target: null,
        },
      ],
      total: 1,
    };
    mockApiClient.mockResolvedValueOnce(priorResponse);

    const { result } = renderHook(() => useReportEvidenceSearch("analysis-1"));

    await act(async () => {
      await result.current.search("aspirin");
    });

    mockApiClient.mockRejectedValueOnce(
      new Error("postgres://secret-token evidence backend exploded"),
    );

    await act(async () => {
      await result.current.search("celecoxib");
    });

    expect(result.current.data).toEqual(priorResponse);
    expect(result.current.interpretedQuery).toBe("aspirin evidence search");
    expect(result.current.resultQuery).toBe("aspirin");
    expect(result.current.totalResults).toBe(1);
    expect(result.current.isSearching).toBe(false);
    expect(result.current.error).toBe(REPORT_EVIDENCE_SEARCH_ERROR_MESSAGE);
    expect(result.current.error).not.toContain("postgres://secret-token");
    expect(result.current.failedQuery).toBe("celecoxib");
    expect(result.current.isShowingPreviousResults).toBe(true);
  });

  it("clears private evidence-search state on auth boundary changes", async () => {
    mockApiClient.mockResolvedValueOnce({
      query: "aspirin",
      interpreted_query: "aspirin evidence search",
      scope: {
        mode: "report_evidence",
        external_live_retrieval: false,
        comment_routing_available: true,
        sources_considered: [],
        governed_note: "Report-derived only",
      },
      results: [],
      total: 0,
    });
    const { result } = renderHook(() => useReportEvidenceSearch("analysis-1"));

    await act(async () => {
      await result.current.search("aspirin");
    });
    expect(result.current.interpretedQuery).toBe("aspirin evidence search");

    act(() => {
      emitAuthBoundaryChanged({ refreshToken: false });
    });

    expect(result.current.data).toBeUndefined();
    expect(result.current.interpretedQuery).toBe("");
    expect(result.current.totalResults).toBe(0);
    expect(result.current.resultQuery).toBe("");
    expect(result.current.failedQuery).toBeNull();
    expect(result.current.isShowingPreviousResults).toBe(false);
    expect(result.current.isSearching).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("does not repopulate private state when pre-boundary evidence search resolves late", async () => {
    let resolveSearch!: (value: unknown) => void;
    mockApiClient.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveSearch = resolve;
      }) as any,
    );
    const { result } = renderHook(() => useReportEvidenceSearch("analysis-1"));

    act(() => {
      void result.current.search("aspirin");
    });
    expect(result.current.isSearching).toBe(true);

    act(() => {
      emitAuthBoundaryChanged({ refreshToken: false });
    });

    await act(async () => {
      resolveSearch({
        query: "aspirin",
        interpreted_query: "aspirin evidence search",
        scope: {
          mode: "report_evidence",
          external_live_retrieval: false,
          comment_routing_available: true,
          sources_considered: [],
          governed_note: "Report-derived only",
        },
        results: [],
        total: 0,
      });
      await Promise.resolve();
    });

    expect(result.current.data).toBeUndefined();
    expect(result.current.interpretedQuery).toBe("");
    expect(result.current.totalResults).toBe(0);
    expect(result.current.resultQuery).toBe("");
    expect(result.current.failedQuery).toBeNull();
    expect(result.current.isShowingPreviousResults).toBe(false);
    expect(result.current.isSearching).toBe(false);
    expect(result.current.error).toBeNull();
  });
});
