import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  createDemoReviewerDecision,
  getDemoReviewerDecisions,
  resetDemoReviewerDecisions,
} from "@/lib/demo-reviewer-decisions";
import { SHOWCASE_REPORT } from "@/lib/showcase-report";

describe("canonical demo reviewer decisions", () => {
  beforeEach(() => {
    resetDemoReviewerDecisions();
    vi.useRealTimers();
  });

  it("seeds the completed showcase without legacy identities", () => {
    const response = getDemoReviewerDecisions("ana_demo_001");
    const serialized = JSON.stringify(response);

    expect(response.items[0]?.finding_ref).toBe(
      SHOWCASE_REPORT.patent_analyses[0]?.patent_id,
    );
    expect(response.counts).toEqual({ accept: 0, reject: 0, edit: 1 });
    expect(serialized).not.toMatch(
      /Succinic acid|US0000000001A1|Aspirin|Ibuprofen|Ada Reviewer|ada\.reviewer|@praviar\.example/i,
    );
    expect(response.items[0]).toMatchObject({
      reviewer_user_id: "user-fictional-reviewer",
      reviewer_name: "Fictional reviewer",
      reviewer_email: "reviewer@fictional.invalid",
    });
  });

  it("keeps a saved decision available to the active demo session", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2031-02-03T04:05:06.000Z"));

    const created = createDemoReviewerDecision("ana_demo_001", {
      finding_type: "claim_element",
      finding_ref: "claim-fictional-1:element-1",
      decision: "accept",
      note: "Synthetic review state saved for the gallery.",
    });
    const response = getDemoReviewerDecisions("ana_demo_001");

    expect(created.created_at).toBe("2031-02-03T04:05:06.000Z");
    expect(response.items).toContainEqual(created);
    expect(response.counts).toEqual({ accept: 1, reject: 0, edit: 1 });
  });

  it("isolates mutable decision state between demo analyses", () => {
    expect(getDemoReviewerDecisions("ana_demo_002")).toEqual({
      items: [],
      counts: { accept: 0, reject: 0, edit: 0 },
    });

    createDemoReviewerDecision("ana_demo_002", {
      finding_type: "patent",
      finding_ref: "XX-FICTION-0002-A1",
      decision: "accept",
    });

    expect(getDemoReviewerDecisions("ana_demo_002").counts).toEqual({
      accept: 1,
      reject: 0,
      edit: 0,
    });
    expect(getDemoReviewerDecisions("ana_demo_001").counts).toEqual({
      accept: 0,
      reject: 0,
      edit: 1,
    });
  });
});
