"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import {
  authScopedQueryKey,
  invalidateAuthScopedQueries,
} from "@/lib/query-keys";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import type { PipelineConfig } from "@/types/pipeline";

interface ConfigPreset {
  id: string;
  name: string;
  description: string;
  config: Partial<PipelineConfig>;
  is_default: boolean;
}

interface OrgDefaultsResponse {
  config: Partial<PipelineConfig>;
  can_manage: boolean;
}

export function useConfigPresets(token: string | null) {
  return useQuery({
    queryKey: authScopedQueryKey(["config-presets"] as const, token),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve<ConfigPreset[]>([]);
      }
      return apiClient<ConfigPreset[]>("/configs/presets", {
        token: token || undefined,
        signal,
      });
    },
    enabled: DEMO_MODE_ENABLED || !!token,
  });
}

export function useOrgDefaultConfig(token: string | null) {
  return useQuery({
    queryKey: authScopedQueryKey(["config-defaults"] as const, token),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve<OrgDefaultsResponse>({
          config: {},
          can_manage: true,
        });
      }
      return apiClient<OrgDefaultsResponse>("/configs/defaults", {
        token: token || undefined,
        signal,
      });
    },
    enabled: DEMO_MODE_ENABLED || !!token,
  });
}

export function useCreatePreset(token: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: {
      name: string;
      description?: string;
      config: Partial<PipelineConfig>;
    }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve({
          id: `demo-${data.name.toLowerCase().replaceAll(/\s+/g, "-")}`,
        });
      }
      return apiClient<{ id: string }>("/configs/presets", {
        method: "POST",
        body: JSON.stringify(data),
        token: token || undefined,
      });
    },
    onSuccess: () => {
      invalidateAuthScopedQueries(queryClient, ["config-presets"], token);
    },
  });
}
