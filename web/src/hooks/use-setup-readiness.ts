"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import { authScopedQueryKey } from "@/lib/query-keys";

export type SetupReadinessItemStatus =
  | "complete"
  | "action_required"
  | "blocked"
  | "not_required";

export interface SetupReadinessItem {
  id:
    | "identity"
    | "collaborators"
    | "evidence_policy"
    | "billing"
    | "sso"
    | "first_analysis"
    | "review_handoff"
    | "share_export";
  label: string;
  description: string;
  status: SetupReadinessItemStatus;
  owner: string;
  recovery_label: string;
  recovery_href: string | null;
  evidence: string;
}

export interface SetupReadiness {
  overall_status: "ready" | "action_required";
  current_user_role: "admin" | "attorney" | "scientist" | "client";
  completed_items: number;
  applicable_items: number;
  items: SetupReadinessItem[];
  observed_at: string;
}

const DEMO_SETUP_READINESS: SetupReadiness = {
  overall_status: "action_required",
  current_user_role: "admin",
  completed_items: 6,
  applicable_items: 7,
  observed_at: "2026-07-13T10:00:00.000Z",
  items: [
    ["identity", "Identity and organization", "Workspace administrator"],
    ["collaborators", "Collaborators and roles", "Workspace administrator"],
    [
      "evidence_policy",
      "Default evidence policy",
      "Attorney or workspace administrator",
    ],
    ["billing", "Billing capacity", "Workspace administrator"],
    ["first_analysis", "First analysis", "Analysis team"],
    ["review_handoff", "Review handoff", "Reviewer or counsel"],
  ].map(([id, label, owner]) => ({
    id: id as SetupReadinessItem["id"],
    label,
    owner,
    description: "Persisted demo-workspace evidence is available.",
    status: "complete" as const,
    recovery_label: "Review evidence",
    recovery_href: "/dashboard",
    evidence: "Verified in the seeded demo workspace.",
  })),
};

DEMO_SETUP_READINESS.items.push(
  {
    id: "sso",
    label: "Single sign-on",
    description: "Complete SSO enrollment when required by workspace policy.",
    status: "not_required",
    owner: "Workspace administrator",
    recovery_label: "Review sign-on controls",
    recovery_href: "/settings#single-sign-on",
    evidence: "SSO is not required by the seeded demo workspace policy.",
  },
  {
    id: "share_export",
    label: "Share or export",
    description: "Prove the governed delivery path.",
    status: "action_required",
    owner: "Attorney or analysis team",
    recovery_label: "Open completed analyses",
    recovery_href: "/analyses?status=completed",
    evidence: "No completed demo delivery has been recorded in this session.",
  },
);

export function useSetupReadiness(token: string | null) {
  return useQuery({
    queryKey: authScopedQueryKey(["setup-readiness"] as const, token),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(DEMO_SETUP_READINESS);
      }
      return apiClient<SetupReadiness>("/setup-readiness", {
        token: token || undefined,
        signal,
      });
    },
    enabled: DEMO_MODE_ENABLED || !!token,
    initialData: DEMO_MODE_ENABLED ? DEMO_SETUP_READINESS : undefined,
  });
}
