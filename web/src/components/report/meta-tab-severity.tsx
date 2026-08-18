"use client";

import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import type { VerificationCheck } from "@praviar/shared-types";

export function SeverityIcon({ check }: { check: VerificationCheck }) {
  const severity = check.severity ?? (check.passed ? "pass" : "fail");
  const normalizedSeverity =
    severity === "pass" || severity === "warning" || severity === "fail"
      ? severity
      : check.passed
        ? "pass"
        : "fail";
  const Icon =
    normalizedSeverity === "pass"
      ? CheckCircle2
      : normalizedSeverity === "warning"
        ? AlertTriangle
        : XCircle;
  const label =
    normalizedSeverity === "pass"
      ? "Passed"
      : normalizedSeverity === "warning"
        ? "Warning"
        : "Failed";
  const colorClass =
    normalizedSeverity === "pass"
      ? "text-success"
      : normalizedSeverity === "warning"
        ? "text-warning"
        : "text-error";

  return (
    <span
      className={`inline-flex items-center justify-center gap-1.5 ${colorClass}`}
    >
      <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span className="text-xs font-semibold">{label}</span>
    </span>
  );
}
