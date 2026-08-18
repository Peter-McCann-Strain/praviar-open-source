import type {
  AccusedActRecordValue,
  IntendedAction,
  MatterScopePreflightValue,
  ProductContextValue,
} from "@/types/pipeline";
import type { AnalysisProductContext } from "@/types/api";
import type { ClaimedUseMatchReceipt } from "@praviar/shared-types";

export type ProductContextField = keyof ProductContextValue;

export interface ProductContextEntry {
  key: ProductContextField;
  label: string;
  value: string;
}

export type ProductContextPayload = Partial<{
  product_name: string;
  dosage_form: string;
  route_of_administration: string;
  strength: string;
  release_profile: string;
  salt_polymorph_form: string;
  key_excipients: string[];
  indication: string;
  patient_population: string;
  combination_assets: string[];
  reference_product: string;
  manufacturing_route: string;
  commercial_action: string;
  decision_deadline: string;
  commercial_territories: string[];
  accused_acts: Array<{
    act: AccusedActRecordValue["act"];
    jurisdiction: string;
    start_date: string;
    end_date?: string;
    actor: string;
    status: AccusedActRecordValue["status"];
    purpose: AccusedActRecordValue["purpose"];
    regulatory_path: AccusedActRecordValue["regulatoryPath"];
    instrumentality: string;
    liability_theory: AccusedActRecordValue["liabilityTheory"];
    performs_all_claim_steps?: boolean;
    direct_infringer?: string;
    knowledge_of_patent?: boolean;
    affirmative_encouragement?: boolean;
    manufacturing_jurisdiction?: string;
    process_used?: string;
    process_use_verified?: boolean;
    materially_changed_after_process?: boolean;
    trivial_component_after_process?: boolean;
    target_product_identity?: string;
    proposed_indication?: string;
    proposed_label_use?: string;
    label_carve_out_state?: AccusedActRecordValue["labelCarveOutState"];
    claimed_use_match_receipts?: ClaimedUseMatchReceipt[];
  }>;
  known_patents_or_assignees: string[];
  owned_or_licensed_ip: string;
}>;

export const EMPTY_PRODUCT_CONTEXT: ProductContextValue = {
  productName: "",
  dosageForm: "",
  routeOfAdministration: "",
  strength: "",
  releaseProfile: "",
  saltPolymorphForm: "",
  keyExcipients: [],
  indication: "",
  patientPopulation: "",
  combinationAssets: [],
  referenceProduct: "",
  manufacturingRoute: "",
  commercialAction: "",
  decisionDeadline: "",
  commercialTerritories: [],
  accusedActs: [],
  knownPatentsOrAssignees: [],
  ownedOrLicensedIp: "",
};

export const PRODUCT_CONTEXT_LABELS: Record<ProductContextField, string> = {
  productName: "Product or program",
  dosageForm: "Dosage form",
  routeOfAdministration: "Route",
  strength: "Strength",
  releaseProfile: "Release profile",
  saltPolymorphForm: "Salt / polymorph",
  keyExcipients: "Key excipients",
  indication: "Indication",
  patientPopulation: "Patient population",
  combinationAssets: "Combination assets",
  referenceProduct: "Reference product",
  manufacturingRoute: "Manufacturing route",
  commercialAction: "Commercial action",
  decisionDeadline: "Decision deadline",
  commercialTerritories: "Commercial territories",
  accusedActs: "Structured accused acts",
  knownPatentsOrAssignees: "Known patents / assignees",
  ownedOrLicensedIp: "Owned or licensed IP",
};

const PAYLOAD_KEYS: Record<ProductContextField, keyof ProductContextPayload> = {
  productName: "product_name",
  dosageForm: "dosage_form",
  routeOfAdministration: "route_of_administration",
  strength: "strength",
  releaseProfile: "release_profile",
  saltPolymorphForm: "salt_polymorph_form",
  keyExcipients: "key_excipients",
  indication: "indication",
  patientPopulation: "patient_population",
  combinationAssets: "combination_assets",
  referenceProduct: "reference_product",
  manufacturingRoute: "manufacturing_route",
  commercialAction: "commercial_action",
  decisionDeadline: "decision_deadline",
  commercialTerritories: "commercial_territories",
  accusedActs: "accused_acts",
  knownPatentsOrAssignees: "known_patents_or_assignees",
  ownedOrLicensedIp: "owned_or_licensed_ip",
};

const LIST_FIELDS = new Set<ProductContextField>([
  "keyExcipients",
  "combinationAssets",
  "commercialTerritories",
  "knownPatentsOrAssignees",
]);

const BASE_REVIEW_FIELDS: ProductContextField[] = [
  "productName",
  "dosageForm",
  "routeOfAdministration",
  "strength",
  "indication",
  "commercialAction",
];

const HIGH_RELIANCE_ACTION_LABELS: Partial<Record<IntendedAction, string>> = {
  commercial_launch: "commercial launch",
  manufacture_import: "manufacture/import",
};

const HIGH_RELIANCE_ACTIONS = new Set<IntendedAction>([
  "commercial_launch",
  "manufacture_import",
]);

const CORE_HIGH_RELIANCE_FIELDS: ProductContextField[] = [
  "productName",
  "dosageForm",
  "routeOfAdministration",
  "strength",
  "commercialAction",
];

const FIELDS_BY_INTENDED_ACTION: Partial<
  Record<IntendedAction, ProductContextField[]>
> = {
  commercial_launch: ["indication", "commercialTerritories", "accusedActs"],
  manufacture_import: [
    "manufacturingRoute",
    "commercialTerritories",
    "accusedActs",
  ],
  formulation_review: ["dosageForm", "keyExcipients"],
  method_of_use_review: ["indication", "patientPopulation", "accusedActs"],
  design_around: ["knownPatentsOrAssignees"],
};

const FIELDS_BY_ASSET_TYPE: Partial<
  Record<MatterScopePreflightValue["assetTypeHint"], ProductContextField[]>
> = {
  formulation: [
    "dosageForm",
    "routeOfAdministration",
    "strength",
    "keyExcipients",
    "saltPolymorphForm",
  ],
  process_or_synthesis: ["manufacturingRoute", "commercialAction"],
  combination: [
    "combinationAssets",
    "dosageForm",
    "routeOfAdministration",
    "indication",
  ],
  biologic_or_sequence: [
    "routeOfAdministration",
    "strength",
    "indication",
    "patientPopulation",
  ],
};

function normalizeText(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export function parseContextList(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function contextListToText(
  value: readonly string[] | undefined,
): string {
  return value?.join(", ") ?? "";
}

function formatContextValue(value: ProductContextValue[ProductContextField]) {
  if (Array.isArray(value)) {
    return value
      .map((item) =>
        typeof item === "object" && item !== null && "act" in item
          ? `${item.act} · ${item.jurisdiction} · ${item.status}`
          : normalizeText(item),
      )
      .filter(Boolean)
      .join(", ");
  }
  return normalizeText(value);
}

function hasProductContextFieldValue(
  context: ProductContextValue | undefined,
  field: ProductContextField,
): boolean {
  const value = context?.[field];
  if (field === "accusedActs" && Array.isArray(value)) {
    return (value as AccusedActRecordValue[]).some(
      (record) =>
        (record.status === "actual" || record.status === "planned") &&
        Boolean(record.jurisdiction.trim()) &&
        Boolean(record.startDate) &&
        Boolean(record.actor.trim()) &&
        Boolean(record.instrumentality.trim()),
    );
  }
  if (Array.isArray(value)) {
    return value.map(normalizeText).filter(Boolean).length > 0;
  }
  return Boolean(normalizeText(value));
}

function formatPlainList(items: readonly string[]) {
  if (items.length <= 1) return items[0] ?? "";
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}

function getIntendedActionContextFields(
  matterScope: MatterScopePreflightValue,
): ProductContextField[] {
  return matterScope.intendedActions.flatMap(
    (action) => FIELDS_BY_INTENDED_ACTION[action] ?? [],
  );
}

export function getProductContextEntries(
  context: ProductContextValue | undefined,
): ProductContextEntry[] {
  if (!context) {
    return [];
  }

  return (Object.keys(PRODUCT_CONTEXT_LABELS) as ProductContextField[])
    .map((key) => ({
      key,
      label: PRODUCT_CONTEXT_LABELS[key],
      value: formatContextValue(context[key]),
    }))
    .filter((entry) => entry.value.length > 0);
}

export function hasProductContextValue(
  context: ProductContextValue | undefined,
): boolean {
  return getProductContextEntries(context).length > 0;
}

export function serializeProductContext(
  context: ProductContextValue | undefined,
): ProductContextPayload | undefined {
  if (!context) {
    return undefined;
  }

  const payload: ProductContextPayload = {};
  const writablePayload = payload as Record<string, string | string[]>;

  (Object.keys(PRODUCT_CONTEXT_LABELS) as ProductContextField[]).forEach(
    (key) => {
      const payloadKey = PAYLOAD_KEYS[key];
      const rawValue = context[key];

      if (LIST_FIELDS.has(key)) {
        const listValue = Array.isArray(rawValue)
          ? rawValue.map(normalizeText).filter(Boolean)
          : [];
        if (listValue.length > 0) {
          writablePayload[payloadKey] = listValue;
        }
        return;
      }

      if (key === "accusedActs") {
        const accusedActs = Array.isArray(rawValue)
          ? (rawValue as AccusedActRecordValue[])
          : [];
        if (accusedActs.length > 0) {
          payload.accused_acts = accusedActs.map((record) => ({
            act: record.act,
            jurisdiction: record.jurisdiction.trim(),
            start_date: record.startDate,
            ...(record.endDate ? { end_date: record.endDate } : {}),
            actor: record.actor.trim(),
            status: record.status,
            purpose: record.purpose,
            regulatory_path: record.regulatoryPath,
            instrumentality: record.instrumentality.trim(),
            liability_theory: record.liabilityTheory,
            ...(record.performsAllClaimSteps !== undefined
              ? { performs_all_claim_steps: record.performsAllClaimSteps }
              : {}),
            ...(record.directInfringer?.trim()
              ? { direct_infringer: record.directInfringer.trim() }
              : {}),
            ...(record.knowledgeOfPatent !== undefined
              ? { knowledge_of_patent: record.knowledgeOfPatent }
              : {}),
            ...(record.affirmativeEncouragement !== undefined
              ? { affirmative_encouragement: record.affirmativeEncouragement }
              : {}),
            ...(record.manufacturingJurisdiction?.trim()
              ? {
                  manufacturing_jurisdiction:
                    record.manufacturingJurisdiction.trim(),
                }
              : {}),
            ...(record.processUsed?.trim()
              ? { process_used: record.processUsed.trim() }
              : {}),
            ...(record.processUseVerified !== undefined
              ? { process_use_verified: record.processUseVerified }
              : {}),
            ...(record.materiallyChangedAfterProcess !== undefined
              ? {
                  materially_changed_after_process:
                    record.materiallyChangedAfterProcess,
                }
              : {}),
            ...(record.trivialComponentAfterProcess !== undefined
              ? {
                  trivial_component_after_process:
                    record.trivialComponentAfterProcess,
                }
              : {}),
            ...(record.targetProductIdentity?.trim()
              ? { target_product_identity: record.targetProductIdentity.trim() }
              : {}),
            ...(record.proposedIndication?.trim()
              ? { proposed_indication: record.proposedIndication.trim() }
              : {}),
            ...(record.proposedLabelUse?.trim()
              ? { proposed_label_use: record.proposedLabelUse.trim() }
              : {}),
            ...(record.labelCarveOutState
              ? { label_carve_out_state: record.labelCarveOutState }
              : {}),
            ...(record.claimedUseMatchReceipts?.length
              ? {
                  claimed_use_match_receipts:
                    record.claimedUseMatchReceipts.map((receipt) => ({
                      ...receipt,
                    })),
                }
              : {}),
          }));
        }
        return;
      }

      const textValue = normalizeText(rawValue);
      if (textValue) {
        writablePayload[payloadKey] = textValue;
      }
    },
  );

  return Object.keys(payload).length > 0 ? payload : undefined;
}

export function productContextPayloadToValue(
  payload: AnalysisProductContext | undefined | null,
): ProductContextValue {
  if (!payload) {
    return { ...EMPTY_PRODUCT_CONTEXT };
  }

  return {
    productName: payload.product_name ?? "",
    dosageForm: payload.dosage_form ?? "",
    routeOfAdministration: payload.route_of_administration ?? "",
    strength: payload.strength ?? "",
    releaseProfile: payload.release_profile ?? "",
    saltPolymorphForm: payload.salt_polymorph_form ?? "",
    keyExcipients: payload.key_excipients ?? [],
    indication: payload.indication ?? "",
    patientPopulation: payload.patient_population ?? "",
    combinationAssets: payload.combination_assets ?? [],
    referenceProduct: payload.reference_product ?? "",
    manufacturingRoute: payload.manufacturing_route ?? "",
    commercialAction: payload.commercial_action ?? "",
    decisionDeadline: payload.decision_deadline ?? "",
    commercialTerritories: payload.commercial_territories ?? [],
    accusedActs:
      payload.accused_acts?.map((record) => ({
        act: record.act,
        jurisdiction: record.jurisdiction,
        startDate: record.start_date,
        endDate: record.end_date ?? undefined,
        actor: record.actor,
        status: record.status,
        purpose: record.purpose,
        regulatoryPath: record.regulatory_path,
        instrumentality: record.instrumentality,
        liabilityTheory: record.liability_theory,
        performsAllClaimSteps: record.performs_all_claim_steps ?? undefined,
        directInfringer: record.direct_infringer ?? undefined,
        knowledgeOfPatent: record.knowledge_of_patent ?? undefined,
        affirmativeEncouragement: record.affirmative_encouragement ?? undefined,
        manufacturingJurisdiction:
          record.manufacturing_jurisdiction ?? undefined,
        processUsed: record.process_used ?? undefined,
        processUseVerified: record.process_use_verified ?? undefined,
        materiallyChangedAfterProcess:
          record.materially_changed_after_process ?? undefined,
        trivialComponentAfterProcess:
          record.trivial_component_after_process ?? undefined,
        targetProductIdentity: record.target_product_identity ?? undefined,
        proposedIndication: record.proposed_indication ?? undefined,
        proposedLabelUse: record.proposed_label_use ?? undefined,
        labelCarveOutState: record.label_carve_out_state ?? undefined,
        claimedUseMatchReceipts:
          record.claimed_use_match_receipts?.map((receipt) => ({
            ...receipt,
          })) ?? [],
      })) ?? [],
    knownPatentsOrAssignees: payload.known_patents_or_assignees ?? [],
    ownedOrLicensedIp: payload.owned_or_licensed_ip ?? "",
  };
}

export function getProductContextRequiredFields(
  matterScope: MatterScopePreflightValue,
): ProductContextField[] {
  const fields = [
    ...BASE_REVIEW_FIELDS,
    ...(FIELDS_BY_ASSET_TYPE[matterScope.assetTypeHint] ?? []),
    ...getIntendedActionContextFields(matterScope),
  ];
  return Array.from(new Set(fields));
}

export function isProductContextLaunchGated(
  matterScope: MatterScopePreflightValue,
): boolean {
  return matterScope.intendedActions.some((action) =>
    HIGH_RELIANCE_ACTIONS.has(action),
  );
}

export function getProductContextLaunchRequiredFields(
  matterScope: MatterScopePreflightValue,
): ProductContextField[] {
  if (!isProductContextLaunchGated(matterScope)) {
    return [];
  }

  const fields = [
    ...CORE_HIGH_RELIANCE_FIELDS,
    ...(FIELDS_BY_ASSET_TYPE[matterScope.assetTypeHint] ?? []),
    ...getIntendedActionContextFields(matterScope),
  ];

  return Array.from(new Set(fields));
}

export function getProductContextLaunchGaps({
  context,
  matterScope,
}: {
  context: ProductContextValue | undefined;
  matterScope: MatterScopePreflightValue;
}): ProductContextField[] {
  return getProductContextLaunchRequiredFields(matterScope).filter(
    (field) => !hasProductContextFieldValue(context, field),
  );
}

export function getProductContextLaunchBlocker({
  context,
  matterScope,
}: {
  context: ProductContextValue | undefined;
  matterScope: MatterScopePreflightValue;
}): string | null {
  const gaps = getProductContextLaunchGaps({ context, matterScope });

  if (gaps.length === 0) {
    return null;
  }

  const actionLabels = matterScope.intendedActions
    .map((action) => HIGH_RELIANCE_ACTION_LABELS[action])
    .filter((label): label is string => Boolean(label));
  const scopeLabel = formatPlainList(actionLabels);
  const gapLabels = gaps.map((field) => PRODUCT_CONTEXT_LABELS[field]);
  const preview =
    gapLabels.length > 5
      ? `${gapLabels.slice(0, 5).join(", ")}, and ${gapLabels.length - 5} more`
      : formatPlainList(gapLabels);

  return `${scopeLabel} scopes require core product context before launch: ${preview}. Add facts or enter "Unknown" for fields counsel has not supplied.`;
}

export function getProductContextGaps({
  context,
  matterScope,
}: {
  context: ProductContextValue | undefined;
  matterScope: MatterScopePreflightValue;
}): ProductContextField[] {
  return getProductContextRequiredFields(matterScope).filter(
    (field) => !hasProductContextFieldValue(context, field),
  );
}
