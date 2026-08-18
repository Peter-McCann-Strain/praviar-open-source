import { Button } from "@/components/ui/button";

interface BatchPaginationProps {
  page: number;
  totalPages: number;
  total: number;
  onPrevious: () => void;
  onNext: () => void;
}

export function BatchPagination({
  page,
  totalPages,
  total,
  onPrevious,
  onNext,
}: BatchPaginationProps) {
  if (totalPages <= 1) {
    return null;
  }

  return (
    <div className="flex items-center justify-between">
      <p className="text-xs text-[var(--text-tertiary)]">
        Page {page} of {totalPages} ({total} total)
      </p>
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={page <= 1}
          onClick={onPrevious}
        >
          Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={page >= totalPages}
          onClick={onNext}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
