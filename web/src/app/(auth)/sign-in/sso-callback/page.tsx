import { Suspense } from "react";
import { AuthLoadingState } from "@/components/auth/auth-surface";
import { SignInSSOCallbackContent } from "./sign-in-sso-callback-content";

export default function SignInSSOCallback() {
  return (
    <div data-testid="sign-in-sso-callback-route-surface">
      <Suspense fallback={<AuthLoadingState title="Sign In" />}>
        <SignInSSOCallbackContent />
      </Suspense>
    </div>
  );
}
