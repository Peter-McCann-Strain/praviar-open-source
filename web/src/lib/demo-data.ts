import type { FTOReport, RiskLevel } from "@praviar/shared-types";

import type { ProductContextPayload } from "@/lib/product-context";
import type { AnalysisListItem, AnalysisProductContext } from "@/types/api";

import {
  SHOWCASE_FIXTURE_RECEIPT,
  SHOWCASE_PAYLOAD,
  SHOWCASE_REPORT as TEST_REPORT,
} from "./showcase-report";

export const DEMO_ANALYSIS_ID = "ana_demo_001";
export const DEMO_SHARE_TOKEN = "sg_demo_mailbox_grant_7Kp2mQ9xV4cN8rT6wH3z";
export const DEMO_SHARE_VERIFICATION_CODE = "24681357";
const DEMO_ANALYSES_STORAGE_KEY = "praviar_demo_analyses";
const DEMO_ANALYSIS_ID_PATTERN = /^ana_demo_\d+$/;
const DEMO_ANALYSIS_ID_ALIASES = new Map<string, string>([
  ["demo", DEMO_ANALYSIS_ID],
  ["demo-analysis", DEMO_ANALYSIS_ID],
  ["demo-analysis-001", DEMO_ANALYSIS_ID],
  ["prv-2026-0142", DEMO_ANALYSIS_ID],
  ["prv-demo-report", DEMO_ANALYSIS_ID],
  ["sample", DEMO_ANALYSIS_ID],
  ["rep_demo_001", DEMO_ANALYSIS_ID],
  ["rpt_ana_demo_001", DEMO_ANALYSIS_ID],
  [`rpt_${SHOWCASE_PAYLOAD.analysis.id}`, DEMO_ANALYSIS_ID],
]);

const INITIAL_ANALYSES: AnalysisListItem[] = [
  {
    id: DEMO_ANALYSIS_ID,
    compound_input: SHOWCASE_PAYLOAD.compound.submitted_identity,
    compound_name: SHOWCASE_PAYLOAD.compound.display_name,
    compound_smiles: "",
    status: "completed",
    current_step: 8,
    progress_pct: 100,
    overall_risk: TEST_REPORT.risk_summary.overall_risk,
    blocking_patents_count: 0,
    total_patents_found: SHOWCASE_PAYLOAD.analysis.families.length,
    executive_summary: TEST_REPORT.risk_summary.executive_summary,
    estimated_cost_usd: 0,
    pipeline_duration_seconds: 1440,
    flagged_for_review: true,
    current_user_role: "admin",
    risk_ratings_restricted: false,
    launch_context: {
      trust_mode: "explorer",
      jurisdiction_bundle: "fictional_showcase",
      target_jurisdictions: [...SHOWCASE_PAYLOAD.compound.jurisdictions],
      development_stage: "discovery",
      asset_type_hint: "unknown",
      matter_type: "small_molecule",
      intended_actions: ["diligence_screen"],
      product_context: {
        product_name: SHOWCASE_PAYLOAD.matter.title,
        commercial_action: SHOWCASE_PAYLOAD.compound.intended_use,
        commercial_territories: [...SHOWCASE_PAYLOAD.compound.jurisdictions],
      },
    },
    share_active: true,
    share_view_count: 0,
    share_last_viewed_at: null,
    created_at: SHOWCASE_PAYLOAD.analysis.started_at,
    updated_at: SHOWCASE_PAYLOAD.analysis.completed_at,
  },
  {
    id: "ana_demo_002",
    compound_input: SHOWCASE_PAYLOAD.compound.submitted_identity,
    compound_name: `${SHOWCASE_PAYLOAD.compound.display_name} — retrieval replay`,
    compound_smiles: "",
    status: "running",
    current_step: 2,
    progress_pct: 50,
    overall_risk: null,
    blocking_patents_count: 0,
    total_patents_found: SHOWCASE_PAYLOAD.analysis.families.length,
    executive_summary: "",
    estimated_cost_usd: 0,
    pipeline_duration_seconds: null,
    flagged_for_review: false,
    current_user_role: "admin",
    risk_ratings_restricted: false,
    launch_context: {
      trust_mode: "explorer",
      jurisdiction_bundle: "custom",
      target_jurisdictions: [...SHOWCASE_PAYLOAD.compound.jurisdictions],
      development_stage: "discovery",
      asset_type_hint: "unknown",
      matter_type: "small_molecule",
      intended_actions: ["diligence_screen"],
      product_context: { product_name: SHOWCASE_PAYLOAD.matter.title },
    },
    share_active: false,
    share_view_count: 0,
    share_last_viewed_at: null,
    created_at: SHOWCASE_PAYLOAD.analysis.started_at,
    updated_at: SHOWCASE_PAYLOAD.analysis.completed_at,
  },
  {
    id: "ana_demo_003",
    compound_input: SHOWCASE_PAYLOAD.compound.submitted_identity,
    compound_name: `${SHOWCASE_PAYLOAD.compound.display_name} — partial-source example`,
    compound_smiles: "",
    status: "failed",
    current_step: 3,
    progress_pct: 75,
    overall_risk: null,
    blocking_patents_count: 0,
    total_patents_found: SHOWCASE_PAYLOAD.analysis.families.length,
    executive_summary: SHOWCASE_PAYLOAD.failure_states[0].message,
    estimated_cost_usd: 0,
    pipeline_duration_seconds: 1080,
    flagged_for_review: true,
    current_user_role: "admin",
    risk_ratings_restricted: false,
    launch_context: {
      trust_mode: "explorer",
      jurisdiction_bundle: "custom",
      target_jurisdictions: [...SHOWCASE_PAYLOAD.compound.jurisdictions],
      development_stage: "discovery",
      asset_type_hint: "small_molecule",
      matter_type: "small_molecule",
      intended_actions: ["diligence_screen"],
      product_context: {},
    },
    share_active: false,
    share_view_count: 0,
    share_last_viewed_at: null,
    created_at: SHOWCASE_PAYLOAD.analysis.started_at,
    updated_at: SHOWCASE_PAYLOAD.analysis.completed_at,
  },
];

const demoAnalyses = new Map(
  INITIAL_ANALYSES.map((analysis) => [analysis.id, analysis]),
);
const initialDemoAnalysisIds = new Set(
  INITIAL_ANALYSES.map((analysis) => analysis.id),
);
let persistedDemoAnalysesHydrated = false;

type ClearanceOutcome = "clear" | "unclear" | "blocked";
type DemoLaunchContext = NonNullable<AnalysisListItem["launch_context"]>;
type DemoAnalysisCreateInput = {
  compound_input: string;
  trust_mode?: string;
  intended_actions?: string[];
  target_jurisdictions?: string[];
  jurisdiction_bundle?: string;
  development_stage?: string;
  asset_type_hint?: string | null;
  product_context?: ProductContextPayload;
};

type DemoStructuredReport = Omit<
  FTOReport,
  | "clearance_decision"
  | "jurisdiction_decisions"
  | "commercial_exposure"
  | "future_risk"
> & {
  clearance_decision?: unknown;
  jurisdiction_decisions?: unknown;
  commercial_exposure?: unknown;
  future_risk?: unknown;
};

function matterTypeFromAssetHint(assetTypeHint: string | null | undefined) {
  switch (assetTypeHint) {
    case "markush_candidate":
      return "markush_candidate";
    case "biologic_or_sequence":
      return "biologic";
    case "formulation":
      return "formulation";
    case "process_or_synthesis":
      return "process";
    case "combination":
      return "combination";
    case "small_molecule":
      return "small_molecule";
    default:
      return "small_molecule";
  }
}

function buildDemoLaunchContext(
  input: DemoAnalysisCreateInput,
): DemoLaunchContext {
  const assetTypeHint = input.asset_type_hint ?? "unknown";
  const intendedActions = input.intended_actions?.filter(Boolean) ?? [];
  const targetJurisdictions = input.target_jurisdictions?.filter(Boolean) ?? [];

  return {
    trust_mode: input.trust_mode ?? "explorer",
    jurisdiction_bundle: input.jurisdiction_bundle ?? "custom",
    target_jurisdictions:
      targetJurisdictions.length > 0 ? targetJurisdictions : ["US", "EP"],
    development_stage: input.development_stage ?? "discovery",
    asset_type_hint: assetTypeHint,
    matter_type: matterTypeFromAssetHint(assetTypeHint),
    intended_actions:
      intendedActions.length > 0 ? intendedActions : ["diligence_screen"],
    product_context: buildDemoSafeProductContext(input.product_context),
  };
}

function buildDemoSafeProductContext(
  productContext: ProductContextPayload | undefined,
): AnalysisProductContext {
  if (!productContext) {
    return {};
  }

  const safeProductContext = { ...productContext };
  delete safeProductContext.owned_or_licensed_ip;
  return safeProductContext;
}

function mapRiskToDecision(risk: RiskLevel): ClearanceOutcome {
  switch (risk) {
    case "clear":
    case "low":
      return "clear";
    case "medium":
      return "unclear";
    case "high":
    default:
      return "blocked";
  }
}

function getDecisionConfidence(decision: ClearanceOutcome): number {
  switch (decision) {
    case "clear":
      return 0.81;
    case "unclear":
      return 0.66;
    case "blocked":
    default:
      return 0.88;
  }
}

function getEvidenceQuality(decision: ClearanceOutcome): number {
  switch (decision) {
    case "clear":
      return 0.9;
    case "unclear":
      return 0.67;
    case "blocked":
    default:
      return 0.8;
  }
}

function isBrowserStorageAvailable() {
  return (
    typeof window !== "undefined" && typeof window.localStorage !== "undefined"
  );
}

function isPersistableDemoAnalysis(value: unknown): value is AnalysisListItem {
  if (!value || typeof value !== "object") {
    return false;
  }
  const candidate = value as Partial<AnalysisListItem>;
  return Boolean(
    typeof candidate.id === "string" &&
    DEMO_ANALYSIS_ID_PATTERN.test(candidate.id) &&
    typeof candidate.compound_input === "string" &&
    typeof candidate.compound_name === "string" &&
    typeof candidate.status === "string" &&
    typeof candidate.created_at === "string" &&
    typeof candidate.updated_at === "string",
  );
}

function hydratePersistedDemoAnalyses() {
  if (persistedDemoAnalysesHydrated || !isBrowserStorageAvailable()) {
    return;
  }
  persistedDemoAnalysesHydrated = true;

  try {
    const raw = window.localStorage.getItem(DEMO_ANALYSES_STORAGE_KEY);
    if (!raw) {
      return;
    }

    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return;
    }

    for (const item of parsed) {
      if (isPersistableDemoAnalysis(item)) {
        demoAnalyses.set(item.id, {
          ...item,
          current_user_role: item.current_user_role ?? "admin",
          risk_ratings_restricted: item.risk_ratings_restricted ?? false,
        });
      }
    }
  } catch {
    // Demo fixtures are best-effort only; malformed localStorage should not
    // break report viewing.
  }
}

function persistDemoAnalyses() {
  if (!isBrowserStorageAvailable()) {
    return;
  }

  try {
    const generatedAnalyses = Array.from(demoAnalyses.values()).filter(
      (analysis) => !initialDemoAnalysisIds.has(analysis.id),
    );
    window.localStorage.setItem(
      DEMO_ANALYSES_STORAGE_KEY,
      JSON.stringify(generatedAnalyses),
    );
  } catch {
    // Ignore storage failures; the in-memory demo still works for this tab.
  }
}

function buildFallbackDemoAnalysis(id: string): AnalysisListItem | null {
  if (!DEMO_ANALYSIS_ID_PATTERN.test(id)) {
    return null;
  }

  const suffix = id.replace("ana_demo_", "").replace(/^0+/, "") || "1";
  const createdAt = "2026-07-03T00:00:00.000Z";

  return {
    ...INITIAL_ANALYSES[0],
    id,
    compound_input: `demo compound ${suffix}`,
    compound_name: `Demo Compound ${suffix}`,
    launch_context: buildDemoLaunchContext({
      compound_input: `demo compound ${suffix}`,
    }),
    share_active: false,
    share_view_count: 0,
    share_last_viewed_at: null,
    created_at: createdAt,
    updated_at: createdAt,
  };
}

export function normalizeDemoAnalysisId(
  id: string | null | undefined,
): string | null {
  const candidate = id?.trim();
  if (!candidate) {
    return null;
  }
  const normalizedCandidate = candidate.toLowerCase();

  const aliasedId =
    DEMO_ANALYSIS_ID_ALIASES.get(candidate) ??
    DEMO_ANALYSIS_ID_ALIASES.get(normalizedCandidate);
  if (aliasedId) {
    return aliasedId;
  }

  if (DEMO_ANALYSIS_ID_PATTERN.test(normalizedCandidate)) {
    return normalizedCandidate;
  }

  if (normalizedCandidate.startsWith("rpt_")) {
    return normalizeDemoAnalysisId(normalizedCandidate.slice(4));
  }

  return null;
}

function buildDemoClearanceDecision(
  overallRisk: RiskLevel,
  analysis: AnalysisListItem,
): Record<string, unknown> {
  const decision = mapRiskToDecision(overallRisk);
  const queriedSourceNames = TEST_REPORT.search_sources_used;
  const successfulSourceEntries = TEST_REPORT.source_health.entries.filter(
    (entry) => entry.status === "ok",
  );
  const failedSourceEntries = TEST_REPORT.source_health.entries.filter(
    (entry) => entry.status !== "ok",
  );
  const reviewedPatentIds = TEST_REPORT.patent_analyses.map(
    (patent) => patent.patent_id,
  );
  const blockingPatentIds = TEST_REPORT.patent_analyses
    .slice(0, analysis.blocking_patents_count ?? 0)
    .map((patent) => patent.patent_id);
  const evidenceWarnings =
    decision === "clear"
      ? []
      : decision === "blocked"
        ? [
            `${blockingPatentIds[0] ?? "A material patent"} remains blocking after claim-level review.`,
          ]
        : [
            "At least one material family still requires deeper attorney review.",
          ];
  const insufficiencyReasons =
    decision === "clear"
      ? []
      : decision === "blocked"
        ? [
            "Blocking exposure remains unresolved for at least one material patent family.",
          ]
        : ["Evidence remains mixed across the reviewed record."];

  return {
    decision,
    decision_confidence: getDecisionConfidence(decision),
    evidence_quality: getEvidenceQuality(decision),
    decision_reasoning:
      decision === "clear"
        ? [
            `The reviewed ${TEST_REPORT.audit_trail.patents_analyzed} material patents resolved below the blocking threshold.`,
            "No decisive claim chart or prosecution signal remained unresolved in the demo record.",
          ]
        : decision === "blocked"
          ? [
              `${blockingPatentIds[0] ?? "A lead patent"} remains blocking against the evaluated commercialization path.`,
              "Commercial launch would require either design-around work or external legal resolution before clearance.",
            ]
          : [
              "The current record does not justify a positive clearance conclusion.",
              "Further evidence collection or attorney review is required before launch decisions.",
            ],
    decision_audit: {
      queried_sources_count: queriedSourceNames.length,
      successful_sources_count: successfulSourceEntries.length,
      material_patents_reviewed: TEST_REPORT.audit_trail.patents_analyzed,
      material_us_patents: reviewedPatentIds.filter((patentId) =>
        patentId.startsWith("US"),
      ).length,
      material_ep_patents: reviewedPatentIds.filter((patentId) =>
        patentId.startsWith("EP"),
      ).length,
      patents_with_claims: reviewedPatentIds.length,
      patents_with_family: reviewedPatentIds.length,
      us_patents_with_prosecution_context: reviewedPatentIds.filter(
        (patentId) => patentId.startsWith("US"),
      ).length,
      ep_patents_with_register_context: reviewedPatentIds.filter((patentId) =>
        patentId.startsWith("EP"),
      ).length,
      analysis_failures_count: TEST_REPORT.analysis_failures.length,
      failed_sources: failedSourceEntries.map((entry) => entry.source),
      evidence_sufficient_for_clearance: decision === "clear",
      insufficiency_reasons: insufficiencyReasons,
      evidence_warnings: evidenceWarnings,
      search_iterations:
        decision === "blocked" ? 5 : decision === "unclear" ? 4 : 3,
      coverage_summary: {
        queried_source_names: queriedSourceNames,
        successful_source_names: successfulSourceEntries.map(
          (entry) => entry.source,
        ),
        failed_source_names: failedSourceEntries.map((entry) => entry.source),
        reviewed_patent_ids: reviewedPatentIds,
        reviewed_us_patent_ids: reviewedPatentIds.filter((patentId) =>
          patentId.startsWith("US"),
        ),
        reviewed_ep_patent_ids: reviewedPatentIds.filter((patentId) =>
          patentId.startsWith("EP"),
        ),
        patents_missing_claims: [],
        patents_missing_family_context: [],
        us_patents_missing_prosecution_context: [],
        ep_patents_missing_register_context: [],
        failed_analysis_patent_ids: TEST_REPORT.analysis_failures.map(
          (failure) => failure.patent_id,
        ),
        verification_gaps:
          decision === "clear"
            ? []
            : [
                "Manual legal review is still recommended before commercialization.",
              ],
      },
      decisive_references:
        decision === "clear"
          ? [
              {
                category: "clearance_support",
                summary:
                  "The reviewed demo record did not leave a blocking patent unresolved.",
                source_name: SHOWCASE_FIXTURE_RECEIPT.fixtureId,
              },
            ]
          : blockingPatentIds.map((patentId) => ({
              category: "blocking_patent",
              patent_id: patentId,
              jurisdiction: patentId.slice(0, 2),
              summary: `${patentId} remains a decisive blocker in the demo matter.`,
            })),
    },
  };
}

function buildDemoJurisdictionDecisions(
  overallRisk: RiskLevel,
  analysis: AnalysisListItem,
): Array<Record<string, unknown>> {
  const decision = mapRiskToDecision(overallRisk);
  const reviewedPatentIds = TEST_REPORT.patent_analyses.map(
    (patent) => patent.patent_id,
  );
  const blockingPatentIds = TEST_REPORT.patent_analyses
    .slice(0, analysis.blocking_patents_count ?? 0)
    .map((patent) => patent.patent_id);

  return [
    {
      jurisdiction: "US",
      decision,
      decision_confidence: getDecisionConfidence(decision),
      evidence_quality: getEvidenceQuality(decision),
      reviewed_patent_ids: reviewedPatentIds,
      blocking_patent_ids: blockingPatentIds,
      reasoning:
        decision === "clear"
          ? ["Reviewed US patents resolved below the blocking threshold."]
          : decision === "blocked"
            ? ["At least one reviewed US patent remains blocking."]
            : ["US exposure remains mixed and needs deeper review."],
    },
  ];
}

function buildDemoCommercialExposure(
  overallRisk: RiskLevel,
  analysis: AnalysisListItem,
): Record<string, unknown> {
  const decision = mapRiskToDecision(overallRisk);
  const blockingPatentIds = TEST_REPORT.patent_analyses
    .slice(0, analysis.blocking_patents_count ?? 0)
    .map((patent) => patent.patent_id);

  if (decision === "clear") {
    return {
      damages_injunction_risk: "low",
      business_severity: "low",
      blocking_patent_ids: [],
      rationale: [
        "No immediate blocking exposure appears in the reviewed demo record.",
      ],
      summary:
        "No immediate injunction or damages exposure is indicated by the reviewed demo matter.",
    };
  }

  if (decision === "unclear") {
    return {
      damages_injunction_risk: "medium",
      business_severity: "medium",
      blocking_patent_ids: blockingPatentIds,
      rationale: [
        "The record remains incomplete enough that launch-at-risk exposure cannot be ruled out.",
      ],
      summary:
        "Commercial exposure remains uncertain pending deeper legal review.",
    };
  }

  return {
    damages_injunction_risk: "high",
    business_severity: "high",
    blocking_patent_ids: blockingPatentIds,
    rationale: [
      "A blocking patent remains unresolved in the current demo record.",
    ],
    summary:
      "Commercial launch would face material injunction and damages exposure in the current demo matter.",
  };
}

function buildDemoFutureRisk(
  overallRisk: RiskLevel,
): Array<Record<string, unknown>> {
  const decision = mapRiskToDecision(overallRisk);

  if (decision === "clear") {
    return [
      {
        patent_id: SHOWCASE_PAYLOAD.analysis.families[0].publications.at(-1),
        jurisdiction: SHOWCASE_PAYLOAD.analysis.families[0].publications
          .at(-1)
          ?.slice(0, 2),
        risk_type: "monitoring",
        severity: "low",
        summary:
          "Continue monitoring related continuations and family activity.",
      },
    ];
  }

  return [
    {
      patent_id: SHOWCASE_PAYLOAD.analysis.families[0].publications.at(-1),
      jurisdiction: SHOWCASE_PAYLOAD.analysis.families[0].publications
        .at(-1)
        ?.slice(0, 2),
      risk_type: "pending_continuation",
      severity: decision === "blocked" ? "high" : "medium",
      summary:
        "A related continuation should remain on the monitoring list while clearance remains unresolved.",
    },
  ];
}

function cloneReportForAnalysis(analysis: AnalysisListItem): FTOReport {
  const overallRisk = (analysis.overall_risk ??
    TEST_REPORT.risk_summary.overall_risk) as RiskLevel;
  const report = {
    ...TEST_REPORT,
    report_id: `rpt_${analysis.id}`,
    generated_at: analysis.updated_at,
    compound: {
      ...TEST_REPORT.compound,
      name: analysis.compound_name,
      canonical_smiles: analysis.compound_smiles,
      original_input: analysis.compound_input,
    },
    risk_summary: {
      ...TEST_REPORT.risk_summary,
      overall_risk: overallRisk,
      blocking_patents_count: analysis.blocking_patents_count,
      executive_summary:
        analysis.executive_summary ||
        TEST_REPORT.risk_summary.executive_summary,
    },
    total_patents_found: analysis.total_patents_found,
    estimated_cost_usd: analysis.estimated_cost_usd,
  } as DemoStructuredReport;

  report.clearance_decision = buildDemoClearanceDecision(overallRisk, analysis);
  report.jurisdiction_decisions = buildDemoJurisdictionDecisions(
    overallRisk,
    analysis,
  );
  report.commercial_exposure = buildDemoCommercialExposure(
    overallRisk,
    analysis,
  );
  report.future_risk = buildDemoFutureRisk(overallRisk);

  return report as FTOReport;
}

export function listDemoAnalyses(): AnalysisListItem[] {
  hydratePersistedDemoAnalyses();
  return Array.from(demoAnalyses.values()).sort(
    (a, b) =>
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
}

export function getDemoAnalysis(id: string): AnalysisListItem | null {
  hydratePersistedDemoAnalyses();
  const analysisId = normalizeDemoAnalysisId(id);
  if (!analysisId) {
    return null;
  }

  const analysis = demoAnalyses.get(analysisId);
  if (analysis) {
    return analysis;
  }

  const fallback = isBrowserStorageAvailable()
    ? buildFallbackDemoAnalysis(analysisId)
    : null;
  if (fallback) {
    demoAnalyses.set(fallback.id, fallback);
    persistDemoAnalyses();
    return fallback;
  }

  return null;
}

export function isDemoAnalysisId(id: string | null | undefined): id is string {
  const analysisId = normalizeDemoAnalysisId(id);
  if (!analysisId) {
    return false;
  }

  hydratePersistedDemoAnalyses();
  return (
    demoAnalyses.has(analysisId) || DEMO_ANALYSIS_ID_PATTERN.test(analysisId)
  );
}

export function isSeedDemoAnalysisId(
  id: string | null | undefined,
): id is string {
  const analysisId = normalizeDemoAnalysisId(id);
  return Boolean(analysisId && initialDemoAnalysisIds.has(analysisId));
}

export function createDemoAnalysis(
  input: string | DemoAnalysisCreateInput,
): AnalysisListItem {
  hydratePersistedDemoAnalyses();
  const request = typeof input === "string" ? { compound_input: input } : input;
  const now = new Date().toISOString();
  const nextNumber =
    Math.max(
      ...Array.from(demoAnalyses.keys()).map((id) => {
        const match = id.match(/^ana_demo_(\d+)$/);
        return match ? Number(match[1]) : 0;
      }),
    ) + 1;
  const nextId = `ana_demo_${String(nextNumber).padStart(3, "0")}`;
  const normalized = request.compound_input.trim();
  const title = normalized
    ? normalized
        .split(/\s+/)
        .map((part) => part[0]?.toUpperCase() + part.slice(1))
        .join(" ")
    : "Demo Compound";

  const analysis: AnalysisListItem = {
    ...INITIAL_ANALYSES[0],
    id: nextId,
    compound_input: normalized,
    compound_name: title,
    compound_smiles: INITIAL_ANALYSES[0].compound_smiles,
    executive_summary: `This demo freedom-to-operate screen evaluates ${title} against the same synthetic evidence corpus used for product review. Treat the generated report as a source-linked first-pass example, not a legal clearance opinion.`,
    launch_context: buildDemoLaunchContext({
      ...request,
      compound_input: normalized,
    }),
    share_active: false,
    share_view_count: 0,
    share_last_viewed_at: null,
    created_at: now,
    updated_at: now,
  };

  demoAnalyses.set(analysis.id, analysis);
  persistDemoAnalyses();
  return analysis;
}

export function getDemoReport(analysisId: string): FTOReport | null {
  const analysis = getDemoAnalysis(analysisId);
  if (!analysis || analysis.status !== "completed") {
    return null;
  }

  return cloneReportForAnalysis(analysis);
}

export function getDemoReportSummary(analysisId: string): {
  overall_risk: RiskLevel;
  blocking_patents_count: number;
  total_patents_found: number;
  executive_summary: string;
  risk_ratings_restricted: boolean;
} | null {
  const report = getDemoReport(analysisId);
  if (!report) {
    return null;
  }

  return {
    overall_risk: report.risk_summary.overall_risk,
    blocking_patents_count: report.risk_summary.blocking_patents_count,
    total_patents_found: report.total_patents_found,
    executive_summary: report.risk_summary.executive_summary,
    risk_ratings_restricted: false,
  };
}

export function getDemoSharedReport(token: string): {
  report_id: string;
  share_id: string;
  packet_version: string;
  source_snapshot_at: string;
  pipeline_version: string;
  model_version: string;
  integrity_digest: string;
  compound_name: string;
  overall_risk: RiskLevel;
  blocking_patents_count: number;
  total_patents_found: number;
  executive_summary: string;
  key_findings: string[];
  generated_at: string;
  share_expires_at: string;
  key_patents: {
    patent_number: string;
    risk_level: RiskLevel;
    patent_url: string;
    source_reference: string;
  }[];
} | null {
  if (token !== DEMO_SHARE_TOKEN) {
    return null;
  }

  const report = getDemoReport(DEMO_ANALYSIS_ID);
  if (!report) {
    return null;
  }

  const key_patents = report.patent_analyses.slice(0, 3).map((p) => ({
    patent_number: p.patent_id,
    risk_level: p.risk_level as RiskLevel,
    patent_url: `https://patents.google.com/patent/${encodeURIComponent(
      p.patent_id,
    )}`,
    source_reference: "Google Patents",
  }));

  return {
    report_id: report.report_id,
    share_id: `shr_${SHOWCASE_PAYLOAD.analysis.id}`,
    packet_version: "public-share-v1",
    source_snapshot_at: report.generated_at,
    pipeline_version: "demo-pipeline",
    model_version: "demo-agentic-report",
    integrity_digest: `sha256:${SHOWCASE_FIXTURE_RECEIPT.digest}`,
    compound_name: report.compound.name,
    overall_risk: report.risk_summary.overall_risk,
    blocking_patents_count: report.risk_summary.blocking_patents_count,
    total_patents_found: report.total_patents_found,
    executive_summary: report.risk_summary.executive_summary,
    key_findings: report.risk_summary.key_risks,
    generated_at: report.generated_at,
    share_expires_at: "2027-05-09T11:24:00.000Z",
    key_patents,
  };
}
