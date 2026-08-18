"use client";

import {
  ClerkDegraded,
  ClerkFailed,
  ClerkLoaded,
  ClerkLoading,
} from "@clerk/nextjs";
import { AlertTriangle } from "lucide-react";
import type { ReactNode } from "react";
import type { AuthCheckoutIntent } from "@/components/auth/auth-checkout-intent";
import {
  AuthLoadingState,
  AuthSurface,
  AuthUnavailableState,
} from "@/components/auth/auth-surface";

interface ClerkRuntimeBoundaryProps {
  children: ReactNode;
  title: string;
  checkoutIntent?: AuthCheckoutIntent | null;
  context?: "entry" | "sso-callback";
}

export function ClerkRuntimeBoundary({
  children,
  title,
  checkoutIntent,
  context = "entry",
}: ClerkRuntimeBoundaryProps) {
  return (
    <>
      <ClerkLoading>
        <AuthLoadingState title={title} checkoutIntent={checkoutIntent} />
      </ClerkLoading>

      <ClerkFailed>
        <AuthUnavailableState
          title={title}
          checkoutIntent={checkoutIntent}
          context={context}
        />
      </ClerkFailed>

      <ClerkLoaded>
        <AuthSurface checkoutIntent={checkoutIntent}>
          <ClerkDegraded>
            <div
              className="mb-3 flex w-full max-w-md items-start gap-3 rounded-lg border border-[var(--color-border-warning)] bg-[var(--color-bg-warning)] p-3 text-[var(--color-text-warning)]"
              data-testid="auth-provider-degraded"
              role="status"
              aria-live="polite"
            >
              <AlertTriangle
                className="mt-0.5 h-4 w-4 shrink-0"
                aria-hidden="true"
              />
              <div className="min-w-0">
                <p className="text-sm font-semibold">
                  Identity provider operating in recovery mode
                </p>
                <p className="mt-1 text-xs leading-5">
                  Sign-in may be limited. Workspace evidence stays sealed until
                  identity verification completes.
                </p>
              </div>
            </div>
          </ClerkDegraded>
          {children}
        </AuthSurface>
      </ClerkLoaded>
    </>
  );
}
