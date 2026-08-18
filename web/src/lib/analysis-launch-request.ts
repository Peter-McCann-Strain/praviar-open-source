import { storeToPipelineConfig } from "@/lib/pipeline-config";
import { serializeProductContext } from "@/lib/product-context";
import type { InputType } from "@/components/chemistry/smiles-input";
import type { ConfigState } from "@/stores/config-store";
import type {
  MatterScopePreflightValue,
  ProductContextValue,
} from "@/types/pipeline";

type ConfirmedSubmittedIdentity = {
  inputType: Exclude<InputType, null>;
  value: string;
};

const SUBMITTED_INPUT_TYPE: Record<
  ConfirmedSubmittedIdentity["inputType"],
  "name" | "smiles" | "cas" | "inchi" | "inchikey"
> = {
  "CAS Number": "cas",
  InChI: "inchi",
  InChIKey: "inchikey",
  Name: "name",
  SMILES: "smiles",
};

export function buildAnalysisLaunchRequest(
  compoundInput: string,
  state: ConfigState,
  matterScope?: MatterScopePreflightValue,
  productContext?: ProductContextValue,
  submittedIdentity?: ConfirmedSubmittedIdentity,
) {
  const normalizedCompoundInput = compoundInput.trim();
  if (
    !submittedIdentity ||
    submittedIdentity.value.trim() !== normalizedCompoundInput
  ) {
    throw new Error(
      "A confirmed submitted identity matching the compound input is required",
    );
  }
  const serializedProductContext = serializeProductContext(productContext);

  return {
    compound_input: normalizedCompoundInput,
    input_type: SUBMITTED_INPUT_TYPE[submittedIdentity.inputType],
    submitted_identity_confirmed: true as const,
    submitted_identity_value: normalizedCompoundInput,
    trust_mode: state.trustMode,
    jurisdiction_bundle: state.jurisdictionBundle,
    target_jurisdictions: state.targetJurisdictions,
    ...(matterScope
      ? {
          asset_type_hint: matterScope.assetTypeHint,
          development_stage: matterScope.developmentStage,
          intended_actions: matterScope.intendedActions,
        }
      : {}),
    ...(serializedProductContext
      ? { product_context: serializedProductContext }
      : {}),
    config: storeToPipelineConfig(state),
  };
}
