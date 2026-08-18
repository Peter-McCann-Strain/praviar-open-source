"use client";

import { useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowRight, Menu, X } from "lucide-react";
import { PraviarLockup } from "@/components/brand/praviar-lockup";
import { BRAND } from "@/marketing/content";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { PUBLIC_PRIMARY_ACTION } from "@/marketing/public-readiness";

const NAV_ITEMS = [
  { label: "Product", href: "/demo" },
  { label: "Sample Dossier", href: "/sample-reports/example-molecule-alpha" },
  { label: "Methodology", href: "/methodology" },
  { label: "Trust", href: "/trust" },
  { label: "Open Source", href: "/#project" },
];

const MOBILE_FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])';

function isNavItemActive(pathname: string, href: string) {
  if (href === "/#project") return false;
  if (href.startsWith("/sample-reports")) {
    return pathname.startsWith("/sample-reports");
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function MarketingNav() {
  const pathname = usePathname();
  const [mobileMenuState, setMobileMenuState] = useState({
    open: false,
    pathname,
  });
  const mobileNavId = useId();
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const mobileSheetRef = useRef<HTMLDivElement>(null);
  const mobileOpen =
    mobileMenuState.open && mobileMenuState.pathname === pathname;

  useEffect(() => {
    if (!mobileOpen) return;

    const body = document.body;
    const previousOverflow = body.style.overflow;
    const previousPaddingRight = body.style.paddingRight;
    const scrollbarWidth = Math.max(
      0,
      window.innerWidth - document.documentElement.clientWidth,
    );

    body.style.overflow = "hidden";
    if (scrollbarWidth > 0) {
      body.style.paddingRight = `${scrollbarWidth}px`;
    }

    const getFocusableElements = () => {
      const sheetElements = Array.from(
        mobileSheetRef.current?.querySelectorAll<HTMLElement>(
          MOBILE_FOCUSABLE_SELECTOR,
        ) ?? [],
      );

      return menuButtonRef.current
        ? [menuButtonRef.current, ...sheetElements]
        : sheetElements;
    };

    const initialFocus = mobileSheetRef.current?.querySelector<HTMLElement>(
      MOBILE_FOCUSABLE_SELECTOR,
    );
    initialFocus?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setMobileMenuState({ open: false, pathname });
        queueMicrotask(() => menuButtonRef.current?.focus());
        return;
      }

      if (event.key !== "Tab") return;

      const focusableElements = getFocusableElements();
      const firstElement = focusableElements[0];
      const lastElement = focusableElements.at(-1);
      const activeElement = document.activeElement;

      if (!firstElement || !lastElement) return;

      if (!focusableElements.includes(activeElement as HTMLElement)) {
        event.preventDefault();
        (event.shiftKey ? lastElement : (initialFocus ?? firstElement)).focus();
        return;
      }

      if (event.shiftKey && activeElement === firstElement) {
        event.preventDefault();
        lastElement.focus();
      } else if (!event.shiftKey && activeElement === lastElement) {
        event.preventDefault();
        firstElement.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      body.style.overflow = previousOverflow;
      body.style.paddingRight = previousPaddingRight;
    };
  }, [mobileOpen, pathname]);

  const closeMobileMenu = ({ restoreFocus = false } = {}) => {
    setMobileMenuState({ open: false, pathname });
    if (restoreFocus) {
      queueMicrotask(() => menuButtonRef.current?.focus());
    }
  };

  const toggleMobileMenu = () => {
    if (mobileOpen) {
      closeMobileMenu();
      return;
    }

    setMobileMenuState({ open: true, pathname });
  };

  return (
    <header className="sticky top-0 z-50 h-14 min-h-14 border-b border-[var(--border-default)] bg-[var(--surface-glass)] shadow-[var(--shadow-xs)] backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
        <Link
          href="/"
          aria-label={`${BRAND.name} home`}
          className="flex min-h-11 min-w-0 items-center gap-2 rounded-xl text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
          data-praviar-brand-lockup
          translate="no"
        >
          <PraviarLockup size="topbar" wordmark={BRAND.name} />
        </Link>

        <nav className="hidden items-center gap-6 lg:flex" aria-label="Primary">
          {NAV_ITEMS.map((item) => {
            const active = isNavItemActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "inline-flex min-h-11 min-w-11 items-center justify-center rounded-md px-2 text-sm transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
                  active
                    ? "text-[var(--text-primary)]"
                    : "text-[var(--text-secondary)]",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="hidden items-center gap-3 lg:flex">
          <Link
            href="/sign-in"
            className="inline-flex min-h-11 items-center text-sm text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
          >
            Sign In
          </Link>
          <Link
            href={PUBLIC_PRIMARY_ACTION.href}
            className={cn(buttonVariants({ size: "sm" }), "min-h-11 gap-1.5")}
          >
            {PUBLIC_PRIMARY_ACTION.label}
            <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </div>

        <button
          ref={menuButtonRef}
          type="button"
          className="praviar-glass-pill inline-flex h-11 w-11 items-center justify-center rounded-lg text-[var(--text-primary)] lg:hidden"
          onClick={toggleMobileMenu}
          aria-label={mobileOpen ? "Close menu" : "Open menu"}
          aria-controls={mobileNavId}
          aria-expanded={mobileOpen}
        >
          {mobileOpen ? (
            <X className="h-5 w-5" aria-hidden="true" />
          ) : (
            <Menu className="h-5 w-5" aria-hidden="true" />
          )}
        </button>
      </div>

      {mobileOpen && (
        <>
          <button
            type="button"
            tabIndex={-1}
            aria-label="Close navigation overlay"
            className="fixed inset-x-0 bottom-0 top-14 z-40 cursor-default bg-[rgba(11,31,36,0.46)] backdrop-blur-[2px] lg:hidden"
            data-testid="marketing-mobile-menu-scrim"
            onClick={() => closeMobileMenu({ restoreFocus: true })}
          />
          <div
            ref={mobileSheetRef}
            id={mobileNavId}
            role="dialog"
            aria-label="Primary navigation"
            aria-modal="true"
            className="fixed inset-x-0 top-14 z-50 max-h-[calc(100dvh-3.5rem)] overflow-y-auto overscroll-contain border-t border-[var(--border-default)] bg-[var(--bg-base)] px-4 py-5 shadow-[var(--shadow-lg)] lg:hidden"
            data-testid="marketing-mobile-menu-sheet"
          >
            <nav
              className="mx-auto flex max-w-lg flex-col gap-1"
              aria-label="Mobile"
            >
              <p className="type-marketing-label px-3 pb-2">Explore</p>
              {NAV_ITEMS.map((item) => {
                const active = isNavItemActive(pathname, item.href);

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex min-h-11 items-center rounded-lg px-3 py-2.5 text-base font-medium transition-colors hover:bg-[var(--surface-muted)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70",
                      active
                        ? "bg-[var(--surface-muted)] text-[var(--text-primary)]"
                        : "text-[var(--text-secondary)]",
                    )}
                    onClick={() => closeMobileMenu()}
                  >
                    {item.label}
                  </Link>
                );
              })}
              <div className="mt-3 flex flex-col gap-2 border-t border-[var(--border-subtle)] pt-4">
                <p className="type-marketing-label px-3 pb-1">Account</p>
                <Link
                  href="/sign-in"
                  className="flex min-h-11 items-center rounded-lg px-3 py-2.5 text-base font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-muted)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
                  onClick={() => closeMobileMenu()}
                >
                  Sign In
                </Link>
                <Link
                  href={PUBLIC_PRIMARY_ACTION.href}
                  className={cn(
                    buttonVariants({ size: "sm" }),
                    "min-h-11 w-full justify-center gap-1.5",
                  )}
                  onClick={() => closeMobileMenu()}
                >
                  {PUBLIC_PRIMARY_ACTION.label}
                  <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                </Link>
              </div>
            </nav>
          </div>
        </>
      )}
    </header>
  );
}
