"use client";

export type MarketingEventName =
  | "homepage_start_analysis_clicked"
  | "sample_report_opened"
  | "methodology_opened"
  | "pricing_viewed"
  | "prefilled_analysis_started";

declare global {
  interface Window {
    __praviarAnalyticsQueue?: Array<{
      name: MarketingEventName;
      properties?: Record<string, unknown>;
      timestamp: string;
    }>;
    plausible?: (
      eventName: string,
      options?: { props?: Record<string, unknown> },
    ) => void;
    gtag?: (
      command: string,
      eventName: string,
      properties?: Record<string, unknown>,
    ) => void;
  }
}

const SENSITIVE_PROPERTY_NAMES = new Set([
  "cas",
  "cas_number",
  "canonical_smiles",
  "compound",
  "compound_input",
  "compoundInput",
  "inchi",
  "smiles",
]);

const EVENT_PROPERTY_ALLOWLIST: Record<MarketingEventName, Set<string>> = {
  homepage_start_analysis_clicked: new Set(["destination", "mode"]),
  methodology_opened: new Set(["source"]),
  prefilled_analysis_started: new Set(["destination", "source"]),
  pricing_viewed: new Set(["source"]),
  sample_report_opened: new Set(["slug"]),
};

function isSensitivePropertyName(key: string) {
  const normalized = key.replace(/[^a-z0-9]/gi, "").toLowerCase();

  return (
    SENSITIVE_PROPERTY_NAMES.has(key) ||
    normalized.includes("compound") ||
    normalized.includes("smiles") ||
    normalized.includes("inchi") ||
    normalized === "cas" ||
    normalized.includes("casnumber") ||
    normalized === "query"
  );
}

function sanitizeEventProperties(
  name: MarketingEventName,
  properties: Record<string, unknown>,
) {
  const sanitized: Record<string, unknown> = {};
  const allowedKeys = EVENT_PROPERTY_ALLOWLIST[name];

  for (const [key, value] of Object.entries(properties)) {
    if (allowedKeys && !allowedKeys.has(key)) {
      continue;
    }

    if (isSensitivePropertyName(key)) continue;
    sanitized[key] = value;
  }

  return sanitized;
}

export function trackMarketingEvent(
  name: MarketingEventName,
  properties: Record<string, unknown> = {},
) {
  if (typeof window === "undefined") {
    return;
  }

  const safeProperties = sanitizeEventProperties(name, properties);
  const payload = {
    name,
    properties: safeProperties,
    timestamp: new Date().toISOString(),
  };

  window.__praviarAnalyticsQueue = window.__praviarAnalyticsQueue ?? [];
  window.__praviarAnalyticsQueue.push(payload);
  window.dispatchEvent(
    new CustomEvent("praviar:analytics", { detail: payload }),
  );

  if (typeof window.plausible === "function") {
    window.plausible(name, { props: safeProperties });
  }

  if (typeof window.gtag === "function") {
    window.gtag("event", name, safeProperties);
  }

  if (process.env.NODE_ENV !== "production") {
    console.debug("[marketing-event]", payload);
  }
}
