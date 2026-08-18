"use client";

import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { PRIMARY_TABS, type ReportTabConfig, type ReportTabId } from "./tabs";

const MOBILE_COMMAND_BAR_SCROLL_MARGIN =
  "scroll-mb-[calc(6.75rem+env(safe-area-inset-bottom))] lg:scroll-mb-0";

interface ReportPageTabsProps {
  tab: ReportTabId;
  overflowTabs: ReportTabConfig[];
  tabCounts: Record<string, number>;
  onTabChange: (tab: ReportTabId) => void;
}

export function ReportPageTabs({
  tab,
  overflowTabs,
  tabCounts,
  onTabChange,
}: ReportPageTabsProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const firstMenuItemRef = useRef<HTMLButtonElement>(null);
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const visiblePrimaryTabs = PRIMARY_TABS;
  const menuTabs = overflowTabs;
  const allTabs = [...visiblePrimaryTabs, ...menuTabs];
  const activeOverflowTab = menuTabs.find((tabConfig) => tabConfig.id === tab);
  const tabOrder = visiblePrimaryTabs.map((tabConfig) => tabConfig.id);

  useEffect(() => {
    if (!menuOpen) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setMenuOpen(false);
        requestAnimationFrame(() => menuButtonRef.current?.focus());
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [menuOpen]);

  useEffect(() => {
    if (!menuOpen) return;
    requestAnimationFrame(() => firstMenuItemRef.current?.focus());
  }, [menuOpen]);

  const selectOverflowTab = (nextTab: ReportTabId) => {
    onTabChange(nextTab);
    setMenuOpen(false);
  };

  const focusTab = (index: number) => {
    const nextTabId = tabOrder[index];
    if (nextTabId) {
      tabRefs.current[nextTabId]?.focus();
    }
  };

  const handleTabKeyDown = (
    event: ReactKeyboardEvent<HTMLButtonElement>,
    index: number,
  ) => {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      focusTab((index + 1) % tabOrder.length);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      focusTab((index - 1 + tabOrder.length) % tabOrder.length);
    } else if (event.key === "Home") {
      event.preventDefault();
      focusTab(0);
    } else if (event.key === "End") {
      event.preventDefault();
      focusTab(tabOrder.length - 1);
    }
  };

  const getTabCountLabel = (tabConfig: ReportTabConfig) => {
    const count = tabCounts[tabConfig.id];
    return count != null && count > 0
      ? `${tabConfig.label}, ${count} record${count === 1 ? "" : "s"}`
      : tabConfig.label;
  };

  const focusMenuItem = (index: number) => {
    const items = Array.from(
      menuRef.current?.querySelectorAll<HTMLButtonElement>(
        '[role="menuitem"]',
      ) ?? [],
    );
    if (items.length === 0) return;
    items[index]?.focus();
  };

  const handleMenuKeyDown = (
    event: ReactKeyboardEvent<HTMLButtonElement>,
    index: number,
  ) => {
    if (event.key === "Escape") {
      event.preventDefault();
      setMenuOpen(false);
      requestAnimationFrame(() => menuButtonRef.current?.focus());
      return;
    }

    const menuItemCount = menuTabs.length;
    if (menuItemCount === 0) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      focusMenuItem((index + 1) % menuItemCount);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      focusMenuItem((index - 1 + menuItemCount) % menuItemCount);
    } else if (event.key === "Home") {
      event.preventDefault();
      focusMenuItem(0);
    } else if (event.key === "End") {
      event.preventDefault();
      focusMenuItem(menuItemCount - 1);
    }
  };

  return (
    <div
      className="sticky top-14 z-30 scroll-mb-[calc(6.75rem+env(safe-area-inset-bottom))] lg:scroll-mb-0"
      data-no-print
    >
      {activeOverflowTab ? (
        <span id={`overflow-tab-${activeOverflowTab.id}`} className="sr-only">
          {activeOverflowTab.label}
        </span>
      ) : null}
      <div className="flex max-w-full items-stretch gap-2">
        <div className="relative min-w-0 flex-1 sm:hidden">
          <select
            aria-label="Report section"
            value={tab}
            className={cn(
              MOBILE_COMMAND_BAR_SCROLL_MARGIN,
              "min-h-11 w-full appearance-none rounded-lg border border-[var(--border-default)] bg-[var(--surface-glass)] py-2 pl-3 pr-10 text-sm font-semibold text-[var(--text-primary)] shadow-[var(--shadow-xs)] backdrop-blur-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]",
            )}
            onChange={(event) =>
              onTabChange(event.currentTarget.value as ReportTabId)
            }
          >
            {allTabs.map((tabConfig) => (
              <option key={tabConfig.id} value={tabConfig.id}>
                {getTabCountLabel(tabConfig)}
              </option>
            ))}
          </select>
          <ChevronDown
            className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-brand-primary"
            aria-hidden="true"
          />
        </div>
        <div className="relative hidden min-w-0 flex-1 sm:block">
          <div
            role="tablist"
            aria-label="Report sections"
            className={cn(
              MOBILE_COMMAND_BAR_SCROLL_MARGIN,
              "grid min-w-0 flex-1 grid-cols-5 items-center gap-1 rounded-lg border border-[var(--border-default)] bg-[var(--surface-glass)] p-1 shadow-[var(--shadow-xs)] backdrop-blur-xl",
            )}
            data-praviar-report-tabs-stable-shell
          >
            {visiblePrimaryTabs.map((tabConfig, index) => {
              const Icon = tabConfig.icon;
              const active = tabConfig.id === tab;
              return (
                <button
                  key={tabConfig.id}
                  ref={(node) => {
                    tabRefs.current[tabConfig.id] = node;
                  }}
                  type="button"
                  role="tab"
                  id={`tab-${tabConfig.id}`}
                  aria-label={getTabCountLabel(tabConfig)}
                  aria-selected={active}
                  aria-controls={
                    active ? `tabpanel-${tabConfig.id}` : undefined
                  }
                  data-state={active ? "active" : "inactive"}
                  tabIndex={
                    active || (activeOverflowTab && index === 0) ? 0 : -1
                  }
                  className={cn(
                    "inline-flex min-h-11 min-w-[6.5rem] flex-1 shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg border border-transparent px-2 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)] sm:min-w-0 sm:shrink sm:gap-1 sm:px-2 sm:text-sm lg:gap-2 lg:px-4",
                    MOBILE_COMMAND_BAR_SCROLL_MARGIN,
                    active && "praviar-glass-pill text-brand-primary",
                  )}
                  onClick={() => onTabChange(tabConfig.id)}
                  onKeyDown={(event) => handleTabKeyDown(event, index)}
                >
                  <Icon className="h-3.5 w-3.5 flex-shrink-0 sm:h-4 sm:w-4" />
                  <span className="min-w-0">
                    {tabConfig.shortLabel ?? tabConfig.label}
                  </span>
                  {tabCounts[tabConfig.id] != null &&
                    tabCounts[tabConfig.id] > 0 && (
                      <span className="hidden text-xs tabular-nums opacity-80 lg:inline">
                        ({tabCounts[tabConfig.id]})
                      </span>
                    )}
                </button>
              );
            })}
          </div>
        </div>
        <div
          ref={menuRef}
          className="relative hidden flex-shrink-0 sm:block"
          onBlur={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget)) {
              setMenuOpen(false);
            }
          }}
        >
          <button
            ref={menuButtonRef}
            type="button"
            className={cn(
              "inline-flex min-h-11 w-24 items-center justify-center gap-1.5 rounded-lg border border-[var(--border-default)] bg-[var(--surface-glass)] px-3 text-xs font-medium text-[var(--text-secondary)] shadow-[var(--shadow-xs)] backdrop-blur-xl transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)] sm:w-36 sm:text-sm lg:w-44",
              MOBILE_COMMAND_BAR_SCROLL_MARGIN,
              activeOverflowTab && "praviar-glass-pill text-brand-primary",
            )}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            aria-controls={menuOpen ? "secondary-report-sections" : undefined}
            aria-label={
              activeOverflowTab
                ? `More report sections, current secondary section ${activeOverflowTab.label}`
                : "More report sections"
            }
            data-state={activeOverflowTab ? "active" : "inactive"}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span className="truncate lg:hidden">
              {activeOverflowTab?.shortLabel ??
                activeOverflowTab?.label ??
                "More"}
            </span>
            <span className="hidden truncate lg:inline">
              {activeOverflowTab?.label ?? "More"}
            </span>
            <ChevronDown
              className={cn(
                "h-3.5 w-3.5 flex-shrink-0 transition-transform",
                menuOpen && "rotate-180",
              )}
              aria-hidden="true"
            />
          </button>
          {menuOpen ? (
            <div
              id="secondary-report-sections"
              role="menu"
              aria-label="Secondary report sections"
              className="praviar-dialog-panel absolute right-0 top-full z-50 mt-2 w-60 rounded-lg p-1.5"
            >
              {menuTabs.map((tabConfig, index) => {
                const Icon = tabConfig.icon;
                const active = tabConfig.id === tab;
                const count = tabCounts[tabConfig.id];
                return (
                  <button
                    key={tabConfig.id}
                    ref={index === 0 ? firstMenuItemRef : undefined}
                    type="button"
                    role="menuitem"
                    id={active ? undefined : `overflow-tab-${tabConfig.id}`}
                    className={cn(
                      "flex min-h-11 w-full items-center gap-2 rounded-lg px-3 text-left text-sm text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60",
                      active && "bg-brand-primary/10 text-brand-primary",
                    )}
                    aria-current={active ? "page" : undefined}
                    onClick={() => selectOverflowTab(tabConfig.id)}
                    onKeyDown={(event) => handleMenuKeyDown(event, index)}
                  >
                    <Icon className="h-4 w-4 flex-shrink-0" aria-hidden />
                    <span className="min-w-0 flex-1 truncate">
                      {tabConfig.label}
                    </span>
                    {count != null && count > 0 ? (
                      <span className="text-xs tabular-nums opacity-75">
                        {count}
                      </span>
                    ) : null}
                    {active ? (
                      <Check className="h-4 w-4 flex-shrink-0" aria-hidden />
                    ) : null}
                  </button>
                );
              })}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
