"use client";

import { cn } from "@/lib/utils";

interface SidebarFooterProps {
  sidebarOpen: boolean;
  userControl: React.ReactNode;
}

export function SidebarFooter({
  sidebarOpen,
  userControl,
}: SidebarFooterProps) {
  return (
    <div className="space-y-3 border-t border-[color-mix(in_srgb,var(--surface-inverted-fg)_12%,transparent)] p-3">
      {sidebarOpen ? (
        <div className="flex items-center justify-center gap-1.5 rounded-md border border-[color-mix(in_srgb,var(--surface-inverted-fg)_14%,transparent)] bg-[color-mix(in_srgb,var(--surface-inverted-fg)_7%,transparent)] px-3 py-1.5 text-xs text-[var(--surface-inverted-fg-muted)]">
          <kbd className="rounded border border-[color-mix(in_srgb,var(--surface-inverted-fg)_18%,transparent)] bg-[color-mix(in_srgb,var(--surface-inverted-fg)_8%,transparent)] px-1.5 py-0.5 font-mono text-xs text-[var(--surface-inverted-fg-muted)]">
            {"\u2318"}K
          </kbd>
          <span>Search</span>
        </div>
      ) : null}
      <div
        className={cn("flex items-center gap-3", !sidebarOpen && "flex-col")}
      >
        {userControl}
      </div>
    </div>
  );
}
