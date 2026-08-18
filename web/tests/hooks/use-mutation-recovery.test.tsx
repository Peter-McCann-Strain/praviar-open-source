import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  getMutationRecoveryMode,
  useMutationRecovery,
} from "@/hooks/use-mutation-recovery";
import { emitAuthBoundaryChanged } from "@/lib/auth-events";
import { APIError } from "@/lib/api-client";

describe("useMutationRecovery", () => {
  it("classifies definitive API rejections separately from unknown outcomes", () => {
    expect(getMutationRecoveryMode(new APIError(422, "Invalid"))).toBe(
      "failed",
    );
    expect(getMutationRecoveryMode(new APIError(503, "Unavailable"))).toBe(
      "outcome-unknown",
    );
    expect(getMutationRecoveryMode(new Error("network connection lost"))).toBe(
      "outcome-unknown",
    );
    expect(
      getMutationRecoveryMode(
        new Error("Authenticated monitor updates require a token."),
      ),
    ).toBe("failed");
  });

  it("preserves the exact mutation variables without retaining the raw error", () => {
    const variables = {
      monitorId: "monitor-1",
      data: { is_active: false },
    };
    const { result } = renderHook(() =>
      useMutationRecovery<typeof variables>(),
    );
    const attempt = result.current.beginAttempt();

    act(() => {
      result.current.captureFailure(
        new Error("network outcome unknown"),
        variables,
        attempt,
      );
    });

    expect(result.current.recovery).toEqual({
      mode: "outcome-unknown",
      variables,
    });
    expect(result.current.recovery?.variables).toBe(variables);
    expect(result.current.recovery).not.toHaveProperty("error");
  });

  it("clears recovery state on explicit and auth-boundary resets", () => {
    const { result } = renderHook(() => useMutationRecovery<string>());
    let attempt = result.current.beginAttempt();

    act(() => {
      result.current.captureFailure(
        new APIError(409, "Conflict"),
        "key-1",
        attempt,
      );
    });
    expect(result.current.recovery?.mode).toBe("failed");

    act(() => {
      result.current.clearRecovery();
    });
    expect(result.current.recovery).toBeNull();

    act(() => {
      attempt = result.current.beginAttempt();
      result.current.captureFailure(new Error("timeout"), "key-2", attempt);
      emitAuthBoundaryChanged({ refreshToken: false });
    });
    expect(result.current.recovery).toBeNull();
  });

  it("ignores a late failure callback from an attempt started before an auth boundary switch", () => {
    const { result } = renderHook(() =>
      useMutationRecovery<{ organizationLabel: string }>(),
    );
    const oldAttempt = result.current.beginAttempt();

    act(() => {
      emitAuthBoundaryChanged({ refreshToken: false });
    });

    act(() => {
      result.current.captureFailure(
        new Error("old organization request aborted late"),
        { organizationLabel: "Old organization" },
        oldAttempt,
      );
    });

    expect(result.current.recovery).toBeNull();

    const currentAttempt = result.current.beginAttempt();
    act(() => {
      result.current.captureFailure(
        new Error("current organization network failure"),
        { organizationLabel: "Current organization" },
        currentAttempt,
      );
    });

    expect(result.current.recovery).toEqual({
      mode: "outcome-unknown",
      variables: { organizationLabel: "Current organization" },
    });
  });

  it("invalidates late callbacks when a recovery flow is explicitly dismissed", () => {
    const { result } = renderHook(() => useMutationRecovery<string>());
    const dismissedAttempt = result.current.beginAttempt();

    act(() => {
      result.current.clearRecovery();
      result.current.captureFailure(
        new Error("late callback after dismissal"),
        "dismissed-operation",
        dismissedAttempt,
      );
    });

    expect(result.current.recovery).toBeNull();
  });
});
