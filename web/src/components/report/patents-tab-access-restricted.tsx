"use client";

import { AlertTriangle } from "lucide-react";

export function PatentsAccessRestricted({
  totalPatentsFound,
}: {
  totalPatentsFound: number;
}) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-info/20 bg-info/5 p-4">
      <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-info" />
      <div>
        <p className="text-sm font-semibold text-info">Access Restricted</p>
        <p className="mt-1 text-xs text-[var(--text-secondary)]">
          Patent analysis details require elevated access. {totalPatentsFound}{" "}
          patents were found but detailed analysis is not available for your
          current role.
        </p>
      </div>
    </div>
  );
}
