import "server-only";

import {
  SHOWCASE_FIXTURE_RECEIPT,
  SHOWCASE_PAYLOAD,
  SHOWCASE_REPORT as TEST_REPORT,
} from "@/lib/showcase-report";
import type {
  AnalysisFailure,
  DataLimitation,
  RiskLevel,
  SourceHealthEntry,
  VerificationCheck,
} from "@praviar/shared-types";

const DEMO_REPORT_SOURCE_REFERENCE = `${SHOWCASE_FIXTURE_RECEIPT.fixtureId}@${SHOWCASE_FIXTURE_RECEIPT.fixtureVersion} · sha256:${SHOWCASE_FIXTURE_RECEIPT.digest}`;

export interface DemoClaimSnapshot {
  patentId: string;
  patentTitle: string;
  claimNumber: number;
  claimStatus: string;
  elements: Array<{
    label: string;
    elementText: string;
    status: string;
    reasoning: string;
    confidence: number;
    evidence: string;
    traceId: string;
    sourceCitation: string;
    sourceExcerpt: string;
    supportStatus: string;
    reviewRequired: boolean;
  }>;
}

export interface DemoEvidenceRow {
  patentId: string;
  title: string;
  assignee: string;
  expiryDate: string | null;
  riskLevel: RiskLevel;
  claimReference: string;
  rationale: string;
  sourceLabel: string;
  sourceUrl: string;
  sourceTraceId: string;
  sourcePosture: string;
  sourcesFoundIn: string[];
  rank: number | null;
  score: number | null;
  filterReason: string;
  triageReason: string;
  triageConfidence: number | null;
  selectionReason: string;
  selectedForAnalysis: boolean;
}

export interface DemoProvenanceSummary {
  reportId: string;
  generatedAt: string;
  pipelineVersion: string;
  executionProfile: string;
  modelNames: string[];
  totalInputTokens: number;
  totalOutputTokens: number;
  estimatedCostUsd: number;
}

export interface DemoVerificationSummary {
  checks: VerificationCheck[];
  issues: string[];
  unsupportedVisibleClaims: number;
  reviewNeededClaims: number;
}

export interface DemoArtifactPayload {
  compoundName: string;
  canonicalSmiles: string;
  verdict: RiskLevel;
  blockingPatentsCount: number;
  familiesFlaggedForReviewCount: number;
  totalPatentsFound: number;
  patentsAfterTriage: number;
  patentsAnalyzed: number;
  runtimeLabel: string;
  executiveSummary: string;
  keyFindings: string[];
  searchFunnel: Array<{ stage: string; count: number }>;
  timing: Array<{ step: string; duration_seconds: number }>;
  claimSnapshot: DemoClaimSnapshot;
  evidenceRows?: DemoEvidenceRow[];
  provenance: DemoProvenanceSummary;
  verification: DemoVerificationSummary;
  sourceHealth: SourceHealthEntry[];
  analysisFailures: AnalysisFailure[];
  dataLimitations: DataLimitation[];
  designAround: string;
  invalidityTeaser: string;
  disclaimer: string;
  sourceReference: string;
}

function formatRuntime(totalSeconds: number): string {
  if (totalSeconds < 60) return `${Math.round(totalSeconds)} s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.round(totalSeconds % 60);
  return `${minutes} min ${seconds.toString().padStart(2, "0")} s`;
}

function formatStepName(stepName: string): string {
  const normalized = stepName.replace(/^step\d+_/, "").toLowerCase();
  const buyerFacingNames: Record<string, string> = {
    analyze: "Claim review",
    analyze_claims: "Claim review",
    doe: "Equivalence",
    doe_assessment: "Equivalence",
    invalidity_screening: "Prior-art review",
    report_generation: "Report assembly",
    resolve_compound: "Compound check",
    search_patents: "Patent search",
  };

  if (buyerFacingNames[normalized]) return buyerFacingNames[normalized];

  return stepName
    .replace(/^step\d+_/, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatSourceName(sourceName: string): string {
  const buyerFacingNames: Record<string, string> = {
    bigquery: "Patent full-text search",
    bigquery_annotations: "Patent annotation search",
    patcid: "Structure search",
    pubchem_sdq: "Compound-linked patent search",
    surechembl: "Patent chemistry search",
  };

  return buyerFacingNames[sourceName] ?? formatStepName(sourceName);
}

function getPublicReviewRationale(riskLevel: RiskLevel): string {
  if (riskLevel === "high") {
    return "This fictional family contains claim language close enough to the sample process to merit prompt review by qualified patent counsel.";
  }
  if (riskLevel === "medium") {
    return "This fictional family overlaps part of the sample scenario, but the open claim questions need expert review before drawing a conclusion.";
  }
  if (riskLevel === "low") {
    return "The fictional claim language differs from the sample process in several material ways. Keep the family as context and ask counsel whether those differences hold.";
  }
  return "No overlap is shown in this fictional scenario. That sample label is not a legal clearance conclusion and should not be used for a real matter.";
}

function getPublicTriageReason(riskLevel: RiskLevel): string {
  if (riskLevel === "high") {
    return "Prioritised because the fictional claim map shows several elements that deserve counsel review.";
  }
  if (riskLevel === "medium") {
    return "Retained because the fictional route shares some features with the claim language.";
  }
  if (riskLevel === "low") {
    return "Retained as context because the fictional record names the compound but describes a different route.";
  }
  return "Retained to show how the sample records a candidate with no overlap in this fictional scenario.";
}

export function getMarketingDemoArtifact(): DemoArtifactPayload {
  const leadPatent = TEST_REPORT.patent_analyses[0];
  const leadClaim = leadPatent.claims_analyzed[0];
  const claimSourceSpanMap = TEST_REPORT.claim_source_span_map;
  const searchAuditByPatent = new Map(
    (TEST_REPORT.audit_trail.search_funnel ?? []).map((entry) => [
      entry.patent_id,
      entry,
    ]),
  );
  const analysisAuditByPatent = new Map(
    (TEST_REPORT.audit_trail.analysis_audit ?? []).map((entry) => [
      entry.patent_id,
      entry,
    ]),
  );
  const totalSeconds = TEST_REPORT.audit_trail.timing_data.reduce(
    (sum, step) => sum + step.duration_seconds,
    0,
  );
  const publicPatentIds = new Map(
    TEST_REPORT.patent_analyses.map((patent, index) => [
      patent.patent_id,
      `SYNTH-US-${String(index + 1).padStart(3, "0")}`,
    ]),
  );
  let nextPublicPatentIndex = publicPatentIds.size + 1;
  const sanitizeText = (value: string): string => {
    let sanitized = value;
    for (const [sourceId, publicId] of publicPatentIds) {
      sanitized = sanitized.split(sourceId).join(publicId);
    }
    return sanitized
      .replace(/\bIPR\d{4}-\d+\b/g, "SYNTH-REVIEW-001")
      .replace(/\bfixture\b/gi, "sample");
  };
  const getPublicPatentId = (patentId: string): string => {
    const existingId = publicPatentIds.get(patentId);
    if (existingId) return existingId;

    const publicId = `SYNTH-US-${String(nextPublicPatentIndex).padStart(3, "0")}`;
    nextPublicPatentIndex += 1;
    publicPatentIds.set(patentId, publicId);
    return publicId;
  };

  const publicExecutiveSummary = TEST_REPORT.risk_summary.executive_summary;
  const publicKeyFindings = TEST_REPORT.risk_summary.key_risks ?? [];

  return {
    compoundName: TEST_REPORT.compound.name,
    canonicalSmiles: TEST_REPORT.compound.canonical_smiles,
    verdict: TEST_REPORT.risk_summary.overall_risk,
    blockingPatentsCount: TEST_REPORT.risk_summary.blocking_patents_count,
    familiesFlaggedForReviewCount: SHOWCASE_PAYLOAD.analysis.families.filter(
      (family) => family.posture !== "no_blocker_identified_in_searched_record",
    ).length,
    totalPatentsFound: TEST_REPORT.total_patents_found,
    patentsAfterTriage: TEST_REPORT.audit_trail.patents_after_triage,
    patentsAnalyzed: TEST_REPORT.audit_trail.patents_analyzed,
    runtimeLabel: formatRuntime(totalSeconds),
    executiveSummary: publicExecutiveSummary,
    keyFindings: publicKeyFindings,
    searchFunnel: [
      {
        stage: "Discovered",
        count: TEST_REPORT.audit_trail.total_patents_discovered,
      },
      {
        stage: "Hard Filter",
        count: TEST_REPORT.audit_trail.patents_after_hard_filter,
      },
      {
        stage: "Ranked",
        count: TEST_REPORT.audit_trail.patents_after_ranking,
      },
      {
        stage: "Triaged",
        count: TEST_REPORT.audit_trail.patents_after_triage,
      },
      {
        stage: "Analyzed",
        count: TEST_REPORT.audit_trail.patents_analyzed,
      },
    ],
    timing: TEST_REPORT.audit_trail.timing_data.map((step) => ({
      step: formatStepName(step.step_name),
      duration_seconds: step.duration_seconds,
    })),
    claimSnapshot: {
      patentId: getPublicPatentId(leadPatent.patent_id),
      patentTitle: sanitizeText(leadPatent.title),
      claimNumber: leadClaim.claim_number,
      claimStatus: leadClaim.overall_status,
      elements: leadClaim.elements.slice(0, 3).map((element) => {
        const supportEntry = claimSourceSpanMap?.entries?.find(
          (entry) =>
            entry.patent_id === leadPatent.patent_id &&
            entry.claim_number === leadClaim.claim_number &&
            entry.element_number === element.element_number,
        );
        const spanId = supportEntry?.source_span_ids?.[0];
        const sourceSpan = spanId ? claimSourceSpanMap?.spans?.[spanId] : null;

        return {
          label: `Element ${element.element_number}`,
          elementText: sanitizeText(element.element_text),
          status: element.status,
          reasoning: sanitizeText(element.reasoning),
          confidence: element.confidence,
          evidence: sanitizeText(element.evidence),
          traceId: `sample-${getPublicPatentId(leadPatent.patent_id)}-claim-${leadClaim.claim_number}-element-${element.element_number}`,
          sourceCitation: sanitizeText(
            sourceSpan?.citation ??
              `${leadPatent.patent_id} claim ${leadClaim.claim_number} element ${element.element_number}`,
          ),
          sourceExcerpt: sanitizeText(sourceSpan?.excerpt ?? element.evidence),
          supportStatus: supportEntry?.support_status ?? "supported",
          reviewRequired: supportEntry?.review_required ?? true,
        };
      }),
    },
    evidenceRows: TEST_REPORT.patent_analyses.slice(0, 6).map((patent) => {
      const leadClaim = patent.claims_analyzed[0];
      const searchAudit = searchAuditByPatent.get(patent.patent_id);
      const analysisAudit = analysisAuditByPatent.get(patent.patent_id);
      const sourceCount = searchAudit?.sources_found_in.length ?? 0;

      return {
        patentId: getPublicPatentId(patent.patent_id),
        title: sanitizeText(patent.title),
        assignee: sanitizeText(patent.assignee),
        expiryDate: patent.expiry_date,
        riskLevel: patent.risk_level,
        claimReference: leadClaim
          ? `Claim ${leadClaim.claim_number} · ${
              patent.risk_level === "clear"
                ? "no overlap shown in sample"
                : patent.risk_level === "low"
                  ? "sample differences shown"
                  : "fictional overlap shown"
            }`
          : "Claim review pending",
        rationale: getPublicReviewRationale(patent.risk_level),
        sourceLabel:
          sourceCount > 0
            ? `${sourceCount} sample source${sourceCount === 1 ? "" : "s"}`
            : "Sample source pending",
        sourceUrl: "#sample-evidence-ledger",
        sourceTraceId: `sample-trace-${getPublicPatentId(patent.patent_id)}`,
        sourcePosture: "Fictional sample record",
        sourcesFoundIn:
          searchAudit?.sources_found_in.map(formatSourceName) ?? [],
        rank: searchAudit?.final_rank ?? null,
        score: null,
        filterReason: sanitizeText(searchAudit?.filter_reason ?? ""),
        triageReason: getPublicTriageReason(patent.risk_level),
        triageConfidence: null,
        selectionReason:
          "Selected to demonstrate claim-level review in the fictional sample.",
        selectedForAnalysis:
          analysisAudit?.selected_for_analysis ?? Boolean(leadClaim),
      };
    }),
    provenance: {
      reportId: TEST_REPORT.report_id,
      generatedAt: TEST_REPORT.generated_at,
      pipelineVersion: TEST_REPORT.praviar_pipeline_version,
      executionProfile: "Adaptive sample run",
      modelNames: Array.from(
        new Set(Object.values(TEST_REPORT.llm_models_used ?? {})),
      ),
      totalInputTokens: TEST_REPORT.total_input_tokens,
      totalOutputTokens: TEST_REPORT.total_output_tokens,
      estimatedCostUsd: TEST_REPORT.estimated_cost_usd ?? 0,
    },
    verification: {
      checks: (TEST_REPORT.verification.checks ?? []).map((check) => ({
        ...check,
        details: sanitizeText(check.details),
      })),
      issues: (TEST_REPORT.verification.issues ?? []).map(sanitizeText),
      unsupportedVisibleClaims:
        TEST_REPORT.claim_source_span_map
          ?.unsupported_customer_visible_claim_count ?? 0,
      reviewNeededClaims:
        TEST_REPORT.claim_source_span_map?.needs_review_count ?? 0,
    },
    sourceHealth: (TEST_REPORT.source_health.entries ?? []).map((source) => ({
      ...source,
      source: formatSourceName(source.source),
      error_message: source.error_message
        ? "This sample source was unavailable during the run."
        : source.error_message,
    })),
    analysisFailures: (TEST_REPORT.analysis_failures ?? []).map((failure) => ({
      ...failure,
      patent_id: getPublicPatentId(failure.patent_id),
      step: formatStepName(failure.step),
      error_type: "Sample analysis warning",
      error_message:
        "One sample analysis step did not complete. The report keeps the gap visible for review.",
    })),
    dataLimitations: TEST_REPORT.data_limitations ?? [],
    designAround: SHOWCASE_PAYLOAD.review.required_actions[1],
    invalidityTeaser: SHOWCASE_PAYLOAD.review.required_actions[0],
    disclaimer:
      "This fictional sample shows how Praviar organises a preliminary patent-risk screen. It is not legal advice, a clearance opinion, customer work, or verified legal research. Ask qualified patent counsel to review any decision you plan to act on.",
    sourceReference: DEMO_REPORT_SOURCE_REFERENCE,
  };
}
