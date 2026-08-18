/**
 * API key management hooks — TanStack Query wrappers for API key endpoints.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { useAuthToken } from "@/hooks/use-auth-token";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import {
  authScopedQueryKey,
  invalidateAuthScopedQueries,
} from "@/lib/query-keys";

type APIKeyScope =
  | "analyses:read"
  | "analyses:write"
  | "reports:read"
  | "reports:export"
  | "monitors:manage";

interface CreateAPIKeyPayload {
  name: string;
  scopes: APIKeyScope[];
  expires_at: string;
}

interface APIKeyResponse {
  id: string;
  name: string;
  key_prefix: string;
  scopes: APIKeyScope[];
  expires_at: string;
  last_used_at: string | null;
  revoked: boolean;
  created_at: string;
}

interface APIKeyCreatedResponse {
  id: string;
  name: string;
  key_prefix: string;
  secret_key: string;
  scopes: APIKeyScope[];
  expires_at: string;
  created_at: string;
}

interface APIKeyListResponse {
  items: APIKeyResponse[];
  total: number;
}

const demoApiKeys: APIKeyResponse[] = [
  {
    id: "key_demo_001",
    name: "Production case workspace API",
    key_prefix: "sg_demo_prod",
    scopes: ["analyses:read", "reports:read"],
    expires_at: "2026-10-20T09:30:00.000Z",
    last_used_at: "2026-04-22T09:30:00.000Z",
    revoked: false,
    created_at: "2026-03-12T10:00:00.000Z",
  },
  {
    id: "key_demo_002",
    name: "Reviewer dashboard read-only",
    key_prefix: "sg_demo_ro",
    scopes: ["analyses:read", "reports:read"],
    expires_at: "2026-08-18T16:00:00.000Z",
    last_used_at: "2026-04-21T16:00:00.000Z",
    revoked: false,
    created_at: "2026-03-20T13:45:00.000Z",
  },
];

export function useAPIKeys(page = 1) {
  const token = useAuthToken();
  return useQuery({
    queryKey: authScopedQueryKey(["api-keys", page] as const, token),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve<APIKeyListResponse>({
          items: demoApiKeys,
          total: demoApiKeys.length,
        });
      }
      return apiClient<APIKeyListResponse>(`/api-keys?page=${page}`, {
        token: token || undefined,
        signal,
      });
    },
    enabled: DEMO_MODE_ENABLED || !!token,
  });
}

export function useCreateAPIKey() {
  const token = useAuthToken();
  const queryClient = useQueryClient();
  return useMutation({
    meta: { suppressGlobalErrorToast: true },
    mutationFn: (data: CreateAPIKeyPayload) => {
      if (DEMO_MODE_ENABLED) {
        const now = new Date().toISOString();
        const id = `key_demo_${demoApiKeys.length + 1}_${Math.random()
          .toString(36)
          .slice(2, 6)}`;
        const created: APIKeyCreatedResponse = {
          id,
          name: data.name,
          key_prefix: "sg_demo",
          secret_key: `sg_demo_${Math.random().toString(36).slice(2, 16)}`,
          scopes: data.scopes,
          expires_at: data.expires_at,
          created_at: now,
        };
        demoApiKeys.push({
          id,
          name: data.name,
          key_prefix: created.key_prefix,
          scopes: data.scopes,
          expires_at: data.expires_at,
          last_used_at: null,
          revoked: false,
          created_at: now,
        });
        return Promise.resolve(created);
      }
      return apiClient<APIKeyCreatedResponse>("/api-keys", {
        token: token || undefined,
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    onSuccess: () => {
      invalidateAuthScopedQueries(queryClient, ["api-keys"], token);
    },
  });
}

export function useRevokeAPIKey() {
  const token = useAuthToken();
  const queryClient = useQueryClient();
  return useMutation({
    meta: { suppressGlobalErrorToast: true },
    mutationFn: (keyId: string) => {
      if (DEMO_MODE_ENABLED) {
        const key = demoApiKeys.find((item) => item.id === keyId);
        if (key) {
          key.revoked = true;
        }
        return Promise.resolve({ status: "revoked" });
      }
      return apiClient(`/api-keys/${keyId}`, {
        token: token || undefined,
        method: "DELETE",
      });
    },
    onSuccess: () => {
      invalidateAuthScopedQueries(queryClient, ["api-keys"], token);
    },
  });
}

export type {
  APIKeyCreatedResponse,
  APIKeyListResponse,
  APIKeyResponse,
  APIKeyScope,
  CreateAPIKeyPayload,
};
