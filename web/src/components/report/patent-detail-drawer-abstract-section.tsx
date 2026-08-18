"use client";

import { FileText } from "lucide-react";
import { PatentDetailDrawerSection } from "@/components/report/patent-detail-drawer-section";

export function PatentDetailDrawerAbstractSection({
  abstract,
}: {
  abstract?: string | null;
}) {
  if (!abstract) {
    return null;
  }

  return (
    <PatentDetailDrawerSection title="Abstract" icon={FileText}>
      <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
        {abstract}
      </p>
    </PatentDetailDrawerSection>
  );
}
