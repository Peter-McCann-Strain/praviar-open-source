"use client";

import { Users } from "lucide-react";
import { PatentDetailDrawerSection } from "@/components/report/patent-detail-drawer-section";

export function PatentDetailDrawerInventorsSection({
  inventors,
}: {
  inventors: string[];
}) {
  return (
    <PatentDetailDrawerSection
      title="Inventors"
      icon={Users}
      defaultOpen={false}
    >
      <p className="text-xs text-[var(--text-secondary)]">
        {inventors.join(", ")}
      </p>
    </PatentDetailDrawerSection>
  );
}
