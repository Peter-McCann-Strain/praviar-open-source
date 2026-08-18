import {
  parseDemoExportDescriptor,
  type DemoExportAudience,
  type DemoExportFormat,
} from "@/lib/demo-export-artifact";

export type ExportDownloadTarget =
  | { kind: "protected-api"; path: string }
  | {
      kind: "demo-artifact";
      audience: DemoExportAudience;
      format: DemoExportFormat;
    }
  | { kind: "invalid" };

const URL_POLICY_BASE = "https://download-policy.praviar.invalid";
const PROTECTED_DOWNLOAD_PATH =
  /^\/api\/v1\/exports\/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\/download$/u;
const ENCODED_PATH_CONFUSION = /%(?:2e|2f|3a|5c)/iu;
const DOT_PATH_SEGMENT = /(?:^|\/)\.{1,2}(?:\/|$)/u;

/** Classify an API-provided export URL without ever accepting an origin. */
export function classifyExportDownloadUrl(
  value: string,
  options: { allowDemoArtifact?: boolean } = {},
): ExportDownloadTarget {
  if (options.allowDemoArtifact) {
    const demoDescriptor = parseDemoExportDescriptor(value);
    if (demoDescriptor) {
      return { kind: "demo-artifact", ...demoDescriptor };
    }
  }

  if (
    !value ||
    value !== value.trim() ||
    !value.startsWith("/") ||
    value.startsWith("//") ||
    value.includes("\\") ||
    ENCODED_PATH_CONFUSION.test(value) ||
    DOT_PATH_SEGMENT.test(value)
  ) {
    return { kind: "invalid" };
  }

  let parsed: URL;
  try {
    parsed = new URL(value, URL_POLICY_BASE);
  } catch {
    return { kind: "invalid" };
  }
  if (
    parsed.origin !== URL_POLICY_BASE ||
    parsed.username ||
    parsed.password ||
    parsed.hash ||
    parsed.search
  ) {
    return { kind: "invalid" };
  }

  const path = parsed.pathname;
  if (PROTECTED_DOWNLOAD_PATH.test(parsed.pathname)) {
    return { kind: "protected-api", path };
  }
  return { kind: "invalid" };
}
