import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import { useRef, useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatPanel } from "@/components/report/chat-panel";
import type { ChatCitation, ChatMessage } from "@/hooks/use-report-chat";
import { emitAuthBoundaryChanged } from "@/lib/auth-events";
import { REPORT_CHAT_UNAVAILABLE_MESSAGE } from "@/hooks/report-interaction-copy";

const mockUseReportChat = vi.fn();
const mockScrollIntoView = vi.fn();
const mockMatchMedia = vi.fn();

interface MotionVisualState {
  opacity?: number;
  scale?: number;
}

type MotionButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  animate?: MotionVisualState;
  initial?: false | MotionVisualState;
};

vi.mock("motion/react", () => ({
  AnimatePresence: ({ children }: { children: ReactNode }) => <>{children}</>,
  motion: {
    button: ({ animate, children, initial, ...props }: MotionButtonProps) => {
      const visualState = initial === false ? animate : initial;
      return (
        <button
          {...props}
          style={{
            opacity: visualState?.opacity,
            transform:
              visualState?.scale === undefined
                ? undefined
                : `scale(${visualState.scale})`,
          }}
        >
          {children}
        </button>
      );
    },
    div: ({ children, ...props }: HTMLAttributes<HTMLDivElement>) => (
      <div {...props}>{children}</div>
    ),
  },
}));

vi.mock("@/hooks/use-report-chat", () => ({
  useReportChat: (...args: unknown[]) => mockUseReportChat(...args),
}));

vi.mock("@/components/report/chat-panel-evidence-tab", () => ({
  ChatPanelEvidenceTab: () => <div>Evidence panel</div>,
}));

const citation: ChatCitation = {
  document_index: 2,
  patent_id: "US123",
  claim_number: 1,
  cited_text: "Example citation text",
};

const messages: ChatMessage[] = [
  {
    id: "m1",
    role: "assistant",
    content: "Here is the answer.",
    citations: [citation],
  },
];

describe("ChatPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseReportChat.mockReturnValue({
      messages: [],
      isStreaming: false,
      error: null,
      canSendMessages: true,
      sendMessage: vi.fn(),
      clearHistory: vi.fn(),
    });
    mockScrollIntoView.mockReset();
    window.HTMLElement.prototype.scrollIntoView = mockScrollIntoView;
    mockMatchMedia.mockReturnValue({
      matches: false,
      media: "(prefers-reduced-motion: reduce)",
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    });
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: mockMatchMedia,
    });
  });

  it("renders the floating launcher in its final visual state immediately", () => {
    render(<ChatPanel analysisId="analysis-1" token="tok" />);

    const launcher = screen.getByRole("button", { name: "Open chat" });
    expect(launcher).toHaveStyle({ opacity: "1", transform: "scale(1)" });
    expect(launcher).toHaveClass(
      "fixed",
      "h-12",
      "w-12",
      "sm:bottom-6",
      "sm:right-6",
    );
  });

  it("opens from the floating button, hydrates a suggestion into the composer, and sends it", async () => {
    const sendMessage = vi.fn();
    mockUseReportChat.mockReturnValue({
      messages: [],
      isStreaming: false,
      error: null,
      canSendMessages: true,
      sendMessage,
      clearHistory: vi.fn(),
    });

    render(<ChatPanel analysisId="analysis-1" token="tok" />);

    fireEvent.click(screen.getByRole("button", { name: "Open chat" }));

    expect(screen.getByText("Chat with Report")).toBeInTheDocument();
    expect(screen.getByText("Report-grounded AI review")).toBeInTheDocument();
    expect(screen.getByText("Current report record")).toBeInTheDocument();
    expect(
      screen.getByLabelText("Report AI suggested prompts"),
    ).toBeInTheDocument();
    expect(mockScrollIntoView).not.toHaveBeenCalled();
    const materialRiskPrompt = screen
      .getByText("Material risks")
      .closest("button");
    expect(materialRiskPrompt).toHaveClass("min-h-14");
    fireEvent.click(
      screen.getByRole("button", { name: "Summarize the key findings" }),
    );

    const composer = screen.getByPlaceholderText("Ask about the report...");
    expect(composer).toHaveValue("Summarize the key findings");

    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => {
      expect(sendMessage).toHaveBeenCalledWith(
        "Summarize the key findings",
        undefined,
      );
      expect(composer).toHaveValue("");
    });
  });

  it("shows launch context and seeds the context prompt before sending", async () => {
    const sendMessage = vi.fn();
    const contextPrompt =
      "Review the Patents section of this FTO report with evidence basis and counsel follow-up.";
    mockUseReportChat.mockReturnValue({
      messages: [],
      isStreaming: false,
      error: null,
      canSendMessages: true,
      sendMessage,
      clearHistory: vi.fn(),
    });

    render(
      <ChatPanel
        analysisId="analysis-1"
        token="tok"
        launchContext={{
          description: "Material patents, claim-level risk, and blockers.",
          intent: "section",
          metadata: [
            { label: "Patents", value: "5 records" },
            { label: "Claims", value: "18 analyzed" },
          ],
          prompt: contextPrompt,
          title: "Patents section",
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Open chat" }));

    expect(screen.getByText("Launch context")).toBeInTheDocument();
    expect(screen.getByText("Patents section")).toBeInTheDocument();
    expect(
      screen.getByText("Material patents, claim-level risk, and blockers."),
    ).toBeInTheDocument();
    expect(screen.getByText("5 records")).toBeInTheDocument();
    expect(screen.getByText(contextPrompt)).toHaveClass("line-clamp-3");

    fireEvent.click(screen.getByRole("button", { name: contextPrompt }));
    const composer = screen.getByPlaceholderText("Ask about the report...");
    expect(composer).toHaveValue(contextPrompt);

    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => {
      expect(sendMessage).toHaveBeenCalledWith(contextPrompt, undefined);
    });
  });

  it("runs a launch-context task directly from the context card", async () => {
    const sendMessage = vi.fn();
    const contextPrompt =
      "Verify reliance gaps for succinic acid with cited evidence and counsel follow-up.";
    mockUseReportChat.mockReturnValue({
      messages: [],
      isStreaming: false,
      error: null,
      canSendMessages: true,
      sendMessage,
      clearHistory: vi.fn(),
    });

    render(
      <ChatPanel
        analysisId="analysis-1"
        token="tok"
        open
        launchContext={{
          actionLabel: "Generate reliance gap brief",
          description: "Opened from the report readiness console.",
          intent: "report",
          metadata: [{ label: "Export", value: "blocked" }],
          prompt: contextPrompt,
          title: "succinic acid reliance gaps",
        }}
      />,
    );

    const launchButton = screen.getByRole("button", {
      name: "Generate reliance gap brief",
    });
    expect(launchButton).toHaveClass("min-h-11");

    fireEvent.click(launchButton);

    expect(sendMessage).toHaveBeenCalledTimes(1);
    expect(sendMessage).toHaveBeenCalledWith(contextPrompt, undefined);
    expect(screen.getByPlaceholderText("Ask about the report...")).toHaveValue(
      "",
    );
  });

  it("does not auto-submit URL or launched context without user action", () => {
    const sendMessage = vi.fn();
    mockUseReportChat.mockReturnValue({
      messages: [],
      isStreaming: false,
      error: null,
      canSendMessages: true,
      sendMessage,
      clearHistory: vi.fn(),
    });

    render(
      <ChatPanel
        analysisId="analysis-1"
        token="tok"
        open
        launchContext={{
          actionLabel: "Generate blocker brief",
          description: "Opened from a dashboard AI command.",
          intent: "report",
          prompt: "Draft a source-grounded blocking-patent brief.",
          title: "succinic acid blocker brief",
        }}
      />,
    );

    expect(sendMessage).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "Generate blocker brief" }),
    ).toHaveClass("min-h-11");
  });

  it("stages the launch prompt when chat is unavailable instead of dropping it", () => {
    const sendMessage = vi.fn();
    mockUseReportChat.mockReturnValue({
      messages: [],
      isStreaming: false,
      error: null,
      canSendMessages: false,
      sendMessage,
      clearHistory: vi.fn(),
    });

    render(
      <ChatPanel
        analysisId="analysis-1"
        token={null}
        open
        launchContext={{
          actionLabel: "Generate reliance gap brief",
          description: "Opened from the report readiness console.",
          intent: "report",
          prompt: "Verify reliance gaps for succinic acid.",
          title: "succinic acid reliance gaps",
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Stage prompt" }));

    expect(sendMessage).not.toHaveBeenCalled();
    expect(screen.getByPlaceholderText("Ask about the report...")).toHaveValue(
      "Verify reliance gaps for succinic acid.",
    );
  });

  it("routes a generated launch-context answer into review handoff", async () => {
    const onCreateReviewHandoff = vi.fn();
    const contextPrompt = "Verify reliance gaps for succinic acid.";
    const generatedMessages: ChatMessage[] = [
      {
        id: "m-user-brief",
        role: "user",
        content: contextPrompt,
        timestamp: "2026-04-24T10:00:00.000Z",
      },
      ...messages,
    ];
    mockUseReportChat.mockReturnValue({
      messages: generatedMessages,
      isStreaming: false,
      error: null,
      canSendMessages: true,
      sendMessage: vi.fn(),
      clearHistory: vi.fn(),
    });

    render(
      <ChatPanel
        analysisId="analysis-1"
        token="tok"
        open
        launchContext={{
          actionLabel: "Generate reliance gap brief",
          description: "Opened from the report readiness console.",
          intent: "report",
          metadata: [
            { label: "Export", value: "blocked" },
            { label: "Review", value: "2 / 4 findings reviewed" },
          ],
          prompt: contextPrompt,
          title: "succinic acid reliance gaps",
        }}
        onCreateReviewHandoff={onCreateReviewHandoff}
      />,
    );

    const sendBriefButton = screen.getByRole("button", {
      name: "Send brief to review",
    });
    expect(sendBriefButton).toHaveClass("min-h-11");

    await act(async () => {
      fireEvent.click(sendBriefButton);
    });

    expect(onCreateReviewHandoff).toHaveBeenCalledWith(
      expect.objectContaining({
        body: expect.stringContaining("**Praviar AI-generated review brief**"),
        promote_to_under_review: true,
        review_note: expect.stringContaining(
          "AI-generated report chat brief sent for reviewer follow-up",
        ),
        target_id: "analysis-1",
        target_type: "analysis",
      }),
    );
    const [draft] = onCreateReviewHandoff.mock.calls[0];
    expect(draft.body).toContain("Task: succinic acid reliance gaps");
    expect(draft.body).toContain("Action: Generate reliance gap brief");
    expect(draft.body).toContain("Prompt that generated this brief");
    expect(draft.body).toContain(contextPrompt);
    expect(draft.body).toContain("- Export: blocked");
    expect(draft.body).toContain("- Review: 2 / 4 findings reviewed");
    expect(draft.body).toContain(
      "Decision-support output only. This does not indicate legal clearance.",
    );
    expect(draft.body).toContain("Here is the answer.");
    expect(draft.body).toContain("US123");
    expect(draft.body).toContain("Example citation text");
    expect(draft.body).toContain("Verify against original patent documents");
  });

  it("does not offer review handoff before a generated answer exists", () => {
    mockUseReportChat.mockReturnValue({
      messages: [],
      isStreaming: false,
      error: null,
      canSendMessages: true,
      sendMessage: vi.fn(),
      clearHistory: vi.fn(),
    });

    render(
      <ChatPanel
        analysisId="analysis-1"
        token="tok"
        open
        launchContext={{
          actionLabel: "Generate reliance gap brief",
          description: "Opened from the report readiness console.",
          intent: "report",
          prompt: "Verify reliance gaps for succinic acid.",
          title: "succinic acid reliance gaps",
        }}
        onCreateReviewHandoff={vi.fn()}
      />,
    );

    expect(
      screen.queryByRole("button", { name: "Send brief to review" }),
    ).not.toBeInTheDocument();
  });

  it("does not route a stale assistant answer for a newer launch context", () => {
    mockUseReportChat.mockReturnValue({
      messages: [
        {
          id: "m-user-old",
          role: "user",
          content: "Prepare reviewer questions for succinic acid.",
          timestamp: "2026-04-24T10:00:00.000Z",
        },
        ...messages,
      ],
      isStreaming: false,
      error: null,
      canSendMessages: true,
      sendMessage: vi.fn(),
      clearHistory: vi.fn(),
    });

    render(
      <ChatPanel
        analysisId="analysis-1"
        token="tok"
        open
        launchContext={{
          actionLabel: "Generate blocker brief",
          description: "Opened from a dashboard command.",
          intent: "report",
          prompt: "Draft a source-grounded blocking-patent brief.",
          title: "succinic acid blocker brief",
        }}
        onCreateReviewHandoff={vi.fn()}
      />,
    );

    expect(
      screen.queryByRole("button", { name: "Send brief to review" }),
    ).not.toBeInTheDocument();
  });

  it("does not route a manual follow-up answer as the launch brief", () => {
    mockUseReportChat.mockReturnValue({
      messages: [
        {
          id: "m-user-launch",
          role: "user",
          content: "Prepare reviewer questions for succinic acid.",
          timestamp: "2026-04-24T10:00:00.000Z",
        },
        {
          id: "m-assistant-launch",
          role: "assistant",
          content: "Launch answer.",
          timestamp: "2026-04-24T10:00:01.000Z",
        },
        {
          id: "m-user-manual",
          role: "user",
          content: "Now rewrite that more briefly.",
          timestamp: "2026-04-24T10:00:02.000Z",
        },
        {
          id: "m-assistant-manual",
          role: "assistant",
          content: "Short manual follow-up answer.",
          timestamp: "2026-04-24T10:00:03.000Z",
        },
      ],
      isStreaming: false,
      error: null,
      canSendMessages: true,
      sendMessage: vi.fn(),
      clearHistory: vi.fn(),
    });

    render(
      <ChatPanel
        analysisId="analysis-1"
        token="tok"
        open
        launchContext={{
          actionLabel: "Preparing reviewer questions",
          description: "Opened from a dashboard command.",
          intent: "report",
          prompt: "Prepare reviewer questions for succinic acid.",
          title: "succinic acid reviewer questions",
        }}
        onCreateReviewHandoff={vi.fn()}
      />,
    );

    expect(
      screen.queryByRole("button", { name: "Send brief to review" }),
    ).not.toBeInTheDocument();
  });

  it("hides review handoff when chat is not authenticated", () => {
    mockUseReportChat.mockReturnValue({
      messages: [
        {
          id: "m-user-brief",
          role: "user",
          content: "Verify reliance gaps for succinic acid.",
          timestamp: "2026-04-24T10:00:00.000Z",
        },
        ...messages,
      ],
      isStreaming: false,
      error: null,
      canSendMessages: false,
      sendMessage: vi.fn(),
      clearHistory: vi.fn(),
    });

    render(
      <ChatPanel
        analysisId="analysis-1"
        token={null}
        open
        launchContext={{
          actionLabel: "Generate reliance gap brief",
          description: "Opened from the report readiness console.",
          intent: "report",
          prompt: "Verify reliance gaps for succinic acid.",
          title: "succinic acid reliance gaps",
        }}
        onCreateReviewHandoff={vi.fn()}
      />,
    );

    expect(
      screen.queryByRole("button", { name: "Send brief to review" }),
    ).not.toBeInTheDocument();
  });

  it("dedupes generated brief handoff while the submission is pending", async () => {
    let resolveHandoff: (() => void) | undefined;
    const onCreateReviewHandoff = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveHandoff = resolve;
        }),
    );
    mockUseReportChat.mockReturnValue({
      messages: [
        {
          id: "m-user-brief",
          role: "user",
          content: "Verify reliance gaps for succinic acid.",
          timestamp: "2026-04-24T10:00:00.000Z",
        },
        ...messages,
      ],
      isStreaming: false,
      error: null,
      canSendMessages: true,
      sendMessage: vi.fn(),
      clearHistory: vi.fn(),
    });

    render(
      <ChatPanel
        analysisId="analysis-1"
        token="tok"
        open
        launchContext={{
          actionLabel: "Generate reliance gap brief",
          description: "Opened from the report readiness console.",
          intent: "report",
          prompt: "Verify reliance gaps for succinic acid.",
          title: "succinic acid reliance gaps",
        }}
        onCreateReviewHandoff={onCreateReviewHandoff}
      />,
    );

    const button = screen.getByRole("button", {
      name: "Send brief to review",
    });
    fireEvent.click(button);
    fireEvent.click(button);

    expect(onCreateReviewHandoff).toHaveBeenCalledTimes(1);
    expect(button).toBeDisabled();

    resolveHandoff?.();
    await waitFor(() => expect(button).not.toBeDisabled());
  });

  it("redacts generated brief diagnostics before creating review handoff", async () => {
    const onCreateReviewHandoff = vi.fn();
    const prompt =
      "Verify postgres://user:pass@localhost/db with Bearer abc123 and /Users/example-user/private.";
    mockUseReportChat.mockReturnValue({
      messages: [
        {
          id: "m-user-secret",
          role: "user",
          content: prompt,
          timestamp: "2026-04-24T10:00:00.000Z",
        },
        {
          id: "m-assistant-secret",
          role: "assistant",
          content:
            "Answer includes sk_live_secret and SELECT secret FROM private_table before Traceback stack.",
          citations: [
            {
              cited_text: "Citation has Bearer citationtoken and /tmp/raw.log",
              document_index: 0,
              document_title: "postgres://doc",
            },
          ],
          timestamp: "2026-04-24T10:00:01.000Z",
        },
      ],
      isStreaming: false,
      error: null,
      canSendMessages: true,
      sendMessage: vi.fn(),
      clearHistory: vi.fn(),
    });

    render(
      <ChatPanel
        analysisId="analysis-1"
        token="tok"
        open
        launchContext={{
          actionLabel: "Generate reliance gap brief",
          description: "Opened from the report readiness console.",
          intent: "report",
          metadata: [
            { label: "Secret", value: "sk_test_secret /var/tmp/provider" },
          ],
          prompt,
          title: "succinic acid reliance gaps",
        }}
        onCreateReviewHandoff={onCreateReviewHandoff}
      />,
    );

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Send brief to review" }),
      );
    });

    const [draft] = onCreateReviewHandoff.mock.calls[0];
    expect(draft.body).not.toContain("postgres://");
    expect(draft.body).not.toContain("Bearer abc123");
    expect(draft.body).not.toContain("sk_live_secret");
    expect(draft.body).not.toContain("sk_test_secret");
    expect(draft.body).not.toContain("/Users/example-user/private");
    expect(draft.body).not.toContain("private_table");
    expect(draft.body).toContain("[redacted connection string]");
    expect(draft.body).toContain("Bearer [redacted]");
    expect(draft.body).toContain("[redacted API key]");
    expect(draft.body).toContain("[redacted path]");
    expect(draft.body).toContain("[redacted query]");
  });

  it("targets patent review when the generated brief belongs to a patent chat", async () => {
    const onCreateReviewHandoff = vi.fn();
    mockUseReportChat.mockReturnValue({
      messages: [
        {
          id: "m-user-patent",
          role: "user",
          content: "Review patent US123 in this FTO report.",
          timestamp: "2026-04-24T10:00:00.000Z",
        },
        ...messages,
      ],
      isStreaming: false,
      error: null,
      canSendMessages: true,
      sendMessage: vi.fn(),
      clearHistory: vi.fn(),
    });

    render(
      <ChatPanel
        analysisId="analysis-1"
        token="tok"
        open
        patentId="US123"
        launchContext={{
          actionLabel: "Generating patent review",
          description: "Opened from reviewed evidence search results.",
          intent: "patent",
          prompt: "Review patent US123 in this FTO report.",
          title: "Patent US123",
        }}
        onCreateReviewHandoff={onCreateReviewHandoff}
      />,
    );

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Send brief to review" }),
      );
    });

    expect(onCreateReviewHandoff).toHaveBeenCalledWith(
      expect.objectContaining({
        target_id: "US123",
        target_type: "patent",
      }),
    );
  });

  it("uses mobile-safe panel geometry before the desktop width takes over", () => {
    render(<ChatPanel analysisId="analysis-1" token="tok" />);

    fireEvent.click(screen.getByRole("button", { name: "Open chat" }));

    const dialog = screen.getByRole("dialog", { name: "Chat with report" });
    expect(dialog).toHaveClass("inset-x-3");
    expect(dialog).toHaveClass("max-h-[calc(100dvh-1.5rem)]");
    expect(dialog).toHaveClass("sm:w-[420px]");
    expect(screen.getByRole("button", { name: "Maximize chat" })).toHaveClass(
      "h-11",
      "w-11",
    );
    expect(screen.getByRole("button", { name: "Close chat" })).toHaveClass(
      "h-11",
      "w-11",
    );
    const chatTab = screen.getByRole("tab", { name: "Chat" });
    const evidenceTab = screen.getByRole("tab", { name: "Evidence search" });
    expect(chatTab).toHaveClass("min-h-11");
    expect(evidenceTab).toHaveClass("min-h-11");
    expect(chatTab).toHaveAttribute("aria-controls", "report-chat-panel-chat");
    expect(evidenceTab).toHaveAttribute(
      "aria-controls",
      "report-chat-panel-evidence",
    );
    expect(screen.getByRole("tabpanel"))
      .toHaveAttribute("aria-labelledby", "report-chat-tab-chat")
      .toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("tabpanel")).toHaveClass(
      "focus-visible:ring-2",
      "focus-visible:ring-inset",
    );
    expect(screen.getByPlaceholderText("Ask about the report...")).toHaveClass(
      "min-h-11",
    );
    expect(screen.getByRole("button", { name: "Send message" })).toHaveClass(
      "h-11",
      "w-11",
    );
  });

  it("traps forward and reverse Tab inside the chat dialog", () => {
    render(<ChatPanel analysisId="analysis-1" token="tok" />);

    fireEvent.click(screen.getByRole("button", { name: "Open chat" }));

    const dialog = screen.getByRole("dialog", { name: "Chat with report" });
    const maximize = within(dialog).getByRole("button", {
      name: "Maximize chat",
    });
    const evidenceSearch = within(dialog).getByRole("tab", {
      name: "Evidence search",
    });
    const evidencePanel = within(dialog).getByRole("tabpanel");

    fireEvent.click(evidenceSearch);
    maximize.focus();
    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    expect(evidencePanel).toHaveFocus();

    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(maximize).toHaveFocus();
  });

  it("renders existing messages, routes citation clicks, and confirms clearing history", async () => {
    const clearHistory = vi.fn().mockResolvedValue(true);
    const onCitationClick = vi.fn();
    mockUseReportChat.mockReturnValue({
      messages,
      isStreaming: false,
      error: null,
      canSendMessages: true,
      sendMessage: vi.fn(),
      clearHistory,
    });

    render(
      <ChatPanel
        analysisId="analysis-1"
        token="tok"
        patentId="US123"
        onCitationClick={onCitationClick}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Open chat" }));

    expect(screen.getByText("Chat: US123")).toBeInTheDocument();
    expect(screen.getByText("Here is the answer.")).toBeInTheDocument();
    expect(mockScrollIntoView).toHaveBeenCalledWith({ behavior: "smooth" });

    fireEvent.click(screen.getByRole("button", { name: "Clear chat history" }));
    expect(clearHistory).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "Confirm clear chat history" }),
    ).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Confirm clear chat history" }),
      );
    });
    expect(clearHistory).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /Open citation 3/i }));
    expect(onCitationClick).toHaveBeenCalledWith(citation, 3);
    expect(
      screen.getByRole("button", { name: /Open citation 3/i }),
    ).toHaveClass("min-h-11", "min-w-11", "text-xs");
  });

  it("wraps long chat messages inside the bubble", () => {
    mockUseReportChat.mockReturnValue({
      messages: [
        {
          id: "long-user",
          role: "user",
          content: "C".repeat(180),
          timestamp: "2026-07-01T00:00:00.000Z",
        },
      ],
      isStreaming: false,
      error: null,
      canSendMessages: true,
      sendMessage: vi.fn(),
      clearHistory: vi.fn(),
    });

    render(<ChatPanel analysisId="analysis-1" token="tok" />);

    fireEvent.click(screen.getByRole("button", { name: "Open chat" }));

    const bubbleText = screen.getByText("C".repeat(180));
    expect(bubbleText).toHaveClass("break-words");
    expect(bubbleText.parentElement).toHaveClass("[overflow-wrap:anywhere]");
  });

  it("uses instant autoscroll when reduced motion is preferred", () => {
    mockMatchMedia.mockReturnValue({
      matches: true,
      media: "(prefers-reduced-motion: reduce)",
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    });
    mockUseReportChat.mockReturnValue({
      messages,
      isStreaming: false,
      error: null,
      canSendMessages: true,
      sendMessage: vi.fn(),
      clearHistory: vi.fn(),
    });

    render(<ChatPanel analysisId="analysis-1" token="tok" />);

    fireEvent.click(screen.getByRole("button", { name: "Open chat" }));

    expect(mockScrollIntoView).toHaveBeenCalledWith({ behavior: "auto" });
  });

  it("shows patent-specific placeholder text plus streaming and error states", async () => {
    mockUseReportChat.mockReturnValue({
      messages: [],
      isStreaming: true,
      error: "Something went wrong",
      canSendMessages: true,
      sendMessage: vi.fn(),
      clearHistory: vi.fn(),
    });

    render(<ChatPanel analysisId="analysis-1" token="tok" patentId="US999" />);

    fireEvent.click(screen.getByRole("button", { name: "Open chat" }));

    expect(
      screen.getByPlaceholderText("Ask about this patent..."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Patent-grounded AI review for US999"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "What are the key claims in this patent?",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: /What questions should counsel review for this patent/i,
      }),
    ).toHaveClass("min-h-14");
    expect(screen.getByText("Reviewing evidence...")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
  });

  it("clears private composer text and returns to chat mode on auth boundary changes", () => {
    render(<ChatPanel analysisId="analysis-1" token="tok" />);

    fireEvent.click(screen.getByRole("button", { name: "Open chat" }));
    fireEvent.click(screen.getByRole("tab", { name: "Evidence search" }));

    expect(
      screen.getByRole("tab", { name: "Evidence search" }),
    ).toHaveAttribute("aria-selected", "true");

    fireEvent.click(screen.getByRole("tab", { name: "Chat" }));
    fireEvent.change(screen.getByPlaceholderText("Ask about the report..."), {
      target: { value: "private analysis draft" },
    });

    expect(screen.getByPlaceholderText("Ask about the report...")).toHaveValue(
      "private analysis draft",
    );

    act(() => {
      emitAuthBoundaryChanged({ refreshToken: false });
    });

    expect(screen.getByRole("tab", { name: "Chat" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByPlaceholderText("Ask about the report...")).toHaveValue(
      "",
    );
  });

  it("keeps drafts in place when report chat is unavailable", () => {
    const sendMessage = vi.fn();
    mockUseReportChat.mockReturnValue({
      messages: [],
      isStreaming: false,
      error: null,
      canSendMessages: false,
      sendMessage,
      clearHistory: vi.fn(),
    });

    render(<ChatPanel analysisId="ana_demo_001" token={null} />);

    fireEvent.click(screen.getByRole("button", { name: "Open chat" }));

    const composer = screen.getByPlaceholderText("Ask about the report...");
    fireEvent.change(composer, {
      target: { value: "Summarize blockers without losing this draft" },
    });
    fireEvent.keyDown(composer, { key: "Enter" });

    expect(sendMessage).not.toHaveBeenCalled();
    expect(composer).toHaveValue(
      "Summarize blockers without losing this draft",
    );
    expect(
      screen.getByRole("button", { name: "Chat unavailable" }),
    ).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent(
      REPORT_CHAT_UNAVAILABLE_MESSAGE,
    );
    expect(composer).toHaveAttribute(
      "aria-describedby",
      "report-chat-composer-status",
    );
  });

  it("supports a controlled mobile launcher and restores focus to the external trigger", async () => {
    const onOpenChange = vi.fn();

    function ControlledChatPanel() {
      const [open, setOpen] = useState(true);
      const triggerRef = useRef<HTMLButtonElement>(null);

      return (
        <>
          <button ref={triggerRef} type="button">
            Ask about report evidence
          </button>
          <ChatPanel
            analysisId="analysis-1"
            token="tok"
            open={open}
            onOpenChange={(nextOpen) => {
              onOpenChange(nextOpen);
              setOpen(nextOpen);
            }}
            hideLauncher
            returnFocusRef={triggerRef}
          />
        </>
      );
    }

    render(<ControlledChatPanel />);

    expect(
      screen.queryByRole("button", { name: "Open chat" }),
    ).not.toBeInTheDocument();

    const dialog = screen.getByRole("dialog", { name: "Chat with report" });
    fireEvent.keyDown(dialog, { key: "Escape" });

    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false);
      expect(
        screen.queryByRole("dialog", { name: "Chat with report" }),
      ).not.toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Ask about report evidence" }),
      ).toHaveFocus();
    });
  });
});
