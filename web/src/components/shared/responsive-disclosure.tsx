"use client";

import {
  useState,
  useSyncExternalStore,
  type ComponentPropsWithoutRef,
  type ReactNode,
} from "react";

const DESKTOP_DISCLOSURE_QUERY = "(min-width: 640px)";

function subscribeToDesktopDisclosure(callback: () => void) {
  if (typeof window.matchMedia !== "function") return () => undefined;
  const query = window.matchMedia(DESKTOP_DISCLOSURE_QUERY);
  query.addEventListener("change", callback);
  return () => query.removeEventListener("change", callback);
}

function getDesktopDisclosureSnapshot() {
  if (typeof window.matchMedia !== "function") return true;
  return window.matchMedia(DESKTOP_DISCLOSURE_QUERY).matches;
}

function getServerDesktopDisclosureSnapshot() {
  return false;
}

/** Closed progressive disclosure on mobile; fully expanded content on desktop. */
export function ResponsiveDisclosure({
  children,
  className,
  initiallyOpen = false,
  summary,
  ...props
}: {
  children: ReactNode;
  className?: string;
  initiallyOpen?: boolean;
  summary: ReactNode;
} & Omit<ComponentPropsWithoutRef<"details">, "open" | "onToggle">) {
  const desktopOpen = useSyncExternalStore(
    subscribeToDesktopDisclosure,
    getDesktopDisclosureSnapshot,
    getServerDesktopDisclosureSnapshot,
  );
  const [mobileOpen, setMobileOpen] = useState(initiallyOpen);

  return (
    <details
      {...props}
      className={className}
      open={desktopOpen || mobileOpen}
      onToggle={(event) => {
        if (!desktopOpen) {
          setMobileOpen(event.currentTarget.open);
        }
      }}
    >
      {summary}
      {children}
    </details>
  );
}
