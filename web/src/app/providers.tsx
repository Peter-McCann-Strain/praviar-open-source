"use client";

import {
  QueryCache,
  MutationCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { initErrorReporting, logError } from "@/lib/error-logger";
import { QUERY_STALE_TIME_MS } from "@/lib/constants";
import { hasClerk } from "@/hooks/use-clerk-session";
import { useToastStore } from "@/stores/toast-store";
import { TooltipProvider } from "@/components/ui/tooltip";
import {
  AuthBoundaryEventCacheReset,
  AuthQueryCacheBoundary,
} from "@/components/auth/auth-query-cache-boundary";
import { AuthBoundaryTestBridge } from "@/components/auth/auth-boundary-test-bridge";
import { AuthTokenProvider } from "@/hooks/use-auth-token";

export function Providers({ children }: { children: React.ReactNode }) {
  const addToast = useToastStore((s) => s.addToast);

  const [queryClient] = useState(
    () =>
      new QueryClient({
        queryCache: new QueryCache({
          onError: (error, query) => {
            // Only toast for queries that have already loaded data before
            // (avoids toasting on initial 404s which are expected)
            if (query.state.data !== undefined) {
              logError(error, {
                source: "query",
                extra: { queryKey: query.queryKey },
              });
              // Background/polling queries (notification badge, admin health,
              // export status, review-status) opt out of the user-facing toast
              // via meta so a transient refetch failure does not spam an error
              // banner the user never asked for. The error is still logged
              // above for observability. Mirrors the MutationCache behaviour.
              if (query.meta?.suppressGlobalErrorToast) return;
              addToast(
                "Data refresh failed. Existing visible data was not changed.",
                "error",
              );
            }
          },
        }),
        mutationCache: new MutationCache({
          onError: (error, _variables, _context, mutation) => {
            const key = mutation.options.mutationKey ?? "unknown";
            logError(error, {
              source: "mutation",
              extra: { mutationKey: key },
            });
            if (mutation.meta?.suppressGlobalErrorToast) return;
            addToast(
              "Operation result could not be confirmed. Refresh to verify the current state.",
              "error",
            );
          },
        }),
        defaultOptions: {
          queries: {
            staleTime: QUERY_STALE_TIME_MS,
            retry: 1,
          },
        },
      }),
  );

  // Initialize Sentry on first client render (no-op when DSN is not configured)
  useEffect(() => {
    initErrorReporting();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <AuthTokenProvider>
        <AuthBoundaryEventCacheReset queryClient={queryClient} />
        {hasClerk && <AuthQueryCacheBoundary queryClient={queryClient} />}
        <AuthBoundaryTestBridge />
        <TooltipProvider delayDuration={300}>{children}</TooltipProvider>
      </AuthTokenProvider>
    </QueryClientProvider>
  );
}
