/** A reference to a specific source in the report */
export interface CitationRef {
  /** Display index (1-based) */
  index: number;
  /** Patent number if citing a patent */
  patentId?: string;
  /** Specific claim number */
  claimNumber?: number;
  /** Specific claim element number */
  elementNumber?: number;
  /** The cited text excerpt */
  text: string;
  /** Which section this references (e.g. "summary", "patent:US123", "claim:3") */
  section: string;
  /** Optional external URL */
  url?: string;
}

/** A segment of text that may contain citation markers */
export type TextSegment =
  | { type: "text"; content: string }
  | { type: "citation"; index: number };

interface PatentCitationSource {
  patent_id?: string;
  patent_number?: string;
  title?: string;
  claims_analyzed?: Array<{ claim_number?: number | null }>;
}

interface ClaimAssertionSupportForCitation {
  assertion_id: string;
  patent_id?: string;
  claim_number?: number | null;
  element_number?: number | null;
  assertion_text?: string;
  source_span_ids?: string[];
  support_status?: "supported" | "unsupported" | "needs_review";
  customer_visible?: boolean;
}

interface SourceSpanReferenceForCitation {
  span_id: string;
  source_type?:
    | "claim_text"
    | "verified_claim_text"
    | "element_evidence"
    | "specification_citation"
    | "claim_reasoning";
  patent_id?: string;
  claim_number?: number | null;
  element_number?: number | null;
  citation?: string;
  excerpt?: string;
}

interface ClaimSourceSpanMapForCitation {
  entries?: ClaimAssertionSupportForCitation[];
  spans?: Record<string, SourceSpanReferenceForCitation>;
}

const SOURCE_TYPE_LABELS: Record<
  NonNullable<SourceSpanReferenceForCitation["source_type"]>,
  string
> = {
  claim_reasoning: "Reasoning record",
  claim_text: "Claim text",
  verified_claim_text: "Verified claim text",
  element_evidence: "Element evidence",
  specification_citation: "Specification citation",
};

/** Parse text with [n] citation markers into segments */
export function parseCitationMarkers(text: string): {
  segments: TextSegment[];
  indices: number[];
} {
  const segments: TextSegment[] = [];
  const indices: number[] = [];
  const regex = /\[(\d+)\]/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    // Add preceding text if any
    if (match.index > lastIndex) {
      segments.push({
        type: "text",
        content: text.slice(lastIndex, match.index),
      });
    }
    const citIndex = parseInt(match[1], 10);
    segments.push({ type: "citation", index: citIndex });
    if (!indices.includes(citIndex)) {
      indices.push(citIndex);
    }
    lastIndex = regex.lastIndex;
  }

  // Add trailing text
  if (lastIndex < text.length) {
    segments.push({ type: "text", content: text.slice(lastIndex) });
  }

  // If no markers found, return full text as single segment
  if (segments.length === 0) {
    segments.push({ type: "text", content: text });
  }

  return { segments, indices };
}

/** Build a citation map from patent analyses */
export function buildCitationMap(
  patentAnalyses: PatentCitationSource[],
  claimSourceSpanMap?: ClaimSourceSpanMapForCitation,
): Map<number, CitationRef> {
  const map = new Map<number, CitationRef>();
  patentAnalyses.forEach((pa, i) => {
    const patentId = pa.patent_id ?? pa.patent_number ?? "";
    const support = findBestCitationSupport(patentId, claimSourceSpanMap);
    const claimNumber =
      support?.span?.claim_number ??
      support?.entry.claim_number ??
      pa.claims_analyzed?.find((claim) => claim.claim_number != null)
        ?.claim_number;
    map.set(i + 1, {
      index: i + 1,
      patentId,
      claimNumber: claimNumber ?? undefined,
      text:
        support?.span?.excerpt?.trim() ||
        support?.entry.assertion_text?.trim() ||
        pa.title?.trim() ||
        patentId,
      section: formatCitationSection(patentId, support),
    });
  });
  return map;
}

function findBestCitationSupport(
  patentId: string,
  claimSourceSpanMap?: ClaimSourceSpanMapForCitation,
):
  | {
      entry: ClaimAssertionSupportForCitation;
      span?: SourceSpanReferenceForCitation;
    }
  | undefined {
  if (!patentId || !claimSourceSpanMap?.entries?.length) return undefined;
  const spans = claimSourceSpanMap.spans ?? {};
  const candidates = claimSourceSpanMap.entries.filter(
    (entry) =>
      entry.customer_visible !== false &&
      entry.patent_id === patentId &&
      entry.support_status !== "unsupported",
  );
  const ordered = [
    ...candidates.filter((entry) => entry.support_status === "supported"),
    ...candidates.filter((entry) => entry.support_status === "needs_review"),
    ...candidates.filter((entry) => !entry.support_status),
  ];

  for (const entry of ordered) {
    const span = entry.source_span_ids
      ?.map((spanId) => spans[spanId])
      .find(
        (candidate) =>
          candidate &&
          (candidate.patent_id === undefined ||
            candidate.patent_id === patentId) &&
          Boolean(candidate.excerpt?.trim() || candidate.citation?.trim()),
      );
    if (span) return { entry, span };
  }

  return ordered.length > 0 ? { entry: ordered[0] } : undefined;
}

function formatCitationSection(
  patentId: string,
  support?: {
    entry: ClaimAssertionSupportForCitation;
    span?: SourceSpanReferenceForCitation;
  },
): string {
  if (!support) return patentId ? `patent:${patentId}` : "patent";

  const parts = [
    support.span?.citation?.trim() || (patentId ? `patent:${patentId}` : null),
    support.span?.source_type
      ? SOURCE_TYPE_LABELS[support.span.source_type]
      : null,
    (support.span?.claim_number ?? support.entry.claim_number)
      ? `Claim ${support.span?.claim_number ?? support.entry.claim_number}`
      : null,
    (support.span?.element_number ?? support.entry.element_number)
      ? `Element ${support.span?.element_number ?? support.entry.element_number}`
      : null,
  ].filter((part): part is string => Boolean(part));

  return [...new Set(parts)].join(" · ");
}
