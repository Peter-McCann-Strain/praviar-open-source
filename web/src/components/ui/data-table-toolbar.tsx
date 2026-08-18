"use client";

import { type KeyboardEvent, useId, useRef, useState } from "react";
import type {
  RowSelectionState,
  Table as TanStackTable,
} from "@tanstack/react-table";
import { Check, Columns3, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  getColumnVisibilityLabel,
  getSelectedRowCount,
} from "./data-table-utils";

interface DataTableToolbarProps<TData> {
  enableColumnVisibility: boolean;
  enableRowSelection: boolean;
  enableSearch: boolean;
  globalFilter: string;
  rowSelection: RowSelectionState;
  searchPlaceholder: string;
  setGlobalFilter: (value: string) => void;
  table: TanStackTable<TData>;
}

function ColumnVisibilityDropdown<TData>({
  table,
}: {
  table: TanStackTable<TData>;
}) {
  const menuId = useId();
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  function getMenuItems() {
    return Array.from(
      menuRef.current?.querySelectorAll<HTMLButtonElement>(
        '[role="menuitemcheckbox"]',
      ) ?? [],
    );
  }

  function closeMenu({ restoreFocus = true } = {}) {
    setOpen(false);
    if (restoreFocus) {
      requestAnimationFrame(() => triggerRef.current?.focus());
    }
  }

  function openMenu() {
    setOpen(true);
    requestAnimationFrame(() => getMenuItems()[0]?.focus());
  }

  function handleMenuKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const items = getMenuItems();
    const currentIndex = items.indexOf(
      document.activeElement as HTMLButtonElement,
    );

    if (event.key === "Escape") {
      event.preventDefault();
      closeMenu();
      return;
    }

    if (!items.length) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      items[(currentIndex + 1 + items.length) % items.length]?.focus();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      items[(currentIndex - 1 + items.length) % items.length]?.focus();
    } else if (event.key === "Home") {
      event.preventDefault();
      items[0]?.focus();
    } else if (event.key === "End") {
      event.preventDefault();
      items[items.length - 1]?.focus();
    }
  }

  return (
    <div
      className="relative"
      onKeyDown={(e) => {
        if (e.key === "Escape") closeMenu();
      }}
    >
      <Button
        ref={triggerRef}
        variant="outline"
        size="sm"
        onClick={() => (open ? closeMenu({ restoreFocus: false }) : openMenu())}
        aria-controls={open ? menuId : undefined}
        aria-haspopup="menu"
        aria-expanded={open}
        className="min-h-11 gap-1.5 text-xs"
      >
        <Columns3 className="h-3.5 w-3.5" />
        Columns
      </Button>
      {open && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => closeMenu({ restoreFocus: false })}
          />
          <div
            ref={menuRef}
            id={menuId}
            role="menu"
            aria-label="Toggle table columns"
            className="praviar-dialog-panel absolute right-0 top-full z-50 mt-1 min-w-[180px] rounded-lg p-1.5"
            onBlur={(event) => {
              const next = event.relatedTarget as Node | null;
              if (
                next &&
                (menuRef.current?.contains(next) ||
                  triggerRef.current?.contains(next))
              ) {
                return;
              }
              closeMenu({ restoreFocus: false });
            }}
            onKeyDown={handleMenuKeyDown}
          >
            {table
              .getAllColumns()
              .filter((column) => column.getCanHide())
              .map((column) => (
                <button
                  key={column.id}
                  type="button"
                  role="menuitemcheckbox"
                  aria-checked={column.getIsVisible()}
                  onClick={() =>
                    column.toggleVisibility(!column.getIsVisible())
                  }
                  className="flex min-h-11 w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)] focus-visible:bg-brand-primary/10 focus-visible:text-brand-primary focus-visible:outline-none"
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      "flex h-4 w-4 items-center justify-center rounded border transition-colors",
                      column.getIsVisible()
                        ? "border-brand-primary bg-brand-primary text-[var(--brand-paper)]"
                        : "border-[var(--border-emphasis)] bg-transparent",
                    )}
                  >
                    {column.getIsVisible() && (
                      <Check className="h-3 w-3" aria-hidden="true" />
                    )}
                  </span>
                  <span className="capitalize">
                    {getColumnVisibilityLabel(column)}
                  </span>
                </button>
              ))}
          </div>
        </>
      )}
    </div>
  );
}

export function DataTableToolbar<TData>({
  enableColumnVisibility,
  enableRowSelection,
  enableSearch,
  globalFilter,
  rowSelection,
  searchPlaceholder,
  setGlobalFilter,
  table,
}: DataTableToolbarProps<TData>) {
  const selectedRowCount = getSelectedRowCount(rowSelection);

  if (!enableSearch && !enableColumnVisibility) {
    return null;
  }

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      {enableSearch && (
        <div className="relative w-full min-w-0 sm:max-w-sm sm:flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-disabled)]" />
          <input
            type="text"
            value={globalFilter}
            onChange={(event) => setGlobalFilter(event.target.value)}
            placeholder={searchPlaceholder}
            aria-label={searchPlaceholder ?? "Search table"}
            className="praviar-glass-field flex min-h-11 w-full rounded-lg py-2 pl-9 pr-3 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-disabled)] transition-colors focus:border-brand-primary/60 focus:outline-none focus:ring-2 focus:ring-brand-primary/70 focus:ring-offset-2 focus:ring-offset-[var(--bg-base)]"
          />
        </div>
      )}
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        {enableRowSelection && selectedRowCount > 0 && (
          <span className="text-xs text-[var(--text-secondary)]">
            {selectedRowCount} selected
          </span>
        )}
        {enableColumnVisibility && <ColumnVisibilityDropdown table={table} />}
      </div>
    </div>
  );
}
