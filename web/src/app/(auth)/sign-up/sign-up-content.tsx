"use client";

import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { AuthUnavailableState } from "@/components/auth/auth-surface";
import { resolveAuthCheckoutIntent } from "@/components/auth/auth-checkout-intent";
import { ClerkRuntimeBoundary } from "@/components/auth/clerk-runtime-boundary";
import {
  resolveAuthReturnPath,
  resolveExplicitAuthReturnPath,
} from "@/components/auth/auth-redirects";
import { hasValidClerkPublishableKey } from "@/lib/production-env";

const clerkKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
const hasClerk = hasValidClerkPublishableKey(clerkKey);

const ClerkSignUp = hasClerk
  ? dynamic(() => import("@clerk/nextjs").then((m) => m.SignUp), { ssr: false })
  : null;

export function SignUpContent() {
  const searchParams = useSearchParams();
  const rawReturnTo = searchParams.get("return_to");
  const returnPath = resolveAuthReturnPath(rawReturnTo);
  const explicitReturnPath = resolveExplicitAuthReturnPath(rawReturnTo);
  const checkoutIntent = resolveAuthCheckoutIntent(returnPath);

  if (!ClerkSignUp) {
    return (
      <AuthUnavailableState title="Sign Up" checkoutIntent={checkoutIntent} />
    );
  }

  return (
    <ClerkRuntimeBoundary title="Sign Up" checkoutIntent={checkoutIntent}>
      <ClerkSignUp
        fallbackRedirectUrl={returnPath}
        forceRedirectUrl={explicitReturnPath ?? undefined}
        signInFallbackRedirectUrl={returnPath}
        signInForceRedirectUrl={explicitReturnPath ?? undefined}
        appearance={{
          elements: {
            rootBox: "mx-auto w-full max-w-md",
            card: "praviar-dialog-panel",
            headerTitle: "text-[var(--text-primary)]",
            headerSubtitle: "text-[var(--text-secondary)]",
            formButtonPrimary:
              "min-h-11 rounded-lg bg-[var(--brand-primary)] text-[var(--brand-paper)] hover:bg-[var(--brand-primary-hover)] focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]",
            formFieldInput:
              "praviar-glass-field min-h-11 text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]",
            formFieldLabel: "text-[var(--text-primary)]",
            footerActionLink:
              "text-[var(--brand-primary)] hover:text-[var(--brand-primary-hover)]",
            socialButtonsBlockButton:
              "min-h-11 rounded-lg focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]",
          },
        }}
      />
    </ClerkRuntimeBoundary>
  );
}
