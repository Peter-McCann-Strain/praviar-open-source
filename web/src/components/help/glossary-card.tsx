import { BookOpen } from "lucide-react";
import { ExpandableItem } from "@/components/help/expandable-item";
import {
  GLOSSARY,
  HELP_SECTION_SEARCH_TERMS,
  matchesHelpQuery,
} from "@/components/help/helpers";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface GlossaryCardProps {
  query: string;
}

export function GlossaryCard({ query }: GlossaryCardProps) {
  const filteredGlossary = GLOSSARY.filter((item) =>
    matchesHelpQuery(
      query,
      ...HELP_SECTION_SEARCH_TERMS.glossary,
      item.term,
      item.definition,
    ),
  );

  if (filteredGlossary.length === 0) {
    return null;
  }

  return (
    <Card id="glossary" className="scroll-mt-36">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-brand-primary" />
          Glossary of Patent Terms
        </CardTitle>
        <p className="mt-1 type-body-md text-[var(--text-tertiary)]">
          Key terms used throughout Praviar and FTO analysis
        </p>
      </CardHeader>
      <CardContent className="p-0">
        {filteredGlossary.map((item) => (
          <ExpandableItem key={item.term} title={item.term}>
            {item.definition}
          </ExpandableItem>
        ))}
      </CardContent>
    </Card>
  );
}
