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

const ClerkRedirectCallback = hasClerk
  ? dynamic(
      () =>
        import("@clerk/nextjs").then((m) => m.AuthenticateWithRedirectCallback),
      { ssr: false },
    )
  : null;

export function SignUpSSOCallbackContent() {
  const searchParams = useSearchParams();
  const rawReturnTo = searchParams.get("return_to");
  const returnPath = resolveAuthReturnPath(rawReturnTo);
  const explicitReturnPath = resolveExplicitAuthReturnPath(rawReturnTo);
  const checkoutIntent = resolveAuthCheckoutIntent(returnPath);

  if (!ClerkRedirectCallback) {
    return (
      <AuthUnavailableState
        title="Sign Up"
        checkoutIntent={checkoutIntent}
        context="sso-callback"
      />
    );
  }

  return (
    <ClerkRuntimeBoundary
      title="Sign Up"
      checkoutIntent={checkoutIntent}
      context="sso-callback"
    >
      <ClerkRedirectCallback
        signInFallbackRedirectUrl={returnPath}
        signInForceRedirectUrl={explicitReturnPath ?? undefined}
        signUpFallbackRedirectUrl={returnPath}
        signUpForceRedirectUrl={explicitReturnPath ?? undefined}
      />
    </ClerkRuntimeBoundary>
  );
}
