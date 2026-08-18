"use client";

import { Tag } from "lucide-react";
import { PatentDetailDrawerSection } from "@/components/report/patent-detail-drawer-section";

export function PatentDetailDrawerCpcSection({ codes }: { codes: string[] }) {
  return (
    <PatentDetailDrawerSection
      title="CPC Classification"
      icon={Tag}
      defaultOpen={false}
    >
      <div className="flex flex-wrap gap-1.5">
        {codes.map((code) => (
          <span
            key={code}
            className="rounded-full bg-[var(--surface-muted)] border border-[var(--border-default)] px-2 py-0.5 text-xs font-mono text-[var(--text-secondary)]"
          >
            {code}
          </span>
        ))}
      </div>
    </PatentDetailDrawerSection>
  );
}
