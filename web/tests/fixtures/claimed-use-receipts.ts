import type {
  ClaimedUseReceipt,
  ClaimedUseReceiptListResponse,
} from "@/types/api";

const ANALYSIS_ID = "11111111-1111-4111-8111-111111111111";
const ORG_ID = "22222222-2222-4222-8222-222222222222";
const ISSUER_ID = "33333333-3333-4333-8333-333333333333";
const REVOKER_ID = "44444444-4444-4444-8444-444444444444";
const CURRENT_REPORT_ID = "report-current";
const CURRENT_REPORT_FINGERPRINT = "a".repeat(64);

export function buildClaimedUseReceipt(
  overrides: Partial<ClaimedUseReceipt> = {},
): ClaimedUseReceipt {
  const reportId = overrides.report_id ?? CURRENT_REPORT_ID;
  const reportFingerprint =
    overrides.report_fingerprint ?? CURRENT_REPORT_FINGERPRINT;
  const accusedActIndex = overrides.accused_act_index ?? 0;
  const accusedActSha256 = overrides.accused_act_sha256 ?? "b".repeat(64);
  const patentId = overrides.patent_id ?? "US12345678A1";
  const claimNumber = overrides.claim_number ?? 1;
  const issuerUserId = overrides.issuer_user_id ?? ISSUER_ID;

  return {
    id: "55555555-5555-4555-8555-555555555555",
    analysis_id: ANALYSIS_ID,
    report_id: reportId,
    report_fingerprint: reportFingerprint,
    patent_id: patentId,
    claim_number: claimNumber,
    accused_act_index: accusedActIndex,
    accused_act_sha256: accusedActSha256,
    receipt: {
      schema_version: "claimed-use-match-v3",
      analysis_id: ANALYSIS_ID,
      org_id: ORG_ID,
      report_id: reportId,
      report_fingerprint: reportFingerprint,
      accused_act_index: accusedActIndex,
      accused_act_sha256: accusedActSha256,
      patent_id: patentId,
      claim_number: claimNumber,
      controlling_claim_text_sha256: "c".repeat(64),
      current_claim_receipt_sha256: "d".repeat(64),
      controlling_claim_document_ids: ["US12345678A1:grant-claims"],
      declared_target_product_sha256: "e".repeat(64),
      resolved_compound_identity_sha256: "f".repeat(64),
      proposed_indication_sha256: "1".repeat(64),
      proposed_label_use_sha256: "2".repeat(64),
      label_carve_out_state: "partial",
      claimed_use_match: true,
      product_identity_match: true,
      issuer_user_id: issuerUserId,
      reviewer_role: "attorney",
      attestation_statement_version: "claimed-use-counsel-affirmation-v1",
      verified_at: "2026-07-27T09:00:00Z",
      evidence_references: [
        "US12345678A1:grant-claims",
        "source-span:label-use-17",
      ],
      attestation_key_id: "claimed-use-2026-07",
      attestation_hmac_sha256: "3".repeat(64),
      receipt_sha256: "4".repeat(64),
    },
    issuer_user_id: issuerUserId,
    reviewer_role: "attorney",
    attestation_statement_version: "claimed-use-counsel-affirmation-v1",
    issued_at: "2026-07-27T09:00:00Z",
    revoked_at: null,
    revoked_by_user_id: null,
    revocation_reason: "",
    governs_current_report: true,
    can_revoke: true,
    ...overrides,
  };
}

export function buildClaimedUseReceiptLedger(
  items: ClaimedUseReceipt[] = [buildClaimedUseReceipt()],
): ClaimedUseReceiptListResponse {
  return {
    current_report_id: CURRENT_REPORT_ID,
    current_report_fingerprint: CURRENT_REPORT_FINGERPRINT,
    eligible_uses: [
      {
        accused_act_index: 0,
        jurisdiction: "US",
        actor: "Example Pharma Inc.",
        start_date: "2027-01-20",
        regulatory_path: "anda",
        target_product_identity: "Example 10 mg tablet",
        proposed_indication: "Treatment of example disease",
        proposed_label_use: "One tablet once daily.",
        label_carve_out_state: "partial",
      },
    ],
    items,
  };
}

export function buildPriorClaimedUseReceipt(): ClaimedUseReceipt {
  return buildClaimedUseReceipt({
    id: "66666666-6666-4666-8666-666666666666",
    report_id: "report-prior",
    report_fingerprint: "5".repeat(64),
    governs_current_report: false,
    can_revoke: false,
    receipt: {
      ...buildClaimedUseReceipt().receipt,
      report_id: "report-prior",
      report_fingerprint: "5".repeat(64),
      receipt_sha256: "6".repeat(64),
    },
  });
}

export function buildRevokedClaimedUseReceipt(): ClaimedUseReceipt {
  return buildClaimedUseReceipt({
    id: "77777777-7777-4777-8777-777777777777",
    revoked_at: "2026-07-27T10:00:00Z",
    revoked_by_user_id: REVOKER_ID,
    revocation_reason:
      "The proposed label changed after the attorney completed review.",
    governs_current_report: false,
    can_revoke: false,
    receipt: {
      ...buildClaimedUseReceipt().receipt,
      receipt_sha256: "7".repeat(64),
    },
  });
}
