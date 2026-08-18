export const AUTH_SESSION_RECOVERY_TEST_EVENT =
  "praviar:e2e-auth-session-recovery";

export type AuthSessionRecoveryTestReason = "expired" | "refresh_failed" | null;

export interface AuthSessionRecoveryTestDetail {
  reason: AuthSessionRecoveryTestReason;
}

export type AuthSessionRecoveryTestAction =
  | Exclude<AuthSessionRecoveryTestReason, null>
  | "clear";

export function isAuthBoundaryTestBridgeEnabled(): boolean {
  return (
    process.env.NODE_ENV !== "production" &&
    process.env.NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS === "true" &&
    process.env.NEXT_PUBLIC_ENABLE_AUTH_BOUNDARY_TEST_BRIDGE === "true"
  );
}

export function isAuthSessionRecoveryTestReason(
  value: unknown,
): value is AuthSessionRecoveryTestReason {
  return value === null || value === "expired" || value === "refresh_failed";
}

export function isAuthSessionRecoveryTestAction(
  value: unknown,
): value is AuthSessionRecoveryTestAction {
  return value === "clear" || value === "expired" || value === "refresh_failed";
}
