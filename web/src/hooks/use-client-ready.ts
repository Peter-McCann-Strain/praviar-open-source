"use client";

import { useSyncExternalStore } from "react";

export function useClientReady() {
  return useSyncExternalStore(
    () => () => undefined,
    () => true,
    () => false,
  );
}
