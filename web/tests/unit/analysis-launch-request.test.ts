import { describe, expect, it, vi } from "vitest";
import { buildAnalysisLaunchRequest } from "@/lib/analysis-launch-request";
import type { ConfigState } from "@/stores/config-store";

function createConfig(overrides: Partial<ConfigState> = {}): ConfigState {
  return {
    trustMode: "counsel",
    jurisdictionBundle: "europe_uk",
    targetJurisdictions: ["EP", "UK"],
    searchMaxRankedResults: 200,
    searchTanimotoThreshold: 0.55,
    includeExpired: true,
    jurisdiction: "US",
    enablePubchem: true,
    enableBigquery: true,
    enableSurechembl: true,
    enablePatcid: true,
    maxAnalysisPatents: 20,
    maxDoeCandidates: 15,
    triageBatchSize: 10,
    citationTraversalEnabled: true,
    citationMaxDepth: 2,
    analysisThinkingBudget: 12000,
    expiredGraceYears: 5,
    searchJurisdictions: ["US", "EP", "WO"],
    thinkingEffortAnalysis: "high",
    thinkingEffortTriage: "medium",
    thinkingEffortReport: "high",
    hitlEnabled: false,
    hitlCheckpoints: [],
    hitlAutoSkipMinutes: 10,
    setConfig: vi.fn(),
    applyJurisdictionBundle: vi.fn(),
    setTargetJurisdictions: vi.fn(),
    toggleTargetJurisdiction: vi.fn(),
    applyPreset: vi.fn(),
    reset: vi.fn(),
    ...overrides,
  };
}

describe("buildAnalysisLaunchRequest", () => {
  it("includes jurisdiction and trust fields outside the nested pipeline config", () => {
    const request = buildAnalysisLaunchRequest(
      "aspirin",
      createConfig({
        hitlEnabled: true,
        hitlCheckpoints: ["search_review", "report_review"],
        hitlAutoSkipMinutes: 15,
      }),
      undefined,
      undefined,
      { inputType: "Name", value: "aspirin" },
    );

    expect(request).toMatchObject({
      compound_input: "aspirin",
      input_type: "name",
      submitted_identity_confirmed: true,
      submitted_identity_value: "aspirin",
      trust_mode: "counsel",
      jurisdiction_bundle: "europe_uk",
      target_jurisdictions: ["EP", "UK"],
      config: {
        search_max_ranked_results: 200,
        search_jurisdictions: ["US", "EP", "WO"],
        hitl_enabled: true,
        hitl_checkpoints: ["search_review", "report_review"],
        hitl_auto_skip_minutes: 15,
      },
    });
  });

  it("includes confirmed matter scope fields when provided", () => {
    const request = buildAnalysisLaunchRequest(
      "aspirin",
      createConfig(),
      {
        assetTypeHint: "process_or_synthesis",
        developmentStage: "clinical",
        intendedActions: ["manufacture_import", "design_around"],
      },
      undefined,
      { inputType: "Name", value: "aspirin" },
    );

    expect(request).toMatchObject({
      compound_input: "aspirin",
      asset_type_hint: "process_or_synthesis",
      development_stage: "clinical",
      intended_actions: ["manufacture_import", "design_around"],
    });
  });

  it("includes non-empty product context fields outside the nested pipeline config", () => {
    const request = buildAnalysisLaunchRequest(
      "ibuprofen",
      createConfig(),
      {
        assetTypeHint: "formulation",
        developmentStage: "clinical",
        intendedActions: ["formulation_review", "commercial_launch"],
      },
      {
        productName: "PRV-142 oral tablet",
        dosageForm: "Film-coated tablet",
        routeOfAdministration: "Oral",
        strength: "200 mg",
        keyExcipients: ["Lactose", "HPMC", ""],
        indication: "Pain",
        commercialTerritories: ["US"],
        accusedActs: [
          {
            act: "regulatory_submission",
            jurisdiction: "US",
            startDate: "2027-03-01",
            actor: "Praviar Pharma Ltd",
            status: "planned",
            purpose: "regulatory_approval",
            regulatoryPath: "anda",
            instrumentality: "PRV-142 ANDA",
            liabilityTheory: "artificial_infringement",
            targetProductIdentity: "ibuprofen",
            proposedIndication: "Pain",
            proposedLabelUse: "200 mg orally for pain",
            labelCarveOutState: "none",
          },
        ],
        manufacturingRoute: "",
        knownPatentsOrAssignees: ["US12345678", "Fictional Meridian"],
        ownedOrLicensedIp: "Internal option to use PRV-142 formulation estate",
      },
      { inputType: "Name", value: "ibuprofen" },
    );

    expect(request).toMatchObject({
      compound_input: "ibuprofen",
      product_context: {
        product_name: "PRV-142 oral tablet",
        dosage_form: "Film-coated tablet",
        route_of_administration: "Oral",
        strength: "200 mg",
        key_excipients: ["Lactose", "HPMC"],
        indication: "Pain",
        commercial_territories: ["US"],
        accused_acts: [
          {
            act: "regulatory_submission",
            jurisdiction: "US",
            start_date: "2027-03-01",
            actor: "Praviar Pharma Ltd",
            status: "planned",
            purpose: "regulatory_approval",
            regulatory_path: "anda",
            instrumentality: "PRV-142 ANDA",
            liability_theory: "artificial_infringement",
            target_product_identity: "ibuprofen",
            proposed_indication: "Pain",
            proposed_label_use: "200 mg orally for pain",
            label_carve_out_state: "none",
          },
        ],
        known_patents_or_assignees: ["US12345678", "Fictional Meridian"],
        owned_or_licensed_ip:
          "Internal option to use PRV-142 formulation estate",
      },
    });
    expect(request.product_context).not.toHaveProperty("manufacturing_route");
    expect(request.config).not.toHaveProperty("product_context");
  });

  it("fails closed when confirmation is missing or belongs to another value", () => {
    expect(() => buildAnalysisLaunchRequest("aspirin", createConfig())).toThrow(
      "confirmed submitted identity",
    );
    expect(() =>
      buildAnalysisLaunchRequest(
        "aspirin",
        createConfig(),
        undefined,
        undefined,
        { inputType: "Name", value: "ibuprofen" },
      ),
    ).toThrow("confirmed submitted identity");
  });
});
