import { MessageCircleQuestion } from "lucide-react";
import { ExpandableItem } from "@/components/help/expandable-item";
import {
  FAQ,
  HELP_SECTION_SEARCH_TERMS,
  getFaqForCapabilities,
  highlightFaqAnswer,
  matchesHelpQuery,
} from "@/components/help/helpers";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PrincipalCapabilities } from "@/hooks/use-principal-capabilities";

interface FaqCardProps {
  capabilities?: PrincipalCapabilities;
  query: string;
}

export function FaqCard({ capabilities, query }: FaqCardProps) {
  const availableFaq = capabilities ? getFaqForCapabilities(capabilities) : FAQ;
  const filteredFaq = availableFaq.filter((item) =>
    matchesHelpQuery(query, ...HELP_SECTION_SEARCH_TERMS.faq, item.q, item.a),
  );

  if (filteredFaq.length === 0) {
    return null;
  }

  return (
    <Card id="faq" className="scroll-mt-36">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MessageCircleQuestion className="h-4 w-4 text-brand-primary" />
          Frequently Asked Questions
        </CardTitle>
        <p className="mt-1 type-body-md text-[var(--text-tertiary)]">
          Common questions about Praviar&apos;s capabilities and workflow
        </p>
      </CardHeader>
      <CardContent className="p-0">
        {filteredFaq.map((item) => (
          <ExpandableItem key={item.q} title={item.q}>
            <span>
              {highlightFaqAnswer(item.a).map((segment, index) =>
                segment.highlighted ? (
                  <strong key={`${segment.text}-${index}`}>
                    {segment.text}
                  </strong>
                ) : (
                  <span key={`${segment.text}-${index}`}>{segment.text}</span>
                ),
              )}
            </span>
          </ExpandableItem>
        ))}
      </CardContent>
    </Card>
  );
}
