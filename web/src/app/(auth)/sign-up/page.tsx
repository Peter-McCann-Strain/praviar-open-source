import { Suspense } from "react";
import { AuthLoadingState } from "@/components/auth/auth-surface";
import { SignUpContent } from "./sign-up-content";

export default function SignUpPage() {
  return (
    <div data-testid="sign-up-route-surface">
      <Suspense fallback={<AuthLoadingState title="Sign Up" />}>
        <SignUpContent />
      </Suspense>
    </div>
  );
}
