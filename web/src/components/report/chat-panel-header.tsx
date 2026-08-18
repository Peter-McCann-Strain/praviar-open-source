import { Maximize2, MessageSquare, Minimize2, Trash2, X } from "lucide-react";
import { useState } from "react";

interface ChatPanelHeaderProps {
  expanded: boolean;
  hasMessages: boolean;
  isClearingHistory?: boolean;
  onClearHistory: () => Promise<boolean> | boolean | void;
  onClose: () => void;
  onToggleExpanded: () => void;
  patentId?: string;
}

export function ChatPanelHeader({
  expanded,
  hasMessages,
  isClearingHistory = false,
  onClearHistory,
  onClose,
  onToggleExpanded,
  patentId,
}: ChatPanelHeaderProps) {
  const [confirmingClear, setConfirmingClear] = useState(false);

  const handleClearClick = async () => {
    if (!confirmingClear) {
      setConfirmingClear(true);
      return;
    }

    const cleared = await onClearHistory();
    if (cleared !== false) {
      setConfirmingClear(false);
    }
  };

  return (
    <div className="flex items-center justify-between gap-3 border-b border-[var(--border-default)] px-4 py-3">
      <div className="flex min-w-0 items-center gap-2">
        <MessageSquare className="h-4 w-4 shrink-0 text-brand-primary" />
        <span className="min-w-0 truncate text-sm font-semibold text-[var(--text-primary)]">
          {patentId ? `Chat: ${patentId}` : "Chat with Report"}
        </span>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {hasMessages && (
          <button
            type="button"
            onClick={handleClearClick}
            disabled={isClearingHistory}
            aria-label={
              isClearingHistory
                ? "Clearing chat history"
                : confirmingClear
                  ? "Confirm clear chat history"
                  : "Clear chat history"
            }
            className={`inline-flex h-11 items-center justify-center rounded-lg transition-colors hover:bg-[var(--surface-muted)] ${
              confirmingClear ? "w-auto gap-1.5 px-2 text-xs" : "w-11"
            }`}
            title={confirmingClear ? "Confirm clear history" : "Clear history"}
          >
            <Trash2 className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
            {confirmingClear ? (
              <span className="font-semibold text-error" aria-hidden="true">
                {isClearingHistory ? "Clearing..." : "Confirm clear"}
              </span>
            ) : null}
          </button>
        )}
        {hasMessages && confirmingClear ? (
          <button
            type="button"
            onClick={() => setConfirmingClear(false)}
            disabled={isClearingHistory}
            className="inline-flex h-11 items-center justify-center rounded-lg px-2 text-xs font-semibold text-[var(--text-tertiary)] transition-colors hover:bg-[var(--surface-muted)]"
          >
            Cancel
          </button>
        ) : null}
        <button
          type="button"
          onClick={onToggleExpanded}
          className="inline-flex h-11 w-11 items-center justify-center rounded-lg transition-colors hover:bg-[var(--surface-muted)]"
        >
          {expanded ? (
            <Minimize2 className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
          ) : (
            <Maximize2 className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
          )}
          <span className="sr-only">
            {expanded ? "Minimize chat" : "Maximize chat"}
          </span>
        </button>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex h-11 w-11 items-center justify-center rounded-lg transition-colors hover:bg-[var(--surface-muted)]"
        >
          <X className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
          <span className="sr-only">Close chat</span>
        </button>
      </div>
    </div>
  );
}
