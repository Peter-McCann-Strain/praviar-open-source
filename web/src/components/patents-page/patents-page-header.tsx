import { AppSurfaceHeader } from "@/components/shared/app-surface-header";
import type { PatentItem } from "@/hooks/use-patents";
import { getPatentExpirySignal, normalizeRiskLevel } from "./helpers";

interface PatentsPageHeaderProps {
  isUpdating?: boolean;
  patents?: PatentItem[];
  total?: number;
  canViewRisk?: boolean;
}

export function PatentsPageHeader({
  isUpdating = false,
  patents = [],
  total = 0,
  canViewRisk = false,
}: PatentsPageHeaderProps) {
  const visibleHighRisk = canViewRisk
    ? patents.filter(
        (patent) => normalizeRiskLevel(patent.risk_level) === "high",
      ).length
    : 0;
  const termAttention = patents.filter((patent) => {
    const tone = getPatentExpirySignal(patent.expiry_date).tone;
    return tone === "soon" || tone === "expired";
  }).length;
  const cpcIndexed = patents.filter((patent) =>
    patent.cpc_codes.some(Boolean),
  ).length;
  const metrics: Array<{
    detail: string;
    label: string;
    tone?: "default" | "warning";
    value: string;
  }> = [
    {
      detail: "Server-filtered evidence index",
      label: "Library matches",
      value: total.toLocaleString(),
    },
    {
      detail: isUpdating ? "Refreshing current page" : "Rendered evidence rows",
      label: "Visible page",
      value: patents.length.toLocaleString(),
    },
    canViewRisk
      ? {
          detail: "Visible blocking-risk records",
          label: "Page high risk",
          tone: visibleHighRisk > 0 ? "warning" : "default",
          value: visibleHighRisk.toLocaleString(),
        }
      : {
          detail: "Visible records with classification codes",
          label: "CPC indexed",
          value: cpcIndexed.toLocaleString(),
        },
    {
      detail: "Expired or expiring within 2 years",
      label: "Term attention",
      tone: termAttention > 0 ? "warning" : "default",
      value: termAttention.toLocaleString(),
    },
  ];

  return (
    <AppSurfaceHeader
      eyebrow="Praviar evidence library"
      title="Patent Evidence Library"
      description={
        canViewRisk
          ? "Browse verified patent evidence published from your FTO reports, with risk, expiry, and report handoff context kept attached to every record."
          : "Browse verified patent evidence published from your FTO reports, with classification, expiry, and governed report handoff context attached to every record."
      }
      dataTestId="patents-app-surface-header"
      metrics={metrics}
    />
  );
}
