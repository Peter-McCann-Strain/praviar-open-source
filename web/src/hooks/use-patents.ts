"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import { DEMO_ANALYSIS_ID, getDemoReport } from "@/lib/demo-data";
import {
  authScopeKey,
  authScopedQueryKey,
  keepPreviousDataForAuthScope,
} from "@/lib/query-keys";
import type { RiskLevel } from "@praviar/shared-types";

// ── Response types (mirrors api/src/api/schemas/patents.py) ──────────────

export interface PatentItem {
  id: string;
  patent_number: string;
  title: string;
  assignee: string;
  risk_level?: RiskLevel | string | null;
  cpc_codes: string[];
  expiry_date: string | null;
  analysis_id: string;
  compound_name: string;
}

export interface PatentListResponse {
  items: PatentItem[];
  total: number;
  page: number;
  per_page: number;
}

export type PatentSortOption = "id-asc" | "id-desc" | "risk-desc" | "risk-asc";

const PATENT_RISK_ORDER: Record<string, number> = {
  high: 3,
  medium: 2,
  low: 1,
  clear: 0,
};

function buildDemoPatentItems(): PatentItem[] {
  const report = getDemoReport(DEMO_ANALYSIS_ID);
  if (!report) return [];

  return report.patent_analyses.map((patent, index) => ({
    id: `pat_demo_${index + 1}`,
    patent_number: patent.patent_id,
    title: patent.title,
    assignee: patent.assignee,
    risk_level: patent.risk_level,
    cpc_codes:
      index === 0
        ? ["C12P 7/46", "C12N 15/52"]
        : index === 1
          ? ["C07C 51/43", "C07C 55/10"]
          : ["C12P 7/46"],
    expiry_date: patent.expiry_date ?? null,
    analysis_id: DEMO_ANALYSIS_ID,
    compound_name: report.compound.name,
  }));
}

function buildDemoPatentResponse({
  page,
  perPage,
  riskFilter,
  search,
  sortBy,
}: {
  page: number;
  perPage: number;
  riskFilter?: string;
  search?: string;
  sortBy: PatentSortOption;
}): PatentListResponse {
  const query = search?.trim().toLowerCase() ?? "";
  const filtered = buildDemoPatentItems().filter((patent) => {
    if (
      riskFilter &&
      riskFilter !== "all" &&
      patent.risk_level !== riskFilter
    ) {
      return false;
    }
    if (!query) return true;
    return [
      patent.patent_number,
      patent.title,
      patent.assignee,
      patent.compound_name,
      ...patent.cpc_codes,
    ].some((value) => value.toLowerCase().includes(query));
  });
  filtered.sort((a, b) => comparePatentItems(a, b, sortBy));
  const safePage = Math.max(1, page);
  const safePerPage = Math.max(1, perPage);
  const start = (safePage - 1) * safePerPage;

  return {
    items: filtered.slice(start, start + safePerPage),
    total: filtered.length,
    page: safePage,
    per_page: safePerPage,
  };
}

function comparePatentItems(
  a: PatentItem,
  b: PatentItem,
  sortBy: PatentSortOption,
) {
  switch (sortBy) {
    case "id-asc":
      return a.patent_number.localeCompare(b.patent_number);
    case "id-desc":
      return b.patent_number.localeCompare(a.patent_number);
    case "risk-desc":
      return comparePatentRisk(a, b, "desc");
    case "risk-asc":
      return comparePatentRisk(a, b, "asc");
  }
}

function comparePatentRisk(
  a: PatentItem,
  b: PatentItem,
  direction: "asc" | "desc",
) {
  const aRank = getPatentRiskRank(a.risk_level);
  const bRank = getPatentRiskRank(b.risk_level);
  if (aRank === null && bRank === null) {
    return a.patent_number.localeCompare(b.patent_number);
  }
  if (aRank === null) return 1;
  if (bRank === null) return -1;
  return direction === "asc"
    ? aRank - bRank || a.patent_number.localeCompare(b.patent_number)
    : bRank - aRank || a.patent_number.localeCompare(b.patent_number);
}

function getPatentRiskRank(riskLevel: string | null | undefined) {
  return PATENT_RISK_ORDER[riskLevel?.toLowerCase() ?? ""] ?? null;
}

// ── Hooks ────────────────────────────────────────────────────────────────

export function usePatents(
  token: string | null,
  page = 1,
  perPage = 20,
  riskFilter?: string,
  search?: string,
  sortBy: PatentSortOption = "risk-desc",
) {
  const currentAuthScope = authScopeKey(token);

  return useQuery({
    queryKey: authScopedQueryKey(
      ["patents", page, perPage, riskFilter, search, sortBy] as const,
      token,
    ),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(
          buildDemoPatentResponse({
            page,
            perPage,
            riskFilter,
            search,
            sortBy,
          }),
        );
      }
      if (!token) {
        return Promise.reject(
          new Error("Authenticated patent library requests require a token."),
        );
      }
      const params = new URLSearchParams({
        page: String(page),
        per_page: String(perPage),
        sort_by: sortBy,
      });
      if (riskFilter && riskFilter !== "all")
        params.set("risk_filter", riskFilter);
      if (search) params.set("search", search);
      return apiClient<PatentListResponse>(`/patents?${params}`, {
        token,
        signal,
      });
    },
    enabled: DEMO_MODE_ENABLED || !!token,
    initialData: DEMO_MODE_ENABLED
      ? buildDemoPatentResponse({ page, perPage, riskFilter, search, sortBy })
      : undefined,
    placeholderData:
      DEMO_MODE_ENABLED || token
        ? keepPreviousDataForAuthScope<PatentListResponse>(currentAuthScope)
        : undefined,
  });
}
