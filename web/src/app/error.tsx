"use client";

import { useEffect } from "react";
import Link from "next/link";
import { Home } from "lucide-react";
import { AppErrorState } from "@/components/shared/app-error-state";
import { Button } from "@/components/ui/button";
import { logError } from "@/lib/error-logger";

export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    logError(error, {
      source: "RootErrorBoundary",
      extra: { digest: error.digest, errorName: error.name },
    });
  }, [error]);

  return (
    <main
      id="main-content"
      className="praviar-app-field flex min-h-screen items-center justify-center p-8"
    >
      <AppErrorState
        title="Praviar needs a refresh"
        description="The workspace hit an unexpected rendering issue. The diagnostic context has been logged, and retrying will request a fresh view."
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
            <Link href="/">
              <Home className="h-4 w-4" aria-hidden="true" />
              Go home
            </Link>
          </Button>
        }
      />
    </main>
  );
}
