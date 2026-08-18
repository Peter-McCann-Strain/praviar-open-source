import type { RiskLevel } from "@praviar/shared-types";
import { sanitizePublicEvidenceUrl } from "./public-evidence-url";
import type { KeyPatent, SharedReport } from "./shared-report-types";

const VALID_RISK_LEVELS = new Set<RiskLevel>([
  "clear",
  "low",
  "medium",
  "high",
]);

export function parseSharedReportPayload(
  payload: unknown,
): SharedReport | null {
  if (!isRecord(payload)) {
    return null;
  }

  const compoundName = requiredText(payload.compound_name);
  const overallRisk = parseRiskLevel(payload.overall_risk);
  const blockingPatentsCount = parseNonNegativeInteger(
    payload.blocking_patents_count,
  );
  const totalPatentsFound = parseNonNegativeInteger(
    payload.total_patents_found,
  );
  const executiveSummary = requiredText(payload.executive_summary);
  const keyFindings = parseTextArray(payload.key_findings);
  const generatedAt = parseIsoDate(payload.generated_at);
  const shareExpiresAt = parseIsoDate(payload.share_expires_at);
  const verifiedRecipientEmail = requiredText(payload.verified_recipient_email);
  const attributableViewNumber = parsePositiveInteger(
    payload.attributable_view_number,
  );
  const verifiedSessionExpiresAt = parseIsoDate(
    payload.verified_session_expires_at,
  );

  if (
    !compoundName ||
    !overallRisk ||
    blockingPatentsCount === null ||
    totalPatentsFound === null ||
    !executiveSummary ||
    keyFindings === null ||
    !generatedAt ||
    !shareExpiresAt ||
    !verifiedRecipientEmail ||
    attributableViewNumber === null ||
    !verifiedSessionExpiresAt
  ) {
    return null;
  }

  const report: SharedReport = {
    compound_name: compoundName,
    overall_risk: overallRisk,
    blocking_patents_count: blockingPatentsCount,
    total_patents_found: totalPatentsFound,
    executive_summary: executiveSummary,
    key_findings: keyFindings,
    generated_at: generatedAt,
    share_expires_at: shareExpiresAt,
    verified_recipient_email: verifiedRecipientEmail,
    attributable_view_number: attributableViewNumber,
    verified_session_expires_at: verifiedSessionExpiresAt,
  };

  applyOptionalText(report, payload, "report_id");
  applyOptionalText(report, payload, "share_id");
  applyOptionalText(report, payload, "packet_version");
  applyOptionalText(report, payload, "source_snapshot_at", parseIsoDate);
  applyOptionalText(report, payload, "pipeline_version");
  applyOptionalText(report, payload, "model_version");
  applyOptionalText(report, payload, "integrity_digest");
  applyOptionalText(report, payload, "intended_use");
  applyOptionalText(report, payload, "ai_system_notice");
  applyOptionalText(report, payload, "reliance_boundary");
  applyOptionalText(report, payload, "review_status");

  applyOptionalNumber(report, payload, "total_material_patents");
  applyOptionalNumber(report, payload, "omitted_key_patents_count");
  applyOptionalNumber(report, payload, "omitted_limitations_count");

  applyOptionalTextArray(report, payload, "source_coverage");
  applyOptionalTextArray(report, payload, "jurisdiction_scope");
  applyOptionalTextArray(report, payload, "evidence_limitations");
  applyOptionalTextArray(report, payload, "standard_limitations");

  const keyPatents = parseKeyPatents(payload.key_patents);
  if (keyPatents) {
    report.key_patents = keyPatents;
  }

  if (isRecord(payload.integrity_summary)) {
    report.integrity_summary = {
      affected_patents_count: parseOptionalNonNegativeInteger(
        payload.integrity_summary.affected_patents_count,
      ),
      recoverable_failures_count: parseOptionalNonNegativeInteger(
        payload.integrity_summary.recoverable_failures_count,
      ),
      needs_review_count: parseOptionalNonNegativeInteger(
        payload.integrity_summary.needs_review_count,
      ),
      data_limitations_count: parseOptionalNonNegativeInteger(
        payload.integrity_summary.data_limitations_count,
      ),
      source_caveats_count: parseOptionalNonNegativeInteger(
        payload.integrity_summary.source_caveats_count,
      ),
      evidence_sufficient_for_clearance:
        typeof payload.integrity_summary.evidence_sufficient_for_clearance ===
        "boolean"
          ? payload.integrity_summary.evidence_sufficient_for_clearance
          : undefined,
      metadata_inconsistent:
        typeof payload.integrity_summary.metadata_inconsistent === "boolean"
          ? payload.integrity_summary.metadata_inconsistent
          : undefined,
    };
  }

  return report;
}

export function isSharedReportExpired(
  report: Pick<SharedReport, "share_expires_at">,
  now: Date = new Date(),
): boolean {
  const expiresAt = Date.parse(report.share_expires_at ?? "");
  const currentTime = now.getTime();

  if (Number.isNaN(expiresAt) || Number.isNaN(currentTime)) {
    return true;
  }

  return expiresAt <= currentTime;
}

export function isSharedReportVerificationSessionExpired(
  report: Pick<SharedReport, "verified_session_expires_at">,
  now: Date = new Date(),
): boolean {
  const expiresAt = Date.parse(report.verified_session_expires_at ?? "");
  const currentTime = now.getTime();

  if (Number.isNaN(expiresAt) || Number.isNaN(currentTime)) {
    return true;
  }

  return expiresAt <= currentTime;
}

function applyOptionalText<T extends keyof SharedReport>(
  report: SharedReport,
  payload: Record<string, unknown>,
  key: T,
  parser: (value: unknown) => string | null = optionalText,
) {
  const value = parser(payload[key]);
  if (value) {
    report[key] = value as SharedReport[T];
  }
}

function applyOptionalNumber<T extends keyof SharedReport>(
  report: SharedReport,
  payload: Record<string, unknown>,
  key: T,
) {
  const value = parseOptionalNonNegativeInteger(payload[key]);
  if (typeof value === "number") {
    report[key] = value as SharedReport[T];
  }
}

function applyOptionalTextArray<T extends keyof SharedReport>(
  report: SharedReport,
  payload: Record<string, unknown>,
  key: T,
) {
  const value = parseTextArray(payload[key], true);
  if (value) {
    report[key] = value as SharedReport[T];
  }
}

function parseKeyPatents(value: unknown): KeyPatent[] | null {
  if (!Array.isArray(value)) {
    return null;
  }

  const patents: KeyPatent[] = [];
  for (const item of value) {
    if (!isRecord(item)) {
      continue;
    }

    const patentNumber = requiredText(item.patent_number);
    if (!patentNumber) {
      continue;
    }

    const patent: KeyPatent = { patent_number: patentNumber };
    const riskLevel = parseRiskLevel(item.risk_level);
    if (riskLevel) {
      patent.risk_level = riskLevel;
    }
    const assignee = optionalText(item.assignee);
    if (assignee) {
      patent.assignee = assignee;
    }
    const expiry = optionalText(item.expiry);
    if (expiry) {
      patent.expiry = expiry;
    }
    const patentUrl = optionalHttpsUrl(item.patent_url);
    if (patentUrl) {
      patent.patent_url = patentUrl;
    }
    const sourceReference = optionalText(item.source_reference);
    if (sourceReference) {
      patent.source_reference = sourceReference;
    }
    patents.push(patent);
  }

  return patents;
}

function parseRiskLevel(value: unknown): RiskLevel | null {
  return typeof value === "string" && VALID_RISK_LEVELS.has(value as RiskLevel)
    ? (value as RiskLevel)
    : null;
}

function parseTextArray(value: unknown, optional = false): string[] | null {
  if (value === undefined && optional) {
    return null;
  }
  if (!Array.isArray(value)) {
    return null;
  }

  const cleaned = value
    .map((item) => optionalText(item))
    .filter((item): item is string => Boolean(item));
  return cleaned;
}

function requiredText(value: unknown): string | null {
  const text = optionalText(value);
  return text && text.length > 0 ? text : null;
}

function optionalText(value: unknown): string | null {
  return typeof value === "string" ? value.trim() : null;
}

function optionalHttpsUrl(value: unknown): string | null {
  return sanitizePublicEvidenceUrl(value);
}

function parseIsoDate(value: unknown): string | null {
  const text = requiredText(value);
  if (!text) {
    return null;
  }
  return Number.isNaN(Date.parse(text)) ? null : text;
}

function parseNonNegativeInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= 0
    ? value
    : null;
}

function parsePositiveInteger(value: unknown): number | null {
  const parsed = parseNonNegativeInteger(value);
  return parsed !== null && parsed > 0 ? parsed : null;
}

function parseOptionalNonNegativeInteger(value: unknown): number | undefined {
  return value === undefined
    ? undefined
    : (parseNonNegativeInteger(value) ?? undefined);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
