import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  useCreateReviewerDecision,
  useReviewerDecisions,
} from "@/hooks/use-reviewer-decisions";
import { resetDemoReviewerDecisions } from "@/lib/demo-reviewer-decisions";

const apiMock = vi.fn();

vi.mock("@/lib/api-client", () => ({
  apiClient: (...args: unknown[]) => apiMock(...args),
}));

vi.mock("@/lib/constants", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/constants")>()),
  DEMO_MODE_ENABLED: true,
}));

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const Provider = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  Provider.displayName = "DemoReviewerDecisionTestProvider";
  return Provider;
}

describe("demo reviewer-decision hooks", () => {
  beforeEach(() => {
    apiMock.mockReset();
    resetDemoReviewerDecisions();
  });

  it("keeps a mutation after auth-scoped cache invalidation without an API call", async () => {
    const { result } = renderHook(
      () => ({
        decisions: useReviewerDecisions("ana_demo_001", null),
        create: useCreateReviewerDecision("ana_demo_001", null),
      }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => {
      expect(result.current.decisions.data?.counts).toEqual({
        accept: 0,
        reject: 0,
        edit: 1,
      });
    });

    await act(async () => {
      await result.current.create.mutateAsync({
        finding_type: "patent",
        finding_ref: "XX-FICTION-0001-A1",
        decision: "reject",
        note: "Synthetic decision saved for the deterministic gallery state.",
      });
    });

    await waitFor(() => {
      expect(result.current.decisions.data?.counts).toEqual({
        accept: 0,
        reject: 1,
        edit: 1,
      });
    });
    expect(result.current.decisions.data?.items.at(-1)).toMatchObject({
      id: "reviewer-decision-fictional-2",
      finding_ref: "XX-FICTION-0001-A1",
      decision: "reject",
      reviewer_email: "reviewer@fictional.invalid",
    });
    expect(apiMock).not.toHaveBeenCalled();
  });
});
