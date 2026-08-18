import { AppSurfaceHeader } from "@/components/shared/app-surface-header";
import type { CompoundItem } from "@/hooks/use-compounds";

interface CompoundsPageHeaderProps {
  compounds?: CompoundItem[];
  isUpdating?: boolean;
  selectedCompoundName?: string | null;
  total?: number;
}

type CompoundHeaderMetricTone = "default" | "active";

export function CompoundsPageHeader({
  compounds = [],
  isUpdating = false,
  selectedCompoundName = null,
  total = 0,
}: CompoundsPageHeaderProps) {
  const repeatDossiers = compounds.filter(
    (compound) => compound.analysis_count > 1,
  ).length;
  const detailFocus =
    selectedCompoundName ?? (isUpdating ? "Updating" : "None");
  const metrics: Array<{
    detail: string;
    label: string;
    tone?: CompoundHeaderMetricTone;
    value: string;
  }> = [
    {
      detail: "Server-filtered compound index",
      label: "Library matches",
      value: total.toLocaleString(),
    },
    {
      detail: isUpdating ? "Refreshing current page" : "Rendered dossiers",
      label: "Visible page",
      value: compounds.length.toLocaleString(),
    },
    {
      detail: "Compounds with repeat FTO runs",
      label: "Repeat dossiers",
      value: repeatDossiers.toLocaleString(),
    },
    {
      detail: selectedCompoundName
        ? "Detail rail selected"
        : "Select a row for identity detail",
      label: "Detail focus",
      tone: selectedCompoundName ? "active" : "default",
      value: detailFocus,
    },
  ];

  return (
    <AppSurfaceHeader
      eyebrow="Praviar compound intelligence"
      title="Compound Library"
      description="All compounds analyzed by your organization, normalized into reusable chemistry dossiers with identity, evidence, and enrichment status kept visible."
      dataTestId="compounds-app-surface-header"
      metrics={metrics}
    />
  );
}
