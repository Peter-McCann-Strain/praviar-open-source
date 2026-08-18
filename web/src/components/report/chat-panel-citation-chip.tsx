import { Quote } from "lucide-react";
import { getChatCitationDisplayIndex } from "@/components/report/chat-citation-mapping";
import type { ChatCitation } from "@/hooks/use-report-chat";

interface ChatPanelCitationChipProps {
  citation: ChatCitation;
  index: number;
  onClick?: () => void;
}

export function ChatPanelCitationChip({
  citation,
  index,
  onClick,
}: ChatPanelCitationChipProps) {
  const displayIndex = getChatCitationDisplayIndex(citation, index);
  const labelSource =
    citation.document_title?.trim() ||
    citation.cited_text?.trim() ||
    `source ${displayIndex}`;
  const compactLabel =
    labelSource.length > 96 ? `${labelSource.slice(0, 93)}...` : labelSource;

  return (
    <button
      type="button"
      aria-label={`Open citation ${displayIndex}: ${compactLabel}`}
      onClick={onClick}
      className="inline-flex min-h-11 min-w-11 items-center justify-center gap-1 rounded-md border border-brand-primary/25 bg-brand-primary/15 px-3 py-2 align-baseline text-xs font-bold leading-tight text-brand-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.35)] transition-colors hover:bg-brand-primary/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/45"
      title={labelSource.slice(0, 200)}
    >
      <Quote className="h-3 w-3" />
      {displayIndex}
    </button>
  );
}
