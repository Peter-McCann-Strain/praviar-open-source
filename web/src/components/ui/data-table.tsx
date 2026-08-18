"use client";

import { useState } from "react";
import {
  type ColumnDef,
  type SortingState,
  type VisibilityState,
  type RowSelectionState,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { cn } from "@/lib/utils";
import { DataTableBody } from "./data-table-body";
import { DataTablePagination } from "./data-table-pagination";
import { DataTableToolbar } from "./data-table-toolbar";
import { getSelectedRows } from "./data-table-utils";

/* ── Types ──────────────────────────────────────────────────────────── */

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[];
  data: TData[];
  /** Show loading skeleton rows */
  loading?: boolean;
  /** Number of skeleton rows to show while loading */
  skeletonRows?: number;
  /** Empty state message when no data is present */
  emptyMessage?: string;
  /** Empty state description */
  emptyDescription?: string;
  /** Enable row selection with checkboxes */
  enableRowSelection?: boolean;
  /** Enable global filter search input */
  enableSearch?: boolean;
  /** Search placeholder text */
  searchPlaceholder?: string;
  /** Enable column visibility toggle */
  enableColumnVisibility?: boolean;
  /** Enable pagination controls */
  enablePagination?: boolean;
  /** Default page size */
  defaultPageSize?: number;
  /** Additional class for the wrapper */
  className?: string;
  /** Callback when row selection changes */
  onRowSelectionChange?: (rows: TData[]) => void;
}

/* ── Main DataTable Component ───────────────────────────────────────── */

export function DataTable<TData, TValue>({
  columns,
  data,
  loading = false,
  skeletonRows = 5,
  emptyMessage = "No results found",
  emptyDescription = "Try adjusting your search or filters.",
  enableRowSelection = false,
  enableSearch = true,
  searchPlaceholder = "Search...",
  enableColumnVisibility = true,
  enablePagination = true,
  defaultPageSize = 10,
  className,
  onRowSelectionChange,
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [globalFilter, setGlobalFilter] = useState("");

  // eslint-disable-next-line react-hooks/incompatible-library -- TanStack Table manages mutable table internals intentionally.
  const table = useReactTable({
    data,
    columns,
    state: {
      sorting,
      columnVisibility,
      rowSelection,
      globalFilter,
    },
    enableRowSelection,
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    onRowSelectionChange: (updater) => {
      const next =
        typeof updater === "function" ? updater(rowSelection) : updater;
      setRowSelection(next);
      if (onRowSelectionChange) {
        onRowSelectionChange(getSelectedRows(data, next));
      }
    },
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: enablePagination
      ? getPaginationRowModel()
      : undefined,
    initialState: {
      pagination: {
        pageSize: defaultPageSize,
      },
    },
  });

  const visibleColumns = table.getVisibleFlatColumns().length;

  return (
    <div className={cn("space-y-3", className)}>
      <DataTableToolbar
        enableColumnVisibility={enableColumnVisibility}
        enableRowSelection={enableRowSelection}
        enableSearch={enableSearch}
        globalFilter={globalFilter}
        rowSelection={rowSelection}
        searchPlaceholder={searchPlaceholder}
        setGlobalFilter={setGlobalFilter}
        table={table}
      />

      <DataTableBody
        emptyDescription={emptyDescription}
        emptyMessage={emptyMessage}
        loading={loading}
        skeletonRows={skeletonRows}
        table={table}
        visibleColumns={visibleColumns}
      />

      {enablePagination && !loading && data.length > 0 && (
        <DataTablePagination table={table} />
      )}
    </div>
  );
}

export type { DataTableProps };
export { getSelectedRows };
