"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Globe } from "lucide-react";
import { cn } from "@/lib/utils";

interface FamilyMember {
  country: string;
  doc_number: string;
  kind: string;
}

interface PatentFamily {
  family_id: string;
  members: FamilyMember[];
}

interface PatentFamilyTreeProps {
  family: PatentFamily | null;
  currentPatentId?: string;
  className?: string;
}

const countryFlags: Record<string, string> = {
  US: "\u{1F1FA}\u{1F1F8}",
  EP: "\u{1F1EA}\u{1F1FA}",
  WO: "\u{1F310}",
  JP: "\u{1F1EF}\u{1F1F5}",
  CN: "\u{1F1E8}\u{1F1F3}",
  KR: "\u{1F1F0}\u{1F1F7}",
  DE: "\u{1F1E9}\u{1F1EA}",
  FR: "\u{1F1EB}\u{1F1F7}",
  GB: "\u{1F1EC}\u{1F1E7}",
  CA: "\u{1F1E8}\u{1F1E6}",
  AU: "\u{1F1E6}\u{1F1FA}",
  IN: "\u{1F1EE}\u{1F1F3}",
  BR: "\u{1F1E7}\u{1F1F7}",
  IL: "\u{1F1EE}\u{1F1F1}",
  TW: "\u{1F1F9}\u{1F1FC}",
  SG: "\u{1F1F8}\u{1F1EC}",
  HK: "\u{1F1ED}\u{1F1F0}",
  MX: "\u{1F1F2}\u{1F1FD}",
};

function getKindDescription(kind: string): string {
  const map: Record<string, string> = {
    A1: "Application",
    A2: "Application (2nd pub)",
    B1: "Grant",
    B2: "Grant (reexam)",
    C: "Certificate",
    U: "Utility Model",
  };
  return map[kind] ?? kind;
}

export function PatentFamilyTree({
  family,
  currentPatentId,
  className,
}: PatentFamilyTreeProps) {
  const [expanded, setExpanded] = useState(true);

  if (!family || family.members.length === 0) {
    return (
      <div
        className={cn("text-xs text-[var(--text-tertiary)] italic", className)}
      >
        No patent family data available.
      </div>
    );
  }

  // Group members by country
  const byCountry = new Map<string, FamilyMember[]>();
  for (const m of family.members) {
    const list = byCountry.get(m.country) ?? [];
    list.push(m);
    byCountry.set(m.country, list);
  }

  const countries = Array.from(byCountry.entries()).sort((a, b) => {
    // Put current patent's country first
    if (currentPatentId?.startsWith(a[0])) return -1;
    if (currentPatentId?.startsWith(b[0])) return 1;
    return a[0].localeCompare(b[0]);
  });

  return (
    <div className={cn("space-y-2", className)}>
      {/* Family header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
        aria-expanded={expanded}
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3" />
        ) : (
          <ChevronRight className="h-3 w-3" />
        )}
        <Globe className="h-3.5 w-3.5" />
        Family {family.family_id} ({family.members.length} members across{" "}
        {countries.length} jurisdictions)
      </button>

      {expanded && (
        <div className="ml-5 space-y-1 border-l-2 border-[var(--border-subtle)] pl-4">
          {countries.map(([country, members]) => (
            <div key={country} className="space-y-0.5">
              <div className="flex items-center gap-2 text-xs">
                <span className="text-base leading-none">
                  {countryFlags[country] ?? "\u{1F4C4}"}
                </span>
                <span className="font-medium text-[var(--text-primary)]">
                  {country}
                </span>
                <span className="text-[var(--text-tertiary)]">
                  ({members.length})
                </span>
              </div>
              {members.map((m) => {
                const docId = `${m.country}${m.doc_number}${m.kind}`;
                const isCurrent = currentPatentId === docId;
                return (
                  <div
                    key={docId}
                    className={cn(
                      "ml-6 flex items-center gap-2 text-xs py-0.5 px-2 rounded",
                      isCurrent &&
                        "bg-brand-primary/10 border border-brand-primary/20",
                    )}
                  >
                    <span
                      className={cn(
                        "patent-id",
                        isCurrent
                          ? "text-brand-primary font-semibold"
                          : "text-[var(--text-primary)]",
                      )}
                    >
                      {m.doc_number}
                    </span>
                    <span className="text-xs px-1 py-0.5 rounded bg-[var(--surface-active)] text-[var(--text-tertiary)]">
                      {getKindDescription(m.kind)}
                    </span>
                    {isCurrent && (
                      <span className="text-xs text-brand-primary font-medium">
                        &larr; current
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
