"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { createPipelineStream, type PipelineEvent } from "@/lib/sse-client";
import { getAuthBoundaryVersion, isAuthTokenAccepted } from "@/lib/auth-events";
import { invalidateAuthScopedQueries } from "@/lib/query-keys";
import { logError } from "@/lib/error-logger";
import {
  PIPELINE_CANCELLED_MESSAGE,
  PIPELINE_FAILED_MESSAGE,
  PIPELINE_STREAM_ERROR_MESSAGE,
} from "@/hooks/report-interaction-copy";
import { usePipelineStore } from "@/stores/pipeline-store";
import { useToastStore } from "@/stores/toast-store";

export function usePipelineStream(
  analysisId: string | null,
  token: string | null,
) {
  const cleanup = useRef<(() => void) | null>(null);
  const queryClient = useQueryClient();
  // Bumped when the server times out the live stream while the pipeline is
  // still running, to force the connecting effect to open a fresh stream.
  const [reconnectNonce, setReconnectNonce] = useState(0);
  const {
    setStepStatus,
    setStepProgress,
    setComplete,
    setError,
    setCheckpoint,
    initSteps,
  } = usePipelineStore();
  const addToast = useToastStore((s) => s.addToast);
  const addToastRef = useRef(addToast);
  useEffect(() => {
    addToastRef.current = addToast;
  }, [addToast]);

  // Keep the latest token and handler in refs so the connecting effect can
  // depend only on [analysisId]. A Clerk token refresh mints a new JWT string
  // every ~50 s; without this, the effect would tear down and reconnect the SSE
  // stream on every refresh, causing visible stutter and a full history replay.
  const tokenRef = useRef(token);
  useLayoutEffect(() => {
    tokenRef.current = token;
  }, [token]);

  const handleEvent = useCallback(
    (event: PipelineEvent) => {
      const currentToken = tokenRef.current;
      switch (event.type) {
        case "started":
          setStepStatus(event.step, "running", {
            description: event.payload.description,
          });
          if (event.step > 1) {
            setStepStatus(event.step - 1, "completed");
          }
          break;

        case "progress":
          setStepProgress(event.step, event.payload);
          break;

        case "completed":
          setStepStatus(event.step, "completed");
          if (event.payload.overall_risk) {
            setComplete(event.payload.overall_risk);
          }
          // Invalidate queries so the analyses list and report reflect completion,
          // regardless of whether overall_risk is present in the event payload.
          invalidateAuthScopedQueries(queryClient, ["analyses"], currentToken);
          invalidateAuthScopedQueries(
            queryClient,
            ["reports", analysisId],
            currentToken,
          );
          break;

        case "failed":
          setStepStatus(event.step, "failed");
          if (event.payload.error) {
            logError(new Error("Pipeline reported a processing failure"), {
              source: "usePipelineStream.failed",
              extra: { analysisId, step: event.step },
            });
          }
          setError(PIPELINE_FAILED_MESSAGE);
          invalidateAuthScopedQueries(queryClient, ["analyses"], currentToken);
          invalidateAuthScopedQueries(
            queryClient,
            ["reports", analysisId],
            currentToken,
          );
          break;

        case "cancelled":
          // A cancel (e.g. user cancel or batch cancel from another tab) is
          // terminal. The cancelled event carries step 0, so do not route it
          // through setStepStatus (which only accepts steps 1-8). Surface the
          // stop reason and refetch so the analysis status flips from "running"
          // to "cancelled" without a manual reload.
          if (event.payload.message) {
            logError(new Error("Pipeline reported a cancellation"), {
              source: "usePipelineStream.cancelled",
              extra: { analysisId },
              level: "info",
            });
          }
          setError(PIPELINE_CANCELLED_MESSAGE);
          invalidateAuthScopedQueries(queryClient, ["analyses"], currentToken);
          invalidateAuthScopedQueries(
            queryClient,
            ["reports", analysisId],
            currentToken,
          );
          break;

        case "timeout":
          // The live stream timed out, but the pipeline may still be running
          // server-side. Do not assert a hard error; refetch the analysis so
          // the UI reconciles to the true status (terminal rows render their
          // final state).
          invalidateAuthScopedQueries(queryClient, ["analyses"], currentToken);
          // The SSE client treats "timeout" as terminal and stops without
          // reconnecting (the server closed that stream). But useAnalysis stops
          // polling once status is "running" — SSE is then the only source of
          // progress. If the pipeline is still running, simply refetching leaves
          // the UI frozen with no live updates and no polling until the user
          // navigates away. Bump the nonce so the connecting effect re-runs and
          // opens a fresh stream (which replays history and resumes updates).
          // A genuinely finished/terminal pipeline will replay its final state
          // and end immediately, so reconnecting is safe in both cases.
          setReconnectNonce((n) => n + 1);
          break;

        case "checkpoint":
          setCheckpoint({
            checkpoint_id:
              typeof event.payload.checkpoint_id === "string"
                ? event.payload.checkpoint_id
                : undefined,
            checkpoint_type: event.payload.checkpoint_type,
            context: event.payload.context,
            requires_response: event.payload.requires_response,
            timeout_minutes: event.payload.timeout_minutes,
            step: event.step,
            step_name: event.step_name,
            timestamp: event.timestamp,
          });
          break;

        case "review_required":
          setCheckpoint({
            checkpoint_id:
              typeof event.payload.checkpoint_id === "string"
                ? event.payload.checkpoint_id
                : undefined,
            checkpoint_type: event.payload.checkpoint_type,
            context: {
              ...(event.payload.context ?? {}),
              elapsed_seconds: event.payload.elapsed_seconds,
            },
            requires_response: true,
            timeout_minutes: event.payload.timeout_minutes,
            step: event.step,
            step_name: event.step_name,
            timestamp: event.timestamp,
          });
          break;
      }
    },
    [
      analysisId,
      queryClient,
      setStepStatus,
      setStepProgress,
      setComplete,
      setError,
      setCheckpoint,
    ],
  );

  const handleEventRef = useRef(handleEvent);
  useEffect(() => {
    handleEventRef.current = handleEvent;
  }, [handleEvent]);

  useEffect(() => {
    const currentToken = tokenRef.current;
    if (!analysisId || !currentToken) return;
    if (!isAuthTokenAccepted(currentToken)) return;

    const streamBoundaryVersion = getAuthBoundaryVersion();
    initSteps();

    cleanup.current = createPipelineStream(
      analysisId,
      () => tokenRef.current,
      (event) => {
        const t = tokenRef.current;
        if (
          getAuthBoundaryVersion() !== streamBoundaryVersion ||
          !t ||
          !isAuthTokenAccepted(t)
        ) {
          return;
        }
        handleEventRef.current(event);
      },
      (error) => {
        const t = tokenRef.current;
        if (
          getAuthBoundaryVersion() !== streamBoundaryVersion ||
          !t ||
          !isAuthTokenAccepted(t)
        ) {
          return;
        }
        logError(error, {
          source: "usePipelineStream.connection",
          extra: { analysisId },
        });
        setError(PIPELINE_STREAM_ERROR_MESSAGE);
        addToastRef.current(PIPELINE_STREAM_ERROR_MESSAGE, "error");
      },
    );

    return () => {
      cleanup.current?.();
    };
    // Intentionally excludes token — both event guards and reconnect attempts
    // read tokenRef, so a routine JWT refresh neither tears down a healthy
    // stream nor leaves a later reconnect using the expired token. Auth changes
    // are guarded by streamBoundaryVersion and isAuthTokenAccepted.
    // reconnectNonce is included so a server-side stream timeout (handled
    // above) can force a fresh stream while the pipeline is still running.
  }, [analysisId, initSteps, setError, reconnectNonce]);
}
