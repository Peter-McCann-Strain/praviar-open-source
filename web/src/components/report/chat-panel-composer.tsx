import type { KeyboardEvent, RefObject } from "react";
import { Loader2, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { REPORT_CHAT_UNAVAILABLE_MESSAGE } from "@/hooks/report-interaction-copy";

interface ChatPanelComposerProps {
  canSendMessages?: boolean;
  input: string;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  isStreaming: boolean;
  onChange: (value: string) => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onSend: () => void;
  patentId?: string;
}

export function ChatPanelComposer({
  canSendMessages = true,
  input,
  inputRef,
  isStreaming,
  onChange,
  onKeyDown,
  onSend,
  patentId,
}: ChatPanelComposerProps) {
  const statusId = canSendMessages ? undefined : "report-chat-composer-status";

  return (
    <div className="border-t border-[var(--border-default)] p-3">
      <div className="flex items-end gap-2">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          aria-describedby={statusId}
          placeholder={
            patentId ? "Ask about this patent..." : "Ask about the report..."
          }
          rows={1}
          className="praviar-glass-field min-h-11 flex-1 resize-none rounded-lg px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-disabled)] transition-colors focus:border-brand-primary/50 focus:outline-none"
          style={{ maxHeight: "120px" }}
          onInput={(event) => {
            const target = event.target as HTMLTextAreaElement;
            target.style.height = "auto";
            target.style.height = `${Math.min(target.scrollHeight, 120)}px`;
          }}
        />
        <Button
          size="sm"
          onClick={onSend}
          disabled={!input.trim() || isStreaming || !canSendMessages}
          className="h-11 w-11 flex-shrink-0 p-0"
          aria-label={
            !canSendMessages
              ? "Chat unavailable"
              : isStreaming
                ? "Streaming response"
                : "Send message"
          }
        >
          {isStreaming ? (
            <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </div>
      {!canSendMessages ? (
        <p
          id={statusId}
          role="status"
          className="mt-2 rounded-md border border-warning/25 bg-warning/10 px-3 py-2 text-xs leading-4 text-[var(--text-secondary)]"
        >
          {REPORT_CHAT_UNAVAILABLE_MESSAGE}
        </p>
      ) : null}
      <p className="mt-1.5 text-center text-xs text-[var(--text-disabled)]">
        AI-assisted analysis. Always verify with original patent documents.
      </p>
    </div>
  );
}
