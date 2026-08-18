"use client";

import type { KeyboardEvent } from "react";
import { cn } from "@/lib/utils";
import { FEEDBACK_TABS, type FeedbackTabId } from "./feedback-modal-constants";

interface FeedbackModalTabsProps {
  activeTab: FeedbackTabId;
  hasPatentContext: boolean;
  onTabChange: (tab: FeedbackTabId) => void;
}

export function FeedbackModalTabs({
  activeTab,
  hasPatentContext,
  onTabChange,
}: FeedbackModalTabsProps) {
  const availableTabs = hasPatentContext
    ? FEEDBACK_TABS
    : FEEDBACK_TABS.filter((tab) => tab.id === "report" || tab.id === "text");
  const handleKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    currentIndex: number,
  ) => {
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight") {
      nextIndex = (currentIndex + 1) % availableTabs.length;
    } else if (event.key === "ArrowLeft") {
      nextIndex =
        (currentIndex - 1 + availableTabs.length) % availableTabs.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = availableTabs.length - 1;
    }
    if (nextIndex === null) return;

    event.preventDefault();
    const nextTab = availableTabs[nextIndex];
    onTabChange(nextTab.id);
    requestAnimationFrame(() => {
      document.getElementById(`feedback-tab-${nextTab.id}`)?.focus();
    });
  };

  return (
    <div
      className={cn(
        "grid border-b border-[var(--border-default)]",
        hasPatentContext ? "grid-cols-4" : "grid-cols-2",
      )}
      role="tablist"
      aria-label="Feedback level"
    >
      {availableTabs.map((tab, index) => {
        const Icon = tab.icon;
        const active = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            id={`feedback-tab-${tab.id}`}
            type="button"
            role="tab"
            aria-selected={active}
            aria-controls={`feedback-panel-${tab.id}`}
            tabIndex={active ? 0 : -1}
            onClick={() => onTabChange(tab.id)}
            onKeyDown={(event) => handleKeyDown(event, index)}
            className={cn(
              "-mb-px flex min-w-0 items-center justify-center gap-1 border-b-2 px-1 py-2 text-xs font-medium transition-all focus-visible:rounded-t-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-1 min-[360px]:gap-1.5 min-[360px]:px-2 sm:px-3",
              active
                ? "border-brand-primary text-brand-primary"
                : "border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]",
            )}
          >
            <Icon
              className="hidden h-3.5 w-3.5 shrink-0 min-[360px]:block"
              aria-hidden="true"
            />
            <span className="truncate">{tab.label}</span>
          </button>
        );
      })}
    </div>
  );
}
