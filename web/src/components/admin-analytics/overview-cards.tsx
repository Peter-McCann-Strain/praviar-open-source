import { Activity, DollarSign, TrendingUp, Zap } from "lucide-react";
import type {
  CostBreakdownResponse,
  ModelUsageResponse,
  UsageAnalyticsResponse,
} from "@/hooks/use-admin-analytics";
import { Card, CardContent } from "@/components/ui/card";
import {
  formatCurrency,
  formatPercentLike,
} from "@/components/admin-analytics/helpers";

interface OverviewCardsProps {
  isLoading: boolean;
  costData: CostBreakdownResponse | undefined;
  usageData: UsageAnalyticsResponse | undefined;
  modelData: ModelUsageResponse | undefined;
}

export function OverviewCards({
  isLoading,
  costData,
  usageData,
  modelData,
}: OverviewCardsProps) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardContent className="p-5">
          <div className="flex items-center gap-3.5">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-primary/10">
              <DollarSign className="h-5 w-5 text-brand-primary" />
            </div>
            <div>
              <p className="text-xs text-[var(--text-secondary)]">LLM Spend</p>
              <p className="type-heading-xl text-[var(--text-primary)] tabular-nums">
                {isLoading
                  ? "--"
                  : costData
                    ? formatCurrency(costData.total_cost_usd)
                    : "Unavailable"}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-5">
          <div className="flex items-center gap-3.5">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-success/10">
              <Activity className="h-5 w-5 text-success" />
            </div>
            <div>
              <p className="text-xs text-[var(--text-secondary)]">
                Analyses Run
              </p>
              <p className="type-heading-xl text-[var(--text-primary)] tabular-nums">
                {isLoading
                  ? "--"
                  : usageData
                    ? usageData.total_analyses
                    : "Unavailable"}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-5">
          <div className="flex items-center gap-3.5">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-info/10">
              <TrendingUp className="h-5 w-5 text-info" />
            </div>
            <div>
              <p className="text-xs text-[var(--text-secondary)]">
                Avg LLM Cost / Analysis
              </p>
              <p className="type-heading-xl text-[var(--text-primary)] tabular-nums">
                {isLoading
                  ? "--"
                  : usageData
                    ? formatCurrency(usageData.avg_cost_per_analysis)
                    : "Unavailable"}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-5">
          <div className="flex items-center gap-3.5">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-info/10">
              <Zap className="h-5 w-5 text-info" />
            </div>
            <div>
              <p className="text-xs text-[var(--text-secondary)]">
                Cache Hit Rate
              </p>
              <p className="type-heading-xl text-[var(--text-primary)] tabular-nums">
                {isLoading
                  ? "--"
                  : modelData?.overall_cache_hit_rate != null
                    ? formatPercentLike(modelData.overall_cache_hit_rate)
                    : "N/A"}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
