"use client";

import { Check, Copy, Network } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { MoleculeViewer2D } from "@/components/chemistry/molecule-viewer-2d";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { DrawingStructure } from "@praviar/shared-types";

interface DrawingStructureCardProps {
  structure: DrawingStructure;
}

/** Map fused OCSR confidence to a Badge variant. */
function confidenceBadgeVariant(
  confidence: number | undefined,
  scoreProvided = true,
): "default" | "warning" | "destructive" | "secondary" {
  if (!scoreProvided || confidence === undefined) return "secondary";
  if (confidence >= 0.85) return "default";
  if (confidence >= 0.65) return "warning";
  return "destructive";
}

function confidenceLabel(
  confidence: number | undefined,
  scoreProvided = true,
): string {
  if (!scoreProvided) return "Score not provided";
  if (confidence === undefined) return "Confidence not reported";
  return `${(confidence * 100).toFixed(0)}%`;
}

function markushScopeLabel(
  verdict: DrawingStructure["markush_scope_verdict"],
): string {
  if (!verdict?.verdict) return "Scope not reviewed";
  if (verdict.verdict === "in_scope") return "Scope: In scope";
  if (verdict.verdict === "out_of_scope") return "Scope: Out of scope";
  return "Scope: Ambiguous";
}

export function DrawingStructureCard({ structure }: DrawingStructureCardProps) {
  const [copied, setCopied] = useState(false);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (copyTimerRef.current !== null) clearTimeout(copyTimerRef.current);
    },
    [],
  );

  const isMarkush = structure.is_markush ?? false;
  const markushGrapherScoreUnavailable =
    isMarkush &&
    structure.extraction_tool?.trim().toLowerCase() === "markushgrapher";
  const displayedConfidence = confidenceLabel(
    structure.confidence,
    !markushGrapherScoreUnavailable,
  );
  // For Markush we render the CXSMILES (with R-group placeholders). For
  // regular molecules the canonical SMILES is the publication-grade form.
  const renderSmiles = isMarkush
    ? (structure.markush_cxsmiles ?? "")
    : (structure.canonical_smiles ?? structure.raw_smiles ?? "");
  const rGroups = structure.markush_r_groups ?? [];
  const cropHash = validSha256(structure.input_image_sha256);
  const sourceHash = validSha256(structure.source_page_image_sha256);
  const inputsBound = cropHash && sourceHash;

  const handleCopy = async () => {
    if (!renderSmiles) return;
    try {
      await navigator.clipboard.writeText(renderSmiles);
      setCopied(true);
      if (copyTimerRef.current !== null) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard API can fail in non-secure contexts; degrade silently.
    }
  };

  const headerLabel = `${structure.patent_id ?? "?"} · p.${structure.page_number ?? "?"} · #${structure.structure_index ?? 0}`;

  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex flex-row items-start justify-between gap-2 pb-3">
        <CardTitle
          className="text-sm font-mono text-[var(--text-secondary)] truncate"
          title={headerLabel}
        >
          {headerLabel}
        </CardTitle>
        <Badge
          variant={confidenceBadgeVariant(
            structure.confidence,
            !markushGrapherScoreUnavailable,
          )}
          aria-label={
            markushGrapherScoreUnavailable
              ? "OCSR confidence score not provided by MarkushGrapher"
              : `OCSR confidence ${displayedConfidence}`
          }
        >
          {displayedConfidence}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex justify-center">
          {renderSmiles ? (
            <MoleculeViewer2D
              smiles={renderSmiles}
              isMarkush={isMarkush}
              width={280}
              height={180}
              label={isMarkush ? "Markush template" : undefined}
            />
          ) : (
            <div
              className="flex h-[180px] w-full max-w-[280px] items-center justify-center rounded-lg border border-[var(--border-default)] bg-[var(--surface-subtle)] px-4 text-center text-xs text-[var(--text-disabled)]"
              data-testid="drawing-no-smiles-placeholder"
            >
              No SMILES extracted
            </div>
          )}
        </div>

        {isMarkush && (
          <div className="space-y-2" data-testid="markush-evidence-status">
            <div className="flex flex-wrap gap-2">
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Badge
                      variant="warning"
                      className={cn("cursor-help", "gap-1")}
                      aria-label={`Markush template with ${rGroups.length} R-groups`}
                    >
                      <Network className="h-3 w-3" aria-hidden="true" />
                      Markush
                      {rGroups.length > 0 && (
                        <span className="ml-1 text-xs opacity-80">
                          ({rGroups.length} R-group
                          {rGroups.length === 1 ? "" : "s"})
                        </span>
                      )}
                    </Badge>
                  </TooltipTrigger>
                  <TooltipContent className="max-w-xs">
                    {rGroups.length > 0 ? (
                      <ul
                        className="space-y-1 text-xs"
                        aria-label="R-group definitions"
                      >
                        {rGroups.map((rg, i) => (
                          <li key={i} className="font-mono">
                            {rg}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-xs">
                        No R-group definitions captured.
                      </p>
                    )}
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
              <Badge variant={structure.rdkit_valid ? "default" : "secondary"}>
                {structure.rdkit_valid
                  ? "Structure parsed"
                  : "Validation not confirmed"}
              </Badge>
              <Badge
                variant={
                  structure.markush_scope_verdict?.verdict === "in_scope"
                    ? "destructive"
                    : structure.markush_scope_verdict?.verdict ===
                        "out_of_scope"
                      ? "success"
                      : structure.markush_scope_verdict?.verdict === "ambiguous"
                        ? "warning"
                        : "secondary"
                }
              >
                {markushScopeLabel(structure.markush_scope_verdict)}
              </Badge>
              {structure.llm_verified !== null &&
              structure.llm_verified !== undefined ? (
                <Badge
                  variant={structure.llm_verified ? "default" : "destructive"}
                >
                  {structure.llm_verified
                    ? "Model verification passed"
                    : "Model verification rejected"}
                </Badge>
              ) : null}
            </div>
            {structure.markush_scope_verdict?.abstained_reason ? (
              <p className="text-xs leading-5 text-[var(--text-secondary)]">
                Scope review abstained:{" "}
                {structure.markush_scope_verdict.abstained_reason}
              </p>
            ) : null}
          </div>
        )}

        {renderSmiles && (
          <div className="relative">
            <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-md border border-[var(--border-default)] bg-[var(--surface-subtle)] p-2 pr-14 font-mono text-xs">
              {renderSmiles}
            </pre>
            <button
              type="button"
              onClick={handleCopy}
              aria-label="Copy SMILES to clipboard"
              className="absolute right-1 top-1 inline-flex h-11 w-11 items-center justify-center rounded-md text-[var(--text-disabled)] transition-colors hover:bg-[var(--surface-active)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
            >
              {copied ? (
                <Check className="h-4 w-4 text-success" aria-hidden="true" />
              ) : (
                <Copy className="h-4 w-4" aria-hidden="true" />
              )}
            </button>
          </div>
        )}

        <div
          className="space-y-2 border-t border-[var(--border-subtle)] pt-3 text-xs"
          data-testid="drawing-source-provenance"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-semibold uppercase tracking-[0.1em] text-[var(--text-disabled)]">
              Extraction provenance
            </span>
            <Badge variant={inputsBound ? "success" : "warning"}>
              {inputsBound ? "Inputs bound" : "Source binding missing"}
            </Badge>
          </div>
          <dl className="grid gap-2">
            <ProvenanceRow
              label="Tool"
              value={structure.extraction_tool?.trim() || "Not recorded"}
            />
            <ProvenanceRow
              label="Crop"
              value={cropHash ? shortEvidenceHash(cropHash) : "Not recorded"}
              mono
            />
            <ProvenanceRow
              label="Source page"
              value={
                sourceHash ? shortEvidenceHash(sourceHash) : "Not recorded"
              }
              mono
            />
          </dl>
        </div>
      </CardContent>
    </Card>
  );
}

function validSha256(value: string | undefined): string | null {
  return value && /^[a-f0-9]{64}$/i.test(value) ? value : null;
}

function shortEvidenceHash(value: string): string {
  return `sha256:${value.slice(0, 12)}…`;
}

function ProvenanceRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-2">
      <dt className="text-[var(--text-disabled)]">{label}</dt>
      <dd
        className={`min-w-0 truncate text-right text-[var(--text-secondary)] ${mono ? "font-mono" : ""}`}
        title={value}
      >
        {value}
      </dd>
    </div>
  );
}
