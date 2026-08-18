"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  BookOpenCheck,
  Check,
  Copy,
  ExternalLink,
  FileText,
  Quote,
  Scale,
  ShieldCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import type {
  ClaimAssertionSupport,
  ClaimElement,
  PatentHit,
  SourceSpanReference,
} from "@praviar/shared-types";

export interface EvidenceDrilldownProps {
  patent: PatentHit | null;
  claimNumber: number;
  element: ClaimElement | null;
  reportCitation?: EvidenceCitationReportContext;
  sourceSpan?: SourceSpanReference | null;
  sourceSupport?: ClaimAssertionSupport | null;
  open: boolean;
  onClose: () => void;
}

export interface EvidenceCitationReportContext {
  reportId?: string | null;
  generatedAt?: string | null;
  pipelineVersion?: string | null;
  reportFingerprint?: string | null;
  reviewerDecision?: string | null;
  reviewerTimestamp?: string | null;
}

interface MatchedSpan {
  start: number;
  end: number;
  source: "evidence" | "element_text" | "source_span" | "none";
}

/**
 * Locate the matched passage inside the full claims text.
 * v1 strategy: prefer the analyst's `evidence` quote; otherwise fall back
 * to the literal element text. All matching is case-insensitive and
 * whitespace-normalised so minor formatting differences don't derail
 * the highlight.
 */
export function findMatchedSpan(
  claimsText: string,
  element: ClaimElement,
): MatchedSpan {
  const tryMatch = (needle: string): { start: number; end: number } | null => {
    const trimmed = needle.trim();
    if (!trimmed) return null;

    // Direct search
    const directIdx = claimsText.toLowerCase().indexOf(trimmed.toLowerCase());
    if (directIdx !== -1) {
      return { start: directIdx, end: directIdx + trimmed.length };
    }

    // Whitespace-normalised search: collapse runs of whitespace on both sides,
    // build an index map so we can translate normalised offsets back.
    const normalisedPieces: string[] = [];
    const indexMap: number[] = [];
    let prevWasSpace = false;
    for (let i = 0; i < claimsText.length; i++) {
      const ch = claimsText[i];
      if (/\s/.test(ch)) {
        if (!prevWasSpace) {
          normalisedPieces.push(" ");
          indexMap.push(i);
          prevWasSpace = true;
        }
      } else {
        normalisedPieces.push(ch);
        indexMap.push(i);
        prevWasSpace = false;
      }
    }
    const normalised = normalisedPieces.join("").toLowerCase();
    const normalisedNeedle = trimmed.replace(/\s+/g, " ").toLowerCase();
    const normIdx = normalised.indexOf(normalisedNeedle);
    if (normIdx === -1) return null;

    const originalStart = indexMap[normIdx] ?? 0;
    const lastNormCharIdx = normIdx + normalisedNeedle.length - 1;
    const originalEnd = (indexMap[lastNormCharIdx] ?? originalStart) + 1;
    return { start: originalStart, end: originalEnd };
  };

  if (element.evidence) {
    const match = tryMatch(element.evidence);
    if (match) return { ...match, source: "evidence" };
  }
  const elementMatch = tryMatch(element.element_text);
  if (elementMatch) return { ...elementMatch, source: "element_text" };
  return { start: -1, end: -1, source: "none" };
}

/**
 * Map a patent_id prefix to the appropriate issuing-office URL.
 * Uses Google Patents as a universally-working fallback.
 */
function getJurisdictionLinks(
  patentId: string,
): Array<{ label: string; href: string }> {
  const id = patentId.toUpperCase();
  const links: Array<{ label: string; href: string }> = [
    {
      label: "Google Patents",
      href: `https://patents.google.com/patent/${id}`,
    },
  ];
  if (id.startsWith("US")) {
    links.push({
      label: "USPTO Patent Public Search",
      href: "https://ppubs.uspto.gov/pubwebapp/",
    });
  } else if (id.startsWith("EP")) {
    links.push({
      label: "Espacenet",
      href: `https://worldwide.espacenet.com/patent/search?q=pn%3D${id}`,
    });
  } else if (id.startsWith("WO")) {
    links.push({
      label: "WIPO PATENTSCOPE",
      href: `https://patentscope.wipo.int/search/en/detail.jsf?docId=${id}`,
    });
  }
  return links;
}

function formatEvidenceStatus(status: string): string {
  return status
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatConfidence(confidence: number | null | undefined): string {
  if (typeof confidence !== "number" || Number.isNaN(confidence)) {
    return "Confidence not reported";
  }
  return `${Math.round(confidence * 100).toLocaleString()}% confidence`;
}

function evidenceStatusClass(status: string): string {
  const normalized = status.toLowerCase();
  if (normalized === "met") {
    return "border-error/25 bg-error/10 text-error";
  }
  if (
    normalized === "partial" ||
    normalized === "partially_met" ||
    normalized === "partially met" ||
    normalized === "uncertain" ||
    normalized === "unclear"
  ) {
    return "border-warning/25 bg-warning/10 text-warning";
  }
  if (normalized === "not_met" || normalized === "not met") {
    return "border-success/25 bg-success/10 text-success";
  }
  return "border-[var(--border-subtle)] bg-[var(--surface-muted)] text-[var(--text-secondary)]";
}

function formatPacketValue(value: string | null | undefined): string {
  const trimmed = value?.trim();
  return trimmed ? trimmed : "Not reported";
}

function formatPacketText(value: string | null | undefined): string {
  return formatPacketValue(value).replace(/\s+/g, " ");
}

function getMatchLabel(span: MatchedSpan, claimsText: string): string {
  if (span.source === "source_span") return "Ledger source span";
  if (span.source === "evidence") return "Analyst quote matched";
  if (span.source === "element_text") return "Element text matched";
  return claimsText ? "Exact passage not located" : "Claim text unavailable";
}

function getSourceSpanLabel(
  patentId: string,
  claimNumber: number,
  elementNumber: number,
  span: MatchedSpan,
  sourceSpan?: SourceSpanReference | null,
): string {
  if (sourceSpan?.span_id) return sourceSpan.span_id;
  const position =
    span.start >= 0 ? `offset-${span.start}-${span.end}` : "offset-unresolved";
  return `${patentId}:claim-${claimNumber}:element-${elementNumber}:${position}`;
}

function formatSourceSupportStatus(
  sourceSupport?: ClaimAssertionSupport | null,
): string {
  const status = sourceSupport?.support_status;
  return status ? formatEvidenceStatus(status) : "Not reported";
}

function buildEvidenceCitationPacket({
  patent,
  claimNumber,
  element,
  span,
  links,
  reportCitation,
  sourceSpan,
  sourceSupport,
}: {
  patent: PatentHit | null;
  claimNumber: number;
  element: ClaimElement;
  span: MatchedSpan;
  links: Array<{ label: string; href: string }>;
  reportCitation?: EvidenceCitationReportContext;
  sourceSpan?: SourceSpanReference | null;
  sourceSupport?: ClaimAssertionSupport | null;
}): string {
  const patentId =
    patent?.patent_id ??
    sourceSpan?.patent_id ??
    sourceSupport?.patent_id ??
    "Not reported";
  const patentSources = patent?.sources ?? [];
  const sourceDatabases =
    patentSources.length > 0 ? patentSources.join(", ") : "Not reported";
  const sourceSpanText =
    sourceSpan?.citation || sourceSpan?.excerpt
      ? [sourceSpan.citation, sourceSpan.excerpt].filter(Boolean).join(" - ")
      : span.start >= 0
        ? `${span.start}-${span.end} in collected claims text`
        : "Exact passage not located in collected claims text";
  const familyId =
    patent?.family_id ??
    patent?.family?.family_id ??
    patent?.parent_application_id;
  const reviewerDecision = reportCitation?.reviewerDecision
    ? `${reportCitation.reviewerDecision}${
        reportCitation.reviewerTimestamp
          ? ` at ${reportCitation.reviewerTimestamp}`
          : ""
      }`
    : "See report review ledger";

  const lines = [
    "Praviar evidence citation packet",
    `Report: ${formatPacketValue(reportCitation?.reportId)}`,
    `Generated: ${formatPacketValue(reportCitation?.generatedAt)}`,
    `Pipeline: ${formatPacketValue(reportCitation?.pipelineVersion)}`,
    `Report fingerprint: ${formatPacketValue(reportCitation?.reportFingerprint)}`,
    `Reviewer decision: ${reviewerDecision}`,
    "",
    "Patent record",
    `Patent: ${patentId}`,
    `Title: ${formatPacketText(patent?.title)}`,
    `Family: ${formatPacketValue(familyId)}`,
    `Application: ${formatPacketValue(patent?.application_number)}`,
    `Jurisdiction: ${formatPacketValue(patent?.jurisdiction)}`,
    `Filing: ${formatPacketValue(patent?.filing_date)}`,
    `Priority: ${formatPacketValue(patent?.priority_date)}`,
    `Expiry: ${formatPacketValue(patent?.expiry_date)}`,
    `Legal status: ${formatPacketValue(patent?.legal_status)}`,
    `Claims text source: ${formatPacketValue(patent?.claims_text_source)}`,
    `Source databases: ${sourceDatabases}`,
    "",
    "Claim element",
    `Claim element: Claim ${claimNumber}, element ${element.element_number}`,
    `Status: ${formatEvidenceStatus(element.status)}`,
    `Claim support status: ${formatSourceSupportStatus(sourceSupport)}`,
    `Confidence: ${formatConfidence(element.confidence)}`,
    `Match posture: ${getMatchLabel(span, patent?.claims_text ?? sourceSpan?.excerpt ?? "")}`,
    `Source span ID: ${getSourceSpanLabel(
      patentId,
      claimNumber,
      element.element_number,
      span,
      sourceSpan,
    )}`,
    `Source span: ${sourceSpanText}`,
    `Element text: ${formatPacketText(element.element_text)}`,
    `Analyst evidence: ${formatPacketText(element.evidence)}`,
    `Ledger excerpt: ${formatPacketText(sourceSpan?.excerpt)}`,
    `Reasoning: ${formatPacketText(element.reasoning)}`,
    "",
    "Source links:",
    ...links.map((link) => `- ${link.label}: ${link.href}`),
  ];

  return lines.join("\n");
}

export function EvidenceDrilldown({
  patent,
  claimNumber,
  element,
  reportCitation,
  sourceSpan,
  sourceSupport,
  open,
  onClose,
}: EvidenceDrilldownProps) {
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (copyTimerRef.current !== null) clearTimeout(copyTimerRef.current);
    },
    [],
  );

  const ledgerExcerpt = sourceSpan?.excerpt ?? "";
  const claimsText = patent?.claims_text ?? ledgerExcerpt;
  const span = useMemo(() => {
    if (sourceSpan?.excerpt) {
      return {
        start: 0,
        end: sourceSpan.excerpt.length,
        source: "source_span" as const,
      };
    }
    if (!element || !claimsText)
      return { start: -1, end: -1, source: "none" as const };
    return findMatchedSpan(claimsText, element);
  }, [claimsText, element, sourceSpan]);

  const patentId =
    patent?.patent_id ??
    sourceSpan?.patent_id ??
    sourceSupport?.patent_id ??
    "Report packet";
  const links = useMemo(
    () => (patentId ? getJurisdictionLinks(patentId) : []),
    [patentId],
  );

  const citationPacket = useMemo(() => {
    if (!element) return "";
    return buildEvidenceCitationPacket({
      patent,
      claimNumber,
      element,
      span,
      links,
      reportCitation,
      sourceSpan,
      sourceSupport,
    });
  }, [
    patent,
    claimNumber,
    element,
    span,
    links,
    reportCitation,
    sourceSpan,
    sourceSupport,
  ]);

  const handleCopy = async () => {
    if (!citationPacket) return;
    try {
      await navigator.clipboard.writeText(citationPacket);
      setCopied(true);
      setCopyFailed(false);
      if (copyTimerRef.current !== null) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => {
        setCopied(false);
        setCopyFailed(false);
      }, 2000);
    } catch {
      // Clipboard may be unavailable (e.g. in tests / non-https contexts).
      setCopied(false);
      setCopyFailed(true);
      if (copyTimerRef.current !== null) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => setCopyFailed(false), 2000);
    }
  };

  if (!element) return null;

  const before = span.start >= 0 ? claimsText.slice(0, span.start) : claimsText;
  const highlight =
    span.start >= 0 ? claimsText.slice(span.start, span.end) : "";
  const after = span.start >= 0 ? claimsText.slice(span.end) : "";
  const statusLabel = formatEvidenceStatus(element.status);
  const confidenceLabel = formatConfidence(element.confidence);
  const matchLabel = getMatchLabel(span, claimsText);
  const supportStatusLabel = formatSourceSupportStatus(sourceSupport);
  const patentTitle =
    patent?.title ?? sourceSpan?.citation ?? "Ledger evidence";

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent
        className="flex max-h-[calc(100dvh-1rem)] w-[calc(100vw-1rem)] max-w-5xl flex-col overflow-hidden p-0"
        data-testid="evidence-drilldown"
      >
        <div className="border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] px-4 pb-4 pt-5 sm:px-6">
          <DialogHeader className="pr-8 text-left">
            <DialogTitle className="flex min-w-0 items-start gap-2 text-base leading-6 sm:text-lg">
              <Quote
                className="h-5 w-5 text-brand-primary"
                aria-hidden="true"
              />
              <span className="min-w-0 break-words">
                Evidence: {patentId} — Claim {claimNumber}, Element{" "}
                {element.element_number}
              </span>
            </DialogTitle>
            <DialogDescription className="break-words leading-5">
              {patentTitle} · Filed {patent?.filing_date ?? "unknown"} · Expires{" "}
              {patent?.expiry_date ?? "unknown"}
            </DialogDescription>
          </DialogHeader>

          <div
            aria-label="Evidence provenance"
            className="mt-4 grid gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 p-3 sm:grid-cols-2 lg:grid-cols-4"
          >
            {reportCitation?.reportId ? (
              <EvidenceProvenanceItem
                icon={<ShieldCheck className="h-4 w-4" aria-hidden="true" />}
                label="Report record"
                value={reportCitation.reportId}
              />
            ) : null}
            <EvidenceProvenanceItem
              icon={<FileText className="h-4 w-4" aria-hidden="true" />}
              label="Patent source"
              value={patentId}
            />
            <EvidenceProvenanceItem
              icon={<Scale className="h-4 w-4" aria-hidden="true" />}
              label="Claim position"
              value={`Claim ${claimNumber}, element ${element.element_number}`}
            />
            <EvidenceProvenanceItem
              icon={<ShieldCheck className="h-4 w-4" aria-hidden="true" />}
              label="Review signal"
              value={`${statusLabel}; ${confidenceLabel}; ${supportStatusLabel}`}
            />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
          <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(16rem,0.8fr)_minmax(0,1.25fr)]">
            <section
              aria-labelledby="evidence-element-heading"
              className="min-w-0 space-y-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 shadow-[var(--shadow-xs)]"
            >
              <div className="flex min-w-0 items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                    Claim element
                  </p>
                  <h3
                    id="evidence-element-heading"
                    className="mt-1 text-sm font-semibold text-[var(--text-primary)]"
                  >
                    Element Under Analysis
                  </h3>
                </div>
                <span
                  className={cn(
                    "inline-flex shrink-0 items-center rounded-full border px-2 py-1 text-xs font-semibold uppercase",
                    evidenceStatusClass(element.status),
                  )}
                >
                  {statusLabel}
                </span>
              </div>

              <p className="break-words rounded-md border border-brand-primary/15 bg-brand-primary/8 px-3 py-2 text-sm leading-6 text-[var(--text-primary)]">
                {element.element_text}
              </p>

              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                  Reasoning
                </p>
                <p className="mt-1 break-words text-sm leading-6 text-[var(--text-secondary)]">
                  {element.reasoning}
                </p>
              </div>

              {element.evidence ? (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                    Analyst Evidence
                  </p>
                  <blockquote className="mt-1 break-words rounded-md border-l-2 border-brand-primary/50 bg-[var(--surface-muted)] px-3 py-2 text-sm italic leading-6 text-[var(--text-secondary)]">
                    {element.evidence}
                  </blockquote>
                </div>
              ) : null}
            </section>

            <section
              aria-labelledby="evidence-source-heading"
              className="min-w-0 overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] shadow-[var(--shadow-xs)]"
            >
              <div className="flex min-w-0 flex-col gap-2 border-b border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex min-w-0 items-start gap-2">
                  <BookOpenCheck
                    className="mt-0.5 h-4 w-4 shrink-0 text-brand-primary"
                    aria-hidden="true"
                  />
                  <div className="min-w-0">
                    <h3
                      id="evidence-source-heading"
                      className="text-sm font-semibold text-[var(--text-primary)]"
                    >
                      {sourceSpan ? "Ledger source span" : "Patent claim text"}
                    </h3>
                    <p className="mt-0.5 text-xs leading-5 text-[var(--text-tertiary)]">
                      {sourceSpan?.citation
                        ? `${matchLabel}: ${sourceSpan.citation}`
                        : matchLabel}
                    </p>
                  </div>
                </div>
                {span.source === "none" && claimsText ? (
                  <span
                    className="rounded-full border border-warning/25 bg-warning/10 px-2 py-1 text-xs font-semibold uppercase text-warning"
                    data-testid="evidence-drilldown-no-match"
                  >
                    Exact passage not located
                  </span>
                ) : null}
              </div>

              {claimsText ? (
                <div
                  className="praviar-code-surface max-h-[min(48dvh,34rem)] overflow-y-auto p-4 font-mono text-xs leading-relaxed text-[var(--text-secondary)] whitespace-pre-wrap break-words [overflow-wrap:anywhere]"
                  data-testid="evidence-drilldown-claims"
                >
                  {before}
                  {highlight ? (
                    <mark
                      data-testid="evidence-drilldown-highlight"
                      className={cn(
                        "rounded px-0.5",
                        "bg-[color-mix(in_srgb,var(--warning)_35%,transparent)]",
                        "text-[var(--text-primary)]",
                      )}
                    >
                      {highlight}
                    </mark>
                  ) : null}
                  {after}
                </div>
              ) : (
                <p
                  className="p-4 text-xs italic leading-5 text-[var(--text-tertiary)]"
                  data-testid="evidence-drilldown-empty"
                >
                  Full claim text or a governed source excerpt was not collected
                  for this patent. Use the links below to view the patent at the
                  issuing office.
                </p>
              )}
            </section>
          </div>
        </div>

        <div className="shrink-0 border-t border-[var(--border-subtle)] bg-[var(--bg-surface)] px-4 py-3 shadow-[0_-16px_32px_rgba(11,31,36,0.08)] sm:px-6">
          <section className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              {links.map((link) => (
                <a
                  key={link.href}
                  href={link.href}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-brand-primary/20 bg-brand-primary/8 px-2.5 py-1.5 text-xs font-semibold text-brand-primary transition-colors hover:bg-brand-primary/12"
                >
                  <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                  {link.label}
                </a>
              ))}
            </div>
            <button
              type="button"
              onClick={handleCopy}
              data-testid="evidence-drilldown-copy"
              className="inline-flex min-h-10 w-full items-center justify-center gap-1.5 rounded-md border border-[var(--border-default)] bg-[var(--surface-muted)] px-3 py-2 text-xs font-semibold text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-active)] sm:ml-auto sm:w-auto"
            >
              {copied ? (
                <>
                  <Check className="h-3.5 w-3.5" aria-hidden="true" />
                  Copied
                </>
              ) : copyFailed ? (
                <>
                  <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                  Copy unavailable
                </>
              ) : (
                <>
                  <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                  Copy packet
                </>
              )}
            </button>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function EvidenceProvenanceItem({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex min-w-0 items-start gap-2">
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-brand-primary/15 bg-brand-primary/8 text-brand-primary">
        {icon}
      </span>
      <span className="min-w-0">
        <span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
          {label}
        </span>
        <span className="mt-0.5 block truncate text-xs font-semibold text-[var(--text-primary)]">
          {value}
        </span>
      </span>
    </div>
  );
}
