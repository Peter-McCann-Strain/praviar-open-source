import {
  FileChartColumn,
  FileCode,
  FileSpreadsheet,
  FileText,
} from "lucide-react";

export const FORMAT_OPTIONS = [
  {
    value: "pdf" as const,
    label: "PDF Report",
    icon: FileText,
    description: "Human-readable report with charts, tables, and annotations.",
  },
  {
    value: "docx" as const,
    label: "Word Review Memo",
    icon: FileText,
    description: "Editable counsel work product with citations and caveats.",
  },
  {
    value: "pptx" as const,
    label: "Board Deck",
    icon: FileChartColumn,
    description:
      "Presentation-ready decision brief for board and investor review.",
  },
  {
    value: "csv" as const,
    label: "CSV Data",
    icon: FileSpreadsheet,
    description: "Flat evidence tables for review queues and BI tools.",
  },
  {
    value: "xlsx" as const,
    label: "Excel Spreadsheet",
    icon: FileSpreadsheet,
    description: "Structured data with claim charts, metrics, and mappings.",
  },
  {
    value: "json" as const,
    label: "JSON Data",
    icon: FileCode,
    description: "Machine-readable data for integration and downstream use.",
  },
];

export const SECTION_OPTIONS = [
  {
    id: "executive_summary",
    label: "Executive Summary",
    description: "Risk verdict, key findings, and next actions.",
    defaultOn: true,
  },
  {
    id: "patent_analysis",
    label: "Patent Analysis",
    description: "Material records, source links, and risk rationale.",
    defaultOn: true,
  },
  {
    id: "claim_charts",
    label: "Claim Charts",
    description: "Element mapping and cited evidence.",
    defaultOn: true,
  },
  {
    id: "invalidity_assessment",
    label: "Invalidity Assessment",
    description: "Prior-art posture and validity cues.",
    defaultOn: true,
  },
  {
    id: "audit_trail",
    label: "Audit Trail",
    description: "Reviewer decisions, reliance gates, and provenance trail.",
    defaultOn: true,
  },
  {
    id: "pipeline_metadata",
    label: "Pipeline Metadata",
    description: "Run diagnostics, model context, and configuration metadata.",
    defaultOn: true,
  },
] as const;

export type ExportFormat = (typeof FORMAT_OPTIONS)[number]["value"];
export type ExportSection = (typeof SECTION_OPTIONS)[number]["id"];

export function getExportFormatLabel(format: ExportFormat): string {
  return (
    FORMAT_OPTIONS.find((option) => option.value === format)?.label ?? format
  );
}

export const REQUIRED_EXPORT_SECTION_IDS: readonly ExportSection[] = [
  "audit_trail",
  "pipeline_metadata",
];

export function isRequiredExportSection(sectionId: ExportSection): boolean {
  return REQUIRED_EXPORT_SECTION_IDS.includes(sectionId);
}

export function hasRequiredExportSections(
  selectedSections: Set<ExportSection>,
): boolean {
  return REQUIRED_EXPORT_SECTION_IDS.every((sectionId) =>
    selectedSections.has(sectionId),
  );
}

export function hasExportContentSection(
  selectedSections: Set<ExportSection>,
): boolean {
  return Array.from(selectedSections).some(
    (sectionId) => !isRequiredExportSection(sectionId),
  );
}

export const AUDIENCE_OPTIONS = [
  { value: "full", label: "Full Report" },
  { value: "executive", label: "Executive Brief" },
  { value: "attorney", label: "Patent Counsel" },
  { value: "scientist", label: "R&D Brief" },
  { value: "investor", label: "Investor Pack" },
] as const;

export type ExportAudience = (typeof AUDIENCE_OPTIONS)[number]["value"];

export const AUDIENCE_PACKET_REQUIREMENTS: Record<
  ExportAudience,
  {
    defaultSections: readonly ExportSection[];
    requiredSections: readonly ExportSection[];
    summary: string;
  }
> = {
  full: {
    defaultSections: SECTION_OPTIONS.map((section) => section.id),
    requiredSections: [],
    summary:
      "Complete packet for teams that want the full report surface and source trail.",
  },
  executive: {
    defaultSections: ["executive_summary", "patent_analysis"],
    requiredSections: ["executive_summary"],
    summary:
      "Executive review packet keeps the risk verdict, material patents, and next actions intact.",
  },
  attorney: {
    defaultSections: [
      "patent_analysis",
      "claim_charts",
      "invalidity_assessment",
    ],
    requiredSections: ["patent_analysis", "claim_charts"],
    summary:
      "Counsel packet keeps material patents, claim charts, and validity posture with mandatory provenance.",
  },
  scientist: {
    defaultSections: ["patent_analysis", "claim_charts"],
    requiredSections: ["patent_analysis", "claim_charts"],
    summary:
      "R&D packet keeps technical evidence and element mappings available.",
  },
  investor: {
    defaultSections: ["executive_summary", "patent_analysis"],
    requiredSections: ["executive_summary", "patent_analysis"],
    summary:
      "Investor packet keeps the decision summary, material patents, and audit trail.",
  },
};

export function getExportSectionLabel(sectionId: ExportSection): string {
  return (
    SECTION_OPTIONS.find((section) => section.id === sectionId)?.label ??
    sectionId
  );
}

export function getAudienceRequiredSections(
  audience: ExportAudience,
): readonly ExportSection[] {
  return AUDIENCE_PACKET_REQUIREMENTS[audience].requiredSections;
}

export function getAudienceDefaultSections(
  audience: ExportAudience,
): Set<ExportSection> {
  return new Set([
    ...AUDIENCE_PACKET_REQUIREMENTS[audience].defaultSections,
    ...AUDIENCE_PACKET_REQUIREMENTS[audience].requiredSections,
    ...REQUIRED_EXPORT_SECTION_IDS,
  ]);
}

export function isSectionRequiredForAudience(
  sectionId: ExportSection,
  audience: ExportAudience,
): boolean {
  return getAudienceRequiredSections(audience).includes(sectionId);
}

export function getMissingAudienceRequiredSections(
  audience: ExportAudience,
  selectedSections: Set<ExportSection>,
): ExportSection[] {
  return getAudienceRequiredSections(audience).filter(
    (sectionId) => !selectedSections.has(sectionId),
  );
}

export function getAudienceLabel(audience: ExportAudience) {
  return (
    AUDIENCE_OPTIONS.find((option) => option.value === audience)?.label ??
    "Full Report"
  );
}

export function getExportArtifactLabel(
  audience: ExportAudience,
  format: ExportFormat,
) {
  return `${getAudienceLabel(audience)} · ${getExportFormatLabel(format)}`;
}

export function getAudienceDescription(audience: ExportAudience) {
  switch (audience) {
    case "executive":
      return "2-page summary with risk verdict, key patents, and recommended actions.";
    case "attorney":
      return "Review packet with claim charts, prosecution-history notes, and invalidity screening cues for counsel.";
    case "scientist":
      return "Technical brief with compound details, design-around strategies, and element analysis.";
    case "investor":
      return "Risk overview with patent count, estimated exposure, and portfolio impact.";
    default:
      return "Complete report with all sections.";
  }
}
