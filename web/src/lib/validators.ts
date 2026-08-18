import { z } from "zod/v4";
import type { ClaimedUseMatchReceipt } from "@praviar/shared-types";

import { logError } from "@/lib/error-logger";

export const compoundInputSchema = z.object({
  compound_input: z
    .string()
    .trim()
    .min(1, "Compound input is required")
    .max(5000),
});

export const analysisConfigSchema = z
  .object({
    search_max_ranked_results: z.number().min(50).max(500).default(200),
    search_tanimoto_threshold: z.number().min(0.1).max(1.0).default(0.55),
    include_expired: z.boolean().default(true),
    enable_pubchem: z.boolean().default(true),
    enable_bigquery: z.boolean().default(true),
    enable_surechembl: z.boolean().default(true),
    enable_patcid: z.boolean().default(true),
    max_analysis_patents: z.number().min(5).max(30).default(20),
    max_doe_candidates: z.number().min(5).max(20).default(15),
    triage_batch_size: z.number().min(5).max(15).default(10),
    citation_traversal_enabled: z.boolean().default(true),
    citation_max_depth: z.number().min(1).max(3).default(2),
    search_expired_grace_years: z.number().min(0).max(10).default(5),
    search_jurisdictions: z
      .array(z.string())
      .min(1)
      .default(["US", "EP", "WO"]),
    thinking_effort_analysis: z.enum(["high", "medium", "low"]).default("high"),
    thinking_effort_triage: z.enum(["high", "medium", "low"]).default("medium"),
    thinking_effort_report: z.enum(["high", "medium", "low"]).default("high"),
    hitl_enabled: z.boolean().default(false),
    hitl_checkpoints: z.array(z.string().trim().min(1)).max(20).default([]),
    hitl_auto_skip_minutes: z.number().min(1).max(120).default(60),
    analysis_thinking_budget_tokens: z
      .number()
      .min(4000)
      .max(32000)
      .default(12000),
  })
  .strict();

const trustModeSchema = z.enum(["explorer", "counsel", "monitor"]);
const jurisdictionBundleSchema = z.enum([
  "us_europe",
  "europe_uk",
  "major_markets",
  "custom",
]);
const developmentStageSchema = z.enum([
  "discovery",
  "lead_optimization",
  "preclinical",
  "clinical",
  "commercial",
]);
const assetTypeHintSchema = z.enum([
  "small_molecule",
  "markush_candidate",
  "biologic_or_sequence",
  "formulation",
  "process_or_synthesis",
  "combination",
  "unknown",
]);
const intendedActionSchema = z.enum([
  "manufacture_import",
  "commercial_launch",
  "formulation_review",
  "method_of_use_review",
  "design_around",
  "diligence_screen",
  "monitor_continuations",
]);
const submittedInputTypeSchema = z.enum([
  "name",
  "smiles",
  "cas",
  "inchi",
  "inchikey",
]);

function productContextTextSchema(maxLength: number) {
  return z.string().trim().min(1).max(maxLength);
}

function productContextListSchema(maxItems: number, maxItemLength = 240) {
  return z.array(z.string().trim().min(1).max(maxItemLength)).max(maxItems);
}

const sha256Schema = z.string().regex(/^[0-9a-f]{64}$/);
const timezoneAwareDateTimeSchema = z
  .string()
  .refine(
    (value) =>
      !Number.isNaN(Date.parse(value)) && /(?:Z|[+-]\d{2}:\d{2})$/u.test(value),
  );
const controllingClaimDocumentIdsSchema = z
  .array(z.string().trim().min(1).max(500))
  .min(1)
  .max(20)
  .transform(
    (references) =>
      references as ClaimedUseMatchReceipt["controlling_claim_document_ids"],
  );
const governedEvidenceReferencesSchema = z
  .array(z.string().trim().min(1).max(500))
  .min(1)
  .max(50)
  .transform(
    (references) => references as ClaimedUseMatchReceipt["evidence_references"],
  );

export const claimedUseMatchReceiptSchema = z
  .object({
    schema_version: z.literal("claimed-use-match-v3"),
    analysis_id: z.uuid(),
    org_id: z.uuid(),
    report_id: z.string().trim().min(1).max(64),
    report_fingerprint: sha256Schema,
    accused_act_index: z.number().int().min(0),
    accused_act_sha256: sha256Schema,
    patent_id: z.string().trim().min(4).max(64),
    claim_number: z.number().int().min(1),
    controlling_claim_text_sha256: sha256Schema,
    current_claim_receipt_sha256: sha256Schema,
    controlling_claim_document_ids: controllingClaimDocumentIdsSchema,
    declared_target_product_sha256: sha256Schema,
    resolved_compound_identity_sha256: sha256Schema,
    proposed_indication_sha256: sha256Schema,
    proposed_label_use_sha256: sha256Schema,
    label_carve_out_state: z.enum(["none", "partial", "complete", "unknown"]),
    claimed_use_match: z.literal(true),
    product_identity_match: z.literal(true),
    issuer_user_id: z.uuid(),
    reviewer_role: z.literal("attorney"),
    attestation_statement_version: z.literal(
      "claimed-use-counsel-affirmation-v1",
    ),
    verified_at: timezoneAwareDateTimeSchema,
    evidence_references: governedEvidenceReferencesSchema,
    attestation_key_id: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/),
    attestation_hmac_sha256: sha256Schema,
    receipt_sha256: sha256Schema,
  })
  .strict()
  .superRefine((receipt, context) => {
    if (
      new Set(receipt.controlling_claim_document_ids).size !==
      receipt.controlling_claim_document_ids.length
    ) {
      context.addIssue({
        code: "custom",
        message: "Controlling claim document identifiers must be unique",
        path: ["controlling_claim_document_ids"],
      });
    }
    if (
      new Set(receipt.evidence_references).size !==
      receipt.evidence_references.length
    ) {
      context.addIssue({
        code: "custom",
        message: "Governed evidence references must be unique",
        path: ["evidence_references"],
      });
    }
  });

export const claimedUseEligibleUseSchema = z
  .object({
    accused_act_index: z.number().int().min(0),
    jurisdiction: z.string().trim().min(2).max(40),
    actor: z.string().trim().min(1).max(240),
    start_date: z.string().date(),
    regulatory_path: z.enum([
      "none",
      "anda",
      "nda_505_b_1",
      "nda_505_b_2",
      "bla_351_a",
      "abla",
      "biosimilar_351_k",
      "unknown",
    ]),
    target_product_identity: z.string().trim().min(1).max(500),
    proposed_indication: z.string().trim().min(1).max(1000),
    proposed_label_use: z.string().trim().min(1).max(4000),
    label_carve_out_state: z.enum(["none", "partial", "complete", "unknown"]),
  })
  .strict();

export const claimedUseReceiptResponseSchema = z
  .object({
    id: z.uuid(),
    analysis_id: z.uuid(),
    report_id: z.string().trim().min(1).max(64),
    report_fingerprint: sha256Schema,
    patent_id: z.string().trim().min(4).max(64),
    claim_number: z.number().int().min(1),
    accused_act_index: z.number().int().min(0),
    accused_act_sha256: sha256Schema,
    receipt: claimedUseMatchReceiptSchema,
    issuer_user_id: z.uuid(),
    reviewer_role: z.literal("attorney"),
    attestation_statement_version: z.literal(
      "claimed-use-counsel-affirmation-v1",
    ),
    issued_at: timezoneAwareDateTimeSchema,
    revoked_at: timezoneAwareDateTimeSchema.nullable(),
    revoked_by_user_id: z.uuid().nullable(),
    revocation_reason: z.string().max(1000),
    governs_current_report: z.boolean(),
    can_revoke: z.boolean(),
  })
  .strict()
  .superRefine((row, context) => {
    const bindings = [
      ["analysis_id", row.analysis_id, row.receipt.analysis_id],
      ["report_id", row.report_id, row.receipt.report_id],
      [
        "report_fingerprint",
        row.report_fingerprint,
        row.receipt.report_fingerprint,
      ],
      ["patent_id", row.patent_id, row.receipt.patent_id],
      ["claim_number", row.claim_number, row.receipt.claim_number],
      [
        "accused_act_index",
        row.accused_act_index,
        row.receipt.accused_act_index,
      ],
      [
        "accused_act_sha256",
        row.accused_act_sha256,
        row.receipt.accused_act_sha256,
      ],
      ["issuer_user_id", row.issuer_user_id, row.receipt.issuer_user_id],
      ["reviewer_role", row.reviewer_role, row.receipt.reviewer_role],
      [
        "attestation_statement_version",
        row.attestation_statement_version,
        row.receipt.attestation_statement_version,
      ],
      ["issued_at", row.issued_at, row.receipt.verified_at],
    ] as const;
    for (const [field, persisted, signed] of bindings) {
      if (persisted !== signed) {
        context.addIssue({
          code: "custom",
          message: "Persisted receipt coordinate differs from signed payload",
          path: [field],
        });
      }
    }
    if (
      row.revoked_at === null &&
      (row.revoked_by_user_id !== null || row.revocation_reason !== "")
    ) {
      context.addIssue({
        code: "custom",
        message: "Active receipt cannot contain revocation metadata",
        path: ["revoked_at"],
      });
    }
    if (
      row.revoked_at !== null &&
      (row.revoked_by_user_id === null ||
        row.revocation_reason.trim().length < 10 ||
        row.governs_current_report ||
        row.can_revoke)
    ) {
      context.addIssue({
        code: "custom",
        message:
          "Revoked receipt metadata is incomplete or still marked current",
        path: ["revoked_at"],
      });
    }
    if (
      row.revoked_at !== null &&
      Date.parse(row.revoked_at) < Date.parse(row.issued_at)
    ) {
      context.addIssue({
        code: "custom",
        message: "Receipt cannot be revoked before it was issued",
        path: ["revoked_at"],
      });
    }
  });

export const claimedUseReceiptListResponseSchema = z
  .object({
    current_report_id: z.string().trim().min(1).max(64),
    current_report_fingerprint: sha256Schema,
    eligible_uses: z.array(claimedUseEligibleUseSchema),
    items: z.array(claimedUseReceiptResponseSchema),
  })
  .strict()
  .superRefine((ledger, context) => {
    ledger.items.forEach((item, index) => {
      if (
        item.governs_current_report &&
        (item.revoked_at !== null ||
          item.receipt.report_id !== ledger.current_report_id ||
          item.receipt.report_fingerprint !== ledger.current_report_fingerprint)
      ) {
        context.addIssue({
          code: "custom",
          message: "Current receipt does not bind the current report",
          path: ["items", index, "governs_current_report"],
        });
      }
    });
  });

const accusedActRecordSchema = z
  .object({
    act: z.enum([
      "manufacture",
      "import",
      "offer_for_sale",
      "sale",
      "use",
      "regulatory_submission",
    ]),
    jurisdiction: z.string().trim().min(2).max(40),
    start_date: z.string().date(),
    end_date: z.string().date().optional(),
    actor: z.string().trim().min(1).max(240),
    status: z.enum(["planned", "actual", "denied", "hypothetical"]),
    purpose: z.enum([
      "commercial",
      "regulatory_approval",
      "clinical_research",
      "experimental",
      "internal_research",
      "other",
      "unknown",
    ]),
    regulatory_path: z.enum([
      "none",
      "anda",
      "nda_505_b_1",
      "nda_505_b_2",
      "bla_351_a",
      "abla",
      "biosimilar_351_k",
      "unknown",
    ]),
    instrumentality: z.string().trim().min(1).max(500),
    liability_theory: z.enum([
      "direct",
      "induced",
      "contributory",
      "artificial_infringement",
      "unknown",
    ]),
    performs_all_claim_steps: z.boolean().optional(),
    direct_infringer: z.string().trim().min(1).max(240).optional(),
    knowledge_of_patent: z.boolean().optional(),
    affirmative_encouragement: z.boolean().optional(),
    manufacturing_jurisdiction: z.string().trim().min(2).max(40).optional(),
    process_used: z.string().trim().min(1).max(500).optional(),
    process_use_verified: z.boolean().optional(),
    materially_changed_after_process: z.boolean().optional(),
    trivial_component_after_process: z.boolean().optional(),
    target_product_identity: z.string().trim().min(1).max(500).optional(),
    proposed_indication: z.string().trim().min(1).max(1000).optional(),
    proposed_label_use: z.string().trim().min(1).max(4000).optional(),
    label_carve_out_state: z
      .enum(["none", "partial", "complete", "unknown"])
      .optional(),
    claimed_use_match_receipts: z
      .array(claimedUseMatchReceiptSchema)
      .max(100)
      .optional(),
  })
  .strict()
  .superRefine((record, context) => {
    const today = new Date().toISOString().slice(0, 10);
    if (record.end_date && record.end_date < record.start_date) {
      context.addIssue({
        code: "custom",
        message: "End date must be on or after start date",
        path: ["end_date"],
      });
    }
    if (record.status === "actual" && record.start_date > today) {
      context.addIssue({
        code: "custom",
        message: "Actual acts cannot start in the future",
        path: ["start_date"],
      });
    }
    if (record.status === "planned" && record.start_date < today) {
      context.addIssue({
        code: "custom",
        message:
          "Elapsed planned acts must be reconfirmed as actual or given a future date",
        path: ["start_date"],
      });
    }
    if (
      record.act === "regulatory_submission" &&
      (record.regulatory_path === "none" ||
        record.purpose !== "regulatory_approval" ||
        record.liability_theory !== "artificial_infringement" ||
        !record.target_product_identity ||
        !record.proposed_indication ||
        !record.proposed_label_use ||
        !record.label_carve_out_state)
    ) {
      context.addIssue({
        code: "custom",
        message:
          "Regulatory submissions require a pathway and regulatory-approval purpose",
        path: ["regulatory_path"],
      });
    }
    if (
      record.act !== "regulatory_submission" &&
      (record.regulatory_path !== "none" ||
        record.liability_theory === "artificial_infringement")
    ) {
      context.addIssue({
        code: "custom",
        message: "Only regulatory submissions may declare a regulatory path",
        path: ["regulatory_path"],
      });
    }
    if (
      record.act !== "regulatory_submission" &&
      (record.target_product_identity ||
        record.proposed_indication ||
        record.proposed_label_use ||
        record.label_carve_out_state ||
        (record.claimed_use_match_receipts?.length ?? 0) > 0)
    ) {
      context.addIssue({
        code: "custom",
        message:
          "Proposed-use and claimed-use receipt facts apply only to regulatory submissions",
        path: ["proposed_label_use"],
      });
    }
  });

export const productContextSchema = z
  .object({
    product_name: productContextTextSchema(240).optional(),
    dosage_form: productContextTextSchema(240).optional(),
    route_of_administration: productContextTextSchema(240).optional(),
    strength: productContextTextSchema(240).optional(),
    release_profile: productContextTextSchema(240).optional(),
    salt_polymorph_form: productContextTextSchema(240).optional(),
    key_excipients: productContextListSchema(30).optional(),
    indication: productContextTextSchema(500).optional(),
    patient_population: productContextTextSchema(500).optional(),
    combination_assets: productContextListSchema(30).optional(),
    reference_product: productContextTextSchema(240).optional(),
    manufacturing_route: productContextTextSchema(1000).optional(),
    commercial_action: productContextTextSchema(500).optional(),
    decision_deadline: productContextTextSchema(120).optional(),
    commercial_territories: productContextListSchema(30, 80).optional(),
    accused_acts: z.array(accusedActRecordSchema).max(50).optional(),
    known_patents_or_assignees: productContextListSchema(50).optional(),
    owned_or_licensed_ip: productContextTextSchema(1000).optional(),
  })
  .strict();

export const createAnalysisSchema = compoundInputSchema
  .merge(
    z.object({
      input_type: submittedInputTypeSchema,
      submitted_identity_confirmed: z.literal(true),
      submitted_identity_value: z.string().trim().min(1).max(5000),
      trust_mode: trustModeSchema.optional(),
      intended_actions: z.array(intendedActionSchema).max(20).optional(),
      target_jurisdictions: z
        .array(z.string().trim().min(2).max(10))
        .max(30)
        .optional(),
      jurisdiction_bundle: jurisdictionBundleSchema.optional(),
      development_stage: developmentStageSchema.optional(),
      asset_type_hint: assetTypeHintSchema.nullable().optional(),
      product_context: productContextSchema.optional(),
      config: analysisConfigSchema.optional(),
    }),
  )
  .superRefine((request, context) => {
    if (request.submitted_identity_value !== request.compound_input) {
      context.addIssue({
        code: "custom",
        message:
          "Submitted identity confirmation must match the normalized compound input",
        path: ["submitted_identity_value"],
      });
    }
  });

export type CompoundInput = z.infer<typeof compoundInputSchema>;
export type CreateAnalysis = z.infer<typeof createAnalysisSchema>;

// ── API Response Schemas ────────────────────────────────────────────────

const riskLevelSchema = z.string().nullable();
const apiDateTimeSchema = z
  .string()
  .refine(
    (value) =>
      !Number.isNaN(Date.parse(value)) && /(?:Z|[+-]\d{2}:\d{2})$/u.test(value),
    "Expected a timezone-aware ISO datetime",
  );

export const externalReportGrantStatusSchema = z.enum([
  "active",
  "delivery_pending",
  "delivery_rejected",
  "delivery_outcome_unknown",
  "delivery_cancelled_by_policy",
  "delivery_cancelled_expired",
  "delivery_cancelled_retention_expired",
  "delivery_reconciliation_alert",
  "expired",
  "revoked",
  "view_limit_reached",
]);

export const externalReportGrantSchema = z
  .object({
    id: z.uuid(),
    recipient_email: z.email(),
    recipient_domain: z.string().trim().min(1).max(253),
    invitation_sent_at: apiDateTimeSchema.nullable(),
    expires_at: apiDateTimeSchema,
    revoked_at: apiDateTimeSchema.nullable(),
    max_views: z.number().int().min(1).max(100),
    view_count: z.number().int().nonnegative(),
    download_allowed: z.literal(false),
    max_downloads: z.literal(0),
    download_count: z.literal(0),
    last_accessed_at: apiDateTimeSchema.nullable(),
    status: externalReportGrantStatusSchema,
  })
  .superRefine((grant, context) => {
    if (grant.view_count > grant.max_views) {
      context.addIssue({
        code: "custom",
        message: "Grant view count cannot exceed its authoritative limit",
        path: ["view_count"],
      });
    }
  });

export const externalReportGrantListResponseSchema = z.object({
  items: z.array(externalReportGrantSchema),
});

const externalReportShareTokenSchema = z
  .string()
  .min(40)
  .max(64)
  .regex(/^[A-Za-z0-9_-]+$/u);

export const externalReportGrantCreatedResponseSchema =
  externalReportGrantSchema
    .extend({
      share_token: externalReportShareTokenSchema.nullable(),
      invitation_status: z.literal("provider_accepted"),
      replayed: z.boolean(),
    })
    .superRefine((grant, context) => {
      if (grant.share_token === null && !grant.replayed) {
        context.addIssue({
          code: "custom",
          message: "A newly accepted invitation must expose its one-time token",
          path: ["share_token"],
        });
      }
    });

export const externalReportGrantActivityEventSchema = z.enum([
  "delivery_dispatch_started",
  "delivery_provider_accepted",
  "delivery_rejected",
  "delivery_outcome_unknown",
  "delivery_cancelled_by_policy",
  "delivery_cancelled_expired",
  "delivery_cancelled_retention_expired",
  "delivery_reconciliation_alert",
  "invitation_sent",
  "recipient_verified",
  "report_viewed",
  "revoked",
  "revoked_by_policy",
  "revoked_by_reissue",
]);

export const externalReportGrantActivitySchema = z.object({
  id: z.uuid(),
  event: externalReportGrantActivityEventSchema,
  occurred_at: apiDateTimeSchema,
  view_number: z.number().int().positive().nullable(),
});

export const externalReportGrantActivityResponseSchema = z.object({
  items: z.array(externalReportGrantActivitySchema),
});

export const externalReportGrantRevokedResponseSchema = z.object({
  status: z.literal("revoked"),
});

export type ExternalReportGrant = z.infer<typeof externalReportGrantSchema>;
export type ExternalReportGrantListResponse = z.infer<
  typeof externalReportGrantListResponseSchema
>;
export type ExternalReportGrantCreatedResponse = z.infer<
  typeof externalReportGrantCreatedResponseSchema
>;
export type ExternalReportGrantActivity = z.infer<
  typeof externalReportGrantActivitySchema
>;
export type ExternalReportGrantActivityResponse = z.infer<
  typeof externalReportGrantActivityResponseSchema
>;
export type ExternalReportGrantRevokedResponse = z.infer<
  typeof externalReportGrantRevokedResponseSchema
>;

const sourceSpanReferenceSchema = z
  .object({
    span_id: z.string(),
    source_type: z.enum([
      "claim_text",
      "verified_claim_text",
      "element_evidence",
      "specification_citation",
      "claim_reasoning",
    ]),
    patent_id: z.string().optional(),
    claim_number: z.number().int().positive().nullable().optional(),
    element_number: z.number().int().positive().nullable().optional(),
    citation: z.string().optional(),
    excerpt: z.string().optional(),
    source_document_id: z.string().optional(),
    source_name: z.string().optional(),
    source_text_sha256: z.string().optional(),
    source_retrieved_at: z.string().optional(),
    source_artifact_locator: z.string().optional(),
    collector_identity: z.string().optional(),
    collector_version: z.string().optional(),
    provenance_cassette_sha256: z.string().optional(),
  })
  .superRefine((span, context) => {
    if (span.source_type !== "verified_claim_text") return;

    const requiredTextFields = [
      "patent_id",
      "source_document_id",
      "source_name",
      "source_artifact_locator",
      "collector_identity",
      "collector_version",
    ] as const;
    for (const field of requiredTextFields) {
      if (!span[field]?.trim()) {
        context.addIssue({
          code: "custom",
          message: "Verified claim text requires a complete provenance receipt",
          path: [field],
        });
      }
    }

    if (
      !span.source_retrieved_at ||
      Number.isNaN(Date.parse(span.source_retrieved_at)) ||
      !/(?:Z|[+-]\d{2}:\d{2})$/.test(span.source_retrieved_at)
    ) {
      context.addIssue({
        code: "custom",
        message: "Verified claim text requires a timezone-aware retrieval time",
        path: ["source_retrieved_at"],
      });
    }
    for (const field of [
      "source_text_sha256",
      "provenance_cassette_sha256",
    ] as const) {
      if (!/^[0-9a-f]{64}$/.test(span[field] ?? "")) {
        context.addIssue({
          code: "custom",
          message: "Verified claim text requires a SHA-256 provenance hash",
          path: [field],
        });
      }
    }

    if (!span.excerpt?.trim()) {
      context.addIssue({
        code: "custom",
        message: "Verified claim text requires an exact excerpt",
        path: ["excerpt"],
      });
    }
    if (
      span.patent_id &&
      span.source_document_id &&
      span.source_document_id !== span.patent_id
    ) {
      context.addIssue({
        code: "custom",
        message: "Verified claim text document must match the patent",
        path: ["source_document_id"],
      });
    }
    if (
      span.source_artifact_locator &&
      span.source_text_sha256 &&
      !artifactLocatorBindsSha256(
        span.source_artifact_locator,
        span.source_text_sha256,
      )
    ) {
      context.addIssue({
        code: "custom",
        message: "Verified claim text locator must bind the source hash",
        path: ["source_artifact_locator"],
      });
    }
  });

function artifactLocatorBindsSha256(locator: string, digest: string) {
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

const claimAssertionSupportSchema = z
  .object({
    assertion_id: z.string(),
    patent_id: z.string().optional(),
    claim_number: z.number().int().positive().nullable().optional(),
    element_number: z.number().int().positive().nullable().optional(),
    report_section: z.string(),
    assertion_text: z.string(),
    source_span_ids: z.array(z.string()),
    support_status: z.enum(["supported", "unsupported", "needs_review"]),
    customer_visible: z.boolean(),
    review_required: z.boolean(),
  })
  .passthrough();

const claimElementResponseSchema = z
  .object({
    element_number: z.number().int().positive(),
    element_text: z.string(),
    status: z.enum(["met", "not_met", "partially_met", "unclear"]),
    reasoning: z.string(),
    confidence: z.number().min(0).max(1).optional(),
    evidence: z.string().optional(),
  })
  .passthrough();

const claimAnalysisResponseSchema = z
  .object({
    claim_number: z.number().int().positive(),
    claim_type: z.enum(["independent", "dependent"]),
    depends_on: z.number().int().positive().nullable().optional(),
    elements: z.array(claimElementResponseSchema).optional(),
    reasoning: z.string().optional(),
    overall_status: z.enum(["met", "not_met", "partially_met", "unclear"]),
    overall_confidence: z.number().min(0).max(1).optional(),
  })
  .passthrough();

const doeAssessmentResponseSchema = z
  .object({
    patent_id: z.string(),
    claim_number: z.number().int().positive(),
    element_number: z.number().int().positive(),
    overall_equivalent: z.boolean().optional(),
    confidence: z.number().min(0).max(1).optional(),
  })
  .passthrough();

const claimSourceSpanMapSchema = z
  .object({
    generated_from: z.string().optional(),
    entries: z.array(claimAssertionSupportSchema),
    spans: z.record(z.string(), sourceSpanReferenceSchema),
    unsupported_customer_visible_claim_count: z.number(),
    needs_review_count: z.number(),
  })
  .passthrough();

export const patentAnalysisSchema = z
  .object({
    patent_id: z.string(),
    jurisdiction: z.string().optional(),
    title: z.string().optional(),
    assignee: z.string().optional(),
    expiry_date: z.string().nullable().optional(),
    risk_level: z.string(),
    risk_summary: z.string(),
    claims_analyzed: z.array(claimAnalysisResponseSchema).optional(),
    design_around_suggestions: z.array(z.object({}).passthrough()).optional(),
    orange_book_info: z.object({}).passthrough().nullable().optional(),
    model_used: z.string().optional(),
    analysis_escalated: z.boolean().optional(),
    analysis_review_required: z.boolean().optional(),
    perspective_analyses: z.array(z.object({}).passthrough()).optional(),
  })
  .passthrough();

export type PatentAnalysisSchema = z.infer<typeof patentAnalysisSchema>;

export const reportSummaryResponseSchema = z.object({
  overall_risk: riskLevelSchema.nullable(),
  blocking_patents_count: z.number().nullable(),
  total_patents_found: z.number(),
  executive_summary: z.string(),
  risk_ratings_restricted: z.boolean().default(false),
});

const verificationCheckSchema = z
  .object({
    check_name: z.string(),
    severity: z.enum(["pass", "warning", "fail"]),
    details: z.string(),
  })
  .passthrough();

/**
 * Shape of `FTOReport.verification`.
 *
 * NOTE: the generated contract marks `verification?` as OPTIONAL — the pipeline
 * can omit it entirely (e.g. legacy reports, or a run where verification did
 * not execute). The web barrel (`lib/shared-types/index.ts`) widens it to
 * required for ergonomics, but that is a convenience lie: consumers
 * (`meta-tab-verification-card`, `meta-tab-helpers`, the confidence dashboard)
 * must — and do — guard with `verification?.`. We therefore validate the field
 * as optional here and only assert the inner shape when it is present, rather
 * than rejecting otherwise-valid reports that legitimately lack it.
 */
const verificationResultSchema = z
  .object({
    checks: z.array(verificationCheckSchema).optional(),
    all_citations_valid: z.boolean().optional(),
    all_claims_grounded: z.boolean().optional(),
    all_entities_valid: z.boolean().optional(),
    dates_consistent: z.boolean().optional(),
    risk_levels_justified: z.boolean().optional(),
    issues: z.array(z.string()).optional(),
  })
  .passthrough();

export const ftoReportResponseSchema = z
  .object({
    report_id: z.string(),
    generated_at: z.string(),
    compound: z
      .object({
        name: z.string(),
        canonical_smiles: z.string(),
      })
      .passthrough(),
    risk_summary: z
      .object({
        overall_risk: z.string(),
        blocking_patents_count: z.number(),
      })
      .passthrough(),
    patent_analyses: z.array(patentAnalysisSchema),
    doe_assessments: z.array(doeAssessmentResponseSchema).optional(),
    verification: verificationResultSchema.optional(),
    claim_source_span_map: claimSourceSpanMapSchema,
  })
  .passthrough()
  .superRefine((report, context) => {
    const claimElementTuples = new Set<string>();
    for (const [patentIndex, patent] of report.patent_analyses.entries()) {
      for (const [claimIndex, claim] of (
        patent.claims_analyzed ?? []
      ).entries()) {
        for (const [elementIndex, element] of (
          claim.elements ?? []
        ).entries()) {
          const tuple = `${patent.patent_id}:${claim.claim_number}:${element.element_number}`;
          if (claimElementTuples.has(tuple)) {
            context.addIssue({
              code: "custom",
              message: "Duplicate patent, claim, and element tuple",
              path: [
                "patent_analyses",
                patentIndex,
                "claims_analyzed",
                claimIndex,
                "elements",
                elementIndex,
                "element_number",
              ],
            });
          }
          claimElementTuples.add(tuple);
        }
      }
    }

    const doeTuples = new Set<string>();
    for (const [index, assessment] of (
      report.doe_assessments ?? []
    ).entries()) {
      const tuple = `${assessment.patent_id}:${assessment.claim_number}:${assessment.element_number}`;
      if (doeTuples.has(tuple)) {
        context.addIssue({
          code: "custom",
          message: "Duplicate doctrine-of-equivalents tuple",
          path: ["doe_assessments", index, "element_number"],
        });
      }
      doeTuples.add(tuple);
    }

    const assertionIds = new Set<string>();
    for (const [
      index,
      entry,
    ] of report.claim_source_span_map.entries.entries()) {
      if (assertionIds.has(entry.assertion_id)) {
        context.addIssue({
          code: "custom",
          message: "Duplicate claim assertion identifier",
          path: ["claim_source_span_map", "entries", index, "assertion_id"],
        });
      }
      assertionIds.add(entry.assertion_id);
    }
  });

export type ReportSummaryResponse = z.infer<typeof reportSummaryResponseSchema>;

// ── Validation Helper ───────────────────────────────────────────────────

/**
 * Thrown by `validateApiResponse` when the API payload does not satisfy
 * the declared Zod schema. Surfaces a human-readable contract description
 * so callers can show the failure to the user instead of silently rendering
 * malformed data.
 */
export class ApiResponseValidationError extends Error {
  readonly endpoint: string;
  readonly issues: string;

  constructor(endpoint: string, issues: string) {
    super(`API response validation failed for ${endpoint}: ${issues}`);
    this.name = "ApiResponseValidationError";
    this.endpoint = endpoint;
    this.issues = issues;
  }
}

/**
 * Validate API response data against a Zod schema.
 *
 * Throws `ApiResponseValidationError` on contract violations — callers must
 * catch it and surface the failure to the user. Per the project's
 * "no fallbacks, no silent failures" rule we never return malformed data.
 */
export function validateApiResponse<T>(
  schema: z.ZodType<T>,
  data: unknown,
  endpoint: string,
): T {
  const result = schema.safeParse(data);
  if (!result.success) {
    const safeIssues = result.error.issues.map((issue) => ({
      code: issue.code,
      path: issue.path.map(String).join(".") || "response",
    }));
    const issueSummary = safeIssues
      .map(({ code, path }) => `${code} at ${path}`)
      .join("; ");
    logError(new Error("API response contract validation failed"), {
      source: "apiContract",
      extra: {
        endpoint,
        issueCodes: safeIssues.map(({ code }) => code),
        issuePaths: safeIssues.map(({ path }) => path),
      },
    });
    throw new ApiResponseValidationError(endpoint, issueSummary);
  }
  return result.data;
}
