import { SearchIcon } from "lucide-react";
import { EmptyState } from "@/components/shared/empty-state";

interface HelpNoResultsStateProps {
  search: string;
}

export function HelpNoResultsState({ search }: HelpNoResultsStateProps) {
  return (
    <EmptyState
      icon={SearchIcon}
      title={`No results for "${search}"`}
      description="Try a different search term or clear search to browse all help sections."
      contextItems={[
        "Search can recover",
        "Guides remain available",
        "No workspace data changed",
      ]}
      className="mx-auto max-w-2xl"
    />
  );
}
