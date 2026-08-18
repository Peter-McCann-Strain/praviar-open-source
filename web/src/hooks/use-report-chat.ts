"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getAuthBoundarySignal, isAuthTokenAccepted } from "@/lib/auth-events";
import { API_BASE_URL, DEMO_MODE_ENABLED } from "@/lib/constants";
import { isDemoAnalysisId } from "@/lib/demo-data";
import { buildDemoReportChatResponse } from "@/lib/demo-report-chat";
import { logError } from "@/lib/error-logger";
import { APIError, isAuthBoundaryError } from "@/lib/api-client";
import { useAuthBoundaryReset } from "@/hooks/use-auth-boundary-reset";
import { useToastStore } from "@/stores/toast-store";
import {
  REPORT_CHAT_ERROR_MESSAGE,
  REPORT_CHAT_UNAVAILABLE_MESSAGE,
} from "@/hooks/report-interaction-copy";

export interface ChatCitation {
  cited_text: string;
  document_index: number;
  document_title?: string;
  patent_id?: string;
  patentId?: string;
  claim_number?: number | string | null;
  claimNumber?: number | string | null;
  element_number?: number | string | null;
  elementNumber?: number | string | null;
  source_url?: string;
  url?: string;
  type?: "char" | "block";
  start?: number;
  end?: number;
  start_block?: number;
  end_block?: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: ChatCitation[];
  timestamp: string;
}

/**
 * Workspace metadata derived from the chat stream's `meta` event.
 *
 * The backend can send this in two shapes:
 *   1. A pre-shaped `workspace_meta` block intended for the UI.
 *   2. A richer `capability_metadata` block — we derive UI labels from it
 *      using {@link extractCapabilityMetadata}.
 */
export interface ChatWorkspaceMetadata {
  trust_mode?: "explorer" | "counsel" | "monitor" | string;
  mode_label?: string;
  capability_label?: string;
  scope_label?: string;
  source_coverage?: string;
  evidence_mode?: string;
  monitor_state?: string;
  tool_access?: string[];
}

interface UseReportChatReturn {
  messages: ChatMessage[];
  isStreaming: boolean;
  error: string | null;
  conversationId: string | null;
  workspaceMeta: ChatWorkspaceMetadata | null;
  canSendMessages: boolean;
  sendMessage: (message: string, patentId?: string) => void;
  clearHistory: () => Promise<boolean>;
  isClearingHistory: boolean;
}

const TRUST_MODE_LABELS: Record<string, string> = {
  explorer: "Explorer workspace",
  counsel: "Counsel workspace",
  monitor: "Monitor workspace",
};

const CAPABILITY_PROFILE_LABELS: Record<string, string> = {
  report_grounded: "Report-grounded answers",
  evidence_rich: "Evidence-rich review",
  specialist_supervised: "Supervised specialist review · review required",
  fully_autonomous: "Autonomous synthesis",
};

const EXECUTION_MODE_LABELS: Record<string, string> = {
  report_grounded_only: "Report-grounded only",
  hybrid: "Hybrid evidence",
  external: "External retrieval enabled",
};

const CITATION_VALIDATION_ERROR_CODE = "citation_validation_failed";

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function asStringArray(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const out = value.filter((item): item is string => typeof item === "string");
  return out.length > 0 ? out : undefined;
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value))
    return undefined;
  return value as Record<string, unknown>;
}

/**
 * Convert the backend's `capability_metadata` payload into a UI-shaped
 * {@link ChatWorkspaceMetadata}. Pure — easy to unit-test.
 */
export function extractCapabilityMetadata(
  raw: unknown,
): ChatWorkspaceMetadata | null {
  const record = asRecord(raw);
  if (!record) return null;

  const trustMode = asString(record.trust_mode);
  const capabilityProfile = asString(record.capability_profile);
  const routingProfile = asRecord(record.routing_profile);
  const toolPolicy = asRecord(record.tool_policy);
  const allowedCapabilities = asStringArray(record.allowed_capabilities);

  const modeLabel = trustMode ? TRUST_MODE_LABELS[trustMode] : undefined;
  const capabilityLabel = capabilityProfile
    ? (CAPABILITY_PROFILE_LABELS[capabilityProfile] ?? capabilityProfile)
    : undefined;

  const modality = routingProfile
    ? asString(routingProfile.modality)
    : undefined;
  const routingCapability = routingProfile
    ? asString(routingProfile.capability_profile)
    : undefined;
  const scopeLabel =
    modality && routingCapability
      ? `${modality} · ${routingCapability}`
      : (modality ?? routingCapability);

  const executionMode = toolPolicy
    ? asString(toolPolicy.execution_mode)
    : undefined;
  const evidenceMode = executionMode
    ? (EXECUTION_MODE_LABELS[executionMode] ?? executionMode)
    : undefined;

  let monitorState: string | undefined;
  if (toolPolicy && toolPolicy.monitoring_actions_allowed === true) {
    monitorState = "Monitoring actions allowed";
  } else if (toolPolicy && toolPolicy.monitoring_actions_allowed === false) {
    monitorState = "Monitoring actions blocked";
  }

  const adjustedCapabilityLabel = capabilityLabel;

  const meta: ChatWorkspaceMetadata = {
    trust_mode: trustMode,
    mode_label: modeLabel,
    capability_label: adjustedCapabilityLabel,
    scope_label: scopeLabel,
    evidence_mode: evidenceMode,
    monitor_state: monitorState,
    tool_access: allowedCapabilities,
  };

  // Drop entries that ended up undefined to keep matchers terse
  const cleaned = Object.fromEntries(
    Object.entries(meta).filter(([, v]) => v !== undefined),
  ) as ChatWorkspaceMetadata;

  return Object.keys(cleaned).length > 0 ? cleaned : null;
}

function coerceWorkspaceMeta(raw: unknown): ChatWorkspaceMetadata | null {
  const record = asRecord(raw);
  if (!record) return null;
  return {
    trust_mode: asString(record.trust_mode),
    mode_label: asString(record.mode_label),
    capability_label: asString(record.capability_label),
    scope_label: asString(record.scope_label),
    source_coverage: asString(record.source_coverage),
    evidence_mode: asString(record.evidence_mode),
    monitor_state: asString(record.monitor_state),
    tool_access: asStringArray(record.tool_access),
  };
}

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

function coerceChatCitation(value: unknown): ChatCitation | null {
  const record = asRecord(value);
  if (!record) return null;

  const citedText = asString(record.cited_text);
  const documentIndex =
    typeof record.document_index === "number" &&
    Number.isFinite(record.document_index)
      ? record.document_index
      : null;

  if (!citedText || documentIndex === null) return null;

  const citation: ChatCitation = {
    cited_text: citedText,
    document_index: documentIndex,
    document_title: asString(record.document_title),
    patent_id: asString(record.patent_id),
    patentId: asString(record.patentId),
    claim_number:
      typeof record.claim_number === "number" ||
      typeof record.claim_number === "string"
        ? record.claim_number
        : null,
    claimNumber:
      typeof record.claimNumber === "number" ||
      typeof record.claimNumber === "string"
        ? record.claimNumber
        : null,
    element_number:
      typeof record.element_number === "number" ||
      typeof record.element_number === "string"
        ? record.element_number
        : null,
    elementNumber:
      typeof record.elementNumber === "number" ||
      typeof record.elementNumber === "string"
        ? record.elementNumber
        : null,
    source_url: asString(record.source_url),
    url: asString(record.url),
    type:
      record.type === "char" || record.type === "block"
        ? record.type
        : undefined,
    start: typeof record.start === "number" ? record.start : undefined,
    end: typeof record.end === "number" ? record.end : undefined,
    start_block:
      typeof record.start_block === "number" ? record.start_block : undefined,
    end_block:
      typeof record.end_block === "number" ? record.end_block : undefined,
  };

  return Object.fromEntries(
    Object.entries(citation).filter(([, value]) => value !== undefined),
  ) as ChatCitation;
}

function coerceChatCitations(value: unknown): ChatCitation[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const citation = coerceChatCitation(item);
    return citation ? [citation] : [];
  });
}

function citationMergeKey(citation: ChatCitation) {
  return [
    citation.document_index,
    citation.cited_text,
    citation.type ?? "",
    citation.start ?? "",
    citation.end ?? "",
    citation.start_block ?? "",
    citation.end_block ?? "",
  ].join("::");
}

function mergeChatCitations(
  existing: ChatCitation[] | undefined,
  incoming: ChatCitation[],
): ChatCitation[] {
  if (!incoming.length) return existing ?? [];

  const byKey = new Map<string, ChatCitation>();
  for (const citation of existing ?? []) {
    byKey.set(citationMergeKey(citation), citation);
  }

  for (const citation of incoming) {
    const key = citationMergeKey(citation);
    const current = byKey.get(key);
    byKey.set(key, current ? { ...current, ...citation } : citation);
  }

  return Array.from(byKey.values()).sort(
    (a, b) => a.document_index - b.document_index,
  );
}

export function useReportChat(
  analysisId: string | null,
  token: string | null,
): UseReportChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isClearingHistory, setIsClearingHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chatAccessRestricted, setChatAccessRestricted] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const conversationIdRef = useRef<string | null>(null);
  useEffect(() => {
    conversationIdRef.current = conversationId;
  }, [conversationId]);
  const [workspaceMeta, setWorkspaceMeta] =
    useState<ChatWorkspaceMetadata | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const localDemoWorkspaceEnabled = DEMO_MODE_ENABLED;
  const canUseDemoReportChat = Boolean(
    analysisId && localDemoWorkspaceEnabled && isDemoAnalysisId(analysisId),
  );
  const canSendMessages = Boolean(
    analysisId &&
    !chatAccessRestricted &&
    ((token && isAuthTokenAccepted(token)) || canUseDemoReportChat),
  );

  // Abort any in-flight stream when the hook unmounts (e.g. navigating away).
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const resetLocalState = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setMessages([]);
    setIsStreaming(false);
    setError(null);
    setChatAccessRestricted(false);
    setConversationId(null);
    conversationIdRef.current = null;
    setWorkspaceMeta(null);
  }, []);
  const authBoundaryGenerationRef = useAuthBoundaryReset(resetLocalState);

  const sendMessage = useCallback(
    async (message: string, patentId?: string) => {
      if (isStreaming) return;
      const hasAcceptedToken = Boolean(token && isAuthTokenAccepted(token));
      const demoResponse =
        analysisId && localDemoWorkspaceEnabled
          ? buildDemoReportChatResponse({ analysisId, message, patentId })
          : null;
      if (chatAccessRestricted) {
        setError(REPORT_CHAT_UNAVAILABLE_MESSAGE);
        return;
      }
      if (!analysisId || (!hasAcceptedToken && !demoResponse)) {
        setError(REPORT_CHAT_UNAVAILABLE_MESSAGE);
        return;
      }

      const chatGeneration = authBoundaryGenerationRef.current;
      setError(null);
      setIsStreaming(true);

      // Add user message immediately
      const userMsg: ChatMessage = {
        id: `user-${crypto.randomUUID()}`,
        role: "user",
        content: message,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);

      // Prepare assistant message placeholder
      const assistantId = `assistant-${crypto.randomUUID()}`;
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        citations: [],
        timestamp: new Date().toISOString(),
      };

      if (demoResponse) {
        setMessages((prev) => [
          ...prev,
          {
            ...assistantMsg,
            content: demoResponse.content,
            citations: demoResponse.citations,
          },
        ]);
        setConversationId(demoResponse.conversationId);
        setWorkspaceMeta(demoResponse.workspaceMeta);
        setIsStreaming(false);
        return;
      }

      setMessages((prev) => [...prev, assistantMsg]);

      const controller = new AbortController();
      abortRef.current = controller;
      const unlinkAbort = linkAbortSignal(getAuthBoundarySignal(), controller);

      try {
        const response = await fetch(
          `${API_BASE_URL}/api/v1/analyses/${analysisId}/chat`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token ?? ""}`,
              Accept: "text/event-stream",
            },
            body: JSON.stringify({
              message,
              patent_id: patentId ?? null,
              conversation_id: conversationIdRef.current,
            }),
            signal: controller.signal,
          },
        );

        if (!response.ok) {
          throw new APIError(
            response.status,
            "The chat request could not be completed.",
          );
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error("No readable stream");

        const decoder = new TextDecoder();
        let buffer = "";
        let receivedDone = false;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          if (authBoundaryGenerationRef.current !== chatGeneration) {
            await reader.cancel();
            return;
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data:")) continue;
            const raw = line.slice(5).trim();
            if (!raw) continue;

            try {
              const event = asRecord(JSON.parse(raw));
              if (!event || typeof event.type !== "string") {
                throw new Error("Invalid chat stream event envelope");
              }
              if (authBoundaryGenerationRef.current !== chatGeneration) {
                await reader.cancel();
                return;
              }

              switch (event.type) {
                case "meta": {
                  if (typeof event.conversation_id === "string") {
                    setConversationId(event.conversation_id);
                  }
                  // Prefer pre-shaped workspace_meta when present, else
                  // derive from capability_metadata.
                  const direct = coerceWorkspaceMeta(event.workspace_meta);
                  if (direct) {
                    setWorkspaceMeta(direct);
                  } else {
                    const derived = extractCapabilityMetadata(
                      event.capability_metadata,
                    );
                    if (derived) setWorkspaceMeta(derived);
                  }
                  break;
                }
                case "text": {
                  if (typeof event.text !== "string") {
                    throw new Error("Invalid chat stream text event");
                  }
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantId
                        ? { ...m, content: m.content + event.text }
                        : m,
                    ),
                  );
                  break;
                }
                case "citation": {
                  const citation = coerceChatCitation(event.citation);
                  if (!citation) {
                    throw new Error("Invalid chat stream citation event");
                  }
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantId
                        ? {
                            ...m,
                            citations: mergeChatCitations(m.citations, [
                              citation,
                            ]),
                          }
                        : m,
                    ),
                  );
                  break;
                }
                case "done": {
                  receivedDone = true;
                  const finalCitations = coerceChatCitations(event.citations);
                  if (
                    event.citations !== undefined &&
                    (!Array.isArray(event.citations) ||
                      finalCitations.length !== event.citations.length)
                  ) {
                    throw new Error("Invalid chat stream completion event");
                  }
                  if (finalCitations.length) {
                    setMessages((prev) =>
                      prev.map((m) =>
                        m.id === assistantId
                          ? {
                              ...m,
                              citations: mergeChatCitations(
                                m.citations,
                                finalCitations,
                              ),
                            }
                          : m,
                      ),
                    );
                  }
                  await reader.cancel?.();
                  return;
                }
                case "error":
                  const isCitationValidationFailure =
                    event.code === CITATION_VALIDATION_ERROR_CODE;
                  logError(
                    new Error(
                      isCitationValidationFailure
                        ? "Chat response failed citation validation"
                        : "Chat stream reported a processing failure",
                    ),
                    {
                      source: "useReportChat.stream",
                      extra: {
                        analysisId,
                        conversationId: conversationIdRef.current,
                        errorCode: isCitationValidationFailure
                          ? CITATION_VALIDATION_ERROR_CODE
                          : "stream_error",
                      },
                    },
                  );
                  setError(REPORT_CHAT_ERROR_MESSAGE);
                  // An assistant turn is not decision-grade until the server
                  // emits `done`. Remove the entire in-flight turn atomically
                  // on citation validation or any other terminal stream error.
                  setMessages((prev) =>
                    prev.filter((m) => m.id !== assistantId),
                  );
                  await reader.cancel();
                  return;
                default:
                  throw new Error("Unknown chat stream event type");
              }
            } catch {
              // Once any frame is malformed, no later `done` event may make
              // already-streamed legal analysis look complete. Cancel the
              // transport and let the outer failure path remove the turn.
              await reader.cancel().catch(() => undefined);
              throw new Error("Chat stream contained malformed event data");
            }
          }
        }

        if (!receivedDone) {
          // A partial answer without the protocol's terminal `done` event is
          // not decision-grade output. Remove it before surfacing recovery so
          // truncated legal analysis cannot look complete in the transcript.
          setMessages((prev) =>
            prev.filter((message) => message.id !== assistantId),
          );
          throw new Error("Chat stream ended before completion");
        }
      } catch (err) {
        if (authBoundaryGenerationRef.current !== chatGeneration) return;
        if ((err as Error).name !== "AbortError") {
          if (isAuthBoundaryError(err)) {
            setChatAccessRestricted(true);
            setMessages([]);
            setConversationId(null);
            conversationIdRef.current = null;
            setWorkspaceMeta(null);
            setError(REPORT_CHAT_UNAVAILABLE_MESSAGE);
            return;
          }
          logError(err, {
            source: "useReportChat.sendMessage",
            extra: { analysisId, conversationId: conversationIdRef.current },
          });
          setError(REPORT_CHAT_ERROR_MESSAGE);
          // A transport failure before `done` leaves an incomplete legal
          // answer. Keep the user's prompt for retry, but remove that turn.
          setMessages((prev) => prev.filter((m) => m.id !== assistantId));
        }
      } finally {
        unlinkAbort();
        if (authBoundaryGenerationRef.current === chatGeneration) {
          setIsStreaming(false);
          // Drop the assistant placeholder if the stream ended without ever
          // producing text or citations (e.g. a `done` event with no payload,
          // or the connection closing cleanly mid-handshake). Otherwise an
          // empty bubble lingers in the transcript with nothing to show.
          setMessages((prev) =>
            prev.filter(
              (m) =>
                m.id !== assistantId ||
                m.content.length > 0 ||
                (m.citations?.length ?? 0) > 0,
            ),
          );
        }
        if (abortRef.current === controller) {
          abortRef.current = null;
        }
      }
    },
    [
      analysisId,
      authBoundaryGenerationRef,
      localDemoWorkspaceEnabled,
      token,
      isStreaming,
      chatAccessRestricted,
    ],
  );

  const clearHistory = useCallback(async () => {
    if (isClearingHistory) return false;

    if (analysisId && token && conversationId && isAuthTokenAccepted(token)) {
      const targetConversation = conversationId;
      const targetAnalysis = analysisId;
      const controller = new AbortController();
      const unlinkAbort = linkAbortSignal(getAuthBoundarySignal(), controller);

      setIsClearingHistory(true);
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/v1/analyses/${targetAnalysis}/chat/${targetConversation}`,
          {
            method: "DELETE",
            headers: { Authorization: `Bearer ${token}` },
            signal: controller.signal,
          },
        );

        if (!response.ok) {
          throw new APIError(
            response.status,
            "Chat history could not be cleared.",
          );
        }

        resetLocalState();
        return true;
      } catch (err) {
        if ((err as Error).name === "AbortError") {
          return false;
        }

        if (isAuthBoundaryError(err)) {
          setChatAccessRestricted(true);
          setMessages([]);
          setConversationId(null);
          conversationIdRef.current = null;
          setWorkspaceMeta(null);
          setError(REPORT_CHAT_UNAVAILABLE_MESSAGE);
          return true;
        }

        logError(err, {
          source: "useReportChat.clearHistory",
          extra: {
            analysisId: targetAnalysis,
            conversationId: targetConversation,
          },
        });
        useToastStore
          .getState()
          .addToast(
            "Failed to clear chat history. Existing transcript is unchanged.",
            "error",
          );
        return false;
      } finally {
        unlinkAbort();
        setIsClearingHistory(false);
      }
    }

    resetLocalState();
    return true;
  }, [analysisId, token, conversationId, isClearingHistory, resetLocalState]);

  return {
    messages,
    isStreaming,
    error,
    conversationId,
    workspaceMeta,
    canSendMessages,
    sendMessage,
    clearHistory,
    isClearingHistory,
  };
}
