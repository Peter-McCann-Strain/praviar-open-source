import { Suspense } from "react";
import { AuthLoadingState } from "@/components/auth/auth-surface";
import { SignInContent } from "./sign-in-content";

export default function SignInPage() {
  return (
    <div data-testid="sign-in-route-surface">
      <Suspense fallback={<AuthLoadingState title="Sign In" />}>
        <SignInContent />
      </Suspense>
    </div>
  );
}
