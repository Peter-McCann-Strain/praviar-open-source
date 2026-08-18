"use client";

export interface PrintReportProvenanceItem {
  detail: string;
  label: string;
  value: string;
}

interface PrintReportProvenanceProps {
  items?: PrintReportProvenanceItem[];
}

export const DEFAULT_PRINT_REPORT_PROVENANCE_ITEMS: PrintReportProvenanceItem[] =
  [
    {
      label: "AI provenance",
      value: "Not reported",
      detail: "Model and source metadata were not included.",
    },
    {
      label: "Review posture",
      value: "Counsel review required",
      detail: "Decision support only; not a legal opinion.",
    },
  ];

export function getPrintReportProvenanceItems(
  items?: PrintReportProvenanceItem[],
): PrintReportProvenanceItem[] {
  return items && items.length > 0
    ? items
    : DEFAULT_PRINT_REPORT_PROVENANCE_ITEMS;
}

export function PrintReportProvenance({
  items = [],
}: PrintReportProvenanceProps) {
  const provenanceItems = getPrintReportProvenanceItems(items);

  return (
    <section
      aria-label="Print report AI provenance and evidence scope"
      className="print-provenance-strip"
      role="region"
    >
      <div className="print-provenance-kicker">
        AI provenance and evidence scope
      </div>
      <div className="print-provenance-grid">
        {provenanceItems.map((item) => (
          <div key={item.label} className="print-provenance-item">
            <p className="print-provenance-label">{item.label}</p>
            <p className="print-provenance-value">{item.value}</p>
            <p className="print-provenance-detail">{item.detail}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
