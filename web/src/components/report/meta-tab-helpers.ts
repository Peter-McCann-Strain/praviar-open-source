import type { FTOReport } from "@praviar/shared-types";

export interface MetaTimingDatum {
  step: string;
  duration_seconds: number;
}

export interface MetaUsageDatum {
  step: string;
  input_tokens: number;
  output_tokens: number;
}

export interface MetaVerificationFlag {
  label: string;
  passed: boolean;
}

export function limitationBadgeVariant(category: string) {
  switch (category) {
    case "source_unavailable":
      return "destructive" as const;
    case "enrichment_gap":
      return "warning" as const;
    default:
      return "secondary" as const;
  }
}

export function limitationCategoryLabel(category: string): string {
  switch (category) {
    case "source_unavailable":
      return "Source Unavailable";
    case "enrichment_gap":
      return "Enrichment Gap";
    default:
      return category.replace(/_/g, " ");
  }
}

export function getMetaTimingData(report: FTOReport): MetaTimingDatum[] {
  return (report.audit_trail?.timing_data ?? []).map((timing) => ({
    step: timing.step_name,
    duration_seconds: timing.duration_seconds,
  }));
}

export function getMetaUsageData(report: FTOReport): MetaUsageDatum[] {
  return (report.step_token_usage ?? []).map((stepUsage) => ({
    step: stepUsage.step_name,
    input_tokens: stepUsage.input_tokens,
    output_tokens: stepUsage.output_tokens,
  }));
}

export function getMetaVerificationFlags(
  report: FTOReport,
): MetaVerificationFlag[] {
  const verification = report.verification;
  return [
    {
      label: "All Citations Valid",
      passed: verification?.all_citations_valid ?? false,
    },
    {
      label: "All Claims Grounded",
      passed: verification?.all_claims_grounded ?? false,
    },
    {
      label: "All Entities Valid",
      passed: verification?.all_entities_valid ?? false,
    },
    {
      label: "Dates Consistent",
      passed: verification?.dates_consistent ?? false,
    },
    {
      label: "Risk Levels Justified",
      passed: verification?.risk_levels_justified ?? false,
    },
  ];
}
