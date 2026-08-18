"use client";

import { ADMIN_BUTTON_TARGET_CLASS } from "@/components/admin-dashboard/helpers";
import { Button } from "@/components/ui/button";

export function UsersTabPagination({
  page,
  totalPages,
  onPrevious,
  onNext,
  disabled = false,
}: {
  page: number;
  totalPages: number;
  onPrevious: () => void;
  onNext: () => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <p className="text-xs text-[var(--text-tertiary)]">
        Page {page} of {totalPages}
      </p>
      <div className="grid grid-cols-2 gap-2 sm:flex">
        <Button
          variant="outline"
          size="sm"
          disabled={disabled || page <= 1}
          onClick={onPrevious}
          className={ADMIN_BUTTON_TARGET_CLASS}
        >
          Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={disabled || page >= totalPages}
          onClick={onNext}
          className={ADMIN_BUTTON_TARGET_CLASS}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
