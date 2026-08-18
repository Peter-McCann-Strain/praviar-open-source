"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function ModelsUsedCard({
  modelEntries,
}: {
  modelEntries: Array<[string, string]>;
}) {
  if (modelEntries.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Review Engines</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div
          className="overflow-x-auto focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]"
          role="region"
          tabIndex={0}
          aria-label="Review engines horizontal scroll area"
        >
          <table className="w-full min-w-[24rem] text-sm">
            <thead>
              <tr className="border-b border-[var(--border-default)]">
                <th
                  scope="col"
                  className="px-4 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                >
                  Role
                </th>
                <th
                  scope="col"
                  className="px-4 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                >
                  Engine
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border-default)]">
              {modelEntries.map(([role, model]) => (
                <tr key={role} className="hover:bg-[var(--surface-hover)]">
                  <td className="max-w-[10rem] px-4 py-3 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                    {role}
                  </td>
                  <td className="min-w-0 break-all px-4 py-3 font-mono text-xs text-[var(--text-primary)] [overflow-wrap:anywhere]">
                    {model}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
