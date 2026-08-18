"use client";

import { useEffect, useRef } from "react";
import { AUTH_BOUNDARY_CHANGED_EVENT } from "@/lib/auth-events";

export function useAuthBoundaryReset(onReset: () => void) {
  const generationRef = useRef(0);
  const onResetRef = useRef(onReset);

  useEffect(() => {
    onResetRef.current = onReset;
  }, [onReset]);

  useEffect(() => {
    function handleAuthBoundaryChanged() {
      generationRef.current += 1;
      onResetRef.current();
    }

    window.addEventListener(
      AUTH_BOUNDARY_CHANGED_EVENT,
      handleAuthBoundaryChanged,
    );
    return () => {
      window.removeEventListener(
        AUTH_BOUNDARY_CHANGED_EVENT,
        handleAuthBoundaryChanged,
      );
    };
  }, []);

  return generationRef;
}
