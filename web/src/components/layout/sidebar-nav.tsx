"use client";

import Link from "next/link";
import { getVisibleNavSections } from "@/components/layout/sidebar-constants";
import { cn } from "@/lib/utils";

interface SidebarNavProps {
  pathname: string;
  sidebarOpen: boolean;
  onNavigate: () => void;
  orgRole?: string | null;
  applicationRole?: string | null;
}

export function SidebarNav({
  pathname,
  sidebarOpen,
  onNavigate,
  orgRole,
  applicationRole,
}: SidebarNavProps) {
  const visibleSections = getVisibleNavSections(orgRole, applicationRole);
  const visibleItems = visibleSections.flatMap((section) => section.items);
  const activeHref = visibleItems
    .filter(
      (item) => pathname === item.href || pathname.startsWith(item.href + "/"),
    )
    .sort((left, right) => right.href.length - left.href.length)[0]?.href;

  return (
    <nav
      className="flex-1 overflow-x-visible overflow-y-auto px-2 py-4 [scrollbar-gutter:stable]"
      data-praviar-sidebar-nav
    >
      <div className={cn("space-y-4", !sidebarOpen && "space-y-2")}>
        {visibleSections.map((section, sectionIndex) => {
          const headingId = `sidebar-section-${section.id}`;

          return (
            <section
              key={section.id}
              aria-labelledby={headingId}
              className={cn(
                sectionIndex > 0 &&
                  !sidebarOpen &&
                  "border-t border-[color-mix(in_srgb,var(--surface-inverted-fg)_10%,transparent)] pt-2",
              )}
            >
              <h2
                id={headingId}
                className={cn(
                  "mb-1 px-3 text-[0.6875rem] font-semibold uppercase tracking-[0.12em] text-[var(--surface-inverted-fg-subtle)]",
                  !sidebarOpen && "sr-only",
                )}
              >
                {section.label}
              </h2>
              <ul className="space-y-0.5">
                {section.items.map((item) => {
                  const isActive = item.href === activeHref;

                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        onClick={onNavigate}
                        aria-label={!sidebarOpen ? item.label : undefined}
                        aria-current={isActive ? "page" : undefined}
                        className={cn(
                          "group relative flex min-h-11 min-w-0 items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-mint)] focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--surface-inverted)]",
                          isActive
                            ? "bg-[color-mix(in_srgb,var(--brand-primary)_26%,transparent)] font-semibold text-[var(--surface-inverted-fg)] shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--brand-mint)_20%,transparent)]"
                            : "text-[var(--surface-inverted-fg-muted)] hover:bg-[color-mix(in_srgb,var(--surface-inverted-fg)_8%,transparent)] hover:text-[var(--surface-inverted-fg)]",
                          !sidebarOpen && "justify-center px-0",
                        )}
                      >
                        <item.icon
                          className={cn(
                            "h-[18px] w-[18px] flex-shrink-0",
                            isActive
                              ? "text-[var(--brand-mint)]"
                              : "text-[var(--surface-inverted-fg-subtle)] group-hover:text-[var(--surface-inverted-fg)]",
                          )}
                          aria-hidden="true"
                        />
                        {sidebarOpen ? (
                          <span className="min-w-0 truncate">{item.label}</span>
                        ) : null}
                        {!sidebarOpen ? (
                          <span className="pointer-events-none absolute left-full z-[70] ml-2 whitespace-nowrap rounded-md border border-[color-mix(in_srgb,var(--surface-inverted-fg)_14%,transparent)] bg-[var(--surface-inverted)] px-2.5 py-1.5 text-xs font-medium text-[var(--surface-inverted-fg)] opacity-0 shadow-[var(--shadow-md)] transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100">
                            {item.label}
                          </span>
                        ) : null}
                        {isActive ? (
                          <div className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-[var(--brand-mint)]" />
                        ) : null}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })}
      </div>
    </nav>
  );
}
