"use client";

import { ExternalLink, Globe } from "lucide-react";

interface PatentRiskCardLinksProps {
  patentId: string;
}

export function PatentRiskCardLinks({ patentId }: PatentRiskCardLinksProps) {
  return (
    <div className="flex items-center gap-3">
      <a
        href={`https://patents.google.com/patent/${patentId}`}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center gap-1 text-xs text-brand-primary transition-colors hover:text-brand-primary"
        onClick={(e) => e.stopPropagation()}
      >
        <ExternalLink className="h-3 w-3" />
        Google Patents
      </a>
      <a
        href={`https://worldwide.espacenet.com/patent/search?q=pn%3D${patentId}`}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center gap-1 text-xs text-brand-primary transition-colors hover:text-brand-primary"
        onClick={(e) => e.stopPropagation()}
      >
        <Globe className="h-3 w-3" />
        Espacenet
      </a>
    </div>
  );
}
