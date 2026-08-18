"use client";

import { useState, useCallback } from "react";
import { Download } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { DataTable, getSelectedRows } from "@/components/ui/data-table";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useAuthBoundaryReset } from "@/hooks/use-auth-boundary-reset";
import { usePatentColumns } from "./patent-data-table-columns";
import { exportPatentsToCSV } from "./patent-data-table-export";

/* ── Types ──────────────────────────────────────────────────────────── */

export type RiskLevel = "high" | "medium" | "low" | "clear";

export interface PatentRow {
  patentNumber: string;
  title: string;
  assignee: string;
  filingDate: string;
  riskLevel: RiskLevel;
  jurisdiction: string;
  /** Explicit search relevance supplied by report provenance; null means unreported. */
  relevanceScore: number | null;
}

interface PatentDataTableProps {
  patents: PatentRow[];
  loading?: boolean;
  onPatentClick?: (patentNumber: string) => void;
  className?: string;
}

export function PatentDataTable({
  patents,
  loading = false,
  onPatentClick,
  className,
}: PatentDataTableProps) {
  const columns = usePatentColumns(onPatentClick);
  const [selectedRows, setSelectedRows] = useState<PatentRow[]>([]);
  const [authBoundaryResetKey, setAuthBoundaryResetKey] = useState(0);

  const resetPrivateTableState = useCallback(() => {
    setSelectedRows([]);
    setAuthBoundaryResetKey((current) => current + 1);
  }, []);
  useAuthBoundaryReset(resetPrivateTableState);

  const handleExport = useCallback(() => {
    const toExport = selectedRows.length > 0 ? selectedRows : patents;
    exportPatentsToCSV(toExport);
  }, [selectedRows, patents]);

  return (
    <TooltipProvider delayDuration={300}>
      <div className={cn("space-y-3", className)}>
        {/* Export button */}
        {patents.length > 0 && (
          <div className="flex items-center justify-end">
            <Button
              variant="outline"
              size="sm"
              onClick={handleExport}
              className="min-h-11 gap-1.5 text-xs"
            >
              <Download className="h-3.5 w-3.5" />
              {selectedRows.length > 0
                ? `Export ${selectedRows.length} selected`
                : "Export all"}
            </Button>
          </div>
        )}

        <DataTable
          key={authBoundaryResetKey}
          columns={columns}
          data={patents}
          loading={loading}
          skeletonRows={8}
          enableRowSelection
          enableSearch
          searchPlaceholder="Search patents by number, title, or assignee..."
          enableColumnVisibility
          enablePagination
          defaultPageSize={10}
          emptyMessage="No patents found"
          emptyDescription="No patent analysis results match the current filters."
          onRowSelectionChange={setSelectedRows}
        />
      </div>
    </TooltipProvider>
  );
}

export { getSelectedRows };
