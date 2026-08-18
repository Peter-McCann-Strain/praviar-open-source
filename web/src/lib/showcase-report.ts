import {
  showcaseFixture,
  type ShowcasePayload,
} from "@praviar/showcase-fixture";
import type {
  FTOReport,
  PatentAnalysis,
  PipelineAuditTrail,
  SourceHealth,
  VerificationResult,
} from "@praviar/shared-types";

type AnalysisPayload = ShowcasePayload["analysis"];

export interface CanonicalShowcaseReport extends FTOReport {
  report_id: string;
  generated_at: string;
  praviar_pipeline_version: string;
  patent_analyses: PatentAnalysis[];
  verification: VerificationResult;
  audit_trail: PipelineAuditTrail;
  source_health: SourceHealth;
  claim_source_span_map: NonNullable<FTOReport["claim_source_span_map"]>;
  total_patents_found: number;
  patents_after_triage: number;
  search_sources_used: string[];
  analysis_failures: NonNullable<FTOReport["analysis_failures"]>;
  data_limitations: NonNullable<FTOReport["data_limitations"]>;
  llm_models_used: NonNullable<FTOReport["llm_models_used"]>;
  total_input_tokens: number;
  total_output_tokens: number;
  estimated_cost_usd: number;
}

export const SHOWCASE_FIXTURE_RECEIPT = Object.freeze({
  schemaVersion: showcaseFixture.schema_version,
  fixtureId: showcaseFixture.fixture_id,
  fixtureVersion: showcaseFixture.fixture_version,
  digestAlgorithm: showcaseFixture.fixture_digest_algorithm,
  digest: showcaseFixture.fixture_digest,
});

export const SHOWCASE_PAYLOAD = showcaseFixture.payload;

function postureRisk(
  posture: AnalysisPayload["families"][number]["posture"],
): "medium" | "clear" {
  return posture === "potential_blocking_claim_identified" ? "medium" : "clear";
}

function claimStatus(
  mapping: AnalysisPayload["families"][number]["claims"][number]["mapping"],
): "unclear" | "not_met" {
  return mapping === "candidate_overlap" ? "unclear" : "not_met";
}

const evidenceById = new Map(
  SHOWCASE_PAYLOAD.analysis.evidence.map((evidence) => [evidence.id, evidence]),
);

const patentAnalyses: PatentAnalysis[] = SHOWCASE_PAYLOAD.analysis.families.map(
  (family) => ({
    patent_id: family.publications[0],
    jurisdiction: family.publications[0].slice(0, 2),
    title: family.title,
    assignee: family.assignee,
    expiry_date: null,
    claims_analyzed: family.claims.map((claim) => ({
      claim_number: Number(claim.number),
      claim_type: "independent",
      preamble: "A wholly fictional demonstration claim",
      transitional_phrase: "comprising",
      preamble_limiting: "unresolved",
      elements: [
        {
          element_number: 1,
          element_text: claim.text,
          status: claimStatus(claim.mapping),
          reasoning: claim.review_note,
          confidence: claim.confidence === "medium" ? 0.5 : 0.25,
          evidence: claim.review_note,
          uncertainty_note: claim.review_note,
        },
      ],
      reasoning: claim.review_note,
      overall_status: claimStatus(claim.mapping),
      overall_confidence: claim.confidence === "medium" ? 0.5 : 0.25,
      uncertainty_note: claim.review_note,
    })),
    risk_level: postureRisk(family.posture),
    risk_summary:
      family.posture === "potential_blocking_claim_identified"
        ? "The synthetic claim map requires qualified human review; it is not a blocking conclusion."
        : "No overlap is shown in this synthetic record; no real-world conclusion is represented.",
    design_around_suggestions: [],
    orange_book_info: null,
    model_used: "deterministic-showcase-adapter-v1",
    thinking_text: "",
    input_tokens: 0,
    output_tokens: 0,
    analysis_review_required: true,
  }),
);

const spans = Object.fromEntries(
  SHOWCASE_PAYLOAD.analysis.families.flatMap((family) =>
    family.claims.map((claim) => {
      const evidence = evidenceById.get(family.evidence_ids[0]);
      const spanId = `span-${claim.id}`;
      return [
        spanId,
        {
          span_id: spanId,
          source_type: "claim_text" as const,
          patent_id: family.publications[0],
          claim_number: Number(claim.number),
          element_number: 1,
          citation: evidence?.source_reference ?? family.publications[0],
          excerpt: claim.text,
          source_document_id: evidence?.id ?? family.id,
          source_name: evidence?.source_id ?? "synthetic_showcase",
          source_text_sha256: evidence?.content_sha256 ?? "",
          source_retrieved_at: evidence?.retrieved_at,
          source_artifact_locator: `praviar-showcase://${evidence?.id ?? family.id}`,
          collector_identity: "praviar.canonical_showcase_fixture",
          collector_version: showcaseFixture.fixture_version,
          provenance_schema_version: showcaseFixture.schema_version,
          retrieval_complete: true,
        },
      ];
    }),
  ),
);

const claimEntries = SHOWCASE_PAYLOAD.analysis.families.flatMap((family) =>
  family.claims.map((claim) => ({
    assertion_id: `assertion-${claim.id}`,
    patent_id: family.publications[0],
    claim_number: Number(claim.number),
    element_number: 1,
    report_section: "fictional_claim_map",
    assertion_text: claim.review_note,
    source_span_ids: [`span-${claim.id}`],
    support_status: "needs_review" as const,
    customer_visible: true,
    review_required: true,
  })),
);

const sourceHealthEntries = SHOWCASE_PAYLOAD.analysis.searched_sources.map(
  (source) => ({
    source: source.label,
    status:
      source.status === "complete" ? ("ok" as const) : ("failed" as const),
    patent_count: SHOWCASE_PAYLOAD.analysis.families.length,
    attempted_count: SHOWCASE_PAYLOAD.analysis.families.length,
    covered_count:
      source.status === "complete"
        ? SHOWCASE_PAYLOAD.analysis.families.length
        : 1,
    error_message:
      source.status === "partial"
        ? "The canonical fixture intentionally models partial synthetic coverage."
        : "",
  }),
);

const executiveSummaryBase =
  "This wholly fictional research preview demonstrates how a submitted identity, synthetic source coverage, candidate families, claim-level evidence and explicit limitations are kept together. One synthetic family contains an unresolved candidate overlap, so the only supported outcome is review required. No live search or legal conclusion is represented.";
const firstPatentId = patentAnalyses[0]?.patent_id;
const hasFirstCitationSource = claimEntries.some(
  (entry) =>
    entry.patent_id === firstPatentId &&
    entry.source_span_ids.some((spanId) => {
      const span = spans[spanId];
      return Boolean(span?.citation.trim() && span.excerpt.trim());
    }),
);
const executiveSummary = hasFirstCitationSource
  ? `${executiveSummaryBase} [1]`
  : executiveSummaryBase;

export const SHOWCASE_REPORT: CanonicalShowcaseReport = {
  report_id: `rpt_${SHOWCASE_PAYLOAD.analysis.id}`,
  generated_at: SHOWCASE_PAYLOAD.analysis.completed_at,
  praviar_pipeline_version: `showcase-fixture-${showcaseFixture.fixture_version}`,
  compound: {
    name: SHOWCASE_PAYLOAD.compound.display_name,
    canonical_smiles: "",
    inchi: "",
    inchi_key: "",
    pubchem_cid: null,
    synonyms: [SHOWCASE_PAYLOAD.compound.submitted_identity],
    cas_numbers: [],
    molecular_formula: "",
    molecular_weight: null,
    functional_groups: [],
    related_compounds: [],
    original_input: SHOWCASE_PAYLOAD.compound.submitted_identity,
    input_type: "name",
    compound_type: "small_molecule",
  },
  risk_summary: {
    overall_risk: "medium",
    blocking_patents_count: 0,
    total_patents_analyzed: patentAnalyses.length,
    key_risks: [
      "One synthetic claim mapping remains unresolved and requires qualified review.",
      "One synthetic source intentionally reports partial coverage.",
    ],
    executive_summary: executiveSummary,
    summary_validation_issues: ["Synthetic fixture; no live legal evidence."],
  },
  clearance_decision: {
    decision: "unclear",
    decision_confidence: 0,
    evidence_quality: 0,
    decision_reasoning: [
      "The record is wholly synthetic and cannot support a clearance decision.",
      "A qualified reviewer must assess any real matter independently.",
    ],
    decision_audit: {
      queried_sources_count: sourceHealthEntries.length,
      successful_sources_count: sourceHealthEntries.filter(
        (entry) => entry.status === "ok",
      ).length,
      material_patents_reviewed: patentAnalyses.length,
      patents_with_claims: patentAnalyses.length,
      patents_with_family: patentAnalyses.length,
      evidence_sufficient_for_clearance: false,
      insufficiency_reasons: SHOWCASE_PAYLOAD.analysis.limitations,
      evidence_warnings: [SHOWCASE_PAYLOAD.disclaimer],
    },
  },
  trust_mode: "explorer",
  intended_actions: ["diligence_screen"],
  target_jurisdictions: [...SHOWCASE_PAYLOAD.compound.jurisdictions],
  jurisdiction_bundle: "fictional_showcase",
  development_stage: "demonstration_only",
  asset_type_hint: "withheld_fictional_placeholder",
  routing_profile: { showcase_fixture: SHOWCASE_FIXTURE_RECEIPT },
  opinion_readiness: {
    trust_mode: "explorer",
    attorney_supervision_required: true,
    export_ready: false,
    jurisdictions_blocking_export: [...SHOWCASE_PAYLOAD.compound.jurisdictions],
    gate_failures: SHOWCASE_PAYLOAD.failure_states.map(
      (failure) => failure.message,
    ),
    summary: SHOWCASE_PAYLOAD.export.watermark,
  },
  patent_analyses: patentAnalyses,
  doe_assessments: [],
  invalidity_assessments: [],
  verification: {
    checks: [
      {
        check_name: "canonical_fixture_digest",
        passed: true,
        severity: "pass",
        details: `Payload is bound to ${showcaseFixture.fixture_digest}.`,
      },
      {
        check_name: "synthetic_source_boundary",
        passed: true,
        severity: "warning",
        details:
          "Every displayed source and evidence record is explicitly synthetic.",
      },
      {
        check_name: "human_review_gate",
        passed: true,
        severity: "warning",
        details: SHOWCASE_PAYLOAD.failure_states[1].message,
      },
    ],
    all_citations_valid: true,
    all_claims_grounded: true,
    all_entities_valid: true,
    dates_consistent: true,
    risk_levels_justified: true,
    issues: SHOWCASE_PAYLOAD.analysis.limitations,
  },
  claim_source_span_map: {
    generated_from: showcaseFixture.fixture_id,
    entries: claimEntries,
    spans,
    unsupported_customer_visible_claim_count: 0,
    needs_review_count: claimEntries.length,
  },
  total_patents_found: patentAnalyses.length,
  patents_after_triage: patentAnalyses.length,
  search_sources_used: SHOWCASE_PAYLOAD.analysis.searched_sources.map(
    (source) => source.label,
  ),
  source_health: { entries: sourceHealthEntries },
  analysis_failures: [],
  data_limitations: SHOWCASE_PAYLOAD.analysis.limitations.map((limitation) => ({
    category: "synthetic_showcase",
    description: limitation,
    impact:
      "This demonstration cannot support a real legal or commercial decision.",
  })),
  audit_trail: {
    search_funnel: SHOWCASE_PAYLOAD.analysis.families.map((family, index) => ({
      patent_id: family.publications[0],
      candidate_index: index,
      sources_found_in: SHOWCASE_PAYLOAD.analysis.searched_sources.map(
        (source) => source.label,
      ),
      disposition: "included_in_triage",
      passed_hard_filter: true,
      filter_reason: "",
      composite_score: null,
      bm25_score: null,
      final_blend_score: null,
      final_rank: index + 1,
      included_in_triage: true,
    })),
    triage_audit: patentAnalyses.map((patent) => ({
      patent_id: patent.patent_id,
      relevance: "synthetic_showcase",
      reason: "Included by the canonical fictional showcase fixture.",
      confidence: 0,
      passed_triage: true,
    })),
    analysis_audit: patentAnalyses.map((patent) => ({
      patent_id: patent.patent_id,
      selected_for_analysis: true,
      selection_reason: "Included by the canonical fictional showcase fixture.",
      risk_level: patent.risk_level,
      selected_for_doe: false,
      selected_for_invalidity: false,
    })),
    timing_data: SHOWCASE_PAYLOAD.analysis.pipeline_steps.map(
      (step, index) => ({
        step_name: step.id,
        started_at: SHOWCASE_PAYLOAD.analysis.started_at,
        completed_at: SHOWCASE_PAYLOAD.analysis.completed_at,
        duration_seconds:
          index === 0 ? 120 : index === 1 ? 480 : index === 2 ? 840 : 0,
        items_processed: step.evidence_count,
        items_output: step.evidence_count,
      }),
    ),
    total_patents_discovered: patentAnalyses.length,
    patents_after_hard_filter: patentAnalyses.length,
    patents_after_ranking: patentAnalyses.length,
    patents_after_triage: patentAnalyses.length,
    patents_analyzed: patentAnalyses.length,
  },
  patent_narratives: Object.fromEntries(
    patentAnalyses.map((patent) => [patent.patent_id, patent.risk_summary]),
  ),
  disclaimer: SHOWCASE_PAYLOAD.disclaimer,
  llm_models_used: { adapter: "deterministic-showcase-adapter-v1" },
  action_items: [],
  step_token_usage: [],
  total_input_tokens: 0,
  total_output_tokens: 0,
  estimated_cost_usd: 0,
};
