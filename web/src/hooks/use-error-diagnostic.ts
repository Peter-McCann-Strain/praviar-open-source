"use client";

import { useEffect, useRef } from "react";

const NO_REPORTED_ERROR = Symbol("no-reported-error");

/**
 * Reports an active error once for each error identity.
 *
 * The ref intentionally survives React Strict Mode's development-only effect
 * replay. Leaving the error state resets the guard so a later retry failure
 * can be reported again, even if a caller reuses the same error instance.
 */
export function useErrorDiagnostic(
  active: boolean,
  error: unknown,
  report: (currentError: unknown) => void,
) {
  const lastReportedErrorRef = useRef<unknown>(NO_REPORTED_ERROR);

  useEffect(() => {
    if (!active) {
      lastReportedErrorRef.current = NO_REPORTED_ERROR;
      return;
    }

    if (
      lastReportedErrorRef.current !== NO_REPORTED_ERROR &&
      Object.is(lastReportedErrorRef.current, error)
    ) {
      return;
    }

    lastReportedErrorRef.current = error;
    report(error);
  }, [active, error, report]);
}
