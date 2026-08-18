export const PIPELINE_STEPS = [
  {
    number: 1,
    name: "resolve",
    label: "Resolve Compound",
    icon: "atom",
  },
  { number: 2, name: "search", label: "Search Patents", icon: "search" },
  { number: 3, name: "triage", label: "Triage Patents", icon: "filter" },
  { number: 4, name: "analyze", label: "Claim Analysis", icon: "microscope" },
  { number: 5, name: "doe", label: "Equivalents", icon: "scale" },
  { number: 6, name: "invalidity", label: "Invalidity", icon: "shield-x" },
  { number: 7, name: "verify", label: "Verification", icon: "check-circle" },
  { number: 8, name: "report", label: "Report", icon: "file-text" },
] as const;

export const RISK_COLORS = {
  high: {
    bg: "bg-error/15",
    text: "text-[var(--color-error-badge-fg)]",
    border: "border-error/30",
    hex: "var(--risk-high)",
  },
  medium: {
    bg: "bg-warning/15",
    text: "text-[var(--color-warning-badge-fg)]",
    border: "border-warning/30",
    hex: "var(--risk-medium)",
  },
  low: {
    bg: "bg-success/15",
    text: "text-[var(--color-success-badge-fg)]",
    border: "border-success/30",
    hex: "var(--risk-low)",
  },
  clear: {
    bg: "bg-info/15",
    text: "text-[var(--color-info-badge-fg)]",
    border: "border-info/30",
    hex: "var(--risk-clear)",
  },
} as const;

export const ELEMENT_STATUS_COLORS = {
  met: { bg: "bg-error/10", text: "text-error", label: "Met" },
  not_met: { bg: "bg-success/10", text: "text-success", label: "Not Met" },
  partially_met: {
    bg: "bg-warning/10",
    text: "text-warning",
    label: "Partial",
  },
  unclear: {
    bg: "bg-[var(--surface-active)]",
    text: "text-[var(--text-tertiary)]",
    label: "Unclear",
  },
} as const;

/** External reference URLs */
export const PUBCHEM_COMPOUND_URL = "https://pubchem.ncbi.nlm.nih.gov/compound";

/** Timing constants (milliseconds) */
export const TOAST_AUTO_DISMISS_MS = 3000;
export const COPY_FEEDBACK_RESET_MS = 2000;
export const TOKEN_REFRESH_INTERVAL_MS = 50_000;
export const ANALYSIS_POLL_INTERVAL_MS = 3000;
export const SSE_INITIAL_RETRY_MS = 1000;
export const SSE_MAX_RETRY_MS = 30000;
export const SSE_MAX_RETRIES = 5;
export const EXPORT_POLL_INTERVAL_MS = 2000;
export const QUERY_STALE_TIME_MS = 60_000;
export const AUTH_GIVE_UP_MS = 5_000;
export const AUTH_INITIAL_POLL_MS = 500;
export const AUTH_MAX_POLL_MS = 2_000;
export const DEV_AUTH_BYPASS_ENABLED =
  process.env.NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS === "true";

// Demo-mode detection is owned by `@/lib/demo-mode`. Re-exported here for
// backwards compatibility with existing imports and `vi.mock` targets.
export { DEMO_MODE_ENABLED, isDemoMode } from "@/lib/demo-mode";

import { DEMO_MODE_ENABLED as _DEMO_MODE_ENABLED } from "@/lib/demo-mode";
import { resolvePublicApiOrigin } from "@/lib/production-env";

export const API_BASE_URL = resolvePublicApiOrigin({
  apiUrl: process.env.NEXT_PUBLIC_API_URL,
  nodeEnv: process.env.NODE_ENV,
});

if (!_DEMO_MODE_ENABLED && !API_BASE_URL) {
  throw new Error(
    "NEXT_PUBLIC_API_URL is required unless NEXT_PUBLIC_DEMO_MODE=true",
  );
}
