import { getLaunchReadyJurisdictions } from "@/lib/jurisdiction-bundles";
import type { ConfigState } from "@/stores/config-store";

export type ConfigStore = ConfigState;

export const EFFORT_LEVELS = ["high", "medium", "low"] as const;

export const CONFIG_FIELD_CLASS =
  "h-11 rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-muted)] px-3 text-sm text-[var(--text-secondary)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]";

export const CONFIG_COMPACT_SELECT_CLASS = `${CONFIG_FIELD_CLASS} w-28 text-right`;

export const CONFIG_FORM_ROW_CLASS =
  "grid min-w-0 gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center";

export const CONFIG_SWITCH_LABEL_CLASS =
  "relative inline-flex min-h-11 min-w-11 shrink-0 cursor-pointer items-center justify-center";

export const PRESET_CARDS = [
  {
    key: "quick" as const,
    label: "Focused coverage",
    desc: "Narrower source breadth for early triage",
    border: "border-success bg-success/10",
    resultCount: 50,
  },
  {
    key: "standard" as const,
    label: "Balanced coverage",
    desc: "Default breadth for human-reviewed screening",
    border: "border-brand-primary bg-brand-primary/10",
    resultCount: 200,
  },
  {
    key: "thorough" as const,
    label: "Expanded coverage",
    desc: "Wider source breadth for complex landscapes",
    border: "border-info bg-info/10",
    resultCount: 500,
  },
] as const;

export function getCoverageBudgetLabel(resultCount: number): string {
  if (resultCount <= 50) {
    return "Focused coverage";
  }

  if (resultCount === 200) {
    return "Balanced coverage";
  }

  if (resultCount >= 500) {
    return "Expanded coverage";
  }

  return "Custom coverage";
}

export function getCoverageBudgetDetail(resultCount: number): string {
  return `${resultCount.toLocaleString()} ranked result${resultCount === 1 ? "" : "s"} passed through scoring`;
}

export function getCoverageBudgetImpact(resultCount: number): string {
  if (resultCount <= 50) {
    return "Fastest triage profile with narrower source breadth";
  }

  if (resultCount >= 500) {
    return "Widest default profile for complex patent landscapes";
  }

  if (resultCount === 200) {
    return "Default balance of breadth and review limits";
  }

  return "Custom result budget; confirm review capacity before saving";
}

export const PATENT_SOURCES = [
  {
    key: "enablePubchem" as const,
    label: "PubChem SDQ",
    desc: "Compound-patent cross-references",
  },
  {
    key: "enableBigquery" as const,
    label: "BigQuery Patents",
    desc: "Google full-text patent search",
  },
  {
    key: "enableSurechembl" as const,
    label: "SureChEMBL",
    desc: "Configured chemical-patent index",
  },
  {
    key: "enablePatcid" as const,
    label: "PatCID",
    desc: "Chemical structure search",
  },
] as const;

export const HITL_CHECKPOINTS = [
  { id: "search_review", label: "After Search" },
  { id: "triage_review", label: "After Triage" },
  { id: "analysis_review", label: "After Analysis" },
  { id: "report_review", label: "Before Report" },
] as const;

export function getEnabledSources(config: ConfigStore): string[] {
  return [
    config.enablePubchem && "PubChem",
    config.enableBigquery && "BigQuery",
    config.enableSurechembl && "SureChEMBL",
    config.enablePatcid && "PatCID",
  ].filter(Boolean) as string[];
}

export function getConfigValidationIssues(config: ConfigStore): string[] {
  const issues: string[] = [];

  if (getEnabledSources(config).length === 0) {
    issues.push("Enable at least one patent source.");
  }

  if (config.searchJurisdictions.length === 0) {
    issues.push("Select at least one search jurisdiction.");
  }

  if (getLaunchReadyJurisdictions(config.targetJurisdictions).length === 0) {
    issues.push(
      "Select at least one launch-ready jurisdiction: US, EP, IN, JP, or CN.",
    );
  }

  if (config.hitlEnabled && config.hitlCheckpoints.length === 0) {
    issues.push("Select at least one HITL checkpoint or turn HITL off.");
  }

  return issues;
}
