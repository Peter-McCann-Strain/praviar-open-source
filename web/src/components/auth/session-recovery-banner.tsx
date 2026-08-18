"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { LogIn, RefreshCw, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { resolveAuthReturnPath } from "@/components/auth/auth-redirects";
import { useAuthSessionRecovery } from "@/hooks/use-auth-token";

export const SESSION_RECOVERY_TITLE = "Your session expired";
export const SESSION_RECOVERY_UNCHANGED_COPY =
  "Private workspace actions are locked. Existing analyses, reports, monitors, review decisions, and account settings are unchanged.";

export function buildSessionRecoverySignInHref(
  pathname: string | null,
  search: string,
): string {
  const normalizedSearch = search.replace(/^\?/, "");
  const currentPath = `${pathname ?? ""}${
    normalizedSearch ? `?${normalizedSearch}` : ""
  }`;
  const returnTo = resolveAuthReturnPath(currentPath);

  return `/sign-in?${new URLSearchParams({ return_to: returnTo }).toString()}`;
}

export function SessionRecoveryBanner() {
  const { isRefreshing, reason, retrySession } = useAuthSessionRecovery();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  if (reason === null) {
    return null;
  }

  const signInHref = buildSessionRecoverySignInHref(
    pathname,
    searchParams.toString(),
  );

  return (
    <aside
      aria-label="Session recovery"
      className="border-b border-warning/30 bg-warning/10 px-4 py-3 text-[var(--text-primary)] sm:px-5 md:px-6"
      data-testid="session-recovery-banner"
      role="alert"
    >
      <div className="mx-auto flex max-w-6xl flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-warning/25 bg-[var(--surface-card)] text-warning shadow-[var(--shadow-xs)]">
            <ShieldAlert className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {SESSION_RECOVERY_TITLE}
            </p>
            <p className="mt-1 max-w-3xl text-sm leading-5 text-[var(--text-secondary)]">
              {SESSION_RECOVERY_UNCHANGED_COPY}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 flex-col gap-2 sm:flex-row">
          <Button
            className="min-h-11 w-full sm:w-auto"
            loading={isRefreshing}
            onClick={retrySession}
            size="sm"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Retry session
          </Button>
          <Button
            asChild
            className="min-h-11 w-full bg-[var(--surface-card)] sm:w-auto"
            size="sm"
            variant="outline"
          >
            <Link href={signInHref}>
              <LogIn className="h-4 w-4" aria-hidden="true" />
              Sign in again
            </Link>
          </Button>
        </div>
      </div>
    </aside>
  );
}
