import type { Column, RowSelectionState } from "@tanstack/react-table";

export const PAGE_SIZE_OPTIONS = [10, 25, 50] as const;

export function getSelectedRows<TData>(
  data: TData[],
  rowSelection: RowSelectionState,
): TData[] {
  return Object.keys(rowSelection)
    .filter((key) => rowSelection[key])
    .map((key) => data[Number(key)])
    .filter(Boolean);
}

export function getSelectedRowCount(rowSelection: RowSelectionState): number {
  return Object.keys(rowSelection).filter((key) => rowSelection[key]).length;
}

export function getColumnVisibilityLabel<TData>(
  column: Column<TData, unknown>,
): string {
  return typeof column.columnDef.header === "string"
    ? column.columnDef.header
    : column.id.replace(/_/g, " ");
}
