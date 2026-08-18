import type {
  LegalEvent,
  PatentAnalysis,
  PatentFamily,
  PatentFamilyMember,
  PatentHit,
  PatentTermInfo,
} from "@praviar/shared-types";

type UnknownRecord = Record<string, unknown>;

function record(value: unknown): UnknownRecord | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as UnknownRecord)
    : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function nullableString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function normalizeFamilyMember(value: unknown): PatentFamilyMember | null {
  const item = record(value);
  if (!item) return null;
  const country = stringValue(item.country);
  const docNumber = stringValue(item.doc_number);
  const kind = stringValue(item.kind);
  if (!country || !docNumber || !kind) return null;
  return { country, doc_number: docNumber, kind };
}

function normalizeFamily(value: unknown): PatentFamily | null {
  const item = record(value);
  const familyId = stringValue(item?.family_id);
  if (!item || !familyId) return null;
  return {
    family_id: familyId,
    members: Array.isArray(item.members)
      ? item.members
          .map(normalizeFamilyMember)
          .filter((member): member is PatentFamilyMember => member !== null)
      : [],
    jurisdictions: stringArray(item.jurisdictions),
    earliest_priority_date: nullableString(item.earliest_priority_date),
  };
}

function normalizeLegalEvent(value: unknown): LegalEvent | null {
  const item = record(value);
  if (!item) return null;
  const eventCode = stringValue(item.event_code);
  const eventDescription = stringValue(item.event_description);
  const country = stringValue(item.country);
  if (!eventCode || !eventDescription || !country) return null;
  return {
    event_date: nullableString(item.event_date),
    event_code: eventCode,
    event_description: eventDescription,
    country,
  };
}

function normalizePatentTermInfo(value: unknown): PatentTermInfo | null {
  const item = record(value);
  if (!item) return null;
  const patentId = stringValue(item.patent_id);
  const ptaDays = finiteNumber(item.pta_days);
  const pteDays = finiteNumber(item.pte_days);
  const calculationConfidence = finiteNumber(item.calculation_confidence);
  const maintenanceFeeStatus = stringValue(item.maintenance_fee_status);
  if (
    !patentId ||
    ptaDays === null ||
    pteDays === null ||
    calculationConfidence === null ||
    !["paid", "lapsed", "grace_period", "unknown"].includes(
      maintenanceFeeStatus ?? "",
    )
  ) {
    return null;
  }
  return {
    patent_id: patentId,
    effective_filing_date: nullableString(item.effective_filing_date),
    grant_date: nullableString(item.grant_date),
    base_expiry: nullableString(item.base_expiry),
    pta_days: ptaDays,
    pte_days: pteDays,
    terminal_disclaimer: item.terminal_disclaimer === true,
    td_linked_patent: nullableString(item.td_linked_patent) ?? "",
    td_linked_expiry: nullableString(item.td_linked_expiry),
    maintenance_fee_status:
      maintenanceFeeStatus as PatentTermInfo["maintenance_fee_status"],
    maintenance_fee_next_due: nullableString(item.maintenance_fee_next_due),
    adjusted_expiry: nullableString(item.adjusted_expiry),
    calculation_confidence: calculationConfidence,
    calculation_notes: stringArray(item.calculation_notes),
  };
}

/**
 * `patent_details` is an evidence envelope, not a guaranteed complete
 * PatentHit. Merge the analysis summary with whichever raw fields are present
 * before a drawer or claim consumer sees the record.
 */
export function normalizeReportPatentDetail({
  analysis,
  patentId,
  rawDetail,
}: {
  analysis: PatentAnalysis | null;
  patentId: string;
  rawDetail: unknown;
}): PatentHit {
  const detail = record(rawDetail) ?? {};
  const detailAssignees = stringArray(detail.assignees);
  const analysisAssignee = stringValue(analysis?.assignee);
  const legalEvents = Array.isArray(detail.legal_events)
    ? detail.legal_events
        .map(normalizeLegalEvent)
        .filter((event): event is LegalEvent => event !== null)
    : [];

  return {
    patent_id: stringValue(detail.patent_id) ?? patentId,
    title:
      stringValue(detail.title) ??
      stringValue(analysis?.title) ??
      "Title not reported",
    abstract: stringValue(detail.abstract) ?? "",
    claims_text: stringValue(detail.claims_text) ?? "",
    claims_text_source: stringValue(detail.claims_text_source) ?? undefined,
    sources: stringArray(detail.sources),
    confidence_score: finiteNumber(detail.confidence_score) ?? 0,
    filing_date: nullableString(detail.filing_date),
    priority_date: nullableString(detail.priority_date),
    expiry_date:
      nullableString(detail.expiry_date) ?? analysis?.expiry_date ?? null,
    assignees:
      detailAssignees.length > 0
        ? detailAssignees
        : analysisAssignee
          ? [analysisAssignee]
          : [],
    inventors: stringArray(detail.inventors),
    cpc_codes: stringArray(detail.cpc_codes),
    legal_status: stringValue(detail.legal_status) ?? "Status not reported",
    match_type: stringValue(detail.match_type) ?? "report_evidence",
    tanimoto_score: finiteNumber(detail.tanimoto_score),
    jurisdiction: stringValue(detail.jurisdiction) ?? undefined,
    family_id: stringValue(detail.family_id) ?? undefined,
    citations: stringArray(detail.citations),
    cited_by: stringArray(detail.cited_by),
    is_granted: detail.is_granted === true,
    application_number: stringValue(detail.application_number) ?? undefined,
    examiner: stringValue(detail.examiner) ?? undefined,
    attorney: stringValue(detail.attorney) ?? undefined,
    legal_events: legalEvents,
    family: normalizeFamily(detail.family),
    family_broadest:
      typeof detail.family_broadest === "boolean"
        ? detail.family_broadest
        : undefined,
    family_role: stringValue(detail.family_role) ?? undefined,
    parent_application_id:
      stringValue(detail.parent_application_id) ?? undefined,
    patent_term_info: normalizePatentTermInfo(detail.patent_term_info),
  };
}
