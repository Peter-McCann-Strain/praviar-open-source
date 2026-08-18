"use client";

import { useEffect } from "react";
import { Home } from "lucide-react";
import Link from "next/link";
import { AppErrorState } from "@/components/shared/app-error-state";
import { Button } from "@/components/ui/button";
import { logError } from "@/lib/error-logger";

interface RouteErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
  /** Route context for error logging and display (e.g. "Analyses", "Config"). */
  section: string;
  /** Fallback link for "Go back" button. Defaults to /dashboard. */
  backHref?: string;
  /** Label for the fallback link. Defaults to Dashboard. */
  backLabel?: string;
}

export function RouteError({
  error,
  reset,
  section,
  backHref = "/dashboard",
  backLabel = "Dashboard",
}: RouteErrorProps) {
  useEffect(() => {
    logError(error, {
      source: `${section}ErrorBoundary`,
      extra: { digest: error.digest },
    });
  }, [error, section]);

  return (
    <div className="flex min-h-[60vh] items-center justify-center px-4 py-12 sm:py-16">
      <AppErrorState
        title={`${section} temporarily unavailable`}
        description="We could not load this workspace. The issue has been logged, and retrying will request a fresh view."
        detail={error.digest}
        headingLevel={1}
        actionLabel="Try again"
        onAction={reset}
        className="w-full max-w-2xl"
        secondaryAction={
          <Button
            variant="outline"
            className="min-h-11 w-full gap-2 sm:w-auto"
            asChild
          >
            <Link href={backHref}>
              <Home className="h-4 w-4" />
              {backLabel}
            </Link>
          </Button>
        }
      />
    </div>
  );
}
