import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatPanel } from "@/components/report/chat-panel";

const mockUseReportChat = vi.fn();
const mockUseReportWorkspaceSummary = vi.fn();
const mockScrollIntoView = vi.fn();

vi.mock("motion/react", () => ({
  AnimatePresence: ({ children }: { children: ReactNode }) => <>{children}</>,
  motion: {
    button: ({
      children,
      ...props
    }: ButtonHTMLAttributes<HTMLButtonElement>) => (
      <button {...props}>{children}</button>
    ),
    div: ({ children, ...props }: HTMLAttributes<HTMLDivElement>) => (
      <div {...props}>{children}</div>
    ),
  },
}));

vi.mock("@/hooks/use-report-chat", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/hooks/use-report-chat")>();
  return {
    ...actual,
    useReportChat: (...args: unknown[]) => mockUseReportChat(...args),
  };
});

vi.mock("@/hooks/use-report-workspace-summary", () => ({
  useReportWorkspaceSummary: (...args: unknown[]) =>
    mockUseReportWorkspaceSummary(...args),
}));

vi.mock("@/hooks/use-monitors", () => ({
  useCreateMonitor: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
}));

vi.mock("@/components/report/chat-panel-evidence-tab", () => ({
  ChatPanelEvidenceTab: ({
    onReviewHandoffSuccess,
  }: {
    onReviewHandoffSuccess?: () => void;
  }) => (
    <div
      data-testid="evidence-tab"
      data-has-handoff={typeof onReviewHandoffSuccess === "function"}
    />
  ),
}));

describe("ChatPanel handoff wiring", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseReportWorkspaceSummary.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    mockUseReportChat.mockReturnValue({
      messages: [],
      isStreaming: false,
      error: null,
      workspaceMeta: null,
      sendMessage: vi.fn(),
      clearHistory: vi.fn(),
    });
    HTMLElement.prototype.scrollIntoView = mockScrollIntoView;
  });

  it("forwards the review handoff success callback into the evidence workspace", async () => {
    const onReviewHandoffSuccess = vi.fn();

    render(
      <ChatPanel
        analysisId="analysis-1"
        token="tok"
        onReviewHandoffSuccess={onReviewHandoffSuccess}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Open chat" }));
    fireEvent.click(screen.getByRole("tab", { name: "Evidence search" }));

    await waitFor(() => {
      expect(screen.getByTestId("evidence-tab")).toHaveAttribute(
        "data-has-handoff",
        "true",
      );
    });
  });
});
