import type {
  FTOReport,
  PatentAnalysis,
  RiskLevel,
} from "@praviar/shared-types";

import { getDemoReport, isDemoAnalysisId } from "@/lib/demo-data";

interface DemoReportChatCitation {
  cited_text: string;
  document_index: number;
  document_title?: string;
  patent_id?: string;
  claim_number?: number | string | null;
  element_number?: number | string | null;
  source_url?: string;
}

export interface DemoReportChatResponse {
  citations: DemoReportChatCitation[];
  content: string;
  conversationId: string;
  workspaceMeta: {
    trust_mode: "counsel";
    mode_label: string;
    capability_label: string;
    scope_label: string;
    source_coverage?: string;
    evidence_mode: string;
    monitor_state: string;
    tool_access: string[];
  };
}

const RISK_WEIGHT: Record<RiskLevel, number> = {
  high: 0,
  medium: 1,
  low: 2,
  clear: 3,
};

function sentence(value: string | undefined): string {
  if (!value) return "";
  const trimmed = value.trim();
  if (!trimmed) return "";
  const first = trimmed.split(/\n\n|(?<=\.)\s+/)[0]?.trim() ?? trimmed;
  return first.endsWith(".") ? first : `${first}.`;
}

function formatPatentLabel(patent: PatentAnalysis): string {
  return [patent.patent_id, patent.assignee].filter(Boolean).join(" / ");
}

function getSortedPatents(report: FTOReport): PatentAnalysis[] {
  return [...(report.patent_analyses ?? [])].sort((a, b) => {
    const riskDelta = RISK_WEIGHT[a.risk_level] - RISK_WEIGHT[b.risk_level];
    if (riskDelta !== 0) return riskDelta;
    return a.patent_id.localeCompare(b.patent_id);
  });
}

function getMaterialPatents(
  report: FTOReport,
  patentId?: string,
): PatentAnalysis[] {
  const patents = getSortedPatents(report);
  if (patentId) {
    const matched = patents.find((patent) => patent.patent_id === patentId);
    if (matched) return [matched];
  }

  const material = patents.filter((patent) =>
    ["high", "medium"].includes(patent.risk_level),
  );
  return (material.length > 0 ? material : patents).slice(0, 3);
}

function buildCitation(
  patent: PatentAnalysis,
  documentIndex: number,
): DemoReportChatCitation {
  const claim = patent.claims_analyzed?.find(
    (candidate) => candidate.claim_number != null,
  );
  const element = claim?.elements?.find(
    (candidate) => candidate.element_number != null,
  );

  return {
    cited_text: sentence(patent.risk_summary),
    document_index: documentIndex,
    document_title: `${patent.patent_id}${patent.title ? ` - ${patent.title}` : ""}`,
    patent_id: patent.patent_id,
    claim_number: claim?.claim_number ?? null,
    element_number: element?.element_number ?? null,
  };
}

function buildCitationSet(patents: PatentAnalysis[]): DemoReportChatCitation[] {
  return patents.map((patent, index) => buildCitation(patent, index));
}

function buildBlockerBrief(
  report: FTOReport,
  patents: PatentAnalysis[],
): string {
  const blockers = patents
    .map((patent) => {
      const designAround = patent.design_around_suggestions?.[0]?.suggestion;
      return `- ${formatPatentLabel(patent)}: ${patent.risk_level.toUpperCase()} risk. ${sentence(
        patent.risk_summary,
      )}${designAround ? ` Primary design-around: ${designAround}` : ""}`;
    })
    .join("\n");

  const gaps = report.coverage_gaps?.slice(0, 2).map((gap) => gap.description);
  const gapCopy = gaps?.length
    ? `\n\nOpen reliability checks:\n${gaps.map((gap) => `- ${gap}`).join("\n")}`
    : "";

  return [
    `Blocker brief for ${report.compound.name}: ${report.risk_summary.overall_risk.toUpperCase()} overall risk with ${
      report.risk_summary.blocking_patents_count ?? patents.length
    } blocking patent${(report.risk_summary.blocking_patents_count ?? patents.length) === 1 ? "" : "s"} flagged.`,
    "",
    blockers,
    gapCopy,
    "",
    "Recommended next move: send the high-risk claim elements and the strongest design-around route to counsel before relying on this report for commercial action.",
  ]
    .filter(Boolean)
    .join("\n");
}

function buildReviewQuestions(
  report: FTOReport,
  patents: PatentAnalysis[],
): string {
  const questions = patents
    .flatMap((patent) => {
      const claim = patent.claims_analyzed?.[0];
      return [
        `- For ${formatPatentLabel(patent)}, should claim ${claim?.claim_number ?? "1"} be construed broadly enough to cover the evaluated process?`,
        patent.design_around_suggestions?.[0]
          ? `- Is the proposed design-around for ${patent.patent_id} commercially feasible without creating a new equivalence theory?`
          : null,
      ];
    })
    .filter((item): item is string => Boolean(item));

  return [
    `Counsel review queue for ${report.compound.name}:`,
    "",
    ...questions.slice(0, 6),
    "- Confirm whether any prosecution history, family status, or local jurisdiction evidence changes the launch decision.",
  ].join("\n");
}

function buildDesignAroundBrief(
  report: FTOReport,
  patents: PatentAnalysis[],
): string {
  const suggestions = patents
    .flatMap((patent) =>
      (patent.design_around_suggestions ?? []).slice(0, 2).map((item) => ({
        patent,
        item,
      })),
    )
    .slice(0, 5);

  if (!suggestions.length) {
    return `I do not see a structured design-around suggestion in the demo report for ${report.compound.name}. Escalate the material claims to counsel before treating this as clear.`;
  }

  return [
    `Design-around options for ${report.compound.name}:`,
    "",
    ...suggestions.map(
      ({ patent, item }) =>
        `- ${formatPatentLabel(patent)}: avoid element ${item.element_avoided} by ${item.suggestion}${
          item.feasibility ? ` Feasibility: ${item.feasibility}` : ""
        }`,
    ),
    "",
    "Treat these as decision-support hypotheses. They still need claim construction, process feasibility, and jurisdiction-specific counsel review.",
  ].join("\n");
}

function buildDefaultSummary(
  report: FTOReport,
  patents: PatentAnalysis[],
): string {
  const keyRisks = report.risk_summary.key_risks?.slice(0, 3) ?? [];
  const patentLines = patents.map(
    (patent) =>
      `- ${formatPatentLabel(patent)}: ${patent.risk_level.toUpperCase()} risk.`,
  );

  return [
    `Summary for ${report.compound.name}: ${sentence(
      report.risk_summary.executive_summary,
    )}`,
    "",
    keyRisks.length ? "Key risks:" : "Material patents:",
    ...(keyRisks.length ? keyRisks.map((risk) => `- ${risk}`) : patentLines),
    "",
    "This demo answer is grounded in the local report packet and keeps the same caveat as the report: it is not a legal clearance opinion.",
  ].join("\n");
}

function classifyPrompt(message: string) {
  const normalized = message.toLowerCase();
  if (
    normalized.includes("block") ||
    normalized.includes("highest") ||
    normalized.includes("risk") ||
    normalized.includes("brief")
  ) {
    return "blocker_brief";
  }
  if (
    normalized.includes("design-around") ||
    normalized.includes("design around") ||
    normalized.includes("available")
  ) {
    return "design_around";
  }
  if (
    normalized.includes("question") ||
    normalized.includes("counsel") ||
    normalized.includes("review")
  ) {
    return "review_questions";
  }
  return "summary";
}

export function buildDemoReportChatResponse({
  analysisId,
  message,
  patentId,
}: {
  analysisId: string | null;
  message: string;
  patentId?: string;
}): DemoReportChatResponse | null {
  if (!isDemoAnalysisId(analysisId)) return null;

  const report = getDemoReport(analysisId);
  if (!report) return null;

  const patents = getMaterialPatents(report, patentId);
  if (!patents.length) return null;

  const promptType = classifyPrompt(message);
  const content =
    promptType === "blocker_brief"
      ? buildBlockerBrief(report, patents)
      : promptType === "review_questions"
        ? buildReviewQuestions(report, patents)
        : promptType === "design_around"
          ? buildDesignAroundBrief(report, patents)
          : buildDefaultSummary(report, patents);

  return {
    citations: buildCitationSet(patents),
    content,
    conversationId: `demo-report-chat-${analysisId}`,
    workspaceMeta: {
      trust_mode: "counsel",
      mode_label: "Counsel demo workspace",
      capability_label: "Report-grounded demo answers",
      scope_label: patentId ? `Patent ${patentId}` : "Full FTO report",
      source_coverage: report.search_sources_used?.join(", "),
      evidence_mode: "Demo report-grounded only",
      monitor_state: "Live monitoring actions disabled in demo",
      tool_access: ["report_grounded_qna", "review_handoff_draft"],
    },
  };
}
