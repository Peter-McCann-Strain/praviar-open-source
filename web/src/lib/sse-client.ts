import {
  API_BASE_URL,
  SSE_INITIAL_RETRY_MS,
  SSE_MAX_RETRY_MS,
  SSE_MAX_RETRIES,
} from "./constants";
import {
  getAuthBoundarySignal,
  getAuthBoundaryVersion,
  isAuthTokenAccepted,
} from "@/lib/auth-events";
import type { PipelineEvent } from "@/types/pipeline";
import { logError } from "@/lib/error-logger";

export type { PipelineEvent };
export type PipelineStreamTokenProvider = () => string | null;

/**
 * Creates an authenticated SSE stream using fetch + ReadableStream.
 * EventSource doesn't support Authorization headers, so we use fetch instead.
 */
function linkAbortSignal(
  source: AbortSignal,
  target: AbortController,
): () => void {
  if (source.aborted) {
    target.abort(source.reason);
    return () => {};
  }
  const handler = () => target.abort(source.reason);
  source.addEventListener("abort", handler, { once: true });
  return () => source.removeEventListener("abort", handler);
}

export function createPipelineStream(
  analysisId: string,
  tokenOrProvider: string | PipelineStreamTokenProvider,
  onEvent: (event: PipelineEvent) => void,
  onError?: (error: Error) => void,
): () => void {
  let abortController: AbortController | null = null;
  let unlinkBoundary: (() => void) | null = null;
  let retryCount = 0;
  let closed = false;
  let retryTimeout: ReturnType<typeof setTimeout> | null = null;
  let generation = 0;
  const maxRetries = SSE_MAX_RETRIES;
  const streamBoundaryVersion = getAuthBoundaryVersion();

  function currentToken(): string | null {
    return typeof tokenOrProvider === "function"
      ? tokenOrProvider()
      : tokenOrProvider;
  }

  function authBoundaryChanged() {
    const token = currentToken();
    return (
      getAuthBoundaryVersion() !== streamBoundaryVersion ||
      !token ||
      !isAuthTokenAccepted(token)
    );
  }

  function scheduleReconnect() {
    if (closed) return;
    if (authBoundaryChanged()) {
      cleanup();
      return;
    }

    if (retryCount < maxRetries) {
      retryCount++;
      const delay = Math.min(
        SSE_INITIAL_RETRY_MS * Math.pow(2, retryCount),
        SSE_MAX_RETRY_MS,
      );
      retryTimeout = setTimeout(connect, delay);
      return;
    }

    const error = new Error("SSE connection failed after max retries");
    logError(error, { source: "SSE", extra: { action: "stream" } });
    cleanup();
    onError?.(error);
  }

  async function connect() {
    if (closed) return;
    if (authBoundaryChanged()) {
      cleanup();
      return;
    }
    const token = currentToken();
    if (!token) {
      cleanup();
      return;
    }

    // Increment generation so any in-flight read loop from a previous connect()
    // call can detect it is stale and exit without calling cleanup().
    const myGeneration = ++generation;

    unlinkBoundary?.();
    abortController = new AbortController();
    unlinkBoundary = linkAbortSignal(getAuthBoundarySignal(), abortController);
    const url = `${API_BASE_URL}/api/v1/analyses/${analysisId}/stream`;

    try {
      const response = await fetch(url, {
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "text/event-stream",
        },
        signal: abortController.signal,
      });

      if (!response.ok) {
        throw new Error(`SSE connection failed: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No readable stream available");

      const decoder = new TextDecoder();
      let buffer = "";
      let dataLines: string[] = [];

      while (!closed) {
        const { done, value } = await reader.read();
        if (myGeneration !== generation) return;
        if (done) break;
        if (authBoundaryChanged()) {
          cleanup();
          return;
        }

        // Any bytes, including SSE comments/heartbeats, prove the replacement
        // connection is alive. A connection that closes before sending bytes
        // keeps the escalating retry count and eventually surfaces an error.
        retryCount = 0;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        // Keep the last incomplete line in the buffer
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (line.startsWith("data:")) {
            dataLines.push(line.slice(5).trim());
          } else if (line.trim() === "" && dataLines.length > 0) {
            // Blank line = end of SSE message
            const data = dataLines.join("\n");
            dataLines = [];
            try {
              const event = JSON.parse(data) as PipelineEvent;
              if (authBoundaryChanged()) {
                cleanup();
                return;
              }
              onEvent(event);
              retryCount = 0;

              // Terminal events end the stream. "completed"/"failed" mark a
              // finished pipeline; "cancelled" stops a running one (the server
              // does not close the channel for cancel, so the client must); and
              // "timeout" means the server intentionally ended this stream, so
              // do not reconnect.
              if (
                event.type === "completed" ||
                event.type === "failed" ||
                event.type === "cancelled" ||
                event.type === "timeout"
              ) {
                cleanup();
                return;
              }
            } catch {
              logError(new Error("SSE event payload could not be parsed"), {
                source: "SSE",
                extra: { action: "parse_event" },
              });
              // Log only — do not call onError for parse failures as it would disconnect the stream
            }
          }
        }
      }

      // A clean EOF without a terminal event is still a transport disconnect.
      // Reconnect instead of leaving a running analysis frozen with no error.
      if (!closed && myGeneration === generation && !authBoundaryChanged()) {
        scheduleReconnect();
      }
    } catch (err) {
      if (closed) return;
      // Stale read loop aborted by a newer connect() call — ignore.
      if (myGeneration !== generation) return;
      if ((err as Error).name === "AbortError" || authBoundaryChanged()) {
        cleanup();
        return;
      }

      scheduleReconnect();
    }
  }

  function cleanup() {
    closed = true;
    if (retryTimeout) {
      clearTimeout(retryTimeout);
      retryTimeout = null;
    }
    unlinkBoundary?.();
    unlinkBoundary = null;
    abortController?.abort();
    document.removeEventListener("visibilitychange", handleVisibilityChange);
  }

  // Reconnect when tab becomes visible again
  function handleVisibilityChange() {
    if (document.visibilityState === "visible" && !closed) {
      if (authBoundaryChanged()) {
        cleanup();
        return;
      }
      if (retryTimeout) {
        clearTimeout(retryTimeout);
        retryTimeout = null;
      }
      abortController?.abort();
      retryCount = 0;
      connect();
    }
  }

  document.addEventListener("visibilitychange", handleVisibilityChange);
  connect();

  return () => {
    document.removeEventListener("visibilitychange", handleVisibilityChange);
    cleanup();
  };
}
