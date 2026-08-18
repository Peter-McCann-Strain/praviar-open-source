import { sanitizeDiagnosticText } from "@/lib/diagnostic-redaction";

export function sanitizeReportDiagnosticText(
  value: string | null | undefined,
  fallback: string,
): string {
  return sanitizeDiagnosticText(value, fallback);
}
