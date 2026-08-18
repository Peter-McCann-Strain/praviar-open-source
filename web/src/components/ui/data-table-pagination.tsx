import type { Table as TanStackTable } from "@tanstack/react-table";
import { useId } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { PAGE_SIZE_OPTIONS } from "./data-table-utils";

function PageSizeSelector<TData>({ table }: { table: TanStackTable<TData> }) {
  const labelId = useId();

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <span id={labelId} className="text-xs text-[var(--text-tertiary)]">
        Rows per page
      </span>
      <select
        value={table.getState().pagination.pageSize}
        onChange={(event) => table.setPageSize(Number(event.target.value))}
        aria-labelledby={labelId}
        className="praviar-glass-field min-h-11 rounded-lg px-3 text-xs text-[var(--text-primary)] focus:border-brand-primary/60 focus:outline-none focus:ring-2 focus:ring-brand-primary/70 focus:ring-offset-2 focus:ring-offset-[var(--bg-base)]"
      >
        {PAGE_SIZE_OPTIONS.map((size) => (
          <option key={size} value={size}>
            {size}
          </option>
        ))}
      </select>
    </div>
  );
}

export function DataTablePagination<TData>({
  table,
}: {
  table: TanStackTable<TData>;
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
      <PageSizeSelector table={table} />

      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="mr-1 text-xs text-[var(--text-tertiary)]">
          Page {table.getState().pagination.pageIndex + 1} of{" "}
          {table.getPageCount() || 1}
        </span>
        <Button
          variant="outline"
          size="icon"
          className="min-h-11 min-w-11"
          onClick={() => table.setPageIndex(0)}
          disabled={!table.getCanPreviousPage()}
          aria-label="Go to first page"
        >
          <ChevronsLeft className="h-3.5 w-3.5" />
          <span className="sr-only">First page</span>
        </Button>
        <Button
          variant="outline"
          size="icon"
          className="min-h-11 min-w-11"
          onClick={() => table.previousPage()}
          disabled={!table.getCanPreviousPage()}
          aria-label="Go to previous page"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          <span className="sr-only">Previous page</span>
        </Button>
        <Button
          variant="outline"
          size="icon"
          className="min-h-11 min-w-11"
          onClick={() => table.nextPage()}
          disabled={!table.getCanNextPage()}
          aria-label="Go to next page"
        >
          <ChevronRight className="h-3.5 w-3.5" />
          <span className="sr-only">Next page</span>
        </Button>
        <Button
          variant="outline"
          size="icon"
          className="min-h-11 min-w-11"
          onClick={() => table.setPageIndex(table.getPageCount() - 1)}
          disabled={!table.getCanNextPage()}
          aria-label="Go to last page"
        >
          <ChevronsRight className="h-3.5 w-3.5" />
          <span className="sr-only">Last page</span>
        </Button>
      </div>
    </div>
  );
}
