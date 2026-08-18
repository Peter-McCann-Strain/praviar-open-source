import { SHOWCASE_PAYLOAD, SHOWCASE_REPORT } from "@/lib/showcase-report";

export type FindingType = "patent" | "claim_element" | "doe" | "invalidity";
export type Decision = "accept" | "reject" | "edit";

export interface ReviewerDecision {
  id: string;
  finding_type: FindingType;
  finding_ref: string;
  decision: Decision;
  note: string;
  edited_text: string;
  reviewer_user_id: string;
  reviewer_name: string;
  reviewer_email: string;
  created_at: string;
  updated_at: string;
}

export interface ReviewerDecisionInput {
  finding_type: FindingType;
  finding_ref: string;
  decision: Decision;
  note?: string;
  edited_text?: string;
}

export interface ReviewerDecisionListResponse {
  items: ReviewerDecision[];
  counts: {
    accept: number;
    reject: number;
    edit: number;
  };
}

const canonicalPatentId = SHOWCASE_REPORT.patent_analyses[0]?.patent_id;

if (!canonicalPatentId) {
  throw new Error("Canonical showcase report has no reviewable patent finding");
}

const seedDecision: ReviewerDecision = {
  id: "reviewer-decision-fictional-1",
  finding_type: "patent",
  finding_ref: canonicalPatentId,
  decision: "edit",
  note: "Qualified counsel must verify the fictional claim mapping before any downstream use.",
  edited_text:
    "Synthetic finding retained with an explicit human-verification requirement.",
  reviewer_user_id: "user-fictional-reviewer",
  reviewer_name: "Fictional reviewer",
  reviewer_email: "reviewer@fictional.invalid",
  created_at: SHOWCASE_PAYLOAD.analysis.completed_at,
  updated_at: SHOWCASE_PAYLOAD.analysis.completed_at,
};

const decisionsByAnalysis = new Map<string, ReviewerDecision[]>();

function cloneDecision(value: ReviewerDecision): ReviewerDecision {
  return { ...value };
}

function decisionStore(analysisId: string): ReviewerDecision[] {
  const existing = decisionsByAnalysis.get(analysisId);
  if (existing) return existing;

  const initial =
    analysisId === "ana_demo_001" ? [cloneDecision(seedDecision)] : [];
  decisionsByAnalysis.set(analysisId, initial);
  return initial;
}

function summarize(items: ReviewerDecision[]): ReviewerDecisionListResponse {
  return {
    items: items.map(cloneDecision),
    counts: {
      accept: items.filter((item) => item.decision === "accept").length,
      reject: items.filter((item) => item.decision === "reject").length,
      edit: items.filter((item) => item.decision === "edit").length,
    },
  };
}

export function getDemoReviewerDecisions(
  analysisId: string,
): ReviewerDecisionListResponse {
  return summarize(decisionStore(analysisId));
}

export function createDemoReviewerDecision(
  analysisId: string,
  input: ReviewerDecisionInput,
): ReviewerDecision {
  const store = decisionStore(analysisId);
  const timestamp = new Date().toISOString();
  const decision: ReviewerDecision = {
    id: `reviewer-decision-fictional-${store.length + 1}`,
    finding_type: input.finding_type,
    finding_ref: input.finding_ref,
    decision: input.decision,
    note: input.note ?? "",
    edited_text: input.edited_text ?? "",
    reviewer_user_id: "user-fictional-reviewer",
    reviewer_name: "Fictional reviewer",
    reviewer_email: "reviewer@fictional.invalid",
    created_at: timestamp,
    updated_at: timestamp,
  };
  store.push(decision);
  return cloneDecision(decision);
}

export function resetDemoReviewerDecisions(): void {
  decisionsByAnalysis.clear();
}
