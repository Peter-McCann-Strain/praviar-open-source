"use client";

import { Check, Copy, ExternalLink, X } from "lucide-react";
import { useState } from "react";
import type { CompoundItem } from "@/hooks/use-compounds";
import { cn } from "@/lib/utils";
import {
  formatAnalysisCount,
  formatCompoundDate,
  normalizeFunctionalGroups,
  formatWeight,
} from "@/components/compounds/helpers";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

interface CompoundDetailCardProps {
  id: string;
  compound: CompoundItem;
  className?: string;
  onClose: () => void;
}

export function CompoundDetailCard({
  id,
  compound,
  className,
  onClose,
}: CompoundDetailCardProps) {
  const [copiedField, setCopiedField] = useState<{
    compoundId: string;
    label: string;
  } | null>(null);
  const titleId = `${id}-title`;
  const copySupported =
    typeof navigator !== "undefined" && Boolean(navigator.clipboard?.writeText);
  const functionalGroups = normalizeFunctionalGroups(
    compound.functional_groups,
  );

  function copyIdentifier(label: string, value: string) {
    if (!navigator.clipboard?.writeText) return;
    void navigator.clipboard
      .writeText(value)
      .then(() => {
        setCopiedField({ compoundId: compound.id, label });
      })
      .catch(() => {
        setCopiedField(null);
      });
  }

  return (
    <Card
      id={id}
      aria-labelledby={titleId}
      className={cn("animate-fade-up overflow-hidden", className)}
    >
      <CardHeader className="praviar-glass-strip flex flex-row items-start justify-between gap-4 border-b border-[var(--border-default)]">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
            Selected compound dossier
          </p>
          <CardTitle id={titleId} className="mt-1 break-words">
            {compound.name}
          </CardTitle>
          <div className="mt-3 flex flex-wrap gap-1.5">
            <Badge variant="outline" className="font-mono">
              {compound.molecular_formula || "Formula unknown"}
            </Badge>
            <Badge variant="secondary">
              {formatWeight(compound.molecular_weight)}
            </Badge>
            <Badge variant="secondary">
              {formatAnalysisCount(compound.analysis_count)}
            </Badge>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0"
          onClick={onClose}
          aria-label="Close compound details"
        >
          <X className="h-4 w-4" />
        </Button>
      </CardHeader>
      <CardContent className="space-y-5 p-4 sm:p-5">
        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 p-4">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            Organization-scoped identity
          </p>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            Normalized from completed FTO analyses in this workspace. Linked
            external references support lookup and enrichment; they are not
            legal clearance signals.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4">
          <IdentifierBlock
            label="SMILES"
            value={compound.canonical_smiles}
            copySupported={copySupported}
            copied={
              copiedField?.compoundId === compound.id &&
              copiedField.label === "SMILES"
            }
            onCopy={() => copyIdentifier("SMILES", compound.canonical_smiles)}
          />
          <IdentifierBlock
            label="InChI Key"
            value={compound.inchi_key}
            copySupported={copySupported}
            copied={
              copiedField?.compoundId === compound.id &&
              copiedField.label === "InChI Key"
            }
            onCopy={() => copyIdentifier("InChI Key", compound.inchi_key)}
          />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-1">
            <DetailStat
              label="First analyzed in workspace"
              value={formatCompoundDate(compound.first_analyzed_at)}
            />
            <DetailStat
              label="Workspace analyses"
              value={formatAnalysisCount(compound.analysis_count)}
            />
          </div>
          {compound.pubchem_cid !== null ? (
            <div>
              <p className="mb-1 text-xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]">
                Matched PubChem reference
              </p>
              <Button asChild variant="link" size="sm" className="h-auto p-0">
                <a
                  href={`https://pubchem.ncbi.nlm.nih.gov/compound/${compound.pubchem_cid}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`Open PubChem CID ${compound.pubchem_cid} for ${compound.name} in PubChem`}
                >
                  CID {compound.pubchem_cid}
                  <ExternalLink className="h-3 w-3" aria-hidden="true" />
                </a>
              </Button>
            </div>
          ) : (
            <DetailStat label="Matched PubChem reference" value="Not indexed" />
          )}
        </div>

        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]">
            Functional Groups
          </p>
          {functionalGroups.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {functionalGroups.map((group, index) => (
                <Badge
                  key={`${group}-${index}`}
                  variant="secondary"
                  className="max-w-full min-w-0 whitespace-normal break-words [overflow-wrap:break-word] [word-break:normal]"
                  title={group}
                >
                  {group}
                </Badge>
              ))}
            </div>
          ) : (
            <p className="text-sm text-[var(--text-secondary)]">
              No functional groups indexed for this compound.
            </p>
          )}
        </div>

        <p className="sr-only" role="status" aria-live="polite">
          {copiedField?.compoundId === compound.id
            ? `${copiedField.label} copied`
            : ""}
        </p>
      </CardContent>
    </Card>
  );
}

function IdentifierBlock({
  label,
  value,
  copySupported,
  copied,
  onCopy,
}: {
  label: string;
  value: string;
  copySupported: boolean;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-3">
        <p className="text-xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]">
          {label}
        </p>
        {copySupported ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 gap-1.5 px-2 text-xs"
            aria-label={copied ? `${label} copied` : `Copy ${label}`}
            onClick={onCopy}
          >
            {copied ? (
              <Check className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <Copy className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            {copied ? "Copied" : "Copy"}
          </Button>
        ) : null}
      </div>
      <p className="break-all rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 p-3 font-mono text-sm leading-6 text-[var(--text-primary)] [overflow-wrap:anywhere]">
        {value}
      </p>
    </div>
  );
}

function DetailStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="mb-1 text-xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="text-sm text-[var(--text-primary)]">{value}</p>
    </div>
  );
}
