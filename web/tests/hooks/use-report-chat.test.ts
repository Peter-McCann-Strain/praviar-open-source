import { renderHook, waitFor, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/constants", () => ({
  API_BASE_URL: "https://api.example.test",
  DEMO_MODE_ENABLED: true,
  DEV_AUTH_BYPASS_ENABLED: true,
  TOAST_AUTO_DISMISS_MS: 5000,
}));

import { useReportChat } from "@/hooks/use-report-chat";
import {
  REPORT_CHAT_ERROR_MESSAGE,
  REPORT_CHAT_UNAVAILABLE_MESSAGE,
} from "@/hooks/report-interaction-copy";
import { acceptAuthToken, emitAuthBoundaryChanged } from "@/lib/auth-events";

describe("useReportChat", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReset();
    acceptAuthToken("tok");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("captures workspace metadata from the SSE meta payload", async () => {
    const encoded = new TextEncoder().encode(
      [
        'data: {"type":"meta","conversation_id":"conv-1","workspace_meta":{"trust_mode":"counsel","mode_label":"Counsel workspace","capability_label":"Evidence-rich review","scope_label":"Patent US123","source_coverage":"Governed metadata"}}',
        "",
        'data: {"type":"done","usage":{"input_tokens":1,"output_tokens":1}}',
        "",
      ].join("\n"),
    );

    const reader = {
      read: vi
        .fn()
        .mockResolvedValueOnce({ done: false, value: encoded })
        .mockResolvedValueOnce({ done: true, value: undefined }),
    };

    fetchMock.mockResolvedValue({
      ok: true,
      body: {
        getReader: () => reader,
      },
    });

    const { result } = renderHook(() => useReportChat("analysis-1", "tok"));

    await act(async () => {
      await result.current.sendMessage("Need evidence");
    });

    await waitFor(() => {
      expect(result.current.workspaceMeta).toMatchObject({
        trust_mode: "counsel",
        mode_label: "Counsel workspace",
        capability_label: "Evidence-rich review",
        scope_label: "Patent US123",
        source_coverage: "Governed metadata",
      });
    });
  });

  it("merges final structured citations into streamed chat citations", async () => {
    const encoded = new TextEncoder().encode(
      [
        'data: {"type":"text","text":"Claim 12 is the relevant anchor."}',
        "",
        'data: {"type":"citation","citation":{"cited_text":"claim text","document_index":2}}',
        "",
        'data: {"type":"done","citations":[{"cited_text":"claim text","document_index":2,"document_title":"Patent US-9988776-B2 Claim 12","patent_id":"US9988776B2","claim_number":12,"element_number":3,"source_url":"https://patents.example/US9988776B2"}]}',
        "",
      ].join("\n"),
    );

    const reader = {
      read: vi
        .fn()
        .mockResolvedValueOnce({ done: false, value: encoded })
        .mockResolvedValueOnce({ done: true, value: undefined }),
    };

    fetchMock.mockResolvedValue({
      ok: true,
      body: {
        getReader: () => reader,
      },
    });

    const { result } = renderHook(() => useReportChat("analysis-1", "tok"));

    await act(async () => {
      await result.current.sendMessage("Where is claim 12 anchored?");
    });

    const assistant = result.current.messages.find(
      (message) => message.role === "assistant",
    );
    expect(assistant?.content).toBe("Claim 12 is the relevant anchor.");
    expect(assistant?.citations).toHaveLength(1);
    expect(assistant?.citations?.[0]).toMatchObject({
      cited_text: "claim text",
      document_index: 2,
      document_title: "Patent US-9988776-B2 Claim 12",
      patent_id: "US9988776B2",
      claim_number: 12,
      element_number: 3,
      source_url: "https://patents.example/US9988776B2",
    });
  });

  it("removes uncited partial text after terminal citation validation failure", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const encoded = new TextEncoder().encode(
      [
        'data: {"type":"meta","conversation_id":"conv-uncited"}',
        "",
        'data: {"type":"text","text":"Unsupported legal conclusion"}',
        "",
        'data: {"type":"error","code":"citation_validation_failed","error":"safe public copy"}',
        "",
      ].join("\n"),
    );
    const reader = {
      read: vi
        .fn()
        .mockResolvedValueOnce({ done: false, value: encoded })
        .mockResolvedValueOnce({ done: true, value: undefined }),
      cancel: vi.fn().mockResolvedValue(undefined),
    };
    fetchMock.mockResolvedValue({
      ok: true,
      body: { getReader: () => reader },
    });

    const { result } = renderHook(() => useReportChat("analysis-1", "tok"));

    await act(async () => {
      await result.current.sendMessage("Assess this claim");
    });

    expect(result.current.messages).toEqual([
      expect.objectContaining({ role: "user", content: "Assess this claim" }),
    ]);
    expect(result.current.error).toBe(REPORT_CHAT_ERROR_MESSAGE);
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.canSendMessages).toBe(true);
    expect(reader.cancel).toHaveBeenCalledOnce();
    expect(JSON.stringify(consoleSpy.mock.calls)).not.toContain(
      "Unsupported legal conclusion",
    );
  });

  it("fails closed when a malformed frame is followed by done", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const encoded = new TextEncoder().encode(
      [
        'data: {"type":"text","text":"Partial answer"}',
        "",
        'data: {"type":"text","text":"UNPUBLISHED_ASSET_PRV_142"',
        "",
        'data: {"type":"done"}',
        "",
      ].join("\n"),
    );
    const reader = {
      read: vi.fn().mockResolvedValueOnce({ done: false, value: encoded }),
      cancel: vi.fn().mockResolvedValue(undefined),
    };
    fetchMock.mockResolvedValue({
      ok: true,
      body: { getReader: () => reader },
    });

    const { result } = renderHook(() => useReportChat("analysis-1", "tok"));

    await act(async () => {
      await result.current.sendMessage("Assess malformed stream handling");
    });

    expect(result.current.messages).toEqual([
      expect.objectContaining({
        role: "user",
        content: "Assess malformed stream handling",
      }),
    ]);
    expect(result.current.error).toBe(REPORT_CHAT_ERROR_MESSAGE);
    expect(result.current.isStreaming).toBe(false);
    expect(reader.cancel).toHaveBeenCalledOnce();
    expect(reader.read).toHaveBeenCalledOnce();
    expect(JSON.stringify(consoleSpy.mock.calls)).not.toContain(
      "UNPUBLISHED_ASSET_PRV_142",
    );
  });

  it("removes an incomplete assistant turn after an unrelated transport failure", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const encoded = new TextEncoder().encode(
      [
        'data: {"type":"text","text":"Partial answer before disconnect"}',
        "",
      ].join("\n"),
    );
    const reader = {
      read: vi
        .fn()
        .mockResolvedValueOnce({ done: false, value: encoded })
        .mockRejectedValueOnce(new TypeError("network disconnected")),
    };
    fetchMock.mockResolvedValue({
      ok: true,
      body: { getReader: () => reader },
    });

    const { result } = renderHook(() => useReportChat("analysis-1", "tok"));

    await act(async () => {
      await result.current.sendMessage("Assess transport handling");
    });

    expect(result.current.messages).toEqual([
      expect.objectContaining({
        role: "user",
        content: "Assess transport handling",
      }),
    ]);
    expect(result.current.error).toBe(REPORT_CHAT_ERROR_MESSAGE);
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.canSendMessages).toBe(true);
    expect(JSON.stringify(consoleSpy.mock.calls)).not.toContain(
      "Partial answer before disconnect",
    );
  });

  it("removes a partial assistant answer when the stream closes before done", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const encoded = new TextEncoder().encode(
      [
        'data: {"type":"meta","conversation_id":"conv-truncated"}',
        "",
        'data: {"type":"text","text":"This answer is incomplete"}',
        "",
      ].join("\n"),
    );
    const reader = {
      read: vi
        .fn()
        .mockResolvedValueOnce({ done: false, value: encoded })
        .mockResolvedValueOnce({ done: true, value: undefined }),
    };
    fetchMock.mockResolvedValue({
      ok: true,
      body: { getReader: () => reader },
    });

    const { result } = renderHook(() => useReportChat("analysis-1", "tok"));

    await act(async () => {
      await result.current.sendMessage("Need a complete answer");
    });

    expect(result.current.error).toBe(REPORT_CHAT_ERROR_MESSAGE);
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0]).toMatchObject({
      role: "user",
      content: "Need a complete answer",
    });
    expect(
      result.current.messages.some((message) =>
        message.content.includes("This answer is incomplete"),
      ),
    ).toBe(false);
    expect(JSON.stringify(consoleSpy.mock.calls)).not.toContain(
      "This answer is incomplete",
    );
  });

  it("rejects a clean EOF that arrives before any chat payload", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const reader = {
      read: vi.fn().mockResolvedValue({ done: true, value: undefined }),
    };
    fetchMock.mockResolvedValue({
      ok: true,
      body: { getReader: () => reader },
    });

    const { result } = renderHook(() => useReportChat("analysis-1", "tok"));

    await act(async () => {
      await result.current.sendMessage("Need evidence");
    });

    expect(result.current.error).toBe(REPORT_CHAT_ERROR_MESSAGE);
    expect(result.current.messages).toEqual([
      expect.objectContaining({ role: "user", content: "Need evidence" }),
    ]);
    expect(consoleSpy).toHaveBeenCalledWith(
      "[useReportChat.sendMessage]",
      "Chat stream ended before completion",
      expect.any(Object),
    );
  });

  it("reports tokenless non-demo chat as unavailable without mutating the transcript", async () => {
    const { result } = renderHook(() => useReportChat("analysis-1", null));

    expect(result.current.canSendMessages).toBe(false);

    await act(async () => {
      await result.current.sendMessage("Summarize the blockers");
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.messages).toEqual([]);
    expect(result.current.error).toBe(REPORT_CHAT_UNAVAILABLE_MESSAGE);
  });

  it("answers demo report chat without a backend token", async () => {
    const { result } = renderHook(() => useReportChat("ana_demo_001", null));
    const blockerPrompt =
      "Draft a source-grounded blocking-patent brief for Example Molecule Alpha. Focus on active or blocking patent families, claim elements, expiry or legal status, design-around assumptions, unresolved uncertainty, and counsel follow-up.";

    expect(result.current.canSendMessages).toBe(true);

    await act(async () => {
      await result.current.sendMessage(blockerPrompt);
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.error).toBeNull();
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.conversationId).toBe("demo-report-chat-ana_demo_001");
    expect(result.current.workspaceMeta).toMatchObject({
      mode_label: "Counsel demo workspace",
      capability_label: "Report-grounded demo answers",
      evidence_mode: "Demo report-grounded only",
    });
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[0]).toMatchObject({
      role: "user",
      content: blockerPrompt,
    });
    expect(result.current.messages[1]).toMatchObject({
      role: "assistant",
    });
    expect(result.current.messages[1]?.content).toContain("Blocker brief");
    expect(result.current.messages[1]?.content).toContain("XX-FICTION-0001-A1");
    expect(result.current.messages[1]?.citations).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          patent_id: "XX-FICTION-0001-A1",
          claim_number: 1,
        }),
      ]),
    );
  });

  it("keeps demo report chat local even when a dev token is present", async () => {
    fetchMock.mockRejectedValue(new Error("backend chat unavailable"));
    const { result } = renderHook(() => useReportChat("ana_demo_001", "tok"));

    await act(async () => {
      await result.current.sendMessage("Generate a blocker brief for counsel.");
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.error).toBeNull();
    expect(result.current.conversationId).toBe("demo-report-chat-ana_demo_001");
    expect(result.current.workspaceMeta).toMatchObject({
      mode_label: "Counsel demo workspace",
      evidence_mode: "Demo report-grounded only",
    });
    expect(result.current.messages[1]?.content).toContain("Blocker brief");
  });

  it("derives workspace metadata from backend capability metadata", async () => {
    const encoded = new TextEncoder().encode(
      [
        'data: {"type":"meta","conversation_id":"conv-2","capability_metadata":{"trust_mode":"monitor","capability_profile":"specialist_supervised","routing_profile":{"modality":"biologic_or_sequence","capability_profile":"specialist_supervised"},"opinion_readiness":{"export_ready":false},"allowed_capabilities":["report_grounded_qna","monitor_delta_summary"],"tool_policy":{"execution_mode":"report_grounded_only","monitoring_actions_allowed":true},"evidence_basis":[{"field":"trust_mode","value":"monitor"}]}}',
        "",
        'data: {"type":"done","usage":{"input_tokens":1,"output_tokens":1}}',
        "",
      ].join("\n"),
    );

    const reader = {
      read: vi
        .fn()
        .mockResolvedValueOnce({ done: false, value: encoded })
        .mockResolvedValueOnce({ done: true, value: undefined }),
    };

    fetchMock.mockResolvedValue({
      ok: true,
      body: {
        getReader: () => reader,
      },
    });

    const { result } = renderHook(() => useReportChat("analysis-1", "tok"));

    await act(async () => {
      await result.current.sendMessage("Monitor changes");
    });

    await waitFor(() => {
      expect(result.current.workspaceMeta).toMatchObject({
        trust_mode: "monitor",
        mode_label: "Monitor workspace",
        capability_label: "Supervised specialist review · review required",
        scope_label: "biologic_or_sequence · specialist_supervised",
        evidence_mode: "Report-grounded only",
        monitor_state: "Monitoring actions allowed",
        tool_access: ["report_grounded_qna", "monitor_delta_summary"],
      });
    });
  });

  it("clears private chat state and aborts streaming on auth boundary changes", async () => {
    let capturedSignal: AbortSignal | undefined;
    fetchMock.mockImplementation((_url: string, init: RequestInit) => {
      capturedSignal = init.signal ?? undefined;
      return new Promise((_resolve, reject) => {
        capturedSignal?.addEventListener("abort", () => {
          reject(new DOMException("Aborted", "AbortError"));
        });
      });
    });

    const { result } = renderHook(() => useReportChat("analysis-1", "tok"));

    act(() => {
      result.current.sendMessage("Need evidence");
    });

    expect(result.current.messages).toHaveLength(2);
    expect(result.current.isStreaming).toBe(true);

    act(() => {
      emitAuthBoundaryChanged({ refreshToken: false });
    });

    expect(capturedSignal?.aborted).toBe(true);
    expect(result.current.messages).toEqual([]);
    expect(result.current.conversationId).toBeNull();
    expect(result.current.workspaceMeta).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.isStreaming).toBe(false);
  });

  it("does not repopulate private chat state when a pre-boundary stream resolves late", async () => {
    let resolveRead!: (value: { done: boolean; value?: Uint8Array }) => void;
    const encoded = new TextEncoder().encode(
      [
        'data: {"type":"meta","conversation_id":"conv-stale","workspace_meta":{"mode_label":"Counsel workspace"}}',
        "",
        'data: {"type":"text","text":"stale answer"}',
        "",
      ].join("\n"),
    );
    const reader = {
      read: vi.fn().mockReturnValueOnce(
        new Promise((resolve) => {
          resolveRead = resolve;
        }),
      ),
    };
    fetchMock.mockResolvedValue({
      ok: true,
      body: {
        getReader: () => reader,
      },
    });

    const { result } = renderHook(() => useReportChat("analysis-1", "tok"));

    act(() => {
      result.current.sendMessage("Need evidence");
    });
    await act(async () => {
      await Promise.resolve();
    });

    act(() => {
      emitAuthBoundaryChanged({ refreshToken: false });
    });

    await act(async () => {
      resolveRead({ done: false, value: encoded });
      await Promise.resolve();
    });

    expect(result.current.messages).toEqual([]);
    expect(result.current.conversationId).toBeNull();
    expect(result.current.workspaceMeta).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.isStreaming).toBe(false);
  });

  it("uses safe copy for HTTP chat failures", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 500,
      json: () =>
        Promise.resolve({
          detail: "postgres://secret-token chat backend exploded",
        }),
    });

    const { result } = renderHook(() => useReportChat("analysis-1", "tok"));

    await act(async () => {
      await result.current.sendMessage("Need evidence");
    });

    expect(result.current.error).toBe(REPORT_CHAT_ERROR_MESSAGE);
    expect(result.current.error).not.toContain("postgres://secret-token");
  });

  it("clears transcript and disables sends when chat access is revoked", async () => {
    const encoded = new TextEncoder().encode(
      [
        'data: {"type":"meta","conversation_id":"conv-private","workspace_meta":{"mode_label":"Counsel workspace"}}',
        "",
        'data: {"type":"text","text":"Private report answer."}',
        "",
        'data: {"type":"done"}',
        "",
      ].join("\n"),
    );
    const reader = {
      read: vi
        .fn()
        .mockResolvedValueOnce({ done: false, value: encoded })
        .mockResolvedValueOnce({ done: true, value: undefined }),
    };

    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        body: {
          getReader: () => reader,
        },
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 403,
        json: () =>
          Promise.resolve({
            detail: "postgres://secret-token forbidden",
          }),
      });

    const { result } = renderHook(() => useReportChat("analysis-1", "tok"));

    await act(async () => {
      await result.current.sendMessage("Need evidence");
    });

    expect(result.current.messages).toHaveLength(2);
    expect(result.current.conversationId).toBe("conv-private");
    expect(result.current.workspaceMeta).toMatchObject({
      mode_label: "Counsel workspace",
    });

    await act(async () => {
      await result.current.sendMessage("Ask again");
    });

    expect(result.current.messages).toEqual([]);
    expect(result.current.conversationId).toBeNull();
    expect(result.current.workspaceMeta).toBeNull();
    expect(result.current.error).toBe(REPORT_CHAT_UNAVAILABLE_MESSAGE);
    expect(result.current.canSendMessages).toBe(false);

    await act(async () => {
      await result.current.sendMessage("Still blocked");
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("uses safe copy for SSE chat error events", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const encoded = new TextEncoder().encode(
      [
        'data: {"type":"error","error":"UNPUBLISHED_ASSET_PRV_142 stream failure"}',
        "",
      ].join("\n"),
    );

    const reader = {
      read: vi
        .fn()
        .mockResolvedValueOnce({ done: false, value: encoded })
        .mockResolvedValueOnce({ done: true, value: undefined }),
      cancel: vi.fn().mockResolvedValue(undefined),
    };

    fetchMock.mockResolvedValue({
      ok: true,
      body: {
        getReader: () => reader,
      },
    });

    const { result } = renderHook(() => useReportChat("analysis-1", "tok"));

    await act(async () => {
      await result.current.sendMessage("Need evidence");
    });

    expect(result.current.error).toBe(REPORT_CHAT_ERROR_MESSAGE);
    expect(result.current.error).not.toContain("UNPUBLISHED_ASSET_PRV_142");
    expect(JSON.stringify(consoleSpy.mock.calls)).not.toContain(
      "UNPUBLISHED_ASSET_PRV_142",
    );
    expect(reader.cancel).toHaveBeenCalled();
  });

  it("clears local transcript and disables sends when clear history access is revoked", async () => {
    const encoded = new TextEncoder().encode(
      [
        'data: {"type":"meta","conversation_id":"conv-revoked-clear","workspace_meta":{"mode_label":"Counsel workspace"}}',
        "",
        'data: {"type":"text","text":"Private transcript."}',
        "",
        'data: {"type":"done"}',
        "",
      ].join("\n"),
    );
    const reader = {
      read: vi
        .fn()
        .mockResolvedValueOnce({ done: false, value: encoded })
        .mockResolvedValueOnce({ done: true, value: undefined }),
    };

    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        body: {
          getReader: () => reader,
        },
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 403,
        json: () =>
          Promise.resolve({
            detail: "postgres://secret-token forbidden",
          }),
      });

    const { result } = renderHook(() => useReportChat("analysis-1", "tok"));

    await act(async () => {
      await result.current.sendMessage("Need evidence");
    });

    expect(result.current.conversationId).toBe("conv-revoked-clear");
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.workspaceMeta).toMatchObject({
      mode_label: "Counsel workspace",
    });

    await act(async () => {
      const cleared = await result.current.clearHistory();
      expect(cleared).toBe(true);
    });

    expect(fetchMock).toHaveBeenLastCalledWith(
      "https://api.example.test/api/v1/analyses/analysis-1/chat/conv-revoked-clear",
      expect.objectContaining({
        method: "DELETE",
        headers: { Authorization: "Bearer tok" },
      }),
    );
    expect(result.current.messages).toEqual([]);
    expect(result.current.conversationId).toBeNull();
    expect(result.current.workspaceMeta).toBeNull();
    expect(result.current.error).toBe(REPORT_CHAT_UNAVAILABLE_MESSAGE);
    expect(result.current.canSendMessages).toBe(false);
  });

  it("keeps the transcript visible when server-side clear history fails", async () => {
    const encoded = new TextEncoder().encode(
      [
        'data: {"type":"meta","conversation_id":"conv-keep"}',
        "",
        'data: {"type":"text","text":"Keep this answer visible."}',
        "",
        'data: {"type":"done"}',
        "",
      ].join("\n"),
    );
    const reader = {
      read: vi
        .fn()
        .mockResolvedValueOnce({ done: false, value: encoded })
        .mockResolvedValueOnce({ done: true, value: undefined }),
    };

    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        body: {
          getReader: () => reader,
        },
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

    const { result } = renderHook(() => useReportChat("analysis-1", "tok"));

    await act(async () => {
      await result.current.sendMessage("Need evidence");
    });

    expect(result.current.conversationId).toBe("conv-keep");
    expect(result.current.messages).toHaveLength(2);

    await act(async () => {
      const cleared = await result.current.clearHistory();
      expect(cleared).toBe(false);
    });

    expect(fetchMock).toHaveBeenLastCalledWith(
      "https://api.example.test/api/v1/analyses/analysis-1/chat/conv-keep",
      expect.objectContaining({
        method: "DELETE",
        headers: { Authorization: "Bearer tok" },
      }),
    );
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.conversationId).toBe("conv-keep");
  });
});
