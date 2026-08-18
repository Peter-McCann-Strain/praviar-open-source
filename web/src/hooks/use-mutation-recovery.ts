"use client";

import { useCallback, useRef, useState } from "react";

import { useAuthBoundaryReset } from "@/hooks/use-auth-boundary-reset";
import { APIError } from "@/lib/api-client";
import { getAuthBoundaryVersion } from "@/lib/auth-events";

export type MutationRecoveryMode = "failed" | "outcome-unknown";

export interface MutationRecoveryState<TVariables> {
  mode: MutationRecoveryMode;
  variables: TVariables;
}

export interface MutationRecoveryAttempt {
  authBoundaryVersion: number;
  sequence: number;
}

function errorStatus(error: unknown): number | null {
  if (error instanceof APIError) {
    return error.status;
  }
  if (typeof error === "object" && error !== null && "status" in error) {
    const status = (error as { status?: unknown }).status;
    return typeof status === "number" ? status : null;
  }
  return null;
}

export function getMutationRecoveryMode(error: unknown): MutationRecoveryMode {
  const status = errorStatus(error);
  if (status !== null) {
    return status === 408 || status >= 500 ? "outcome-unknown" : "failed";
  }

  if (error instanceof Error) {
    const message = error.message.toLowerCase();
    if (
      message.includes("require a token") ||
      message.includes("authentication required") ||
      message.includes("api client is unavailable")
    ) {
      return "failed";
    }
  }

  return "outcome-unknown";
}

export function useMutationRecovery<TVariables>() {
  const [recovery, setRecovery] =
    useState<MutationRecoveryState<TVariables> | null>(null);
  const latestAttemptSequenceRef = useRef(0);
  const clearRecovery = useCallback(() => {
    latestAttemptSequenceRef.current += 1;
    setRecovery(null);
  }, []);
  const resetForAuthBoundary = useCallback(() => {
    latestAttemptSequenceRef.current += 1;
    setRecovery(null);
  }, []);
  useAuthBoundaryReset(resetForAuthBoundary);

  const beginAttempt = useCallback((): MutationRecoveryAttempt => {
    return {
      authBoundaryVersion: getAuthBoundaryVersion(),
      sequence: latestAttemptSequenceRef.current,
    };
  }, []);

  const isAttemptCurrent = useCallback((attempt: MutationRecoveryAttempt) => {
    return (
      attempt.authBoundaryVersion === getAuthBoundaryVersion() &&
      attempt.sequence === latestAttemptSequenceRef.current
    );
  }, []);

  const clearRecoveryForAttempt = useCallback(
    (attempt: MutationRecoveryAttempt) => {
      if (!isAttemptCurrent(attempt)) return false;
      setRecovery(null);
      return true;
    },
    [isAttemptCurrent],
  );

  const captureFailure = useCallback(
    (
      error: unknown,
      variables: TVariables,
      attempt: MutationRecoveryAttempt,
      mode = getMutationRecoveryMode(error),
    ) => {
      if (!isAttemptCurrent(attempt)) return false;
      setRecovery({ mode, variables });
      return true;
    },
    [isAttemptCurrent],
  );

  return {
    recovery,
    beginAttempt,
    captureFailure,
    clearRecovery,
    clearRecoveryForAttempt,
    isAttemptCurrent,
  };
}
