import type { FTOReport } from "@praviar/shared-types";

import { DEMO_MODE_ENABLED } from "@/lib/constants";
import { getDemoReport, isDemoAnalysisId } from "@/lib/demo-data";

export interface DemoReportSearchResult {
  patent_id: string;
  section: string;
  relevance: number;
  snippet: string;
}

export interface DemoReportSearchResponse {
  query: string;
  interpreted_query: string;
  results: DemoReportSearchResult[];
  total: number;
}

export type DemoEvidenceSearchRetrievalMode =
  | "report_evidence"
  | "external_evidence";

export interface DemoEvidenceSearchProvenanceItem {
  label: string;
  value: string;
}

export interface DemoEvidenceSearchResult {
  result_id: string;
  title: string;
  summary: string;
  source_name: string;
  authority_tier: string;
  freshness: string;
  artifact_type: string;
  section: string;
  patent_id: string;
  relevance: number;
  provenance: DemoEvidenceSearchProvenanceItem[];
  follow_up_target: {
    target_type: "analysis" | "patent" | "claim";
    target_id: string;
    suggested_note: string;
  } | null;
}

export interface DemoEvidenceSearchResponse {
  query: string;
  interpreted_query: string;
  scope: {
    mode: DemoEvidenceSearchRetrievalMode;
    external_live_retrieval: boolean;
    comment_routing_available: boolean;
    sources_considered: string[];
    governed_note: string;
    provider_capabilities: Array<{
      provider_id?: string;
      provider_name: string;
      provider_class: string;
      provider_status?: string;
      live_retrieval_supported: boolean;
      configured?: boolean;
      configured_for_org?: boolean;
      materialized_in_report?: boolean;
      execution_mode?: string;
      modality_coverage: string[];
      jurisdiction_coverage: string[];
      governance_note: string;
      source_as_of?: string;
      dataset_version?: string;
    }>;
    hybrid_evidence_ready: boolean;
  };
  results: DemoEvidenceSearchResult[];
  total: number;
}

interface RankedDocument<T> {
  item: T;
  text: string;
  title?: string;
  patentId?: string;
}

const MAX_REPORT_RESULTS = 8;
const MAX_EVIDENCE_RESULTS = 10;

function shouldUseDemoSearch(analysisId: string | null | undefined) {
  return DEMO_MODE_ENABLED && isDemoAnalysisId(analysisId);
}

function normalizeQuery(query: string) {
  return query.trim().replace(/\s+/g, " ");
}

function tokenize(query: string) {
  return normalizeQuery(query)
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((token) => token.length >= 3);
}

function compactText(parts: Array<string | number | null | undefined>) {
  return parts
    .filter(
      (part): part is string | number => part !== null && part !== undefined,
    )
    .map((part) => String(part).trim())
    .filter(Boolean)
    .join(" ");
}

function truncateSnippet(text: string, maxLength = 280) {
  const compacted = text.replace(/\s+/g, " ").trim();
  if (compacted.length <= maxLength) return compacted;
  return `${compacted.slice(0, maxLength - 1).trimEnd()}...`;
}

function scoreText(text: string, query: string, tokens: string[]) {
  const haystack = text.toLowerCase();
  const normalizedQuery = query.toLowerCase();
  let score = haystack.includes(normalizedQuery) ? 4 : 0;

  for (const token of tokens) {
    if (haystack.includes(token)) score += 1;
  }

  return score;
}

function rankDocuments<T>(
  docs: Array<RankedDocument<T>>,
  query: string,
  tokens: string[],
) {
  return docs
    .map((doc, index) => ({
      ...doc,
      index,
      score:
        scoreText(doc.text, query, tokens) +
        scoreText(doc.title ?? "", query, tokens) * 1.4 +
        scoreText(doc.patentId ?? "", query, tokens) * 2,
    }))
    .filter((doc) => doc.score > 0)
    .sort((a, b) => b.score - a.score || a.index - b.index);
}

function getDemoSearchReport(analysisId: string): FTOReport | null {
  if (!shouldUseDemoSearch(analysisId)) return null;
  return getDemoReport(analysisId);
}

function buildReportDocuments(report: FTOReport) {
  const documents: Array<RankedDocument<DemoReportSearchResult>> = [
    {
      patentId: report.report_id,
      title: "Risk summary",
      text: compactText([
        report.compound.name,
        report.risk_summary.overall_risk,
        report.risk_summary.executive_summary,
        ...(report.risk_summary.key_risks ?? []),
      ]),
      item: {
        patent_id: report.report_id,
        section: "Risk summary",
        relevance: 0,
        snippet: truncateSnippet(report.risk_summary.executive_summary),
      },
    },
  ];

  for (const patent of report.patent_analyses ?? []) {
    documents.push({
      patentId: patent.patent_id,
      title: patent.title,
      text: compactText([
        patent.patent_id,
        patent.title,
        patent.assignee,
        patent.risk_level,
        patent.risk_summary,
      ]),
      item: {
        patent_id: patent.patent_id,
        section: "Patent analysis",
        relevance: 0,
        snippet: truncateSnippet(
          compactText([patent.title, patent.assignee, patent.risk_summary]),
        ),
      },
    });

    for (const claim of patent.claims_analyzed ?? []) {
      const claimText = compactText([
        patent.patent_id,
        patent.title,
        `Claim ${claim.claim_number}`,
        claim.claim_type,
        claim.preamble,
        claim.overall_status,
        claim.reasoning,
        ...(claim.elements ?? []).flatMap((element) => [
          element.element_text,
          element.status,
          element.reasoning,
          element.evidence,
        ]),
      ]);

      documents.push({
        patentId: patent.patent_id,
        title: `Claim ${claim.claim_number}`,
        text: claimText,
        item: {
          patent_id: patent.patent_id,
          section: `Claim ${claim.claim_number}`,
          relevance: 0,
          snippet: truncateSnippet(claimText),
        },
      });
    }

    for (const suggestion of patent.design_around_suggestions ?? []) {
      const designAroundText = compactText([
        patent.patent_id,
        patent.title,
        "design around",
        suggestion.element_avoided,
        suggestion.suggestion,
        suggestion.feasibility,
      ]);

      documents.push({
        patentId: patent.patent_id,
        title: "Design-around option",
        text: designAroundText,
        item: {
          patent_id: patent.patent_id,
          section: "Design-around",
          relevance: 0,
          snippet: truncateSnippet(designAroundText),
        },
      });
    }
  }

  return documents;
}

function buildEvidenceDocuments(report: FTOReport, analysisId: string) {
  const documents: Array<RankedDocument<DemoEvidenceSearchResult>> = [];

  for (const patent of report.patent_analyses ?? []) {
    documents.push({
      patentId: patent.patent_id,
      title: patent.title,
      text: compactText([
        patent.patent_id,
        patent.title,
        patent.assignee,
        patent.risk_level,
        patent.risk_summary,
      ]),
      item: {
        result_id: `demo-${patent.patent_id}-risk-summary`,
        title: `Risk rationale: ${patent.patent_id}`,
        summary: truncateSnippet(patent.risk_summary, 360),
        source_name: "Demo report claim analysis",
        authority_tier:
          patent.risk_level === "high" ? "material" : "supporting",
        freshness: "report snapshot",
        artifact_type: "patent_risk_summary",
        section: "patents",
        patent_id: patent.patent_id,
        relevance: 0,
        provenance: [
          { label: "report_id", value: report.report_id },
          { label: "assignee", value: patent.assignee ?? "Unknown" },
          { label: "risk_level", value: patent.risk_level },
        ],
        follow_up_target: {
          target_type: "patent",
          target_id: patent.patent_id,
          suggested_note: `Review ${patent.patent_id} risk rationale against the launch path.`,
        },
      },
    });

    for (const claim of patent.claims_analyzed ?? []) {
      for (const element of claim.elements ?? []) {
        const elementText = compactText([
          patent.patent_id,
          patent.title,
          `Claim ${claim.claim_number}`,
          `Element ${element.element_number}`,
          claim.overall_status,
          element.status,
          element.element_text,
          element.reasoning,
          element.evidence,
        ]);

        documents.push({
          patentId: patent.patent_id,
          title: `Claim ${claim.claim_number} element ${element.element_number}`,
          text: elementText,
          item: {
            result_id: `demo-${patent.patent_id}-claim-${claim.claim_number}-element-${element.element_number}`,
            title: `${patent.patent_id} claim ${claim.claim_number}, element ${element.element_number}`,
            summary: truncateSnippet(
              compactText([
                element.element_text,
                element.reasoning,
                element.evidence,
              ]),
              360,
            ),
            source_name: "Demo claim element evidence",
            authority_tier:
              element.status === "met" ? "material" : "supporting",
            freshness: "report snapshot",
            artifact_type: "claim_element",
            section: "claims",
            patent_id: patent.patent_id,
            relevance: 0,
            provenance: [
              { label: "report_id", value: report.report_id },
              { label: "claim", value: String(claim.claim_number) },
              { label: "element", value: String(element.element_number) },
              { label: "status", value: element.status },
            ],
            follow_up_target: {
              target_type: "claim",
              target_id: `${patent.patent_id}:claim-${claim.claim_number}:element-${element.element_number}`,
              suggested_note: `Check claim ${claim.claim_number}, element ${element.element_number} for ${patent.patent_id}.`,
            },
          },
        });
      }
    }
  }

  documents.push({
    patentId: report.report_id,
    title: "Report decision context",
    text: compactText([
      report.compound.name,
      report.risk_summary.overall_risk,
      report.risk_summary.executive_summary,
      ...(report.risk_summary.key_risks ?? []),
    ]),
    item: {
      result_id: `demo-${analysisId}-decision-context`,
      title: "Decision context from the demo report",
      summary: truncateSnippet(report.risk_summary.executive_summary, 360),
      source_name: "Demo report risk summary",
      authority_tier: "material",
      freshness: "report snapshot",
      artifact_type: "risk_summary",
      section: "summary",
      patent_id: report.report_id,
      relevance: 0,
      provenance: [
        { label: "report_id", value: report.report_id },
        { label: "compound", value: report.compound.name },
      ],
      follow_up_target: {
        target_type: "analysis",
        target_id: analysisId,
        suggested_note: "Review the report decision context for this search.",
      },
    },
  });

  return documents;
}

function withRelevance<T extends { relevance: number }>(
  item: T,
  score: number,
  maxScore: number,
) {
  return {
    ...item,
    relevance: Number(
      (0.72 + (score / Math.max(maxScore, 1)) * 0.25).toFixed(2),
    ),
  };
}

export function buildDemoReportSearchResponse(
  analysisId: string,
  rawQuery: string,
): DemoReportSearchResponse | null {
  const query = normalizeQuery(rawQuery);
  const report = getDemoSearchReport(analysisId);
  if (!report || !query) return null;

  const tokens = tokenize(query);
  const ranked = rankDocuments(buildReportDocuments(report), query, tokens);
  const maxScore = ranked[0]?.score ?? 1;
  const results = ranked
    .slice(0, MAX_REPORT_RESULTS)
    .map((doc) => withRelevance(doc.item, doc.score, maxScore));

  return {
    query,
    interpreted_query: `${query} in the materialized demo report`,
    results,
    total: results.length,
  };
}

export function buildDemoEvidenceSearchResponse(
  analysisId: string,
  rawQuery: string,
  retrievalMode: DemoEvidenceSearchRetrievalMode,
): DemoEvidenceSearchResponse | null {
  const query = normalizeQuery(rawQuery);
  const report = getDemoSearchReport(analysisId);
  if (!report || !query) return null;

  const tokens = tokenize(query);
  const ranked = rankDocuments(
    buildEvidenceDocuments(report, analysisId),
    query,
    tokens,
  );
  const maxScore = ranked[0]?.score ?? 1;
  const results = ranked
    .slice(0, MAX_EVIDENCE_RESULTS)
    .map((doc) => withRelevance(doc.item, doc.score, maxScore));

  return {
    query,
    interpreted_query: `${query} in the governed demo evidence snapshot`,
    scope: {
      mode: retrievalMode,
      external_live_retrieval: false,
      comment_routing_available: true,
      sources_considered: [
        "demo_report_fixture",
        "claim_element_evidence",
        "risk_summary",
      ],
      governed_note:
        retrievalMode === "external_evidence"
          ? "Local demo mode uses the materialized report snapshot; live external retrieval is disabled until connected to the API."
          : "Report-grounded demo search stays inside materialized report artifacts, claim evidence, and risk rationale.",
      provider_capabilities: [
        {
          provider_id: "demo_report_derived",
          provider_name: "Demo report-derived evidence layer",
          provider_class: "report_derived",
          provider_status: "active",
          live_retrieval_supported: false,
          configured: true,
          configured_for_org: true,
          materialized_in_report: true,
          execution_mode: "report_materialized",
          modality_coverage: ["small_molecule", "process"],
          jurisdiction_coverage: ["US", "EP", "WO", "JP"],
          governance_note:
            "Uses only the bundled demo report record, so shared demo links do not depend on backend availability.",
          source_as_of: report.generated_at,
          dataset_version: "demo_report_fixture",
        },
      ],
      hybrid_evidence_ready: false,
    },
    results,
    total: results.length,
  };
}
