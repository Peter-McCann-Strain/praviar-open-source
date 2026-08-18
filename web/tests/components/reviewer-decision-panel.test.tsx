import { describe, expect, it, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import * as React from "react";

import { ReviewerDecisionPanel } from "@/components/report/reviewer-decision-panel";
import { emitAuthBoundaryChanged } from "@/lib/auth-events";
import { APIError } from "@/lib/api-client";

const apiMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    apiClient: (...args: unknown[]) => apiMock(...args),
  };
});

function Wrapped({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const SAMPLE_REPORT = {
  patents: [
    { patent_id: "US-12345-B2", assignee: "Acme Pharma", risk_level: "HIGH" },
    { patent_id: "EP-999-A1", assignee: "Bio Corp", risk_level: "LOW" },
  ],
};

function renderPanel(
  overrides: {
    initialFindingRef?: string;
    onClose?: () => void;
    report?: unknown;
    reviewStatus?: React.ComponentProps<
      typeof ReviewerDecisionPanel
    >["reviewStatus"];
  } = {},
) {
  return render(
    <Wrapped>
      <ReviewerDecisionPanel
        open
        onClose={overrides.onClose ?? (() => {})}
        analysisId="abc"
        initialFindingRef={overrides.initialFindingRef}
        token="tok"
        report={overrides.report ?? SAMPLE_REPORT}
        reviewStatus={overrides.reviewStatus}
      />
    </Wrapped>,
  );
}

async function waitForReviewerDecisionsReady() {
  const ledger = screen.getByRole("status", {
    name: "Review ledger summary",
  });
  await waitFor(() => {
    expect(ledger).not.toHaveTextContent("Loading decision ledger");
  });
}

describe("ReviewerDecisionPanel", () => {
  beforeEach(() => {
    apiMock.mockReset();
    // Default GET response: no existing decisions.
    apiMock.mockResolvedValue({
      items: [],
      counts: { accept: 0, reject: 0, edit: 0 },
    });
  });

  it("renders one row per patent finding from the report", () => {
    renderPanel();
    expect(
      screen.getByTestId("reviewer-finding-US-12345-B2"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("reviewer-finding-EP-999-A1"),
    ).toBeInTheDocument();
  });

  it("keeps the report identity and research boundary visible inside the modal", () => {
    renderPanel({
      report: {
        compound: { name: "Example Molecule Alpha" },
        disclaimer:
          "Fictional research preview for software demonstration only. Not legal advice or an FTO opinion.",
        patents: SAMPLE_REPORT.patents,
      },
    });

    const context = screen.getByRole("note", { name: "Review context" });
    expect(context).toHaveTextContent("Example Molecule Alpha");
    expect(context).toHaveTextContent("research preview");
    expect(context).toHaveTextContent("Not legal advice");
    expect(context.closest("header")).toHaveClass("sticky");
  });

  it("fails closed when a report has no usable compound identity", () => {
    renderPanel({ report: { compound: { name: "   " }, patents: [] } });

    const context = screen.getByRole("note", { name: "Review context" });
    expect(context).toHaveTextContent("Report identity unavailable");
    expect(context).not.toHaveTextContent("Example Molecule Alpha");
    expect(context).toHaveTextContent("Research boundary unavailable");
    expect(context).not.toHaveTextContent("not legal advice");
  });

  it("derives review coverage from the same findings rendered in the ledger", async () => {
    apiMock.mockResolvedValue({
      items: [
        {
          id: "decision-us",
          finding_type: "patent",
          finding_ref: "US-12345-B2",
          decision: "accept",
          note: "",
          edited_text: "",
          reviewer_user_id: "reviewer-us",
          reviewer_name: "US Counsel",
          reviewer_email: "us@example.test",
          created_at: "2026-04-24T10:00:00.000Z",
          updated_at: "2026-04-24T10:00:00.000Z",
        },
        {
          id: "decision-ep",
          finding_type: "patent",
          finding_ref: "EP-999-A1",
          decision: "edit",
          note: "",
          edited_text: "Edited EP finding.",
          reviewer_user_id: "reviewer-ep",
          reviewer_name: "EP Counsel",
          reviewer_email: "ep@example.test",
          created_at: "2026-04-24T10:01:00.000Z",
          updated_at: "2026-04-24T10:01:00.000Z",
        },
      ],
      counts: { accept: 1, reject: 0, edit: 1 },
    });
    renderPanel({
      reviewStatus: {
        analysis_id: "abc",
        status: "under_review",
        note: "Review in progress.",
        reviewer_name: "Patent Counsel",
        reviewer_email: "counsel@example.test",
        reviewed_at: null,
        updated_at: "2026-04-24T10:00:00.000Z",
        decision_counts: { accept: 1, reject: 0, edit: 1 },
        findings_total: 4,
        findings_reviewed: 2,
        completion_pct: 50,
      },
    });

    await waitForReviewerDecisionsReady();

    const ledger = screen.getByRole("status", {
      name: "Review ledger summary",
    });

    expect(ledger).toHaveTextContent("Decision ledger scope");
    expect(ledger).toHaveTextContent("2 / 2 panel findings decided");
    expect(ledger).toHaveTextContent("Decision mix");
    expect(ledger).toHaveTextContent("1 accepted / 1 edited");
  });

  it("uses the refreshed decision ledger for the saved mix and persisted rationale", async () => {
    const editedDecision = {
      id: "decision-existing-edit",
      finding_type: "patent",
      finding_ref: "US-12345-B2",
      decision: "edit",
      note: "Existing counsel qualification.",
      edited_text: "Existing edited finding.",
      reviewer_user_id: "reviewer-existing",
      reviewer_name: "Existing reviewer",
      reviewer_email: "existing@example.test",
      created_at: "2026-04-24T10:00:00.000Z",
      updated_at: "2026-04-24T10:00:00.000Z",
    };
    const rejectedDecision = {
      id: "decision-saved-reject",
      finding_type: "patent",
      finding_ref: "EP-999-A1",
      decision: "reject",
      note: "Qualified reviewer rejected this finding after source review.",
      edited_text: "",
      reviewer_user_id: "reviewer-saved",
      reviewer_name: "Saving reviewer",
      reviewer_email: "saving@example.test",
      created_at: "2026-04-24T10:01:00.000Z",
      updated_at: "2026-04-24T10:01:00.000Z",
    };
    apiMock
      .mockResolvedValueOnce({
        items: [editedDecision],
        counts: { accept: 0, reject: 0, edit: 1 },
      })
      .mockResolvedValueOnce(rejectedDecision)
      .mockResolvedValueOnce({
        items: [editedDecision, rejectedDecision],
        counts: { accept: 0, reject: 1, edit: 1 },
      });

    renderPanel({
      reviewStatus: {
        analysis_id: "abc",
        status: "under_review",
        note: "Review in progress.",
        reviewer_name: "Patent Counsel",
        reviewer_email: "counsel@example.test",
        reviewed_at: null,
        updated_at: "2026-04-24T10:00:00.000Z",
        // The status endpoint has not observed the new save yet. The open
        // ledger must describe the exact decisions it is already rendering.
        decision_counts: { accept: 0, reject: 0, edit: 1 },
        findings_total: 2,
        findings_reviewed: 1,
        completion_pct: 50,
      },
    });
    await waitForReviewerDecisionsReady();

    const finding = screen.getByTestId("reviewer-finding-EP-999-A1");
    fireEvent.click(within(finding).getByRole("radio", { name: "reject" }));
    fireEvent.change(screen.getByTestId("reviewer-note-EP-999-A1"), {
      target: {
        value: "Qualified reviewer rejected this finding after source review.",
      },
    });
    fireEvent.click(screen.getByTestId("reviewer-submit-EP-999-A1"));

    const ledger = screen.getByRole("status", {
      name: "Review ledger summary",
    });
    await waitFor(() => {
      expect(ledger).toHaveTextContent("1 edited / 1 rejected");
      expect(
        within(finding).getByTestId(
          "reviewer-persisted-decision-decision-saved-reject",
        ),
      ).toHaveTextContent(
        "Saved rationale: Qualified reviewer rejected this finding after source review.",
      );
    });
    expect(ledger).toHaveTextContent("2 / 2 panel findings decided");
    expect(screen.getByTestId("reviewer-note-EP-999-A1")).toHaveValue("");
  });

  it("renders findings from canonical patent_analyses reports", () => {
    render(
      <Wrapped>
        <ReviewerDecisionPanel
          open
          onClose={() => {}}
          analysisId="abc"
          token="tok"
          report={{
            patent_analyses: [
              {
                patent_id: "US-CANONICAL-1",
                assignee: "Canonical Pharma",
                risk_level: "MEDIUM",
              },
            ],
          }}
        />
      </Wrapped>,
    );

    expect(
      screen.getByTestId("reviewer-finding-US-CANONICAL-1"),
    ).toBeInTheDocument();
  });

  it("prefers canonical patent_analyses over stale patent arrays", () => {
    render(
      <Wrapped>
        <ReviewerDecisionPanel
          open
          onClose={() => {}}
          analysisId="abc"
          token="tok"
          report={{
            patent_analyses: [
              {
                patent_id: "US-CANONICAL-1",
                assignee: "Canonical Pharma",
                risk_level: "MEDIUM",
              },
            ],
            patents: [
              {
                patent_id: "US-STALE-1",
                assignee: "Stale Pharma",
                risk_level: "HIGH",
              },
            ],
          }}
        />
      </Wrapped>,
    );

    expect(
      screen.getByTestId("reviewer-finding-US-CANONICAL-1"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("reviewer-finding-US-STALE-1"),
    ).not.toBeInTheDocument();
  });

  it("renders findings keyed only by publication_number", () => {
    render(
      <Wrapped>
        <ReviewerDecisionPanel
          open
          onClose={() => {}}
          analysisId="abc"
          token="tok"
          report={{
            patent_analyses: [
              {
                publication_number: "WO-2026-123456",
                assignee: "Fallback Pharma",
                risk_level: "HIGH",
              },
            ],
          }}
        />
      </Wrapped>,
    );

    expect(
      screen.getByTestId("reviewer-finding-WO-2026-123456"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("reviewer-review-progress-WO-2026-123456"),
    ).toHaveTextContent("0/2 reviews");
  });

  it("renders findings keyed only by patent_number", () => {
    render(
      <Wrapped>
        <ReviewerDecisionPanel
          open
          onClose={() => {}}
          analysisId="abc"
          token="tok"
          report={{
            patent_analyses: [
              {
                patent_number: "US-PATENT-NUMBER-1",
                assignee: "Patent Number Pharma",
                risk_level: "HIGH",
              },
            ],
          }}
        />
      </Wrapped>,
    );

    expect(
      screen.getByTestId("reviewer-finding-US-PATENT-NUMBER-1"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("reviewer-review-progress-US-PATENT-NUMBER-1"),
    ).toHaveTextContent("0/2 reviews");
  });

  it("shows an empty state when there are no findings", () => {
    render(
      <Wrapped>
        <ReviewerDecisionPanel
          open
          onClose={() => {}}
          analysisId="abc"
          token="tok"
          report={{ patents: [] }}
        />
      </Wrapped>,
    );
    expect(screen.getByText(/No findings available/i)).toBeInTheDocument();
  });

  it("locks decision controls when decision access is restricted", async () => {
    apiMock.mockRejectedValue(new APIError(403, "Forbidden"));

    renderPanel();

    expect(
      await screen.findByText("Reviewer decisions access restricted"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("reviewer-decisions-load-error")).toHaveAttribute(
      "role",
      "alert",
    );
    expect(screen.getByText("Decision ledger unavailable")).toBeInTheDocument();
    expect(
      screen.queryByText("No reviewer decisions recorded"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId("reviewer-decision-US-12345-B2-accept"),
    ).toBeDisabled();
    expect(screen.getByTestId("reviewer-note-US-12345-B2")).toBeDisabled();
    expect(screen.getByTestId("reviewer-submit-US-12345-B2")).toBeDisabled();

    fireEvent.click(
      screen.getByRole("button", { name: "Retry decision load" }),
    );

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2));
  });

  it("locks decision controls on transient decision-load failures", async () => {
    apiMock.mockRejectedValue(new Error("decision service unavailable"));

    renderPanel();

    expect(
      await screen.findByText("Reviewer decisions temporarily unavailable"),
    ).toBeInTheDocument();
    expect(screen.getByText("Decision ledger unavailable")).toBeInTheDocument();
    expect(
      screen.queryByText(/decision service unavailable/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("No reviewer decisions recorded"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId("reviewer-decision-US-12345-B2-reject"),
    ).toBeDisabled();
    expect(screen.getByTestId("reviewer-submit-US-12345-B2")).toBeDisabled();
  });

  it("disables submit until a decision button has been clicked", async () => {
    renderPanel();
    await waitForReviewerDecisionsReady();

    const submit = screen.getByTestId("reviewer-submit-US-12345-B2");
    expect(submit).toBeDisabled();
    fireEvent.click(screen.getByTestId("reviewer-decision-US-12345-B2-accept"));
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByTestId("reviewer-note-US-12345-B2"), {
      target: { value: "Reviewed the cited claim and legal-status evidence." },
    });
    expect(submit).toBeEnabled();
  });

  it("requires edited_text before submit when decision = edit", async () => {
    renderPanel();
    await waitForReviewerDecisionsReady();

    fireEvent.click(screen.getByTestId("reviewer-decision-US-12345-B2-edit"));
    const submit = screen.getByTestId("reviewer-submit-US-12345-B2");
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByTestId("reviewer-edit-US-12345-B2"), {
      target: { value: "Corrected claim scope analysis." },
    });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByTestId("reviewer-note-US-12345-B2"), {
      target: { value: "The cited limitation requires this correction." },
    });
    expect(submit).toBeEnabled();
  });

  it("POSTs the decision with the right payload on submit", async () => {
    // GET (from the query) then POST (from mutate).
    apiMock
      .mockResolvedValueOnce({
        items: [],
        counts: { accept: 0, reject: 0, edit: 0 },
      })
      .mockResolvedValueOnce({ id: "new-1", decision: "reject" });

    renderPanel();
    await waitForReviewerDecisionsReady();

    fireEvent.click(screen.getByTestId("reviewer-decision-US-12345-B2-reject"));
    fireEvent.change(screen.getByTestId("reviewer-note-US-12345-B2"), {
      target: { value: "Not blocking; pre-AIA filing." },
    });
    fireEvent.click(screen.getByTestId("reviewer-submit-US-12345-B2"));

    await waitFor(() => {
      const postCall = apiMock.mock.calls.find(
        ([, opts]) => opts && opts.method === "POST",
      );
      expect(postCall).toBeDefined();
      const [path, opts] = postCall!;
      expect(path).toBe("/analyses/abc/decisions");
      const body = JSON.parse(opts.body);
      expect(body).toMatchObject({
        finding_type: "patent",
        finding_ref: "US-12345-B2",
        decision: "reject",
        note: "Not blocking; pre-AIA filing.",
        edited_text: "",
      });
    });
  });

  it("retains the reviewer's selected decision and note when the save is rejected", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    apiMock
      .mockResolvedValueOnce({
        items: [],
        counts: { accept: 0, reject: 0, edit: 0 },
      })
      .mockRejectedValueOnce(new Error("decision service unavailable"))
      .mockResolvedValueOnce({
        items: [],
        counts: { accept: 0, reject: 0, edit: 0 },
      });

    renderPanel();
    await waitForReviewerDecisionsReady();

    const reject = screen.getByTestId("reviewer-decision-US-12345-B2-reject");
    const note = screen.getByTestId("reviewer-note-US-12345-B2");
    fireEvent.click(reject);
    fireEvent.change(note, {
      target: { value: "Preserve this counsel rationale for retry." },
    });
    fireEvent.click(screen.getByTestId("reviewer-submit-US-12345-B2"));

    await waitFor(() =>
      expect(
        screen.getByTestId("reviewer-submit-US-12345-B2"),
      ).toHaveTextContent("Check decision ledger"),
    );
    expect(reject).toHaveAttribute("aria-checked", "true");
    expect(note).toHaveValue("Preserve this counsel rationale for retry.");
    expect(
      screen.getByTestId("reviewer-save-error-US-12345-B2"),
    ).toHaveTextContent("Save outcome unknown.");
    expect(
      screen.getByTestId("reviewer-save-error-US-12345-B2"),
    ).toHaveTextContent("Check the reviewer ledger before retrying.");

    fireEvent.click(screen.getByTestId("reviewer-submit-US-12345-B2"));
    await waitFor(() =>
      expect(
        screen.getByTestId("reviewer-submit-US-12345-B2"),
      ).toHaveTextContent("Retry save"),
    );
    expect(
      screen.getByTestId("reviewer-save-error-US-12345-B2"),
    ).toHaveTextContent("Decision not found after ledger refresh.");
    expect(note).toHaveValue("Preserve this counsel rationale for retry.");
    consoleError.mockRestore();
  });

  it("reconciles a committed reviewer decision before offering any retry", async () => {
    const committedDecision = {
      id: "decision-committed-after-timeout",
      finding_type: "patent",
      finding_ref: "US-12345-B2",
      decision: "reject",
      note: "Response was lost after commit.",
      edited_text: "",
      reviewer_user_id: "reviewer-1",
      reviewer_name: "Patent Counsel",
      reviewer_email: "counsel@example.test",
      created_at: "2026-07-16T12:00:00.000Z",
      updated_at: "2026-07-16T12:00:00.000Z",
    };
    apiMock
      .mockResolvedValueOnce({
        items: [],
        counts: { accept: 0, reject: 0, edit: 0 },
      })
      .mockRejectedValueOnce(new Error("response lost"))
      .mockResolvedValueOnce({
        items: [committedDecision],
        counts: { accept: 0, reject: 1, edit: 0 },
      });

    renderPanel();
    await waitForReviewerDecisionsReady();

    fireEvent.click(screen.getByTestId("reviewer-decision-US-12345-B2-reject"));
    fireEvent.change(screen.getByTestId("reviewer-note-US-12345-B2"), {
      target: { value: "Response was lost after commit." },
    });
    fireEvent.click(screen.getByTestId("reviewer-submit-US-12345-B2"));

    await screen.findByText("Save outcome unknown.");
    fireEvent.click(screen.getByTestId("reviewer-submit-US-12345-B2"));

    await waitFor(() => {
      expect(
        screen.queryByTestId("reviewer-save-error-US-12345-B2"),
      ).not.toBeInTheDocument();
      expect(
        screen.getByTestId("reviewer-submit-US-12345-B2"),
      ).toHaveTextContent("Save my decision");
    });
    expect(apiMock).toHaveBeenCalledTimes(3);
  });

  it("locks all decision controls while a reviewer decision save is pending", async () => {
    apiMock
      .mockResolvedValueOnce({
        items: [],
        counts: { accept: 0, reject: 0, edit: 0 },
      })
      .mockImplementationOnce(() => new Promise(() => undefined));

    renderPanel();
    await waitForReviewerDecisionsReady();

    fireEvent.click(screen.getByTestId("reviewer-decision-EP-999-A1-accept"));
    fireEvent.click(screen.getByTestId("reviewer-decision-US-12345-B2-reject"));
    fireEvent.change(screen.getByTestId("reviewer-note-US-12345-B2"), {
      target: {
        value: "The finding conflicts with the cited prosecution record.",
      },
    });
    fireEvent.click(screen.getByTestId("reviewer-submit-US-12345-B2"));

    await waitFor(() => {
      expect(
        screen.getByTestId("reviewer-submit-US-12345-B2"),
      ).toHaveTextContent("Saving...");
    });

    expect(screen.getByRole("dialog")).toHaveAttribute("aria-busy", "true");
    expect(
      screen.getByTestId("reviewer-decision-EP-999-A1-edit"),
    ).toBeDisabled();
    expect(screen.getByTestId("reviewer-note-EP-999-A1")).toBeDisabled();
    expect(screen.getByTestId("reviewer-submit-EP-999-A1")).toBeDisabled();

    fireEvent.click(screen.getByTestId("reviewer-submit-EP-999-A1"));
    const postCalls = apiMock.mock.calls.filter(
      ([, opts]) => opts && opts.method === "POST",
    );
    expect(postCalls).toHaveLength(1);
  });

  it("shows the current decision when one exists", async () => {
    apiMock.mockResolvedValue({
      items: [
        {
          id: "d1",
          finding_type: "patent",
          finding_ref: "US-12345-B2",
          decision: "accept",
          note: "",
          edited_text: "",
          reviewer_user_id: "u1",
          reviewer_name: "Jane Attorney",
          reviewer_email: "j@example.com",
          created_at: "2026-04-15T12:00:00Z",
          updated_at: "2026-04-15T12:00:00Z",
        },
      ],
      counts: { accept: 1, reject: 0, edit: 0 },
    });
    renderPanel();
    const el = await screen.findByTestId("reviewer-finding-existing");
    expect(el).toHaveTextContent("Accepted · 1 reviewer");
    expect(el).not.toHaveTextContent("Jane Attorney");
    expect(
      screen.getByTestId("reviewer-persisted-decision-d1"),
    ).toHaveTextContent("No reviewer note was recorded.");
  });

  it("shows all conflicting reviewer decisions without choosing a person's draft", async () => {
    apiMock.mockResolvedValue({
      items: [
        {
          id: "d1",
          finding_type: "patent",
          finding_ref: "US-12345-B2",
          decision: "accept",
          note: "First reviewer note",
          edited_text: "",
          reviewer_user_id: "u1",
          reviewer_name: "Reviewer One",
          reviewer_email: "one@example.test",
          created_at: "2026-04-15T12:00:00Z",
          updated_at: "2026-04-15T12:00:00Z",
        },
        {
          id: "d2",
          finding_type: "patent",
          finding_ref: "US-12345-B2",
          decision: "reject",
          note: "Second reviewer note",
          edited_text: "",
          reviewer_user_id: "u2",
          reviewer_name: "Reviewer Two",
          reviewer_email: "two@example.test",
          created_at: "2026-04-15T12:01:00Z",
          updated_at: "2026-04-15T12:01:00Z",
        },
      ],
      counts: { accept: 1, reject: 1, edit: 0 },
    });

    renderPanel();

    const summary = await screen.findByTestId("reviewer-finding-existing");
    expect(summary).toHaveTextContent("Conflict · 1 accept / 1 reject");
    expect(summary).not.toHaveTextContent("Reviewer One");
    expect(summary).not.toHaveTextContent("Reviewer Two");
    const persisted = screen.getByTestId(
      "reviewer-persisted-decisions-US-12345-B2",
    );
    expect(persisted).toHaveTextContent("First reviewer note");
    expect(persisted).toHaveTextContent("Second reviewer note");
    expect(screen.getByTestId("reviewer-note-US-12345-B2")).toHaveValue("");
    expect(
      screen.getByTestId("reviewer-decision-US-12345-B2-accept"),
    ).toHaveAttribute("aria-checked", "false");
    expect(
      screen.getByTestId("reviewer-decision-US-12345-B2-reject"),
    ).toHaveAttribute("aria-checked", "false");
    expect(screen.getByTestId("reviewer-submit-US-12345-B2")).toBeDisabled();
  });

  it("shows required review progress for high and medium findings", async () => {
    apiMock.mockResolvedValue({
      items: [
        {
          id: "d1",
          finding_type: "patent",
          finding_ref: "US-12345-B2",
          decision: "accept",
          note: "",
          edited_text: "",
          reviewer_user_id: "u1",
          reviewer_name: "Jane Attorney",
          reviewer_email: "j@example.com",
          created_at: "2026-04-15T12:00:00Z",
          updated_at: "2026-04-15T12:00:00Z",
        },
      ],
      counts: { accept: 1, reject: 0, edit: 0 },
    });

    render(
      <Wrapped>
        <ReviewerDecisionPanel
          open
          onClose={() => {}}
          analysisId="abc"
          token="tok"
          report={{
            patents: [
              { patent_id: "US-12345-B2", risk_level: "HIGH" },
              { patent_id: "US-MED-1", risk_level: "medium" },
              { patent_id: "US-LOW-1", risk_level: "low" },
            ],
          }}
        />
      </Wrapped>,
    );

    await waitFor(() => {
      expect(
        screen.getByTestId("reviewer-review-progress-US-12345-B2"),
      ).toHaveTextContent("1/2 reviews");
    });
    expect(
      screen.getByTestId("reviewer-review-progress-US-MED-1"),
    ).toHaveTextContent("0/1 reviews");
    expect(
      screen.queryByTestId("reviewer-review-progress-US-LOW-1"),
    ).not.toBeInTheDocument();
  });

  it("renders review-required claim source-span entries", () => {
    renderPanel({
      report: {
        patents: [],
        claim_source_span_map: {
          generated_from: "test_fixture",
          entries: [
            {
              assertion_id: "assertion-needs-review-1",
              patent_id: "US-HIGH-1",
              claim_number: 1,
              element_number: 2,
              report_section: "claim_element_analysis",
              assertion_text: "Claim 1 element 2 was assessed as unclear.",
              source_span_ids: [],
              support_status: "needs_review",
              customer_visible: true,
              review_required: true,
            },
          ],
          spans: {},
          unsupported_customer_visible_claim_count: 0,
          needs_review_count: 1,
        },
      },
    });

    const finding = screen.getByTestId(
      "reviewer-finding-assertion-needs-review-1",
    );
    expect(finding).toHaveTextContent("Claim 1 element 2");
    expect(finding).toHaveTextContent("US-HIGH-1");
    expect(finding).toHaveTextContent("NEEDS REVIEW");
    expect(finding).toHaveTextContent(
      "Claim 1 element 2 was assessed as unclear.",
    );
    expect(
      screen.getByTestId("reviewer-review-progress-assertion-needs-review-1"),
    ).toHaveTextContent("0/1 reviews");
  });

  it("focuses a claim finding opened from the decision matrix", async () => {
    renderPanel({
      initialFindingRef: "assertion-needs-review-1",
      report: {
        patents: [],
        claim_source_span_map: {
          entries: [
            {
              assertion_id: "assertion-needs-review-1",
              patent_id: "US-HIGH-1",
              claim_number: 1,
              element_number: 2,
              report_section: "claim_element_analysis",
              assertion_text: "Claim 1 element 2 needs review.",
              source_span_ids: [],
              support_status: "needs_review",
              customer_visible: true,
              review_required: true,
            },
          ],
          spans: {},
        },
      },
    });

    const finding = screen.getByTestId(
      "reviewer-finding-assertion-needs-review-1",
    );
    await waitFor(() => expect(finding).toHaveFocus());
  });

  it("POSTs claim element decisions with the assertion id", async () => {
    apiMock
      .mockResolvedValueOnce({
        items: [],
        counts: { accept: 0, reject: 0, edit: 0 },
      })
      .mockResolvedValueOnce({ id: "claim-decision-1", decision: "accept" });

    renderPanel({
      report: {
        patents: [],
        claim_source_span_map: {
          generated_from: "test_fixture",
          entries: [
            {
              assertion_id: "assertion-needs-review-1",
              patent_id: "US-HIGH-1",
              claim_number: 1,
              element_number: 2,
              report_section: "claim_element_analysis",
              assertion_text: "Claim 1 element 2 was assessed as unclear.",
              source_span_ids: [],
              support_status: "needs_review",
              customer_visible: true,
              review_required: true,
            },
          ],
          spans: {},
          unsupported_customer_visible_claim_count: 0,
          needs_review_count: 1,
        },
      },
    });

    await waitForReviewerDecisionsReady();

    fireEvent.click(
      screen.getByTestId("reviewer-decision-assertion-needs-review-1-accept"),
    );
    fireEvent.click(
      screen.getByTestId("reviewer-submit-assertion-needs-review-1"),
    );

    await waitFor(() => {
      const postCall = apiMock.mock.calls.find(
        ([, opts]) => opts && opts.method === "POST",
      );
      expect(postCall).toBeDefined();
      const [path, opts] = postCall!;
      expect(path).toBe("/analyses/abc/decisions");
      const body = JSON.parse(opts.body);
      expect(body).toMatchObject({
        finding_type: "claim_element",
        finding_ref: "assertion-needs-review-1",
        decision: "accept",
        note: "",
        edited_text: "",
      });
    });
  });

  it("calls onClose when the close button is clicked", () => {
    const onClose = vi.fn();
    renderPanel({ onClose });
    fireEvent.click(screen.getByTestId("reviewer-decision-panel-close"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("focuses the close control, closes on Escape, and restores opener focus", async () => {
    function ControlledPanel() {
      const [open, setOpen] = React.useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            Open reviewer panel
          </button>
          <ReviewerDecisionPanel
            open={open}
            onClose={() => setOpen(false)}
            analysisId="abc"
            token="tok"
            report={SAMPLE_REPORT}
          />
        </>
      );
    }

    render(
      <Wrapped>
        <ControlledPanel />
      </Wrapped>,
    );
    const opener = screen.getByRole("button", { name: "Open reviewer panel" });
    opener.focus();
    fireEvent.click(opener);

    const closeButton = await screen.findByTestId(
      "reviewer-decision-panel-close",
    );
    await waitFor(() => expect(closeButton).toHaveFocus());

    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(opener).toHaveFocus();
  });

  it("locks background page scroll while the reviewer panel is open", () => {
    const previousOverflow = document.body.style.overflow;
    const { unmount } = renderPanel();

    expect(document.body.style.overflow).toBe("hidden");

    unmount();
    expect(document.body.style.overflow).toBe(previousOverflow);
  });

  it("makes the background inert while preserving the modal portal", () => {
    const { container, unmount } = renderPanel();

    expect(container).toHaveAttribute("aria-hidden", "true");
    expect(container).toHaveProperty("inert", true);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    unmount();

    expect(container).not.toHaveAttribute("aria-hidden");
    expect(container.inert).not.toBe(true);
  });

  it("traps reverse tab navigation inside the reviewer dialog", async () => {
    renderPanel();
    await waitForReviewerDecisionsReady();

    const dialog = screen.getByRole("dialog");
    const closeButton = screen.getByTestId("reviewer-decision-panel-close");
    closeButton.focus();

    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });

    expect(screen.getByTestId("reviewer-note-EP-999-A1")).toHaveFocus();
  });

  it("uses mobile-safe dialog geometry and touch-safe action controls", () => {
    renderPanel();

    const dialog = screen.getByRole("dialog");
    const panel = screen.getByTestId(
      "reviewer-decision-panel",
    ).firstElementChild;
    const finding = screen.getByTestId("reviewer-finding-US-12345-B2");
    const group = within(finding).getByRole("radiogroup", {
      name: "Decision for US-12345-B2",
    });

    expect(dialog).toHaveClass("max-h-[calc(100dvh-3rem)]");
    expect(panel?.parentElement).toHaveClass("items-center");
    expect(panel?.parentElement).toHaveClass(
      "praviar-overlay-scrim-strong",
      "z-[200]",
      "isolate",
      "pointer-events-auto",
    );
    expect(panel).toHaveClass(
      "max-h-[calc(100dvh-3rem)]",
      "relative",
      "z-[1]",
      "overscroll-contain",
    );
    expect(within(finding).getByText("US-12345-B2")).toHaveClass(
      "break-all",
      "[overflow-wrap:anywhere]",
    );
    expect(group).toHaveClass("grid", "w-full", "grid-cols-3", "sm:w-auto");
    expect(screen.getByTestId("reviewer-decision-panel-close")).toHaveClass(
      "h-11",
      "min-h-11",
      "w-11",
      "min-w-11",
      "shrink-0",
    );
    for (const option of ["accept", "reject", "edit"]) {
      expect(within(group).getByRole("radio", { name: option })).toHaveClass(
        "min-h-11",
        "w-full",
        "sm:w-auto",
      );
    }
    expect(screen.getByTestId("reviewer-submit-US-12345-B2")).toHaveClass(
      "min-h-11",
    );
  });

  it("exposes decision choices as radios inside each finding group", async () => {
    renderPanel();
    await waitForReviewerDecisionsReady();

    const finding = screen.getByTestId("reviewer-finding-US-12345-B2");
    const group = within(finding).getByRole("radiogroup", {
      name: "Decision for US-12345-B2",
    });

    expect(
      within(group).getByRole("radio", { name: "accept" }),
    ).toHaveAttribute("aria-checked", "false");
    expect(screen.getByTestId("reviewer-submit-US-12345-B2")).toBeDisabled();
    fireEvent.click(within(group).getByRole("radio", { name: "reject" }));
    expect(
      within(group).getByRole("radio", { name: "reject" }),
    ).toHaveAttribute("aria-checked", "true");
  });

  it("clears private reviewer decision drafts on auth boundary changes", async () => {
    renderPanel();
    await waitForReviewerDecisionsReady();

    fireEvent.click(screen.getByTestId("reviewer-decision-US-12345-B2-edit"));
    fireEvent.change(screen.getByTestId("reviewer-edit-US-12345-B2"), {
      target: { value: "private edited finding" },
    });
    fireEvent.change(screen.getByTestId("reviewer-note-US-12345-B2"), {
      target: { value: "private reviewer note" },
    });

    expect(screen.getByTestId("reviewer-edit-US-12345-B2")).toHaveValue(
      "private edited finding",
    );
    expect(screen.getByTestId("reviewer-note-US-12345-B2")).toHaveValue(
      "private reviewer note",
    );

    act(() => {
      emitAuthBoundaryChanged({ refreshToken: false });
    });

    expect(
      screen.queryByTestId("reviewer-edit-US-12345-B2"),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("reviewer-note-US-12345-B2")).toHaveValue("");
    expect(screen.getByTestId("reviewer-submit-US-12345-B2")).toBeDisabled();
  });
});
