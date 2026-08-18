import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface HardFilterRejectionsCardProps {
  rejectionEntries: Array<[string, number]>;
}

function TableHeaderCell({
  children,
  align = "left",
}: {
  children: string;
  align?: "left" | "right";
}) {
  return (
    <th
      scope="col"
      className={`px-4 py-2 text-xs font-semibold uppercase text-[var(--text-tertiary)] ${
        align === "left" ? "text-left" : "text-right"
      }`}
    >
      {children}
    </th>
  );
}

export function HardFilterRejectionsCard({
  rejectionEntries,
}: HardFilterRejectionsCardProps) {
  if (rejectionEntries.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Hard Filter Rejections</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div
          role="region"
          aria-label="Hard filter rejections table"
          tabIndex={0}
          className="overflow-x-auto [scrollbar-gutter:stable]"
        >
          <table className="w-full min-w-[28rem] text-sm">
            <thead>
              <tr className="border-b border-[var(--border-subtle)]">
                <TableHeaderCell>Reason</TableHeaderCell>
                <TableHeaderCell align="right">Count</TableHeaderCell>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border-subtle)]">
              {rejectionEntries.map(([reason, count]) => (
                <tr key={reason} className="hover:bg-[var(--surface-muted)]">
                  <td className="min-w-0 px-4 py-3 text-[var(--text-primary)] [overflow-wrap:anywhere]">
                    {reason}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right font-medium text-[var(--text-primary)]">
                    {count}
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
