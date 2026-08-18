import {
  isRequiredExportSection,
  SECTION_OPTIONS,
  type ExportSection,
} from "@/components/collaboration/export-dialog-constants";

export function getDefaultExportSections(): Set<ExportSection> {
  return new Set(
    SECTION_OPTIONS.filter((section) => section.defaultOn).map(
      (section) => section.id,
    ),
  );
}

export function toggleExportSection(
  currentSections: Set<ExportSection>,
  sectionId: ExportSection,
): Set<ExportSection> {
  const nextSections = new Set(currentSections);

  if (isRequiredExportSection(sectionId)) {
    nextSections.add(sectionId);
    return nextSections;
  }

  if (nextSections.has(sectionId)) {
    nextSections.delete(sectionId);
  } else {
    nextSections.add(sectionId);
  }

  return nextSections;
}
