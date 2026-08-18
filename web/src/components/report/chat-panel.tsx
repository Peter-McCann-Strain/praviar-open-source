"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type RefObject,
} from "react";
import { FileUp, Loader2, MessageSquare } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { SPRING_SNAPPY } from "@/lib/spring-presets";
import { cn } from "@/lib/utils";
import { motionAwareScrollBehavior } from "@/lib/motion-preferences";
import { ChatPanelComposer } from "@/components/report/chat-panel-composer";
import {
  ChatPanelEmptyState,
  ChatPanelLaunchContextCard,
} from "@/components/report/chat-panel-empty-state";
import { ChatPanelEvidenceTab } from "@/components/report/chat-panel-evidence-tab";
import { ChatPanelHeader } from "@/components/report/chat-panel-header";
import { ChatPanelMessageBubble } from "@/components/report/chat-panel-message-bubble";
import {
  useReportChat,
  type ChatCitation,
  type ChatMessage,
} from "@/hooks/use-report-chat";
import { useAuthBoundaryReset } from "@/hooks/use-auth-boundary-reset";
import type { ReviewHandoffResponse } from "@/hooks/use-review-handoff";
import type { ReportChatLaunchContext } from "@/components/report/chat-launch-context";
import { sanitizeReportDiagnosticText } from "@/components/report/report-diagnostic-copy";
import { Button } from "@/components/ui/button";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

/* ── Main Chat Panel ────────────────────────────────────────────────── */

interface ChatPanelProps {
  analysisId: string;
  token: string | null;
  patentId?: string;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  hideLauncher?: boolean;
  launchContext?: ReportChatLaunchContext | null;
  launcherClassName?: string;
  returnFocusRef?: RefObject<HTMLElement | null>;
  onCitationClick?: (citation: ChatCitation, displayIndex: number) => void;
  onCreateReviewHandoff?: (
    draft: ChatGeneratedReviewHandoffDraft,
  ) => Promise<void> | void;
  onReviewHandoffSuccess?: (response: ReviewHandoffResponse) => void;
  reviewHandoffError?: string | null;
  reviewHandoffPending?: boolean;
  reviewHandoffSuccessLabel?: string | null;
}

export interface ChatGeneratedReviewHandoffDraft {
  body: string;
  promote_to_under_review: true;
  review_note: string;
  target_id: string;
  target_type: "analysis" | "patent";
}

const REVIEW_HANDOFF_BODY_LIMIT = 10000;
const REVIEW_HANDOFF_TRUNCATION_NOTICE =
  "\n\n[Content truncated for review handoff. Open the report chat transcript for the full generated answer.]";

export function ChatPanel({
  analysisId,
  token,
  patentId,
  open: controlledOpen,
  onOpenChange,
  hideLauncher = false,
  launchContext,
  launcherClassName,
  returnFocusRef,
  onCitationClick,
  onCreateReviewHandoff,
  onReviewHandoffSuccess,
  reviewHandoffError,
  reviewHandoffPending = false,
  reviewHandoffSuccessLabel,
}: ChatPanelProps) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false);
  const open = controlledOpen ?? uncontrolledOpen;
  const [expanded, setExpanded] = useState(false);
  const [input, setInput] = useState("");
  const [activeTab, setActiveTab] = useState<"chat" | "evidence">("chat");
  const [pendingGeneratedBriefId, setPendingGeneratedBriefId] = useState<
    string | null
  >(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const toggleButtonRef = useRef<HTMLButtonElement>(null);
  const chatTabRef = useRef<HTMLButtonElement>(null);
  const evidenceTabRef = useRef<HTMLButtonElement>(null);
  const mountedRef = useRef(true);

  const {
    messages,
    isStreaming,
    error,
    canSendMessages = true,
    sendMessage,
    clearHistory,
    isClearingHistory,
    workspaceMeta = null,
  } = useReportChat(analysisId, token);

  const setPanelOpen = useCallback(
    (nextOpen: boolean) => {
      if (controlledOpen === undefined) {
        setUncontrolledOpen(nextOpen);
      }
      onOpenChange?.(nextOpen);
    },
    [controlledOpen, onOpenChange],
  );

  const resetPrivateInput = useCallback(() => {
    setInput("");
    setActiveTab("chat");
  }, []);
  useAuthBoundaryReset(resetPrivateInput);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const closePanel = useCallback(() => {
    setPanelOpen(false);
    setInput("");
    setActiveTab("chat");
    setExpanded(false);
    const focusReturnTarget = () => {
      (returnFocusRef?.current ?? toggleButtonRef.current)?.focus();
    };
    requestAnimationFrame(() => {
      focusReturnTarget();
      requestAnimationFrame(focusReturnTarget);
    });
  }, [returnFocusRef, setPanelOpen]);

  // Auto-scroll on new messages
  useEffect(() => {
    if (!open || messages.length === 0) return;
    messagesEndRef.current?.scrollIntoView({
      behavior: motionAwareScrollBehavior(),
    });
  }, [messages, open]);

  // Focus input when opened; restore focus to trigger element when closed
  useEffect(() => {
    if (open) {
      inputRef.current?.focus();
    }
  }, [open]);

  const handleSuggestionClick = (suggestion: string) => {
    setInput(suggestion);
    inputRef.current?.focus();
  };

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming || !canSendMessages) return;
    sendMessage(trimmed, patentId);
    setInput("");
  };

  const handleLaunchAction = () => {
    if (!launchContext || isStreaming) return;
    if (!canSendMessages) {
      setInput((current) => current || launchContext.prompt);
      inputRef.current?.focus();
      return;
    }
    setActiveTab("chat");
    sendMessage(launchContext.prompt, patentId);
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const setActiveReportTab = (nextTab: "chat" | "evidence") => {
    setActiveTab(nextTab);
    requestAnimationFrame(() => {
      (nextTab === "chat"
        ? chatTabRef.current
        : evidenceTabRef.current
      )?.focus();
    });
  };

  const handleTabListKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;

    e.preventDefault();
    if (e.key === "Home") {
      setActiveReportTab("chat");
      return;
    }
    if (e.key === "End") {
      setActiveReportTab("evidence");
      return;
    }
    setActiveReportTab(activeTab === "chat" ? "evidence" : "chat");
  };

  // Trap focus within the modal chat panel. Without this, Tab/Shift+Tab
  // leaks into the background despite aria-modal="true", stranding keyboard
  // and screen-reader users behind the dialog. Mirrors the established trap
  // in PatentDetailDrawer / ReviewerDecisionPanel.
  const handleDialogKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      closePanel();
      return;
    }
    if (e.key !== "Tab" || !panelRef.current) return;

    const focusable = Array.from(
      panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
    ).filter((el) => el.getAttribute("aria-hidden") !== "true");
    if (focusable.length === 0) {
      e.preventDefault();
      panelRef.current.focus();
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;
    if (e.shiftKey && (active === first || active === panelRef.current)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus();
    }
  };

  const baseSuggestions = patentId
    ? [
        "What are the key claims in this patent?",
        "What is the infringement risk for our compound?",
        "Are there design-around strategies?",
        "What questions should counsel review for this patent?",
      ]
    : [
        "Which patents pose the highest risk?",
        "Summarize the key findings",
        "What design-around strategies are available?",
        "Compare the blocking patents",
      ];
  const suggestions = launchContext?.prompt
    ? [
        launchContext.prompt,
        ...baseSuggestions.filter(
          (suggestion) => suggestion !== launchContext.prompt,
        ),
      ].slice(0, 4)
    : baseSuggestions;
  const latestGeneratedBriefTurn = getLatestGeneratedBriefTurn(messages);
  const generatedBriefMatchesLaunch = Boolean(
    latestGeneratedBriefTurn?.sourcePrompt &&
    launchContext?.prompt === latestGeneratedBriefTurn.sourcePrompt,
  );
  const canRouteGeneratedBrief = Boolean(
    canSendMessages &&
    generatedBriefMatchesLaunch &&
    latestGeneratedBriefTurn &&
    onCreateReviewHandoff &&
    !isStreaming,
  );
  const generatedBriefPending =
    reviewHandoffPending ||
    (latestGeneratedBriefTurn?.assistant.id
      ? pendingGeneratedBriefId === latestGeneratedBriefTurn.assistant.id
      : false);
  const handleGeneratedBriefHandoff = async () => {
    if (
      !latestGeneratedBriefTurn ||
      !onCreateReviewHandoff ||
      generatedBriefPending ||
      isStreaming
    ) {
      return;
    }

    setPendingGeneratedBriefId(latestGeneratedBriefTurn.assistant.id);
    try {
      await onCreateReviewHandoff(
        buildGeneratedBriefHandoffDraft({
          analysisId,
          launchContext,
          message: latestGeneratedBriefTurn.assistant,
          patentId,
          sourcePrompt: latestGeneratedBriefTurn.sourcePrompt,
        }),
      );
    } finally {
      if (mountedRef.current) {
        setPendingGeneratedBriefId(null);
      }
    }
  };

  return (
    <>
      {/* Toggle button (bottom-right floating) */}
      {!open && !hideLauncher && (
        <motion.button
          ref={toggleButtonRef}
          initial={false}
          animate={{ scale: 1, opacity: 1 }}
          className={cn(
            "fixed bottom-4 right-4 z-30 flex h-12 w-12 items-center justify-center rounded-full bg-brand-primary text-[var(--brand-paper)] shadow-lg transition-colors hover:bg-brand-primary-dim sm:bottom-6 sm:right-6",
            launcherClassName,
          )}
          onClick={() => setPanelOpen(true)}
          aria-label="Open chat"
          aria-expanded={open}
        >
          <MessageSquare className="h-5 w-5" />
        </motion.button>
      )}

      {/* Chat panel */}
      <AnimatePresence>
        {open && (
          <motion.div
            ref={panelRef}
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            transition={SPRING_SNAPPY}
            role="dialog"
            aria-modal="true"
            tabIndex={-1}
            aria-label={
              patentId ? `Chat about patent ${patentId}` : "Chat with report"
            }
            onKeyDown={handleDialogKeyDown}
            className={cn(
              "praviar-dialog-panel fixed z-50 flex flex-col rounded-lg focus:outline-none",
              expanded
                ? "inset-3 sm:inset-4"
                : "inset-x-3 bottom-3 h-[min(640px,calc(100dvh-1.5rem))] max-h-[calc(100dvh-1.5rem)] sm:inset-auto sm:bottom-6 sm:right-6 sm:h-[600px] sm:w-[420px]",
            )}
          >
            <ChatPanelHeader
              expanded={expanded}
              hasMessages={messages.length > 0}
              isClearingHistory={isClearingHistory}
              onClearHistory={clearHistory}
              onClose={closePanel}
              onToggleExpanded={() => setExpanded(!expanded)}
              patentId={patentId}
            />

            <div
              className="flex border-b border-[var(--border-default)] px-3 pt-2"
              role="tablist"
              aria-label="Report assistant mode"
              onKeyDown={handleTabListKeyDown}
            >
              <button
                ref={chatTabRef}
                id="report-chat-tab-chat"
                type="button"
                role="tab"
                aria-selected={activeTab === "chat"}
                aria-controls="report-chat-panel-chat"
                tabIndex={activeTab === "chat" ? 0 : -1}
                onClick={() => setActiveReportTab("chat")}
                className={cn(
                  "min-h-11 border-b-2 px-3 py-2 text-xs font-medium transition-colors",
                  activeTab === "chat"
                    ? "border-brand-primary text-brand-primary"
                    : "border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-primary)]",
                )}
              >
                Chat
              </button>
              <button
                ref={evidenceTabRef}
                id="report-chat-tab-evidence"
                type="button"
                role="tab"
                aria-selected={activeTab === "evidence"}
                aria-controls="report-chat-panel-evidence"
                tabIndex={activeTab === "evidence" ? 0 : -1}
                onClick={() => setActiveReportTab("evidence")}
                className={cn(
                  "min-h-11 border-b-2 px-3 py-2 text-xs font-medium transition-colors",
                  activeTab === "evidence"
                    ? "border-brand-primary text-brand-primary"
                    : "border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-primary)]",
                )}
              >
                Evidence search
              </button>
            </div>

            <div
              id={
                activeTab === "evidence"
                  ? "report-chat-panel-evidence"
                  : "report-chat-panel-chat"
              }
              role="tabpanel"
              aria-labelledby={
                activeTab === "evidence"
                  ? "report-chat-tab-evidence"
                  : "report-chat-tab-chat"
              }
              tabIndex={0}
              className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-primary/70"
              aria-live="polite"
              aria-atomic="false"
            >
              {activeTab === "evidence" ? (
                <ChatPanelEvidenceTab
                  analysisId={analysisId}
                  token={token}
                  patentId={patentId}
                  workspaceMeta={workspaceMeta}
                  onReviewHandoffSuccess={onReviewHandoffSuccess}
                />
              ) : (
                <>
                  {launchContext && messages.length > 0 ? (
                    <div className="grid gap-2">
                      <ChatPanelLaunchContextCard
                        compact
                        launchContext={launchContext}
                      />
                      {canRouteGeneratedBrief ? (
                        <div className="sticky top-[8.25rem] z-10 rounded-lg border border-brand-primary/20 bg-[var(--bg-surface)]/92 p-3 shadow-[var(--shadow-xs)] backdrop-blur-xl">
                          <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                            <div className="min-w-0">
                              <p className="text-xs font-semibold text-[var(--text-primary)]">
                                Generated brief is ready for review routing
                              </p>
                              <p className="mt-0.5 text-xs leading-4 text-[var(--text-tertiary)]">
                                Sends this AI-generated answer, task context,
                                and citation summary into the review trail.
                              </p>
                            </div>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              className="min-h-11 shrink-0 gap-2"
                              loading={generatedBriefPending}
                              onClick={handleGeneratedBriefHandoff}
                              disabled={generatedBriefPending || isStreaming}
                            >
                              <FileUp
                                className="h-3.5 w-3.5"
                                aria-hidden="true"
                              />
                              Send brief to review
                            </Button>
                          </div>
                          {reviewHandoffSuccessLabel ? (
                            <p
                              role="status"
                              className="mt-2 rounded-md border border-success/25 bg-success/10 px-3 py-2 text-xs leading-4 text-success"
                            >
                              {reviewHandoffSuccessLabel}
                            </p>
                          ) : null}
                          {reviewHandoffError ? (
                            <p
                              role="alert"
                              className="mt-2 rounded-md border border-error/25 bg-error/10 px-3 py-2 text-xs leading-4 text-error"
                            >
                              {reviewHandoffError}
                            </p>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {messages.length === 0 ? (
                    <ChatPanelEmptyState
                      canRunLaunchAction={canSendMessages}
                      isLaunchActionPending={isStreaming}
                      launchContext={launchContext}
                      onLaunchAction={handleLaunchAction}
                      onSuggestionClick={handleSuggestionClick}
                      patentId={patentId}
                      suggestions={suggestions}
                      workspaceMeta={workspaceMeta}
                    />
                  ) : (
                    messages.map((msg) => (
                      <ChatPanelMessageBubble
                        key={msg.id}
                        message={msg}
                        onCitationClick={onCitationClick}
                      />
                    ))
                  )}

                  {/* Streaming indicator */}
                  {isStreaming && (
                    <div className="flex items-center gap-2 text-xs text-[var(--text-tertiary)]">
                      <Loader2 className="h-3 w-3 animate-spin motion-reduce:animate-none" />
                      Reviewing evidence...
                    </div>
                  )}

                  {/* Error */}
                  {error && (
                    <div
                      role="alert"
                      className="rounded-lg border border-error/20 bg-error/5 p-3"
                    >
                      <p className="text-xs text-error">{error}</p>
                    </div>
                  )}
                </>
              )}

              <div ref={messagesEndRef} />
            </div>

            {activeTab === "chat" ? (
              <ChatPanelComposer
                canSendMessages={canSendMessages}
                input={input}
                inputRef={inputRef}
                isStreaming={isStreaming}
                onChange={setInput}
                onKeyDown={handleKeyDown}
                onSend={handleSend}
                patentId={patentId}
              />
            ) : null}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

function getLatestGeneratedBriefTurn(
  messages: ChatMessage[],
): { assistant: ChatMessage; sourcePrompt: string | null } | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role === "assistant" && message.content.trim().length > 0) {
      const sourcePrompt =
        messages
          .slice(0, index)
          .reverse()
          .find((candidate) => candidate.role === "user")
          ?.content.trim() ?? null;
      return { assistant: message, sourcePrompt };
    }
  }

  return null;
}

function buildGeneratedBriefHandoffDraft({
  analysisId,
  launchContext,
  message,
  patentId,
  sourcePrompt,
}: {
  analysisId: string;
  launchContext?: ReportChatLaunchContext | null;
  message: ChatMessage;
  patentId?: string;
  sourcePrompt: string | null;
}): ChatGeneratedReviewHandoffDraft {
  const includeLaunchMetadata = Boolean(
    sourcePrompt && launchContext?.prompt === sourcePrompt,
  );
  const metadata =
    includeLaunchMetadata && launchContext?.metadata?.length
      ? launchContext.metadata
          .map(
            (item) =>
              `- ${sanitizeHandoffText(item.label, "Metadata")}: ${sanitizeHandoffText(
                item.value,
                "Metadata details are available in the report.",
              )}`,
          )
          .join("\n")
      : "- No launch metadata was attached to this transcript turn.";
  const citations = message.citations?.length
    ? message.citations.map(formatReviewCitation).join("\n")
    : "- No citation chips were returned; verify against source documents.";
  const targetLabel = patentId
    ? `Patent ${patentId}`
    : `Analysis ${analysisId}`;
  const safeTitle = sanitizeHandoffText(
    launchContext?.title,
    "Report chat answer",
  );
  const safeAction = sanitizeHandoffText(
    launchContext?.actionLabel,
    "Generated report brief",
  );
  const safePrompt = sanitizeHandoffText(
    sourcePrompt,
    "Prompt was not available in the local transcript.",
  );
  const safeAnswer = sanitizeHandoffText(
    message.content,
    "Generated answer details are available in the chat transcript.",
  );

  const body = clampReviewHandoffBody(
    [
      "**Praviar AI-generated review brief**",
      "",
      "Decision-support output only. This does not indicate legal clearance.",
      "",
      `Target: ${targetLabel}`,
      `Task: ${safeTitle}`,
      `Action: ${safeAction}`,
      "",
      "Prompt that generated this brief:",
      safePrompt,
      "",
      "Context:",
      metadata,
      "",
      "Generated answer:",
      safeAnswer,
      "",
      "Citations / provenance:",
      citations,
      "",
      "Reviewer note: AI-generated decision support only. Verify against original patent documents before commercial reliance.",
    ].join("\n"),
  );

  return {
    body,
    promote_to_under_review: true,
    review_note: `AI-generated report chat brief sent for reviewer follow-up; verify citations before reliance.`,
    target_id: patentId ?? analysisId,
    target_type: patentId ? "patent" : "analysis",
  };
}

function sanitizeHandoffText(
  value: string | null | undefined,
  fallback: string,
): string {
  return sanitizeReportDiagnosticText(value, fallback);
}

function clampReviewHandoffBody(value: string): string {
  if (value.length <= REVIEW_HANDOFF_BODY_LIMIT) return value;
  const limit =
    REVIEW_HANDOFF_BODY_LIMIT - REVIEW_HANDOFF_TRUNCATION_NOTICE.length;
  return `${value.slice(0, Math.max(0, limit)).trimEnd()}${REVIEW_HANDOFF_TRUNCATION_NOTICE}`;
}

function formatReviewCitation(citation: ChatCitation, index: number): string {
  const claimNumber = citation.claim_number ?? citation.claimNumber;
  const target = [
    citation.document_title,
    citation.patent_id ?? citation.patentId,
    claimNumber ? `claim ${claimNumber}` : null,
  ]
    .filter(Boolean)
    .join(" / ");
  const label = target || `Source ${citation.document_index + 1}`;
  return `- [${index + 1}] ${sanitizeHandoffText(
    label,
    "Source",
  )}: ${sanitizeHandoffText(
    citation.cited_text,
    "Citation details are available in the report.",
  )}`;
}
