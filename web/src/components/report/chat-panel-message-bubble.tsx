import type { ChatCitation, ChatMessage } from "@/hooks/use-report-chat";
import { getChatCitationDisplayIndex } from "@/components/report/chat-citation-mapping";
import { ChatPanelCitationChip } from "@/components/report/chat-panel-citation-chip";

interface ChatPanelMessageBubbleProps {
  message: ChatMessage;
  onCitationClick?: (citation: ChatCitation, displayIndex: number) => void;
}

export function ChatPanelMessageBubble({
  message,
  onCitationClick,
}: ChatPanelMessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-lg px-4 py-2.5 text-sm leading-relaxed [overflow-wrap:anywhere] ${
          isUser
            ? "border border-brand-primary/25 bg-brand-primary/15 text-[var(--text-primary)]"
            : "praviar-glass-chip text-[var(--text-primary)]"
        }`}
      >
        <div className="whitespace-pre-wrap break-words">{message.content}</div>

        {message.citations && message.citations.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1 border-t border-[var(--border-subtle)] pt-2">
            {message.citations.map((citation, index) => {
              const displayIndex = getChatCitationDisplayIndex(citation, index);
              return (
                <ChatPanelCitationChip
                  key={index}
                  citation={citation}
                  index={index}
                  onClick={() => onCitationClick?.(citation, displayIndex)}
                />
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
