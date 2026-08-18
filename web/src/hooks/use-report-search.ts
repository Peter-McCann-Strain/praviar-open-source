import { useState, useCallback, useEffect, useRef } from "react";
import { apiClient } from "@/lib/api-client";
import { useAuthBoundaryReset } from "@/hooks/use-auth-boundary-reset";
import { logError } from "@/lib/error-logger";
import { buildDemoReportSearchResponse } from "@/lib/demo-report-search";
import { REPORT_SEARCH_ERROR_MESSAGE } from "@/hooks/report-interaction-copy";

export interface ReportSearchResult {
  patent_id: string;
  section: string;
  relevance: number;
  snippet: string;
}

export interface ReportSearchResponse {
  query: string;
  interpreted_query: string;
  results: ReportSearchResult[];
  total: number;
}

interface SearchState {
  query: string;
  results: ReportSearchResult[];
  totalResults: number;
  interpretedQuery: string;
  resultQuery: string;
  failedQuery: string;
  isShowingPreviousResults: boolean;
  isSearching: boolean;
  error: string | null;
}

const EMPTY_SEARCH_STATE: SearchState = {
  query: "",
  results: [],
  totalResults: 0,
  interpretedQuery: "",
  resultQuery: "",
  failedQuery: "",
  isShowingPreviousResults: false,
  isSearching: false,
  error: null,
};

export function useReportSearch(analysisId: string, token: string | null) {
  const [state, setState] = useState<SearchState>(EMPTY_SEARCH_STATE);

  // Monotonic id per search() call. Only the latest request may write results,
  // so a slow earlier request resolving after a newer one cannot overwrite the
  // newer (correct) results. The search bar debounce narrows but does not close
  // the window for overlapping in-flight requests.
  const requestSeqRef = useRef(0);

  // Aborts the in-flight HTTP request when a newer search supersedes it (or on
  // clear/unmount). The requestSeq guard already prevents stale writes, but the
  // controller actually cancels the network request rather than letting it run
  // to completion and waste a server round-trip.
  const inFlightControllerRef = useRef<AbortController | null>(null);

  const clear = useCallback(() => {
    requestSeqRef.current += 1;
    inFlightControllerRef.current?.abort();
    inFlightControllerRef.current = null;
    setState(EMPTY_SEARCH_STATE);
  }, []);

  const authBoundaryGenerationRef = useAuthBoundaryReset(clear);

  // Abort any in-flight search when the hook unmounts (e.g. navigating away).
  useEffect(() => {
    return () => {
      inFlightControllerRef.current?.abort();
    };
  }, []);

  const search = useCallback(
    async (query: string): Promise<ReportSearchResponse | null> => {
      if (!query.trim()) {
        requestSeqRef.current += 1;
        inFlightControllerRef.current?.abort();
        inFlightControllerRef.current = null;
        setState((prev) => ({
          ...prev,
          query: "",
          results: [],
          totalResults: 0,
          interpretedQuery: "",
          resultQuery: "",
          failedQuery: "",
          isShowingPreviousResults: false,
          isSearching: false,
          error: null,
        }));
        return null;
      }
      if (!analysisId) return null;

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

      setState((prev) => ({
        ...prev,
        query,
        failedQuery: "",
        isShowingPreviousResults: false,
        isSearching: true,
        error: null,
      }));

      try {
        const demoResponse = buildDemoReportSearchResponse(analysisId, query);

        if (demoResponse) {
          if (isStale()) return null;
          setState((prev) => ({
            ...prev,
            isSearching: false,
            interpretedQuery: demoResponse.interpreted_query,
            resultQuery: demoResponse.query || query,
            failedQuery: "",
            isShowingPreviousResults: false,
            results: demoResponse.results,
            totalResults: demoResponse.total,
          }));
          return demoResponse;
        }

        if (!token) {
          setState((prev) => ({
            ...prev,
            isSearching: false,
          }));
          return null;
        }

        const response = await apiClient<ReportSearchResponse>(
          `/reports/${analysisId}/search`,
          {
            token: token ?? undefined,
            method: "POST",
            body: JSON.stringify({ query }),
            signal: controller.signal,
          },
        );

        if (isStale()) return null;
        setState((prev) => ({
          ...prev,
          isSearching: false,
          interpretedQuery: response.interpreted_query,
          resultQuery: response.query || query,
          failedQuery: "",
          isShowingPreviousResults: false,
          results: response.results,
          totalResults: response.total,
        }));
        return response;
      } catch (err) {
        if (isStale()) return null;
        // A superseded request that was aborted is expected — never surface it
        // as an error to the user.
        if (err instanceof Error && err.name === "AbortError") return null;
        logError(err, {
          source: "useReportSearch.search",
          extra: { analysisId, query },
        });
        setState((prev) => {
          const hasPreviousResults = prev.results.length > 0;
          return {
            ...prev,
            isSearching: false,
            failedQuery: query,
            isShowingPreviousResults: hasPreviousResults,
            error: REPORT_SEARCH_ERROR_MESSAGE,
          };
        });
        return null;
      } finally {
        if (inFlightControllerRef.current === controller) {
          inFlightControllerRef.current = null;
        }
      }
    },
    [analysisId, authBoundaryGenerationRef, token],
  );

  return { ...state, search, clear };
}
