import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createPipelineStream, type PipelineEvent } from "@/lib/sse-client";
import { acceptAuthToken, emitAuthBoundaryChanged } from "@/lib/auth-events";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

// Mock document.addEventListener / removeEventListener for visibility change handling
const mockAddEventListener = vi.fn();
const mockRemoveEventListener = vi.fn();
vi.stubGlobal("document", {
  addEventListener: mockAddEventListener,
  removeEventListener: mockRemoveEventListener,
  visibilityState: "visible",
});

const activeCleanups: Array<() => void> = [];

beforeEach(() => {
  emitAuthBoundaryChanged({ refreshToken: false });
  mockFetch.mockReset();
  mockAddEventListener.mockReset();
  mockRemoveEventListener.mockReset();
  activeCleanups.length = 0;
});

afterEach(() => {
  for (const cleanup of activeCleanups.splice(0)) {
    cleanup();
  }
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function startPipelineStream(
  analysisId: string,
  token: string,
  onEvent: (event: PipelineEvent) => void,
  onError?: (error: Error) => void,
) {
  acceptAuthToken(token);
  const cleanup = createPipelineStream(analysisId, token, onEvent, onError);
  activeCleanups.push(cleanup);
  return cleanup;
}

function streamResponse(chunks: string[]) {
  const encoder = new TextEncoder();
  let index = 0;
  return {
    ok: true,
    body: {
      getReader: () => ({
        read: vi.fn(async () => {
          if (index >= chunks.length) {
            return { done: true, value: undefined };
          }
          return { done: false, value: encoder.encode(chunks[index++]) };
        }),
      }),
    },
  };
}

describe("createPipelineStream", () => {
  it("calls fetch with the correct URL containing the analysis ID", () => {
    // Return a hanging promise so the stream doesn't resolve
    mockFetch.mockReturnValue(new Promise(() => {}));

    startPipelineStream("ana_123", "test-token", vi.fn());

    expect(mockFetch).toHaveBeenCalledOnce();
    const calledUrl = mockFetch.mock.calls[0][0];
    expect(calledUrl).toBe(
      "http://localhost:8000/api/v1/analyses/ana_123/stream",
    );
  });

  it("sets Authorization header with Bearer token", () => {
    mockFetch.mockReturnValue(new Promise(() => {}));

    startPipelineStream("ana_123", "my-secret-token", vi.fn());

    const calledOptions = mockFetch.mock.calls[0][1];
    expect(calledOptions.headers.Authorization).toBe("Bearer my-secret-token");
  });

  it("sets Accept header to text/event-stream", () => {
    mockFetch.mockReturnValue(new Promise(() => {}));

    startPipelineStream("ana_123", "token", vi.fn());

    const calledOptions = mockFetch.mock.calls[0][1];
    expect(calledOptions.headers.Accept).toBe("text/event-stream");
  });

  it("returns a cleanup function", () => {
    mockFetch.mockReturnValue(new Promise(() => {}));

    const cleanup = startPipelineStream("ana_123", "token", vi.fn());

    expect(typeof cleanup).toBe("function");
  });

  it("passes an AbortSignal to fetch", () => {
    mockFetch.mockReturnValue(new Promise(() => {}));

    startPipelineStream("ana_123", "token", vi.fn());

    const calledOptions = mockFetch.mock.calls[0][1];
    expect(calledOptions.signal).toBeDefined();
    expect(calledOptions.signal).toBeInstanceOf(AbortSignal);
  });

  it("cleanup function aborts the fetch signal", () => {
    mockFetch.mockReturnValue(new Promise(() => {}));

    const cleanup = startPipelineStream("ana_123", "token", vi.fn());

    const signal = mockFetch.mock.calls[0][1].signal as AbortSignal;
    expect(signal.aborted).toBe(false);

    cleanup();

    expect(signal.aborted).toBe(true);
  });

  it("registers a visibilitychange event listener", () => {
    mockFetch.mockReturnValue(new Promise(() => {}));

    startPipelineStream("ana_123", "token", vi.fn());

    expect(mockAddEventListener).toHaveBeenCalledWith(
      "visibilitychange",
      expect.any(Function),
    );
  });

  it("cleanup removes the visibilitychange event listener", () => {
    mockFetch.mockReturnValue(new Promise(() => {}));

    const cleanup = startPipelineStream("ana_123", "token", vi.fn());
    cleanup();

    expect(mockRemoveEventListener).toHaveBeenCalledWith(
      "visibilitychange",
      expect.any(Function),
    );
  });

  it("reconnects when the document becomes visible", () => {
    let visibilityHandler: (() => void) | undefined;
    mockAddEventListener.mockImplementation(
      (event: string, handler: () => void) => {
        if (event === "visibilitychange") {
          visibilityHandler = handler;
        }
      },
    );
    mockFetch.mockReturnValue(new Promise(() => {}));

    const cleanup = startPipelineStream("ana_123", "token", vi.fn());
    const firstSignal = mockFetch.mock.calls[0][1].signal as AbortSignal;

    visibilityHandler?.();

    expect(firstSignal.aborted).toBe(true);
    expect(mockFetch).toHaveBeenCalledTimes(2);
    cleanup();
  });

  it("parses multi-line SSE data and cleans up when the stream completes", async () => {
    const onEvent = vi.fn();
    mockFetch.mockResolvedValue(
      streamResponse([
        'data: {"type":"progress",\ndata: "stage":"search"}\n\n',
        'data: {"type":"completed"}\n\n',
      ]),
    );

    startPipelineStream("ana_123", "token", onEvent);

    await vi.waitFor(() => expect(onEvent).toHaveBeenCalledTimes(2));
    expect(onEvent).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({ type: "progress", stage: "search" }),
    );
    expect(onEvent).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ type: "completed" }),
    );
    expect((mockFetch.mock.calls[0][1].signal as AbortSignal).aborted).toBe(
      true,
    );
  });

  it("cleans up when the stream emits a cancelled event", async () => {
    const onEvent = vi.fn();
    mockFetch.mockResolvedValue(
      streamResponse([
        'data: {"type":"cancelled","payload":{"message":"stopped"}}\n\n',
      ]),
    );

    startPipelineStream("ana_123", "token", onEvent);

    await vi.waitFor(() =>
      expect(onEvent).toHaveBeenCalledWith(
        expect.objectContaining({ type: "cancelled" }),
      ),
    );
    expect((mockFetch.mock.calls[0][1].signal as AbortSignal).aborted).toBe(
      true,
    );
  });

  it("cleans up when the stream emits a timeout event", async () => {
    const onEvent = vi.fn();
    mockFetch.mockResolvedValue(
      streamResponse([
        'data: {"type":"timeout","payload":{"message":"Stream timed out"}}\n\n',
      ]),
    );

    startPipelineStream("ana_123", "token", onEvent);

    await vi.waitFor(() =>
      expect(onEvent).toHaveBeenCalledWith(
        expect.objectContaining({ type: "timeout" }),
      ),
    );
    expect((mockFetch.mock.calls[0][1].signal as AbortSignal).aborted).toBe(
      true,
    );
  });

  it("logs malformed SSE payloads and continues reading later events", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const onEvent = vi.fn();
    mockFetch.mockResolvedValue(
      streamResponse(["data: not-json\n\n", 'data: {"type":"completed"}\n\n']),
    );

    startPipelineStream("ana_123", "token", onEvent);

    await vi.waitFor(() =>
      expect(onEvent).toHaveBeenCalledWith(
        expect.objectContaining({ type: "completed" }),
      ),
    );
    expect(consoleSpy).toHaveBeenCalledWith(
      "[SSE]",
      "SSE event payload could not be parsed",
      { action: "parse_event" },
    );
  });

  it("retries failed connections with exponential backoff before surfacing an error", async () => {
    vi.useFakeTimers();
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const onError = vi.fn();
    mockFetch.mockResolvedValue({ ok: false, status: 503 });

    startPipelineStream("ana_retry", "token", vi.fn(), onError);

    await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
    for (let expectedCalls = 2; expectedCalls <= 6; expectedCalls += 1) {
      await vi.runOnlyPendingTimersAsync();
      await vi.waitFor(() =>
        expect(mockFetch).toHaveBeenCalledTimes(expectedCalls),
      );
    }

    await vi.waitFor(() =>
      expect(onError).toHaveBeenCalledWith(
        expect.objectContaining({
          message: "SSE connection failed after max retries",
        }),
      ),
    );
    expect(consoleSpy).toHaveBeenCalledWith(
      "[SSE]",
      "SSE connection failed after max retries",
      { action: "stream" },
    );
  });

  it("reconnects when a nonterminal stream closes cleanly", async () => {
    vi.useFakeTimers();
    mockFetch
      .mockResolvedValueOnce(streamResponse([]))
      .mockReturnValueOnce(new Promise(() => {}));

    startPipelineStream("ana_eof", "token", vi.fn());

    await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
    await vi.runOnlyPendingTimersAsync();

    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("uses the latest accepted token when reconnecting after clean EOF", async () => {
    vi.useFakeTimers();
    let currentToken = "token-old";
    acceptAuthToken(currentToken);
    mockFetch
      .mockResolvedValueOnce(streamResponse([]))
      .mockReturnValueOnce(new Promise(() => {}));

    const cleanup = createPipelineStream(
      "ana_refresh",
      () => currentToken,
      vi.fn(),
    );
    activeCleanups.push(cleanup);

    await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
    currentToken = "token-new";
    acceptAuthToken(currentToken);
    await vi.runOnlyPendingTimersAsync();

    expect(mockFetch).toHaveBeenCalledTimes(2);
    expect(mockFetch.mock.calls[1][1].headers.Authorization).toBe(
      "Bearer token-new",
    );
  });

  it("surfaces repeated clean EOFs instead of retrying forever", async () => {
    vi.useFakeTimers();
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const onError = vi.fn();
    mockFetch.mockImplementation(async () => streamResponse([]));

    startPipelineStream("ana_eof_retry", "token", vi.fn(), onError);

    await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
    for (let expectedCalls = 2; expectedCalls <= 6; expectedCalls += 1) {
      await vi.runOnlyPendingTimersAsync();
      await vi.waitFor(() =>
        expect(mockFetch).toHaveBeenCalledTimes(expectedCalls),
      );
    }
    await vi.runOnlyPendingTimersAsync();

    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({
        message: "SSE connection failed after max retries",
      }),
    );
    expect(consoleSpy).toHaveBeenCalledWith(
      "[SSE]",
      "SSE connection failed after max retries",
      { action: "stream" },
    );
  });

  it("clears a pending retry when the stream is closed", async () => {
    vi.useFakeTimers();
    mockFetch.mockResolvedValue({ ok: false, status: 502 });

    const cleanup = startPipelineStream("ana_retry", "token", vi.fn());

    await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
    cleanup();
    await vi.runOnlyPendingTimersAsync();

    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("aborts the stream and does not retry when the auth boundary changes", async () => {
    const onError = vi.fn();
    mockFetch.mockImplementation(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal!.addEventListener("abort", () => {
            reject(
              new DOMException("Authentication boundary changed", "AbortError"),
            );
          });
        }),
    );

    startPipelineStream("ana_123", "token", vi.fn(), onError);

    const signal = mockFetch.mock.calls[0][1].signal as AbortSignal;
    emitAuthBoundaryChanged({ refreshToken: false });

    await vi.waitFor(() => expect(signal.aborted).toBe(true));
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
  });
});
