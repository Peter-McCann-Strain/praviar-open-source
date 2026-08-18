import type {
  ClaimAssertionSupport,
  DoEAssessment,
  FTOReport,
  PatentHit,
  RiskLevel,
  SourceSpanReference,
} from "@praviar/shared-types";
import { normalizeReportPatentDetail } from "@/components/report/patent-detail-normalizer";
import type {
  Decision,
  ReviewerDecision,
  ReviewerDecisionListResponse,
} from "@/hooks/use-reviewer-decisions";

export type ClaimDecisionFilter =
  | "needs_action"
  | "all"
  | "met_partial"
  | "not_met"
  | "unclear";

export type ClaimDecisionReviewState =
  | "accepted"
  | "rejected"
  | "edited"
  | "conflict"
  | "pending"
  | "not_required"
  | "unknown";

export interface ReviewerDecisionSummary {
  counts: Record<Decision, number>;
  label: string;
  latestUpdatedAt: string | null;
  reviewCount: number;
  state: ClaimDecisionReviewState;
}

export interface ClaimDecisionMatrixRow {
  contextSpans: SourceSpanReference[];
  doeConfidence: number | null;
  doeStatus: "equivalent" | "not_equivalent" | "unclear" | "not_assessed";
  elementConfidence: number | null;
  elementNumber: number;
  elementText: string;
  expiryDate: string | null;
  familyId: string | null;
  id: string;
  jurisdiction: string | null;
  legalStatus: string | null;
  literalStatus: string;
  mappingEvidence: string | null;
  mappingReasoning: string;
  mappingSupport: "supported" | "needs_review" | "unsupported" | "not_reported";
  patentId: string;
  patentTitle: string;
  claimNumber: number;
  reviewRequired: boolean;
  reviewSummary: ReviewerDecisionSummary;
  reviewTargetAssertionId: string | null;
  riskLevel: RiskLevel;
  doeReasoning: string | null;
  verifiedSpans: SourceSpanReference[];
  needsAction: boolean;
}

const SHA256_PATTERN = /^[0-9a-f]{64}$/;

function artifactLocatorBindsHash(locator: string, digest: string) {
  try {
    const url = new URL(locator);
    const embeddedHashes = new URLSearchParams(url.hash.slice(1)).getAll(
      "sha256",
    );
    return embeddedHashes.length === 1 && embeddedHashes[0] === digest;
  } catch {
    return false;
  }
}

export function hasCompleteVerifiedClaimReceipt(span: SourceSpanReference) {
  const sourceDigest = span.source_text_sha256 ?? "";
  return Boolean(
    span.source_type === "verified_claim_text" &&
    span.patent_id?.trim() &&
    span.source_document_id === span.patent_id &&
    span.excerpt?.trim() &&
    span.source_document_id?.trim() &&
    span.source_name?.trim() &&
    span.source_artifact_locator?.trim() &&
    span.collector_identity?.trim() &&
    span.collector_version?.trim() &&
    span.source_retrieved_at &&
    !Number.isNaN(Date.parse(span.source_retrieved_at)) &&
    SHA256_PATTERN.test(sourceDigest) &&
    artifactLocatorBindsHash(
      span.source_artifact_locator ?? "",
      sourceDigest,
    ) &&
    SHA256_PATTERN.test(span.provenance_cassette_sha256 ?? ""),
  );
}

export interface ClaimDecisionMatrixModel {
  rows: ClaimDecisionMatrixRow[];
  total: number;
  needsActionCount: number;
  verifiedSourceCount: number;
  conflictCount: number;
}

function exactTupleMatch(
  value: {
    patent_id?: string;
    claim_number?: number | null;
    element_number?: number | null;
  },
  patentId: string,
  claimNumber: number,
  elementNumber: number,
) {
  return (
    value.patent_id === patentId &&
    value.claim_number === claimNumber &&
    value.element_number === elementNumber
  );
}

function getTupleSupports(
  report: FTOReport,
  patentId: string,
  claimNumber: number,
  elementNumber: number,
): ClaimAssertionSupport[] {
  return (report.claim_source_span_map?.entries ?? []).filter(
    (entry) =>
      entry.customer_visible !== false &&
      exactTupleMatch(entry, patentId, claimNumber, elementNumber),
  );
}

function getTupleSpans(
  report: FTOReport,
  supports: ClaimAssertionSupport[],
  patentId: string,
  claimNumber: number,
  elementNumber: number,
) {
  const spans = report.claim_source_span_map?.spans ?? {};
  const seen = new Set<string>();
  return supports.flatMap((support) =>
    (support.source_span_ids ?? []).flatMap((spanId) => {
      if (seen.has(spanId)) return [];
      const span = spans[spanId];
      if (
        !span ||
        !exactTupleMatch(span, patentId, claimNumber, elementNumber)
      ) {
        return [];
      }
      seen.add(spanId);
      return [span];
    }),
  );
}

function getMappingSupports(supports: ClaimAssertionSupport[]) {
  return supports.filter(
    (support) =>
      support.report_section === "claim_element_analysis" ||
      support.review_required === true,
  );
}

function summarizeMappingSupport(
  supports: ClaimAssertionSupport[],
): ClaimDecisionMatrixRow["mappingSupport"] {
  if (supports.some((support) => support.support_status === "unsupported")) {
    return "unsupported";
  }
  if (
    supports.some(
      (support) =>
        support.support_status === "needs_review" ||
        support.review_required === true,
    )
  ) {
    return "needs_review";
  }
  if (
    supports.length > 0 &&
    supports.every((support) => support.support_status === "supported")
  ) {
    return "supported";
  }
  return "not_reported";
}

function getReviewTargetAssertionId(
  supports: ClaimAssertionSupport[],
): string | null {
  const targets = supports
    .filter(
      (support) =>
        support.review_required === true ||
        support.support_status === "needs_review",
    )
    .map((support) => support.assertion_id)
    .filter(Boolean)
    .sort();
  return targets[0] ?? null;
}

export function summarizeReviewerDecisions(
  decisions: ReviewerDecision[] | undefined,
  {
    loading = false,
    required = true,
    unavailable = false,
  }: { loading?: boolean; required?: boolean; unavailable?: boolean } = {},
): ReviewerDecisionSummary {
  const matching = decisions ?? [];
  const counts: Record<Decision, number> = {
    accept: 0,
    reject: 0,
    edit: 0,
  };
  for (const decision of matching) counts[decision.decision] += 1;
  const reviewCount = new Set(
    matching.map((decision) => decision.reviewer_user_id).filter(Boolean),
  ).size;
  const latestUpdatedAt = matching.reduce<string | null>((latest, decision) => {
    if (!latest || decision.updated_at > latest) return decision.updated_at;
    return latest;
  }, null);

  if (!required) {
    return {
      counts,
      label: "Not required",
      latestUpdatedAt,
      reviewCount,
      state: "not_required",
    };
  }
  if (unavailable) {
    return {
      counts: { accept: 0, reject: 0, edit: 0 },
      label: "Decision ledger unavailable",
      latestUpdatedAt: null,
      reviewCount: 0,
      state: "unknown",
    };
  }
  if (loading) {
    return {
      counts,
      label: "Loading decisions",
      latestUpdatedAt: null,
      reviewCount: 0,
      state: "unknown",
    };
  }
  if (matching.length === 0) {
    return {
      counts,
      label: "Review pending",
      latestUpdatedAt: null,
      reviewCount: 0,
      state: "pending",
    };
  }

  const distinct = (Object.keys(counts) as Decision[]).filter(
    (decision) => counts[decision] > 0,
  );
  if (distinct.length > 1) {
    const mix = distinct
      .map((decision) => `${counts[decision]} ${decision}`)
      .join(" / ");
    return {
      counts,
      label: `Conflict · ${mix}`,
      latestUpdatedAt,
      reviewCount,
      state: "conflict",
    };
  }
  const decision = distinct[0];
  const state =
    decision === "accept"
      ? "accepted"
      : decision === "reject"
        ? "rejected"
        : "edited";
  return {
    counts,
    label: `${state.charAt(0).toUpperCase()}${state.slice(1)} · ${reviewCount} reviewer${reviewCount === 1 ? "" : "s"}`,
    latestUpdatedAt,
    reviewCount,
    state,
  };
}

function getReviewerSummary(
  reviewerDecisions: ReviewerDecisionListResponse | null | undefined,
  assertionId: string | null,
  loading: boolean,
  unavailable: boolean,
) {
  const decisions = assertionId
    ? reviewerDecisions?.items.filter(
        (decision) =>
          decision.finding_type === "claim_element" &&
          decision.finding_ref === assertionId,
      )
    : [];
  return summarizeReviewerDecisions(decisions, {
    loading: Boolean(assertionId && loading),
    required: Boolean(assertionId),
    unavailable: Boolean(assertionId && unavailable),
  });
}

function getPatentHit(report: FTOReport, patentId: string): PatentHit | null {
  const analysis =
    report.patent_analyses.find((item) => item.patent_id === patentId) ?? null;
  const detail = report.patent_details?.[patentId];
  if (!detail && !analysis) return null;
  return normalizeReportPatentDetail({
    analysis,
    patentId,
    rawDetail: detail,
  });
}

function getDoeStatus(doe: DoEAssessment | null) {
  if (!doe) return "not_assessed" as const;
  if (doe.overall_equivalent === true) return "equivalent" as const;
  if (doe.overall_equivalent === false) return "not_equivalent" as const;
  return "unclear" as const;
}

function findDoe(
  report: FTOReport,
  patentId: string,
  claimNumber: number,
  elementNumber: number,
) {
  return (
    report.doe_assessments?.find((assessment) =>
      exactTupleMatch(assessment, patentId, claimNumber, elementNumber),
    ) ?? null
  );
}

export function buildClaimDecisionMatrixModel({
  decisionsLoading = false,
  decisionsUnavailable = false,
  report,
  reviewerDecisions,
}: {
  decisionsLoading?: boolean;
  decisionsUnavailable?: boolean;
  report: FTOReport;
  reviewerDecisions?: ReviewerDecisionListResponse | null;
}): ClaimDecisionMatrixModel {
  const rows = (report.patent_analyses ?? []).flatMap((analysis) => {
    const patent = getPatentHit(report, analysis.patent_id);
    return (analysis.claims_analyzed ?? []).flatMap((claim) =>
      (claim.elements ?? []).map((element) => {
        const supports = getTupleSupports(
          report,
          analysis.patent_id,
          claim.claim_number,
          element.element_number,
        );
        const mappingSupports = getMappingSupports(supports);
        const spans = getTupleSpans(
          report,
          supports,
          analysis.patent_id,
          claim.claim_number,
          element.element_number,
        );
        const supportedSpanIds = new Set(
          supports
            .filter((support) => support.support_status === "supported")
            .flatMap((support) => support.source_span_ids ?? []),
        );
        const verifiedSpans = spans
          .filter(
            (span) =>
              span.source_type === "verified_claim_text" &&
              supportedSpanIds.has(span.span_id) &&
              hasCompleteVerifiedClaimReceipt(span),
          )
          .sort((left, right) => left.span_id.localeCompare(right.span_id));
        const contextSpans = spans
          .filter((span) => span.source_type !== "verified_claim_text")
          .sort((left, right) => left.span_id.localeCompare(right.span_id));
        const reviewTargetAssertionId =
          getReviewTargetAssertionId(mappingSupports);
        const reviewSummary = getReviewerSummary(
          reviewerDecisions,
          reviewTargetAssertionId,
          decisionsLoading,
          decisionsUnavailable,
        );
        const mappingSupport = summarizeMappingSupport(mappingSupports);
        const doe = findDoe(
          report,
          analysis.patent_id,
          claim.claim_number,
          element.element_number,
        );
        const reviewRequired = Boolean(reviewTargetAssertionId);
        const unresolvedReview =
          reviewRequired &&
          ["conflict", "pending", "unknown"].includes(reviewSummary.state);
        const needsAction =
          verifiedSpans.length === 0 ||
          element.reasoning.trim().length === 0 ||
          mappingSupport === "unsupported" ||
          mappingSupport === "not_reported" ||
          unresolvedReview;
        const familyId = patent?.family_id ?? patent?.family?.family_id ?? null;

        return {
          contextSpans,
          doeConfidence:
            typeof doe?.confidence === "number" ? doe.confidence : null,
          doeReasoning: doe?.reasoning?.trim() || null,
          doeStatus: getDoeStatus(doe),
          elementConfidence:
            typeof element.confidence === "number" ? element.confidence : null,
          elementNumber: element.element_number,
          elementText: element.element_text,
          expiryDate: analysis.expiry_date ?? patent?.expiry_date ?? null,
          familyId,
          id: `${analysis.patent_id}:claim-${claim.claim_number}:element-${element.element_number}`,
          jurisdiction: analysis.jurisdiction ?? patent?.jurisdiction ?? null,
          legalStatus: patent?.legal_status ?? null,
          literalStatus: element.status,
          mappingEvidence: element.evidence?.trim() || null,
          mappingReasoning: element.reasoning.trim(),
          mappingSupport,
          patentId: analysis.patent_id,
          patentTitle: analysis.title ?? patent?.title ?? "Title not reported",
          claimNumber: claim.claim_number,
          reviewRequired,
          reviewSummary,
          reviewTargetAssertionId,
          riskLevel: analysis.risk_level,
          verifiedSpans,
          needsAction,
        } satisfies ClaimDecisionMatrixRow;
      }),
    );
  });

  const seenTupleIds = new Set<string>();
  for (const row of rows) {
    if (seenTupleIds.has(row.id)) {
      throw new Error(
        `Duplicate claim element tuple in report contract: ${row.id}`,
      );
    }
    seenTupleIds.add(row.id);
  }

  rows.sort(compareClaimDecisionRows);
  return {
    rows,
    total: rows.length,
    needsActionCount: rows.filter((row) => row.needsAction).length,
    verifiedSourceCount: rows.filter((row) => row.verifiedSpans.length > 0)
      .length,
    conflictCount: rows.filter((row) => row.reviewSummary.state === "conflict")
      .length,
  };
}

function priority(row: ClaimDecisionMatrixRow) {
  if (row.verifiedSpans.length === 0) return 0;
  if (row.reviewSummary.state === "conflict") return 1;
  if (["pending", "unknown"].includes(row.reviewSummary.state)) return 2;
  if (
    row.riskLevel === "high" &&
    ["met", "partially_met"].includes(row.literalStatus)
  ) {
    return 3;
  }
  if (["equivalent", "unclear"].includes(row.doeStatus)) return 4;
  return 5;
}

function compareClaimDecisionRows(
  left: ClaimDecisionMatrixRow,
  right: ClaimDecisionMatrixRow,
) {
  return (
    priority(left) - priority(right) ||
    left.patentId.localeCompare(right.patentId) ||
    left.claimNumber - right.claimNumber ||
    left.elementNumber - right.elementNumber
  );
}

export function filterClaimDecisionRows(
  rows: ClaimDecisionMatrixRow[],
  filter: ClaimDecisionFilter,
) {
  if (filter === "all") return rows;
  if (filter === "needs_action") return rows.filter((row) => row.needsAction);
  if (filter === "met_partial") {
    return rows.filter((row) =>
      ["met", "partially_met"].includes(row.literalStatus),
    );
  }
  if (filter === "not_met") {
    return rows.filter((row) => row.literalStatus === "not_met");
  }
  return rows.filter((row) => row.literalStatus === "unclear");
}
