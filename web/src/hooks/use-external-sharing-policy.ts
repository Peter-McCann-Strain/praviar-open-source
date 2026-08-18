"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuthToken } from "@/hooks/use-auth-token";
import { APIError, apiClient } from "@/lib/api-client";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import {
  authScopedQueryKey,
  invalidateAuthScopedQueries,
} from "@/lib/query-keys";

export type ExternalSharingPolicyMode = "open" | "approved_domains_only";

export interface ExternalSharingPolicy {
  mode: ExternalSharingPolicyMode;
  approved_domains: string[];
  version: number;
}

export interface ExternalSharingPolicyUpdate extends ExternalSharingPolicy {
  status: "confirmation_required" | "applied";
  impact: {
    active_grant_count: number;
    pending_grant_count: number;
    total_grant_count: number;
  };
  proposal_digest: string | null;
  revoked_grant_count: number;
}

let demoPolicy: ExternalSharingPolicy = {
  mode: "approved_domains_only",
  approved_domains: [],
  version: 1,
};

const DEMO_POLICY_PROPOSAL_DIGEST = "d".repeat(64);

function demoPolicyImpact(): ExternalSharingPolicyUpdate["impact"] {
  return {
    active_grant_count: 1,
    pending_grant_count: 1,
    total_grant_count: 2,
  };
}

function isDestructiveDemoPolicyChange(
  current: ExternalSharingPolicy,
  proposal: ExternalSharingPolicyPatch,
): boolean {
  if (proposal.mode !== "approved_domains_only") return false;
  return (
    current.mode === "open" ||
    current.approved_domains.some(
      (domain) => !proposal.approved_domains.includes(domain),
    )
  );
}

export interface ExternalSharingPolicyPatch {
  mode: ExternalSharingPolicyMode;
  approved_domains: string[];
  expected_version: number;
  confirm_destructive: boolean;
  proposal_digest?: string;
}

export function useExternalSharingPolicy() {
  const token = useAuthToken();
  return useQuery({
    queryKey: authScopedQueryKey(
      ["admin", "external-sharing-policy"] as const,
      token,
    ),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) return Promise.resolve(demoPolicy);
      return apiClient<ExternalSharingPolicy>(
        "/admin/external-sharing-policy",
        {
          token: token || undefined,
          signal,
        },
      );
    },
    enabled: DEMO_MODE_ENABLED || Boolean(token),
    staleTime: 30_000,
  });
}

export function useUpdateExternalSharingPolicy() {
  const token = useAuthToken();
  const queryClient = useQueryClient();
  return useMutation({
    meta: { suppressGlobalErrorToast: true },
    mutationFn: (policy: ExternalSharingPolicyPatch) => {
      if (DEMO_MODE_ENABLED) {
        if (policy.expected_version !== demoPolicy.version) {
          return Promise.reject(
            new APIError(
              409,
              "Policy version conflict",
              "The synthetic policy changed while it was being reviewed",
            ),
          );
        }
        const destructive = isDestructiveDemoPolicyChange(demoPolicy, policy);
        if (destructive && !policy.confirm_destructive) {
          return Promise.resolve<ExternalSharingPolicyUpdate>({
            mode: policy.mode,
            approved_domains: policy.approved_domains,
            version: demoPolicy.version,
            status: "confirmation_required",
            impact: demoPolicyImpact(),
            proposal_digest: DEMO_POLICY_PROPOSAL_DIGEST,
            revoked_grant_count: 0,
          });
        }
        if (
          destructive &&
          policy.proposal_digest !== DEMO_POLICY_PROPOSAL_DIGEST
        ) {
          return Promise.reject(
            new APIError(
              409,
              "Policy proposal conflict",
              "The synthetic recipient impact preview must be reviewed again",
            ),
          );
        }
        demoPolicy = {
          mode: policy.mode,
          approved_domains:
            policy.mode === "open" ? [] : policy.approved_domains,
          version: policy.expected_version + 1,
        };
        return Promise.resolve<ExternalSharingPolicyUpdate>({
          ...demoPolicy,
          status: "applied",
          impact: destructive
            ? demoPolicyImpact()
            : {
                active_grant_count: 0,
                pending_grant_count: 0,
                total_grant_count: 0,
              },
          proposal_digest: null,
          revoked_grant_count: destructive ? 2 : 0,
        });
      }
      return apiClient<ExternalSharingPolicyUpdate>(
        "/admin/external-sharing-policy",
        {
          token: token || undefined,
          method: "PATCH",
          body: JSON.stringify(policy),
        },
      );
    },
    onSuccess: (updated) => {
      if (updated.status !== "applied") return;
      queryClient.setQueryData(
        authScopedQueryKey(
          ["admin", "external-sharing-policy"] as const,
          token,
        ),
        {
          mode: updated.mode,
          approved_domains: updated.approved_domains,
          version: updated.version,
        } satisfies ExternalSharingPolicy,
      );
      invalidateAuthScopedQueries(
        queryClient,
        ["admin", "external-sharing-policy"],
        token,
      );
    },
  });
}
