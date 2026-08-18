"use client";

interface PrintReportRelianceItem {
  label: string;
  value: string;
}

interface PrintReportRelianceProps {
  items?: PrintReportRelianceItem[];
}

export const DEFAULT_PRINT_REPORT_RELIANCE_ITEMS: PrintReportRelianceItem[] = [
  {
    label: "Reliance boundary",
    value: "Decision support only; not a legal opinion.",
  },
  {
    label: "Evidence basis",
    value: "Generated report packet and cited source records.",
  },
  {
    label: "AI governance",
    value: "AI-assisted synthesis requires citation review.",
  },
  {
    label: "Review gate",
    value: "Qualified counsel sign-off remains required.",
  },
];

export function getPrintReportRelianceItems(
  items?: PrintReportRelianceItem[],
): PrintReportRelianceItem[] {
  return items && items.length > 0
    ? items
    : DEFAULT_PRINT_REPORT_RELIANCE_ITEMS;
}

export function PrintReportReliance({ items }: PrintReportRelianceProps) {
  const relianceItems = getPrintReportRelianceItems(items);

  return (
    <section
      aria-label="Print report reliance boundary"
      className="print-reliance-banner"
      role="note"
    >
      <p className="print-reliance-title">Reliance boundary</p>
      <div className="print-reliance-grid">
        {relianceItems.map((item) => (
          <div key={item.label} className="print-reliance-item">
            <p className="print-reliance-label">{item.label}</p>
            <p className="print-reliance-value">{item.value}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

export type { PrintReportRelianceItem };
