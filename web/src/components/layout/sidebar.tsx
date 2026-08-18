"use client";

import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { usePathname } from "next/navigation";
import dynamic from "next/dynamic";
import { ChevronLeft, X } from "lucide-react";
import { PraviarLockup } from "@/components/brand/praviar-lockup";
import { SidebarFooter } from "@/components/layout/sidebar-footer";
import { hasClerk } from "@/components/layout/sidebar-constants";
import { SidebarNav } from "@/components/layout/sidebar-nav";
import { SidebarUserPlaceholder } from "@/components/layout/sidebar-user-placeholder";
import { useAuthToken } from "@/hooks/use-auth-token";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/stores/ui-store";

// Lazy-load Clerk components — they require ClerkProvider at render time
const ClerkUserButton = dynamic(
  () => import("@clerk/nextjs").then((m) => m.UserButton),
  { ssr: false, loading: () => <SidebarUserPlaceholder /> },
);

const ClerkOrgSwitcher = dynamic(
  () => import("@clerk/nextjs").then((m) => m.OrganizationSwitcher),
  { ssr: false },
);

function ClerkScopedSidebarNav({
  pathname,
  sidebarOpen,
  onNavigate,
}: {
  pathname: string;
  sidebarOpen: boolean;
  onNavigate: () => void;
}) {
  const { isLoaded, orgRole } = useAuth();
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);

  return (
    <SidebarNav
      pathname={pathname}
      sidebarOpen={sidebarOpen}
      onNavigate={onNavigate}
      orgRole={isLoaded ? orgRole : null}
      applicationRole={principal.data?.role ?? null}
    />
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const wasMobileSidebarOpenRef = useRef(false);
  const [isMobileViewport, setIsMobileViewport] = useState(false);
  const {
    sidebarOpen,
    mobileSidebarOpen,
    setMobileSidebarOpen,
    toggleSidebar,
  } = useUIStore();
  const labelsOpen = sidebarOpen || (isMobileViewport && mobileSidebarOpen);
  const mobileClosed = isMobileViewport && !mobileSidebarOpen;

  const closeMobileSidebar = () => setMobileSidebarOpen(false);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;

    const query = window.matchMedia("(max-width: 1023px)");
    const updateIsMobileViewport = () => setIsMobileViewport(query.matches);

    updateIsMobileViewport();
    query.addEventListener("change", updateIsMobileViewport);
    return () => query.removeEventListener("change", updateIsMobileViewport);
  }, []);

  useEffect(() => {
    if (!isMobileViewport) {
      wasMobileSidebarOpenRef.current = false;
      return;
    }

    if (mobileSidebarOpen && !wasMobileSidebarOpenRef.current) {
      const activeElement = document.activeElement;
      returnFocusRef.current =
        activeElement instanceof HTMLElement ? activeElement : null;

      requestAnimationFrame(() => {
        closeButtonRef.current?.focus();
      });
    }

    if (!mobileSidebarOpen && wasMobileSidebarOpenRef.current) {
      returnFocusRef.current?.focus();
      returnFocusRef.current = null;
    }

    wasMobileSidebarOpenRef.current = mobileSidebarOpen;
  }, [isMobileViewport, mobileSidebarOpen]);

  const handleSidebarKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (!isMobileViewport || !mobileSidebarOpen) return;

    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      closeMobileSidebar();
      return;
    }

    if (event.key !== "Tab") return;

    const focusableElements = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>(
        [
          "a[href]",
          "button:not([disabled])",
          "[tabindex]:not([tabindex='-1'])",
        ].join(","),
      ),
    ).filter(
      (element) =>
        !element.hasAttribute("disabled") &&
        element.getAttribute("aria-hidden") !== "true" &&
        element.tabIndex >= 0,
    );

    if (!focusableElements.length) return;

    const firstFocusable = focusableElements[0];
    const lastFocusable = focusableElements[focusableElements.length - 1];

    if (event.shiftKey && document.activeElement === firstFocusable) {
      event.preventDefault();
      lastFocusable.focus();
    } else if (!event.shiftKey && document.activeElement === lastFocusable) {
      event.preventDefault();
      firstFocusable.focus();
    }
  };

  return (
    <>
      {/* Mobile overlay backdrop */}
      {mobileSidebarOpen && (
        <button
          type="button"
          aria-label="Close navigation drawer"
          className="praviar-overlay-scrim fixed inset-0 z-40 w-full cursor-default lg:hidden"
          onClick={closeMobileSidebar}
        />
      )}
      <aside
        id="dashboard-sidebar"
        aria-label="Main navigation"
        aria-hidden={mobileClosed ? "true" : undefined}
        inert={mobileClosed ? true : undefined}
        aria-modal={isMobileViewport && mobileSidebarOpen ? "true" : undefined}
        role={isMobileViewport && mobileSidebarOpen ? "dialog" : undefined}
        onKeyDown={handleSidebarKeyDown}
        className={cn(
          "praviar-sidebar-field fixed inset-y-0 left-0 z-50 flex flex-col border-r border-[color-mix(in_srgb,var(--surface-inverted-fg)_12%,transparent)] text-[var(--surface-inverted-fg)] shadow-[var(--shadow-lg)] backdrop-blur-xl transition-all duration-300",
          // Desktop: show as usual with collapse toggle
          "max-lg:w-[256px]",
          sidebarOpen ? "lg:w-[256px]" : "lg:w-[64px]",
          // Mobile: slide in/out
          mobileSidebarOpen
            ? "max-lg:translate-x-0"
            : "max-lg:-translate-x-full",
        )}
      >
        {/* Logo */}
        <div
          className={cn(
            "relative flex h-16 items-center border-b border-[color-mix(in_srgb,var(--surface-inverted-fg)_12%,transparent)]",
            labelsOpen ? "gap-3 px-4" : "justify-center px-2",
          )}
        >
          <Link
            href="/dashboard"
            aria-label="Praviar dashboard"
            className={cn(
              "group flex min-h-11 min-w-0 items-center rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-mint)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--surface-inverted)]",
              labelsOpen ? "gap-3" : "justify-center",
            )}
            data-praviar-brand-lockup
          >
            <PraviarLockup
              decorative={!labelsOpen}
              size="sidebar"
              surface="dark"
              showWordmark={labelsOpen}
            />
          </Link>
          <button
            type="button"
            onClick={toggleSidebar}
            aria-label={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
            tabIndex={isMobileViewport ? -1 : undefined}
            className={cn(
              "hidden items-center justify-center text-[var(--surface-inverted-fg-subtle)] transition-colors hover:bg-[color-mix(in_srgb,var(--surface-inverted-fg)_8%,transparent)] hover:text-[var(--surface-inverted-fg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-mint)] focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--surface-inverted)] lg:flex",
              sidebarOpen
                ? "ml-auto h-11 w-11 rounded"
                : "absolute -right-5 top-1/2 h-11 w-11 -translate-y-1/2 rounded-full border border-[color-mix(in_srgb,var(--surface-inverted-fg)_18%,transparent)] bg-[var(--surface-inverted)] shadow-[var(--shadow-md)]",
            )}
          >
            <ChevronLeft
              className={cn(
                "h-4 w-4 transition-transform duration-300",
                !sidebarOpen && "rotate-180",
              )}
              aria-hidden="true"
            />
          </button>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={closeMobileSidebar}
            aria-label="Close navigation"
            className="ml-auto flex h-11 w-11 items-center justify-center rounded text-[var(--surface-inverted-fg-subtle)] transition-colors hover:bg-[color-mix(in_srgb,var(--surface-inverted-fg)_8%,transparent)] hover:text-[var(--surface-inverted-fg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-mint)] focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--surface-inverted)] lg:hidden"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        {labelsOpen && hasClerk ? (
          <div className="border-b border-[color-mix(in_srgb,var(--surface-inverted-fg)_12%,transparent)] p-3">
            <ClerkOrgSwitcher
              hidePersonal
              afterSelectOrganizationUrl="/dashboard"
              afterCreateOrganizationUrl="/dashboard"
              appearance={{
                elements: {
                  rootBox: "w-full",
                  organizationSwitcherTrigger:
                    "min-h-11 w-full justify-between border border-[color-mix(in_srgb,var(--surface-inverted-fg)_18%,transparent)] bg-[color-mix(in_srgb,var(--surface-inverted-fg)_8%,transparent)] text-[var(--surface-inverted-fg)] hover:bg-[color-mix(in_srgb,var(--surface-inverted-fg)_12%,transparent)]",
                },
              }}
            />
          </div>
        ) : null}

        {hasClerk ? (
          <ClerkScopedSidebarNav
            pathname={pathname}
            sidebarOpen={labelsOpen}
            onNavigate={closeMobileSidebar}
          />
        ) : (
          <SidebarNav
            pathname={pathname}
            sidebarOpen={labelsOpen}
            onNavigate={closeMobileSidebar}
            orgRole="org:admin"
            applicationRole="admin"
          />
        )}

        <SidebarFooter
          sidebarOpen={labelsOpen}
          userControl={
            hasClerk ? <ClerkUserButton /> : <SidebarUserPlaceholder />
          }
        />
      </aside>
    </>
  );
}
