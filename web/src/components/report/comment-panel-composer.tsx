"use client";

import type { KeyboardEvent, RefObject } from "react";
import { Loader2, Reply, Send } from "lucide-react";
import { Button } from "@/components/ui/button";

const MOBILE_COMMAND_BAR_GAP_PX = 12;

function revealControlOutsideMobileCommandBar(control: HTMLElement) {
  requestAnimationFrame(() => {
    const commandBar = document.querySelector<HTMLElement>(
      "[data-praviar-mobile-command-bar]",
    );
    if (!commandBar) return;

    const controlRect = control.getBoundingClientRect();
    const commandBarRect = commandBar.getBoundingClientRect();
    const intersectsCommandBar =
      controlRect.bottom > commandBarRect.top &&
      controlRect.top < commandBarRect.bottom;
    if (!intersectsCommandBar) return;

    const commandBarIsTopRail = commandBarRect.top < window.innerHeight / 2;
    const overlap = commandBarIsTopRail
      ? commandBarRect.bottom - controlRect.top + MOBILE_COMMAND_BAR_GAP_PX
      : controlRect.bottom - commandBarRect.top + MOBILE_COMMAND_BAR_GAP_PX;

    if (overlap > 0) {
      window.scrollBy({
        top: commandBarIsTopRail ? -overlap : overlap,
        behavior: "auto",
      });
    }
  });
}

interface CommentPanelComposerProps {
  body: string;
  controlsDisabled?: boolean;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  isSubmitting: boolean;
  onBodyChange: (value: string) => void;
  onCancelReply: () => void;
  onKeyDown: (e: KeyboardEvent<HTMLTextAreaElement>) => void;
  onSubmit: () => void;
  replyTo: string | null;
}

export function CommentPanelComposer({
  body,
  controlsDisabled = false,
  inputRef,
  isSubmitting,
  onBodyChange,
  onCancelReply,
  onKeyDown,
  onSubmit,
  replyTo,
}: CommentPanelComposerProps) {
  return (
    <div className="praviar-glass-panel-soft rounded-lg p-3 space-y-3">
      {replyTo && (
        <div className="flex items-center gap-2 text-xs text-[var(--text-tertiary)]">
          <Reply className="h-3 w-3" />
          <span>Replying to comment</span>
          <button
            type="button"
            onClick={onCancelReply}
            disabled={controlsDisabled}
            className="inline-flex min-h-11 items-center rounded-md px-2 text-[var(--text-disabled)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
          >
            Cancel
          </button>
        </div>
      )}
      <textarea
        ref={inputRef}
        value={body}
        onChange={(e) => onBodyChange(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={controlsDisabled}
        placeholder="Add a comment about this analysis..."
        rows={3}
        className="praviar-glass-field w-full resize-none rounded-lg px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-disabled)] focus:border-brand-primary/60 focus:outline-none focus:ring-2 focus:ring-brand-primary/70 focus:ring-offset-2 focus:ring-offset-[var(--bg-base)]"
      />
      <div className="flex items-center justify-between">
        <span className="text-xs text-[var(--text-disabled)]">
          {"\u2318"}+Enter to send
        </span>
        <Button
          size="sm"
          onClick={onSubmit}
          onFocus={(event) =>
            revealControlOutsideMobileCommandBar(event.currentTarget)
          }
          disabled={!body.trim() || isSubmitting || controlsDisabled}
          className="min-h-11 scroll-mt-[11.5rem] gap-1.5 lg:scroll-mt-0"
        >
          {isSubmitting ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
          ) : (
            <Send className="h-3.5 w-3.5" />
          )}
          Comment
        </Button>
      </div>
    </div>
  );
}
