/**
 * Single source of truth for demo-mode detection.
 *
 * Centralised here so test mocks have one stable target and runtime callers
 * never read `process.env.NEXT_PUBLIC_DEMO_MODE` directly. The constant is
 * also re-exported from `@/lib/constants` for legacy imports.
 */

export const DEMO_MODE_ENABLED = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

export function isDemoMode(): boolean {
  return DEMO_MODE_ENABLED;
}
