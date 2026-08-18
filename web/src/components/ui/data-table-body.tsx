import type { Header, Table as TanStackTable } from "@tanstack/react-table";
import { flexRender } from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface DataTableBodyProps<TData> {
  emptyDescription: string;
  emptyMessage: string;
  loading: boolean;
  skeletonRows: number;
  table: TanStackTable<TData>;
  visibleColumns: number;
}

function SortIcon({ sorted }: { sorted: false | "asc" | "desc" }) {
  if (sorted === "asc") {
    return <ArrowUp aria-hidden="true" className="h-3.5 w-3.5" />;
  }
  if (sorted === "desc") {
    return <ArrowDown aria-hidden="true" className="h-3.5 w-3.5" />;
  }
  return <ArrowUpDown aria-hidden="true" className="h-3.5 w-3.5 opacity-40" />;
}

function getHeaderLabel<TData>(header: Header<TData, unknown>) {
  const headerDef = header.column.columnDef.header;
  return typeof headerDef === "string" ? headerDef : header.id;
}

function getSortButtonLabel(label: string, sorted: false | "asc" | "desc") {
  if (sorted === "asc") return `Sort ${label} descending`;
  if (sorted === "desc") return `Clear ${label} sorting`;
  return `Sort ${label} ascending`;
}

function SkeletonRow({ columns }: { columns: number }) {
  return (
    <tr className="border-b border-[var(--border-subtle)]">
      {Array.from({ length: columns }).map((_, index) => (
        <td key={index} className="px-4 py-3">
          <Skeleton className={cn("h-4", index === 0 ? "w-2/3" : "w-1/2")} />
        </td>
      ))}
    </tr>
  );
}

export function DataTableBody<TData>({
  emptyDescription,
  emptyMessage,
  loading,
  skeletonRows,
  table,
  visibleColumns,
}: DataTableBodyProps<TData>) {
  return (
    <div className="praviar-surface-premium overflow-hidden rounded-lg">
      <div
        className="overflow-x-auto focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]"
        role="region"
        tabIndex={0}
        aria-label="Data table horizontal scroll area"
      >
        <table className="w-full min-w-[760px] border-collapse">
          <thead className="sticky top-0 z-10">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr
                key={headerGroup.id}
                className="praviar-glass-strip border-b border-[var(--border-subtle)]"
              >
                {headerGroup.headers.map((header) => {
                  const canSort = header.column.getCanSort();
                  const sorted = header.column.getIsSorted();
                  const headerLabel = getHeaderLabel(header);

                  return (
                    <th
                      key={header.id}
                      scope="col"
                      aria-sort={
                        canSort
                          ? sorted === "asc"
                            ? "ascending"
                            : sorted === "desc"
                              ? "descending"
                              : "none"
                          : undefined
                      }
                      className="px-3 py-1.5 text-left text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]"
                      style={{
                        width:
                          header.getSize() !== 150
                            ? header.getSize()
                            : undefined,
                      }}
                    >
                      {header.isPlaceholder ? null : canSort ? (
                        <button
                          type="button"
                          aria-label={getSortButtonLabel(headerLabel, sorted)}
                          className="flex min-h-11 w-full items-center gap-1.5 rounded-md border-0 bg-transparent px-2 py-1 text-left text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
                          onClick={header.column.getToggleSortingHandler()}
                        >
                          {flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )}
                          <SortIcon sorted={sorted} />
                        </button>
                      ) : (
                        <div className="flex items-center gap-1.5">
                          {flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )}
                        </div>
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-[var(--border-subtle)]">
            {loading ? (
              Array.from({ length: skeletonRows }).map((_, index) => (
                <SkeletonRow key={index} columns={visibleColumns} />
              ))
            ) : table.getRowModel().rows.length > 0 ? (
              table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  data-state={row.getIsSelected() ? "selected" : undefined}
                  className={cn(
                    "h-10 transition-colors odd:bg-[color-mix(in_srgb,var(--brand-soft-mint)_18%,transparent)] hover:bg-[var(--surface-muted)]",
                    row.getIsSelected() &&
                      "bg-brand-primary/5 hover:bg-brand-primary/8",
                  )}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      className="px-3 py-2.5 text-sm text-[var(--text-primary)]"
                    >
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={visibleColumns} className="px-4 py-12 text-center">
                  <div className="flex flex-col items-center gap-1">
                    <p className="text-sm font-medium text-[var(--text-secondary)]">
                      {emptyMessage}
                    </p>
                    <p className="text-xs text-[var(--text-tertiary)]">
                      {emptyDescription}
                    </p>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
