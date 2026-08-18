"use client";

import { MessageSquare } from "lucide-react";

interface CommentPanelHeaderProps {
  count: number;
}

export function CommentPanelHeader({ count }: CommentPanelHeaderProps) {
  return (
    <div className="flex items-center gap-2">
      <MessageSquare className="h-5 w-5 text-brand-primary" />
      <h3 className="type-heading-md text-[var(--text-primary)]">Discussion</h3>
      {count > 0 && (
        <span className="rounded-full bg-[var(--surface-muted)] px-2 py-0.5 text-xs tabular-nums text-[var(--text-tertiary)]">
          {count}
        </span>
      )}
    </div>
  );
}
