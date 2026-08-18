import type { ChatCitation } from "@/hooks/use-report-chat";
import type { CitationRef } from "@/types/citation";

const PATENT_ID_PATTERN =
  /\b(?:US|EP|WO|JP|CN|CA|AU|IN|GB|DE|FR)\s*[-/]?\s*\d{4,}(?:\s*[-/]?\s*[A-Z]\d?)?\b/i;
const CLAIM_NUMBER_PATTERN = /\bclaim\s+(\d+)\b/i;
const ELEMENT_NUMBER_PATTERN = /\belement\s+(\d+)\b/i;

function normalizePatentId(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  if (!trimmed) return undefined;
  const match = trimmed.match(PATENT_ID_PATTERN);
  return match?.[0]?.replace(/[\s/-]+/g, "").toUpperCase();
}

function parsePositiveInteger(value: number | string | null | undefined) {
  if (typeof value === "number") {
    return Number.isFinite(value) && value > 0 ? Math.trunc(value) : undefined;
  }
  if (typeof value !== "string") return undefined;
  const parsed = Number.parseInt(value.trim(), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
}

function inferNumberFromText(
  pattern: RegExp,
  ...values: Array<string | undefined>
) {
  for (const value of values) {
    const match = value?.match(pattern);
    const parsed = parsePositiveInteger(match?.[1]);
    if (parsed) return parsed;
  }
  return undefined;
}

function firstSafeUrl(...values: Array<string | undefined>) {
  return values.find((value) => value?.trim());
}

export function mapChatCitationToCitationRef(
  citation: ChatCitation,
  displayIndex?: number,
): CitationRef {
  const documentTitle = citation.document_title?.trim();
  const citedText =
    citation.cited_text?.trim() ||
    documentTitle ||
    "Citation excerpt was not returned by the report chat response.";
  const citationIndex =
    typeof displayIndex === "number" &&
    Number.isFinite(displayIndex) &&
    displayIndex > 0
      ? Math.trunc(displayIndex)
      : getChatCitationDisplayIndex(citation);
  const patentId =
    normalizePatentId(citation.patent_id) ??
    normalizePatentId(citation.patentId) ??
    normalizePatentId(documentTitle) ??
    normalizePatentId(citedText);
  const claimNumber =
    parsePositiveInteger(citation.claim_number) ??
    parsePositiveInteger(citation.claimNumber) ??
    inferNumberFromText(CLAIM_NUMBER_PATTERN, documentTitle, citedText);
  const elementNumber =
    parsePositiveInteger(citation.element_number) ??
    parsePositiveInteger(citation.elementNumber) ??
    inferNumberFromText(ELEMENT_NUMBER_PATTERN, documentTitle, citedText);

  return {
    index: citationIndex,
    patentId,
    claimNumber,
    elementNumber,
    text: citedText,
    section: documentTitle
      ? `Report chat citation: ${documentTitle}`
      : "Report chat citation",
    url: firstSafeUrl(citation.source_url, citation.url),
  };
}

export function getChatCitationDisplayIndex(
  citation: ChatCitation,
  fallbackArrayIndex = 0,
): number {
  if (
    typeof citation.document_index === "number" &&
    Number.isFinite(citation.document_index) &&
    citation.document_index >= 0
  ) {
    return Math.trunc(citation.document_index) + 1;
  }

  return Math.max(Math.trunc(fallbackArrayIndex), 0) + 1;
}
