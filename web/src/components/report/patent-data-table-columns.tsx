"use client";

import { useMemo } from "react";
import { type ColumnDef } from "@tanstack/react-table";
import { cn, formatDate } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { PatentRow, RiskLevel } from "./patent-data-table";

const RISK_BADGE_STYLES: Record<RiskLevel, string> = {
  high: "bg-error/15 text-error border-error/30",
  medium: "bg-warning/15 text-warning border-warning/30",
  low: "bg-success/15 text-success border-success/30",
  clear: "bg-info/15 text-info border-info/30",
};

function RiskLevelBadge({ level }: { level: RiskLevel }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold uppercase tracking-wider",
        RISK_BADGE_STYLES[level],
      )}
    >
      {level}
    </span>
  );
}

function RelevanceBar({ score }: { score: number | null }) {
  if (score == null || !Number.isFinite(score)) {
    return (
      <span className="text-xs text-[var(--text-tertiary)]">Not reported</span>
    );
  }

  const percentage = Math.min(Math.max(score, 0), 100);
  const color =
    percentage >= 80
      ? "bg-error"
      : percentage >= 60
        ? "bg-warning"
        : percentage >= 40
          ? "bg-brand-primary"
          : "bg-success";

  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 rounded-full bg-[var(--surface-active)] overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", color)}
          style={{ width: `${percentage}%` }}
        />
      </div>
      <span className="text-xs tabular-nums text-[var(--text-secondary)]">
        {percentage}%
      </span>
    </div>
  );
}

function TruncatedCell({
  value,
  maxLength = 28,
}: {
  value: string;
  maxLength?: number;
}) {
  if (value.length <= maxLength) {
    return (
      <span className="text-sm text-[var(--text-secondary)]">{value}</span>
    );
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          aria-label={value}
          title={value}
          className="cursor-default rounded-sm text-sm text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
        >
          {value.slice(0, maxLength)}...
        </span>
      </TooltipTrigger>
      <TooltipContent>
        <p className="max-w-xs">{value}</p>
      </TooltipContent>
    </Tooltip>
  );
}

function CheckboxCell({
  checked,
  indeterminate,
  onChange,
  ariaLabel,
}: {
  checked: boolean;
  indeterminate?: boolean;
  onChange: (checked: boolean) => void;
  ariaLabel: string;
}) {
  return (
    <label className="flex min-h-11 min-w-11 cursor-pointer items-center justify-center rounded-md transition-colors hover:bg-[var(--surface-hover)]">
      <input
        type="checkbox"
        checked={checked}
        ref={(element) => {
          if (element) {
            element.indeterminate = indeterminate ?? false;
          }
        }}
        onChange={(event) => onChange(event.target.checked)}
        aria-label={ariaLabel}
        className="h-5 w-5 cursor-pointer rounded border-[var(--border-emphasis)] bg-[var(--surface-muted)] text-brand-primary accent-[var(--brand-primary)] focus:ring-2 focus:ring-brand-primary/70 focus:ring-offset-0"
      />
    </label>
  );
}

export function usePatentColumns(
  onPatentClick?: (patentNumber: string) => void,
): ColumnDef<PatentRow, unknown>[] {
  return useMemo(
    (): ColumnDef<PatentRow, unknown>[] => [
      {
        id: "select",
        size: 40,
        enableSorting: false,
        enableHiding: false,
        header: ({ table }) => (
          <CheckboxCell
            checked={table.getIsAllPageRowsSelected()}
            indeterminate={table.getIsSomePageRowsSelected()}
            onChange={(checked) => table.toggleAllPageRowsSelected(checked)}
            ariaLabel="Select all rows"
          />
        ),
        cell: ({ row }) => (
          <CheckboxCell
            checked={row.getIsSelected()}
            onChange={(checked) => row.toggleSelected(checked)}
            ariaLabel={`Select patent ${row.original.patentNumber}`}
          />
        ),
      },
      {
        accessorKey: "patentNumber",
        header: "Patent Number",
        size: 160,
        cell: ({ row }) => {
          const value = row.original.patentNumber;
          return (
            <button
              onClick={(event) => {
                event.stopPropagation();
                onPatentClick?.(value);
              }}
              className="inline-flex min-h-11 items-center rounded-md px-2 text-left font-mono text-sm text-brand-primary transition-colors hover:bg-brand-primary/10 hover:text-brand-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
            >
              {value}
            </button>
          );
        },
      },
      {
        accessorKey: "title",
        header: "Title",
        size: 260,
        cell: ({ row }) => (
          <TruncatedCell value={row.original.title} maxLength={40} />
        ),
      },
      {
        accessorKey: "assignee",
        header: "Assignee",
        size: 180,
        cell: ({ row }) => (
          <TruncatedCell value={row.original.assignee} maxLength={28} />
        ),
      },
      {
        accessorKey: "filingDate",
        header: "Filing Date",
        size: 120,
        cell: ({ row }) => (
          <span className="text-sm tabular-nums text-[var(--text-secondary)]">
            {row.original.filingDate
              ? formatDate(row.original.filingDate)
              : "\u2014"}
          </span>
        ),
        sortingFn: (first, second) => {
          const firstDate = new Date(first.original.filingDate).getTime();
          const secondDate = new Date(second.original.filingDate).getTime();
          return firstDate - secondDate;
        },
      },
      {
        accessorKey: "riskLevel",
        header: "Risk Level",
        size: 110,
        cell: ({ row }) => <RiskLevelBadge level={row.original.riskLevel} />,
        sortingFn: (first, second) => {
          const order: Record<RiskLevel, number> = {
            high: 0,
            medium: 1,
            low: 2,
            clear: 3,
          };
          return (
            (order[first.original.riskLevel] ?? 4) -
            (order[second.original.riskLevel] ?? 4)
          );
        },
      },
      {
        accessorKey: "jurisdiction",
        header: "Jurisdiction",
        size: 110,
        cell: ({ row }) => (
          <span className="inline-flex items-center rounded-md bg-[var(--surface-active)] px-2 py-0.5 text-xs font-medium text-[var(--text-secondary)]">
            {row.original.jurisdiction}
          </span>
        ),
      },
      {
        accessorKey: "relevanceScore",
        header: "Reported relevance",
        size: 130,
        cell: ({ row }) => <RelevanceBar score={row.original.relevanceScore} />,
        sortUndefined: "last",
      },
    ],
    [onPatentClick],
  );
}
