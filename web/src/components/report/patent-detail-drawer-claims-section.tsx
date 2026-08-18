"use client";

import { FileText } from "lucide-react";
import { PatentDetailDrawerSection } from "@/components/report/patent-detail-drawer-section";

export function PatentDetailDrawerClaimsSection({
  claimsText,
  claimsExpanded,
  onClaimsExpandedChange,
}: {
  claimsText: string;
  claimsExpanded: boolean;
  onClaimsExpandedChange: (expanded: boolean) => void;
}) {
  const claimsPreview = claimsText.slice(0, 500);
  const hasMoreClaims = claimsText.length > 500;

  return (
    <PatentDetailDrawerSection
      title="Claims Text"
      icon={FileText}
      defaultOpen={false}
    >
      <div className="text-xs text-[var(--text-secondary)] leading-relaxed whitespace-pre-wrap font-mono">
        {claimsExpanded ? claimsText : claimsPreview}
        {hasMoreClaims && !claimsExpanded ? "…" : null}
      </div>
      {hasMoreClaims ? (
        <button
          onClick={() => onClaimsExpandedChange(!claimsExpanded)}
          className="mt-2 text-xs text-brand-primary hover:text-brand-primary transition-colors"
        >
          {claimsExpanded
            ? "Show less"
            : `Show all (${Math.round(claimsText.length / 1000)}K chars)`}
        </button>
      ) : null}
    </PatentDetailDrawerSection>
  );
}
