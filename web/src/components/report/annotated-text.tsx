"use client";

import { parseCitationMarkers, type CitationRef } from "@/types/citation";
import { CitationSuperscript } from "./citation-superscript";

interface AnnotatedTextProps {
  /** Raw text that may contain [n] citation markers */
  text: string;
  /** Map of citation index → citation reference data */
  citations?: Map<number, CitationRef>;
  /** Called when a citation is clicked */
  onCitationClick?: (index: number) => void;
  /** Additional className for the wrapper */
  className?: string;
}

/**
 * Renders text with inline citation superscripts.
 * Parses [n] markers and replaces them with interactive CitationSuperscript components.
 * Falls back to plain text if no markers are found.
 */
export function AnnotatedText({
  text,
  citations,
  onCitationClick,
  className,
}: AnnotatedTextProps) {
  const { segments, indices } = parseCitationMarkers(text);

  // No citations found — render plain text
  if (indices.length === 0) {
    return <span className={className}>{text}</span>;
  }

  return (
    <span className={className}>
      {segments.map((segment, i) => {
        if (segment.type === "text") {
          return <span key={i}>{segment.content}</span>;
        }
        return (
          <CitationSuperscript
            key={`cite-${i}`}
            index={segment.index}
            citation={citations?.get(segment.index)}
            onClick={onCitationClick}
          />
        );
      })}
    </span>
  );
}
