import { Suspense } from "react";
import { AuthLoadingState } from "@/components/auth/auth-surface";
import { SignUpSSOCallbackContent } from "./sign-up-sso-callback-content";

export default function SignUpSSOCallback() {
  return (
    <div data-testid="sign-up-sso-callback-route-surface">
      <Suspense fallback={<AuthLoadingState title="Sign Up" />}>
        <SignUpSSOCallbackContent />
      </Suspense>
    </div>
  );
}
