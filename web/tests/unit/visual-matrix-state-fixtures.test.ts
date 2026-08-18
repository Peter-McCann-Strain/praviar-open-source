import { describe, expect, it } from "vitest";
import {
  buildClaimDecisionMatrixModel,
  hasCompleteVerifiedClaimReceipt,
} from "../../src/components/report/claim-decision-matrix-model";
import type { FTOReport } from "@praviar/shared-types";
import {
  VISUAL_MATRIX_API_KEY_ID,
  VISUAL_MATRIX_API_REPORT_ID,
  VISUAL_MATRIX_CLAIM_ASSERTION_ID,
  VISUAL_MATRIX_CLAIM_SOURCE_SPAN_ID,
  VISUAL_MATRIX_COMMENT_ID,
  VISUAL_MATRIX_CREDIT_CHECKOUT_SESSION_ID,
  VISUAL_MATRIX_LAUNCHED_ANALYSIS_ID,
  VISUAL_MATRIX_MONITOR_ALERT_ID,
  VISUAL_MATRIX_MONITOR_ID,
  VISUAL_MATRIX_REVIEW_LIFECYCLE_AUDIT_NOTE,
} from "../e2e/fixtures/visual-matrix-routes";
import {
  CLAIM_DECISION_MATRIX_REPORT,
  COMPLETED_EXPORT_BODY,
  REPORT_CHAT_SUCCESS_STREAM,
  REVIEW_LIFECYCLE_MUTATION_ACK,
  REVIEW_LIFECYCLE_REFRESHED_STATUS,
  visualMatrixApiContractFixtures,
} from "../e2e/fixtures/visual-matrix-state-fixtures";

describe("visual matrix API fixture contracts", () => {
  it("marks the returned legacy report as synthetic non-release evidence", () => {
    const report = visualMatrixApiContractFixtures().report;

    expect(report.disclaimer).toContain("SYNTHETIC COMPONENT-TEST FIXTURE");
    expect(report.disclaimer).toContain("not the canonical showcase");
    expect(report.disclaimer).toContain("not release evidence");
  });

  it("uses one deterministic production-valid UUID for every API report identity", () => {
    const fixtures = visualMatrixApiContractFixtures();
    expect(VISUAL_MATRIX_API_REPORT_ID).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-8[0-9a-f]{3}-[0-9a-f]{12}$/u,
    );
    expect(fixtures.analysis.id).toBe(VISUAL_MATRIX_API_REPORT_ID);
    expect(fixtures.launchedAnalysis.id).toBe(
      VISUAL_MATRIX_LAUNCHED_ANALYSIS_ID,
    );
    expect(fixtures.creditPackReconciliationApplied.session_id).toBe(
      VISUAL_MATRIX_CREDIT_CHECKOUT_SESSION_ID,
    );
    expect(
      fixtures.creditPackReconciliationApplied
        .current_purchased_credits_balance,
    ).toBe(7);
    expect(fixtures.completedExportJob.file_size_bytes).toBe(
      new TextEncoder().encode(COMPLETED_EXPORT_BODY).byteLength,
    );
    expect(fixtures.pendingExportJob).toMatchObject({
      artifact_sha256: null,
      download_url: null,
      file_size_bytes: 0,
      manifest_hash: null,
      status: "pending",
    });
    expect(fixtures.workspaceSummary.analysis_id).toBe(
      VISUAL_MATRIX_API_REPORT_ID,
    );
    expect(fixtures.workspaceSummary.monitor_seed_defaults.analysis_id).toBe(
      VISUAL_MATRIX_API_REPORT_ID,
    );
    expect(fixtures.reviewStatus.analysis_id).toBe(VISUAL_MATRIX_API_REPORT_ID);
    expect(fixtures.ssoStatusActive).toMatchObject({
      provider: "Okta Workforce Identity",
      sso_enabled: true,
      status: "active",
    });
    expect(fixtures.apiKeyListWithItem.items[0]?.id).toBe(
      VISUAL_MATRIX_API_KEY_ID,
    );
    expect(fixtures.commentList[0]?.id).toBe(VISUAL_MATRIX_COMMENT_ID);
    expect(fixtures.monitorListWithItem.items[0]?.id).toBe(
      VISUAL_MATRIX_MONITOR_ID,
    );
    expect(fixtures.monitorAlertList.items[0]?.id).toBe(
      VISUAL_MATRIX_MONITOR_ALERT_ID,
    );
    expect(fixtures.notificationPreferences).toEqual({
      email_digest_frequency: "weekly",
      email_on_analysis_complete: true,
      email_on_monitor_alert: true,
    });
    expect(REPORT_CHAT_SUCCESS_STREAM).toContain(
      '"conversation_id":"99999999-9999-4999-8999-999999999999"',
    );
    expect(REPORT_CHAT_SUCCESS_STREAM).toContain(
      '"patent_id":"US0000000001A1"',
    );
    expect(REPORT_CHAT_SUCCESS_STREAM).toContain(
      "Verify the cited claim language before relying on this screening result.",
    );
    expect(REVIEW_LIFECYCLE_MUTATION_ACK).toMatchObject({
      note: VISUAL_MATRIX_REVIEW_LIFECYCLE_AUDIT_NOTE,
      reviewer_name: "Pending authoritative refresh",
      status: "changes_requested",
    });
    expect(REVIEW_LIFECYCLE_REFRESHED_STATUS).toMatchObject({
      note: VISUAL_MATRIX_REVIEW_LIFECYCLE_AUDIT_NOTE,
      reviewer_name: "Visual Counsel · authoritative",
      status: "changes_requested",
    });
    expect(
      CLAIM_DECISION_MATRIX_REPORT.claim_source_span_map.entries,
    ).toContainEqual(
      expect.objectContaining({
        assertion_id: VISUAL_MATRIX_CLAIM_ASSERTION_ID,
        review_required: true,
        support_status: "needs_review",
      }),
    );
    expect(
      CLAIM_DECISION_MATRIX_REPORT.claim_source_span_map.spans[
        VISUAL_MATRIX_CLAIM_SOURCE_SPAN_ID
      ],
    ).toMatchObject({
      source_document_id: "US0000000001A1",
      source_type: "verified_claim_text",
    });
    expect(
      hasCompleteVerifiedClaimReceipt(
        CLAIM_DECISION_MATRIX_REPORT.claim_source_span_map.spans[
          VISUAL_MATRIX_CLAIM_SOURCE_SPAN_ID
        ],
      ),
    ).toBe(true);
    const claimDecisionModel = buildClaimDecisionMatrixModel({
      report: CLAIM_DECISION_MATRIX_REPORT as unknown as FTOReport,
      reviewerDecisions: {
        items: [],
        counts: { accept: 0, reject: 0, edit: 0 },
      },
    });
    expect(
      claimDecisionModel.rows.find(
        (row) => row.id === "US0000000001A1:claim-1:element-1",
      ),
    ).toMatchObject({
      mappingSupport: "needs_review",
      needsAction: true,
      reviewSummary: { label: "Review pending", state: "pending" },
      reviewTargetAssertionId: VISUAL_MATRIX_CLAIM_ASSERTION_ID,
      verifiedSpans: [
        expect.objectContaining({
          span_id: VISUAL_MATRIX_CLAIM_SOURCE_SPAN_ID,
        }),
      ],
    });
  });
});
