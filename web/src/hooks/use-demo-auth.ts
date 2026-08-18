"use client";

/**
 * Demo-mode auth: returns a static "demo-token" without any external
 * coordination. Returns `null` when DEMO_MODE_ENABLED is false so callers
 * can fall through to Clerk or the explicit dev-token bypass.
 */
import { DEMO_MODE_ENABLED } from "@/lib/constants";

export function useDemoAuth(): string | null {
  return DEMO_MODE_ENABLED ? "demo-token" : null;
}
