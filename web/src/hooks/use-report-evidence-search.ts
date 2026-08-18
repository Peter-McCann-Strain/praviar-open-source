"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "@/lib/api-client";
import { useAuthBoundaryReset } from "@/hooks/use-auth-boundary-reset";
import { useAuthToken } from "@/hooks/use-auth-token";
import { logError } from "@/lib/error-logger";
import { buildDemoEvidenceSearchResponse } from "@/lib/demo-report-search";
import { REPORT_EVIDENCE_SEARCH_ERROR_MESSAGE } from "@/hooks/report-interaction-copy";

export type EvidenceSearchRetrievalMode =
  | "report_evidence"
  | "external_evidence";

export interface EvidenceSearchProvenanceItem {
  label: string;
  value: string;
}

export interface EvidenceSearchFollowUpTarget {
  target_type: "analysis" | "patent" | "claim";
  target_id: string;
  suggested_note: string;
}

export interface EvidenceSearchProviderCapability {
  provider_id?: string;
  provider_name: string;
  provider_class:
    | "report_derived"
    | "public_open"
    | "licensed_overlay"
    | string;
  provider_status?: "active" | "caution_only" | "declared_only" | string;
  live_retrieval_supported: boolean;
  configured?: boolean;
  configured_for_org?: boolean;
  materialized_in_report?: boolean;
  execution_mode?:
    | "placeholder_contract"
    | "report_materialized"
    | "bundled_dataset"
    | "live_api"
    | string;
  modality_coverage: string[];
  jurisdiction_coverage: string[];
  governance_note: string;
  retrieved_at?: string;
  source_as_of?: string;
  dataset_version?: string;
}

export interface EvidenceSearchResult {
  result_id: string;
  title: string;
  summary: string;
  source_name: string;
  authority_tier: string;
  freshness: string;
  artifact_type: string;
  section: string;
  patent_id: string;
  relevance: number;
  provenance: EvidenceSearchProvenanceItem[];
  follow_up_target: EvidenceSearchFollowUpTarget | null;
}

export interface EvidenceSearchScope {
  mode: EvidenceSearchRetrievalMode;
  external_live_retrieval: boolean;
  comment_routing_available: boolean;
  sources_considered: string[];
  governed_note: string;
  provider_capabilities?: EvidenceSearchProviderCapability[];
  providers?: EvidenceSearchProviderCapability[];
  hybrid_evidence_ready?: boolean;
}

export interface EvidenceSearchResponse {
  query: string;
  interpreted_query: string;
  scope: EvidenceSearchScope;
  results: EvidenceSearchResult[];
  total: number;
}

export interface EvidenceSearchOptions {
  retrievalMode?: EvidenceSearchRetrievalMode;
}

export interface UseReportEvidenceSearchReturn {
  data: EvidenceSearchResponse | undefined;
  interpretedQuery: string;
  resultQuery: string;
  failedQuery: string | null;
  isShowingPreviousResults: boolean;
  totalResults: number;
  isSearching: boolean;
  error: string | null;
  search: (query: string, options?: EvidenceSearchOptions) => Promise<void>;
  clear: () => void;
}

export function useReportEvidenceSearch(
  analysisId: string | null,
  tokenOverride?: string | null,
): UseReportEvidenceSearchReturn {
  const authToken = useAuthToken();
  const token = tokenOverride ?? authToken;
  const [data, setData] = useState<EvidenceSearchResponse | undefined>(
    undefined,
  );
  const [interpretedQuery, setInterpretedQuery] = useState("");
  const [resultQuery, setResultQuery] = useState("");
  const [failedQuery, setFailedQuery] = useState<string | null>(null);
  const [isShowingPreviousResults, setIsShowingPreviousResults] =
    useState(false);
  const [totalResults, setTotalResults] = useState(0);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Monotonic id for each search() invocation. Only the most recent request is
  // allowed to write results, so a slow earlier request that resolves after a
  // newer one cannot clobber the newer (correct) results. The debounce in the
  // search bar reduces but does not eliminate overlapping in-flight requests.
  const requestSeqRef = useRef(0);

  // Aborts the in-flight HTTP request when a newer search supersedes it (or on
  // clear/unmount). The requestSeq guard already prevents stale writes; the
  // controller additionally cancels the network request rather than letting a
  // superseded query run to completion.
  const inFlightControllerRef = useRef<AbortController | null>(null);

  const clear = useCallback(() => {
    requestSeqRef.current += 1;
    inFlightControllerRef.current?.abort();
    inFlightControllerRef.current = null;
    setData(undefined);
    setInterpretedQuery("");
    setResultQuery("");
    setFailedQuery(null);
    setIsShowingPreviousResults(false);
    setTotalResults(0);
    setIsSearching(false);
    setError(null);
  }, []);
  const authBoundaryGenerationRef = useAuthBoundaryReset(clear);

  // Abort any in-flight search when the hook unmounts (e.g. navigating away).
  useEffect(() => {
    return () => {
      inFlightControllerRef.current?.abort();
    };
  }, []);

  const search = useCallback(
    async (query: string, options?: EvidenceSearchOptions) => {
      if (!query.trim()) {
        clear();
        return;
      }

      if (!analysisId) {
        return;
      }

      const searchGeneration = authBoundaryGenerationRef.current;
      const requestSeq = (requestSeqRef.current += 1);
      const isStale = () =>
        authBoundaryGenerationRef.current !== searchGeneration ||
        requestSeqRef.current !== requestSeq;

      // Cancel any earlier in-flight search at the network layer before
      // starting a new one.
      inFlightControllerRef.current?.abort();
      const controller = new AbortController();
      inFlightControllerRef.current = controller;

      setIsSearching(true);
      setError(null);
      setFailedQuery(null);
      setIsShowingPreviousResults(false);

      try {
        const retrievalMode = options?.retrievalMode ?? "report_evidence";
        const demoResponse = buildDemoEvidenceSearchResponse(
          analysisId,
          query,
          retrievalMode,
        );

        if (demoResponse) {
          if (isStale()) return;
          setData(demoResponse);
          setInterpretedQuery(demoResponse.interpreted_query);
          setResultQuery(demoResponse.query || query.trim());
          setFailedQuery(null);
          setIsShowingPreviousResults(false);
          setTotalResults(demoResponse.total);
          setIsSearching(false);
          return;
        }

        if (!token) {
          setIsSearching(false);
          return;
        }

        const response = await apiClient<EvidenceSearchResponse>(
          `/reports/${analysisId}/evidence-search`,
          {
            token,
            method: "POST",
            body: JSON.stringify({
              query,
              retrieval_mode: retrievalMode,
            }),
            signal: controller.signal,
          },
        );

        if (isStale()) return;
        setData(response);
        setInterpretedQuery(response.interpreted_query);
        setResultQuery(response.query || query.trim());
        setFailedQuery(null);
        setIsShowingPreviousResults(false);
        setTotalResults(response.total);
        setIsSearching(false);
      } catch (err) {
        if (isStale()) return;
        // A superseded request that was aborted is expected — never surface it
        // as an error to the user.
        if (err instanceof Error && err.name === "AbortError") return;
        logError(err, {
          source: "useReportEvidenceSearch.search",
          extra: { analysisId, query, retrievalMode: options?.retrievalMode },
        });
        setIsSearching(false);
        setError(REPORT_EVIDENCE_SEARCH_ERROR_MESSAGE);
        setFailedQuery(query.trim());
        setIsShowingPreviousResults(Boolean(data?.results?.length));
      } finally {
        if (inFlightControllerRef.current === controller) {
          inFlightControllerRef.current = null;
        }
      }
    },
    [
      analysisId,
      authBoundaryGenerationRef,
      clear,
      data?.results?.length,
      token,
    ],
  );

  return {
    data,
    interpretedQuery,
    resultQuery,
    failedQuery,
    isShowingPreviousResults,
    totalResults,
    isSearching,
    error,
    search,
    clear,
  };
}
