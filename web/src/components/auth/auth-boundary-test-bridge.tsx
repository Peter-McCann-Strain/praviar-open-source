"use client";

import { useEffect } from "react";
import { emitAuthBoundaryChanged } from "@/lib/auth-events";
import {
  AUTH_SESSION_RECOVERY_TEST_EVENT,
  type AuthSessionRecoveryTestAction,
  type AuthSessionRecoveryTestDetail,
  isAuthBoundaryTestBridgeEnabled,
  isAuthSessionRecoveryTestAction,
} from "@/lib/auth-boundary-test-bridge";

declare global {
  interface Window {
    __praviarE2EEmitAuthBoundaryChanged?: (detail?: {
      refreshToken?: boolean;
    }) => void;
    __praviarE2ESetAuthSessionRecovery?: (
      action: AuthSessionRecoveryTestAction,
    ) => void;
  }
}

export function AuthBoundaryTestBridge() {
  useEffect(() => {
    if (!isAuthBoundaryTestBridgeEnabled()) return;

    const emitBoundaryChange = (detail: { refreshToken?: boolean } = {}) => {
      emitAuthBoundaryChanged({
        refreshToken: detail.refreshToken ?? false,
      });
    };
    const setSessionRecovery = (action: AuthSessionRecoveryTestAction) => {
      if (!isAuthSessionRecoveryTestAction(action)) return;

      window.dispatchEvent(
        new CustomEvent<AuthSessionRecoveryTestDetail>(
          AUTH_SESSION_RECOVERY_TEST_EVENT,
          {
            detail: {
              reason: action === "clear" ? null : action,
            },
          },
        ),
      );
    };

    window.__praviarE2EEmitAuthBoundaryChanged = emitBoundaryChange;
    window.__praviarE2ESetAuthSessionRecovery = setSessionRecovery;

    return () => {
      if (window.__praviarE2EEmitAuthBoundaryChanged === emitBoundaryChange) {
        delete window.__praviarE2EEmitAuthBoundaryChanged;
      }
      if (window.__praviarE2ESetAuthSessionRecovery === setSessionRecovery) {
        setSessionRecovery("clear");
        delete window.__praviarE2ESetAuthSessionRecovery;
      }
    };
  }, []);

  return null;
}
