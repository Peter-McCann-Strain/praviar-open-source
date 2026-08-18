"use client";

import type { FTOReport } from "@praviar/shared-types";
import { CheckCircle, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { sanitizeReportDiagnosticText } from "./report-diagnostic-copy";
import type { MetaVerificationFlag } from "./meta-tab-helpers";
import { SeverityIcon } from "./meta-tab-severity";

export function VerificationCard({
  verification,
  verificationFlags,
}: {
  verification: FTOReport["verification"];
  verificationFlags: MetaVerificationFlag[];
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Verification</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
          {verificationFlags.map((flag) => (
            <div
              key={flag.label}
              className={cn(
                "flex items-center gap-2 rounded-lg px-3 py-2",
                flag.passed
                  ? "bg-success/5 border border-success/10"
                  : "bg-error/5 border border-error/10",
              )}
            >
              {flag.passed ? (
                <CheckCircle
                  className="h-3.5 w-3.5 text-success flex-shrink-0"
                  aria-hidden="true"
                />
              ) : (
                <XCircle
                  className="h-3.5 w-3.5 text-error flex-shrink-0"
                  aria-hidden="true"
                />
              )}
              <span className="min-w-0 text-sm text-[var(--text-primary)]">
                <span className="sr-only">
                  {flag.passed ? "Passed: " : "Failed: "}
                </span>
                {flag.label}
              </span>
            </div>
          ))}
        </div>

        {(verification?.checks?.length ?? 0) > 0 && (
          <div
            className="overflow-x-auto focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]"
            role="region"
            tabIndex={0}
            aria-label="Verification checks horizontal scroll area"
          >
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border-default)]">
                  <th
                    scope="col"
                    className="px-4 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                  >
                    Check
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-2 text-center text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                  >
                    Status
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                  >
                    Details
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-default)]">
                {verification?.checks?.map((check) => (
                  <tr
                    key={check.check_name}
                    className="hover:bg-[var(--surface-hover)]"
                  >
                    <td className="px-4 py-3 text-[var(--text-primary)]">
                      {check.check_name}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <SeverityIcon check={check} />
                    </td>
                    <td className="px-4 py-3 text-[var(--text-secondary)] text-xs max-w-[300px]">
                      {sanitizeReportDiagnosticText(
                        check.details,
                        "Verification detail unavailable.",
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
