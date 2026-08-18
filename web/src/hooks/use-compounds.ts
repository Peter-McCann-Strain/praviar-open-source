"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import { listDemoAnalyses } from "@/lib/demo-data";
import {
  authScopeKey,
  authScopedQueryKey,
  keepPreviousDataForAuthScope,
} from "@/lib/query-keys";

// ── Response types (mirrors api/src/api/schemas/compounds.py) ──

export interface CompoundItem {
  id: string;
  canonical_smiles: string;
  inchi_key: string;
  name: string;
  molecular_formula: string;
  molecular_weight: number | null;
  functional_groups: string[];
  pubchem_cid: number | null;
  first_analyzed_at: string;
  analysis_count: number;
}

export interface CompoundListResponse {
  items: CompoundItem[];
  total: number;
  page: number;
  per_page: number;
}

const DEMO_COMPOUND_DETAILS: Record<
  string,
  Omit<
    CompoundItem,
    "id" | "canonical_smiles" | "name" | "first_analyzed_at" | "analysis_count"
  >
> = {
  "succinic acid": {
    inchi_key: "KDYFGRWQOYBRFD-UHFFFAOYSA-N",
    molecular_formula: "C4H6O4",
    molecular_weight: 118.09,
    functional_groups: ["Dicarboxylic acid", "Carboxylic acid"],
    pubchem_cid: 1110,
  },
  ibuprofen: {
    inchi_key: "HEFNNWSXXWATRW-UHFFFAOYSA-N",
    molecular_formula: "C13H18O2",
    molecular_weight: 206.28,
    functional_groups: ["Carboxylic acid", "Aryl alkyl"],
    pubchem_cid: 3672,
  },
  aspirin: {
    inchi_key: "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
    molecular_formula: "C9H8O4",
    molecular_weight: 180.16,
    functional_groups: ["Carboxylic acid", "Ester", "Aromatic"],
    pubchem_cid: 2244,
  },
};

function buildDemoCompoundResponse(
  page: number,
  perPage: number,
  search?: string,
): CompoundListResponse {
  const query = search?.trim().toLowerCase() ?? "";
  const compounds = listDemoAnalyses()
    .filter((analysis) => analysis.status === "completed")
    .map<CompoundItem>((analysis) => {
      const details = DEMO_COMPOUND_DETAILS[
        analysis.compound_name.toLowerCase()
      ] ?? {
        inchi_key: "UNVERIFIED-DEMO-COMPOUND",
        molecular_formula: "",
        molecular_weight: null,
        functional_groups: [],
        pubchem_cid: null,
      };

      return {
        id: `cmp_${analysis.id}`,
        canonical_smiles: analysis.compound_smiles,
        name: analysis.compound_name,
        first_analyzed_at: analysis.created_at,
        analysis_count: analysis.compound_name === "Succinic acid" ? 2 : 1,
        ...details,
      };
    })
    .filter((compound) => {
      if (!query) return true;
      return [
        compound.name,
        compound.canonical_smiles,
        compound.inchi_key,
        compound.molecular_formula,
        String(compound.pubchem_cid ?? ""),
        ...compound.functional_groups,
      ].some((value) => value.toLowerCase().includes(query));
    });
  const safePage = Math.max(1, page);
  const safePerPage = Math.max(1, perPage);
  const start = (safePage - 1) * safePerPage;

  return {
    items: compounds.slice(start, start + safePerPage),
    total: compounds.length,
    page: safePage,
    per_page: safePerPage,
  };
}

// ── Hooks ───────────────────────────────────────────────────────

export function useCompounds(
  token: string | null,
  page = 1,
  perPage = 20,
  search?: string,
) {
  const currentAuthScope = authScopeKey(token);

  return useQuery({
    queryKey: authScopedQueryKey(
      ["compounds", page, perPage, search] as const,
      token,
    ),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(
          buildDemoCompoundResponse(page, perPage, search),
        );
      }
      if (!token) {
        return Promise.reject(
          new Error("Authenticated compound library requests require a token."),
        );
      }
      const params = new URLSearchParams({
        page: String(page),
        per_page: String(perPage),
      });
      if (search) params.set("search", search);
      return apiClient<CompoundListResponse>(`/compounds?${params}`, {
        token,
        signal,
      });
    },
    enabled: DEMO_MODE_ENABLED || !!token,
    initialData: DEMO_MODE_ENABLED
      ? buildDemoCompoundResponse(page, perPage, search)
      : undefined,
    placeholderData:
      DEMO_MODE_ENABLED || token
        ? keepPreviousDataForAuthScope<CompoundListResponse>(currentAuthScope)
        : undefined,
  });
}
