import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ThinkingPanel } from "./audit-tab-thinking-panel";

interface ThinkingPatent {
  patent_id: string;
  thinking_text?: string | null;
}

interface AuditReasoningCardProps {
  thinkingPatents: ThinkingPatent[];
}

export function AuditReasoningCard({
  thinkingPatents,
}: AuditReasoningCardProps) {
  if (thinkingPatents.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Review Basis Notes</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {thinkingPatents.map((thinkingPatent) => (
          <ThinkingPanel
            key={thinkingPatent.patent_id}
            patentId={thinkingPatent.patent_id}
            text={thinkingPatent.thinking_text ?? ""}
          />
        ))}
      </CardContent>
    </Card>
  );
}
