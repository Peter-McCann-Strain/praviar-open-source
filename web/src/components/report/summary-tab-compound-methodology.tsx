"use client";

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SearchFunnel } from "@/components/charts/search-funnel";
import { CompoundProfileCard } from "@/components/report/summary-tab-compound-profile-card";
import { SourceHealthCard } from "@/components/report/summary-tab-source-health-card";
import { cn } from "@/lib/utils";
import type { FTOReport } from "@praviar/shared-types";

interface CompoundMethodologySectionProps {
  report: FTOReport;
  funnelData: Array<{ stage: string; count: number }>;
  defaultOpen?: boolean;
  variant?: "default" | "rail";
}

export function CompoundMethodologySection({
  report,
  funnelData,
  defaultOpen = false,
  variant = "default",
}: CompoundMethodologySectionProps) {
  const rail = variant === "rail";
  const [open, setOpen] = useState(defaultOpen);

  const methodologyDetails = (
    <>
      <SourceHealthCard report={report} variant={rail ? "rail" : "default"} />
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Patent Search Funnel</CardTitle>
        </CardHeader>
        <CardContent>
          <SearchFunnel data={funnelData} height={260} />
        </CardContent>
      </Card>
    </>
  );

  return (
    <div className={cn(rail && "space-y-4")}>
      {rail ? <CompoundProfileCard report={report} /> : null}
      <details
        open={open}
        onToggle={(event) => {
          setOpen(event.currentTarget.open);
        }}
        className={cn(
          "group",
          rail &&
            "praviar-summary-rail-section rounded-lg border border-[var(--card-border)]",
        )}
      >
        <summary
          className={cn(
            "flex min-h-11 cursor-pointer list-none items-center gap-2 text-sm font-semibold text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)] [&::-webkit-details-marker]:hidden",
            rail ? "px-4 py-3" : "py-2",
          )}
        >
          <ChevronRight
            className="h-4 w-4 flex-shrink-0 transition-transform group-open:rotate-90"
            aria-hidden="true"
          />
          <span>
            {rail
              ? "Search Methodology & Source Health"
              : "Compound Details & Search Methodology"}
          </span>
        </summary>

        <div className={cn("space-y-4", rail ? "px-4 pb-4" : "mt-4")}>
          {rail ? (
            methodologyDetails
          ) : (
            <>
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <CompoundProfileCard report={report} />
                <SourceHealthCard report={report} variant="default" />
              </div>
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">
                    Patent Search Funnel
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <SearchFunnel data={funnelData} height={260} />
                </CardContent>
              </Card>
            </>
          )}
        </div>
      </details>
    </div>
  );
}
