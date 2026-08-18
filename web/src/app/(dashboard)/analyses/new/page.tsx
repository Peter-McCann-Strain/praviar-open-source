"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ChevronDown,
  ClipboardCheck,
  CreditCard,
  FileCheck2,
  Lightbulb,
  LockKeyhole,
  SlidersHorizontal,
  Sparkles,
  Target,
  TriangleAlert,
} from "lucide-react";
import { CreditPackCheckoutReconciliation } from "@/components/billing/credit-pack-reconciliation";
import { useCreateAnalysis } from "@/hooks/use-analysis";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useClientReady } from "@/hooks/use-client-ready";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";
import {
  useBillingStatus,
  useRequestCreditCapacity,
  type BillingStatus,
  type CreditCapacityRequestSource,
} from "@/hooks/use-billing";
import { useConfigPresets, useCreatePreset } from "@/hooks/use-config";
import {
  detectInputType,
  getCompoundInputReadiness,
} from "@/components/chemistry/smiles-input";
import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import { CompoundInputStep } from "@/components/analysis-wizard/compound-input-step";
import { ConfigurationStep } from "@/components/analysis-wizard/configuration-step";
import { EvidenceLaunchRail } from "@/components/analysis-wizard/evidence-launch-rail";
import {
  MatterScopePreflight,
  formatScopeLabel,
  getMatterScopeSuggestion,
} from "@/components/analysis-wizard/matter-scope-preflight";
import { ProductContextBrief } from "@/components/analysis-wizard/product-context-brief";
import {
  ReviewLaunchStep,
  type LaunchCapacitySummary,
} from "@/components/analysis-wizard/review-launch-step";
import { WizardStepper } from "@/components/analysis-wizard/wizard-stepper";
import {
  getConfigValidationIssues,
  getEnabledSources,
} from "@/components/config/helpers";
import { buildAnalysisLaunchRequest } from "@/lib/analysis-launch-request";
import {
  formatJurisdictionList,
  getLaunchReadyJurisdictions,
  getRuntimeSearchJurisdictions,
} from "@/lib/jurisdiction-bundles";
import { trackMarketingEvent } from "@/lib/marketing-analytics";
import { logError } from "@/lib/error-logger";
import { APIError, isAuthBoundaryError } from "@/lib/api-client";
import { authScopeKey } from "@/lib/query-keys";
import { ANALYSIS_LAUNCH_DRAFT_STORAGE_PREFIX } from "@/lib/analysis-launch-draft-storage";
import {
  clearMarketingCompoundHandoff,
  consumeMarketingCompoundHandoff,
} from "@/lib/marketing-compound-handoff";
import {
  pipelineConfigToStore,
  storeToPipelineConfig,
} from "@/lib/pipeline-config";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import {
  EMPTY_PRODUCT_CONTEXT,
  getProductContextLaunchBlocker,
} from "@/lib/product-context";
import {
  formatReportRequestCount,
  getReportCreditCapacitySnapshot,
} from "@/lib/report-credit-capacity";
import { createAnalysisSchema, type CreateAnalysis } from "@/lib/validators";
import { PROBLEM_TYPES } from "@/lib/problem-types";
import { useConfigStore } from "@/stores/config-store";
import { useToastStore } from "@/stores/toast-store";
import type {
  AccusedActRecordValue,
  AssetTypeHint,
  DevelopmentStage,
  IntendedAction,
  MatterScopePreflightValue,
  ProductContextValue,
} from "@/types/pipeline";
import NewAnalysisLoading from "./loading";
import { OperationalStatusFrame } from "@/components/shared/operational-status-frame";

interface NewAnalysisWorkflowProps {
  canManageBilling: boolean;
  canManagePresets: boolean;
  creditCheckoutResumeState: CreditCheckoutResumeState;
  initialCompoundInput: string;
  launchDraft: AnalysisLaunchDraft | null;
  shouldTrackPrefill: boolean;
  token: string | null;
}

type CreditCheckoutResumeState = {
  draftRestored: boolean;
  sessionId: string | null;
  state: "cancelled" | "success";
} | null;

interface AnalysisLaunchDraft {
  authBoundaryKey: string;
  compoundInput: string;
  createdAt: string;
  id: string;
  idempotencyKey: string;
  identityConfirmation: SubmittedIdentityConfirmation | null;
  inputType: string | null;
  matterScope: MatterScopePreflightValue;
  productContext: ProductContextValue;
  step: number;
  version: 5;
}

interface SubmittedIdentityConfirmation {
  inputType: Exclude<ReturnType<typeof detectInputType>, null>;
  value: string;
}

interface LaunchErrorAction {
  href?: string;
  label: string;
  onClick?: () => void;
  pending?: boolean;
}

const DEFAULT_MATTER_SCOPE: MatterScopePreflightValue = {
  assetTypeHint: "small_molecule",
  developmentStage: "discovery",
  intendedActions: ["diligence_screen"],
};

const SAVE_CONFIGURATION_ERROR_MESSAGE =
  "Configuration was not saved. Review your connection and try again.";
const START_ANALYSIS_ERROR_MESSAGE =
  "Launch outcome could not be confirmed. A Report Credit may have been reserved. Reconcile this exact launch before submitting another request.";
const START_ANALYSIS_DISPATCH_ERROR_MESSAGE =
  "Launch outcome could not be confirmed after dispatch handoff. A Report Credit may have been reserved or refunded. Reconcile this exact launch before submitting another request.";
const ANALYSIS_CAPACITY_ERROR_TYPE = PROBLEM_TYPES.analysisCapacityExhausted;
const START_ANALYSIS_RATE_LIMIT_MESSAGE =
  "Analysis launch is temporarily rate-limited. No additional Report Credit is needed; wait for the cooldown, then retry this exact launch.";
const LAUNCH_IDENTITY_CONFIRMATION_ERROR_MESSAGE =
  "Confirm the exact submitted identity before continuing.";
const LAUNCH_DRAFT_VERSION = 5;
const LAUNCH_DRAFT_TTL_MS = 7 * 24 * 60 * 60 * 1000;
const LAUNCH_DRAFT_ID_PATTERN = /^ld_[A-Za-z0-9_-]{8,80}$/;
const LAUNCH_IDEMPOTENCY_KEY_PATTERN = /^[!-~]{16,128}$/u;
const ACTIVE_LAUNCH_DRAFT_STORAGE_PREFIX = `${ANALYSIS_LAUNCH_DRAFT_STORAGE_PREFIX}active:`;
const DEVELOPMENT_STAGES = new Set<DevelopmentStage>([
  "discovery",
  "lead_optimization",
  "preclinical",
  "clinical",
  "commercial",
]);
const ASSET_TYPE_HINTS = new Set<AssetTypeHint>([
  "small_molecule",
  "markush_candidate",
  "biologic_or_sequence",
  "formulation",
  "process_or_synthesis",
  "combination",
  "unknown",
]);
const INTENDED_ACTIONS = new Set<IntendedAction>([
  "manufacture_import",
  "commercial_launch",
  "formulation_review",
  "method_of_use_review",
  "design_around",
  "diligence_screen",
  "monitor_continuations",
]);
const PRODUCT_CONTEXT_TEXT_FIELDS = [
  "productName",
  "dosageForm",
  "routeOfAdministration",
  "strength",
  "releaseProfile",
  "saltPolymorphForm",
  "indication",
  "patientPopulation",
  "referenceProduct",
  "manufacturingRoute",
  "commercialAction",
  "decisionDeadline",
  "ownedOrLicensedIp",
] satisfies Array<keyof ProductContextValue>;
const PRODUCT_CONTEXT_LIST_FIELDS = [
  "keyExcipients",
  "combinationAssets",
  "commercialTerritories",
  "knownPatentsOrAssignees",
] satisfies Array<keyof ProductContextValue>;

function matterScopesEqual(
  left: MatterScopePreflightValue,
  right: MatterScopePreflightValue,
) {
  return (
    left.assetTypeHint === right.assetTypeHint &&
    left.developmentStage === right.developmentStage &&
    left.intendedActions.length === right.intendedActions.length &&
    left.intendedActions.every(
      (action, index) => action === right.intendedActions[index],
    )
  );
}

function getReportRequestCapacityBlocker(
  billingStatus: BillingStatus | undefined,
  isBillingLoading: boolean,
  isBillingAccessRestricted = false,
  canManageBilling = false,
) {
  if (isBillingAccessRestricted) {
    return "FTO report request capacity access is restricted. Restore billing access before starting another request.";
  }

  if (!billingStatus) {
    return isBillingLoading
      ? "Checking FTO report request capacity before launch controls are enabled."
      : "Unable to confirm FTO report request capacity. Reload billing status before starting another request.";
  }

  if (billingStatus.plan === "enterprise") {
    return null;
  }

  const capacity = getReportCreditCapacitySnapshot(billingStatus);

  return capacity.effectiveRemaining <= 0
    ? canManageBilling
      ? "No FTO report request capacity remains. Buy Report Credits or wait for the next billing period before starting another request."
      : "No FTO report request capacity remains. Ask a workspace administrator to add Report Credits or wait for the next billing period."
    : null;
}

function getStartAnalysisCapacityErrorMessage(canManageBilling: boolean) {
  return canManageBilling
    ? "Launch capacity or request rate changed. Reconcile the analysis library, then refresh capacity before buying Report Credits or submitting another request."
    : "Launch capacity or request rate changed. Reconcile the analysis library, then ask a workspace administrator to refresh Report Credit capacity before submitting another request.";
}

function getLaunchCapacitySummary(
  billingStatus: BillingStatus | undefined,
  isBillingLoading: boolean,
  isBillingAccessRestricted = false,
): LaunchCapacitySummary {
  if (isBillingAccessRestricted) {
    return {
      additionalCapacityRemaining: null,
      creditBackedRemaining: null,
      includedRemaining: null,
      isAccessRestricted: true,
      isEnterprise: false,
      isLoading: false,
      purchasedCredits: null,
      totalRemaining: null,
    };
  }

  if (!billingStatus) {
    return {
      additionalCapacityRemaining: null,
      creditBackedRemaining: null,
      includedRemaining: null,
      isEnterprise: false,
      isLoading: isBillingLoading,
      purchasedCredits: null,
      totalRemaining: null,
    };
  }

  if (billingStatus.plan === "enterprise") {
    return {
      additionalCapacityRemaining: null,
      creditBackedRemaining: null,
      includedRemaining: null,
      isEnterprise: true,
      isLoading: false,
      purchasedCredits: null,
      totalRemaining: null,
    };
  }

  const capacity = getReportCreditCapacitySnapshot(billingStatus);

  return {
    additionalCapacityRemaining: capacity.additionalCapacityRemaining,
    creditBackedRemaining: capacity.creditBackedRemaining,
    includedRemaining: capacity.includedRemaining,
    isEnterprise: false,
    isLoading: false,
    purchasedCredits: capacity.purchasedCreditsBalance,
    totalRemaining: capacity.effectiveRemaining,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeDraftText(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function normalizeDraftTextList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map(normalizeDraftText).filter(Boolean);
}

function normalizeDraftStep(value: unknown): number {
  return value === 1 || value === 2 || value === 3 ? value : 1;
}

function parseStoredIdentityConfirmation(
  value: unknown,
  compoundInput: string,
): SubmittedIdentityConfirmation | null {
  if (!isRecord(value)) {
    return null;
  }
  const normalizedCompoundInput = compoundInput.trim();
  const inputType = detectInputType(normalizedCompoundInput);
  const confirmedValue = normalizeDraftText(value.value);
  return inputType &&
    value.inputType === inputType &&
    confirmedValue === normalizedCompoundInput
    ? { inputType, value: confirmedValue }
    : null;
}

function isSafeLaunchDraftId(
  value: string | null | undefined,
): value is string {
  return Boolean(value && LAUNCH_DRAFT_ID_PATTERN.test(value));
}

function readLaunchDraftStorageValue(key: string): string | null {
  for (const storage of [window.sessionStorage, window.localStorage]) {
    try {
      const value = storage.getItem(key);
      if (value !== null) {
        return value;
      }
    } catch {
      // Continue to the other browser storage before failing closed.
    }
  }
  return null;
}

function writeLaunchDraftStorageValue(key: string, value: string) {
  for (const storage of [window.localStorage, window.sessionStorage]) {
    try {
      storage.setItem(key, value);
    } catch {
      // A durable local copy is preferred; the tab-scoped copy is a fallback.
    }
  }
}

function removeLaunchDraftStorageValue(key: string) {
  for (const storage of [window.localStorage, window.sessionStorage]) {
    try {
      storage.removeItem(key);
    } catch {
      // Cleanup is best-effort; auth-bound reads still fail closed.
    }
  }
}

function createAnalysisLaunchDraftId(): string {
  const randomValue =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

  return `ld_${randomValue.replace(/[^A-Za-z0-9_-]/g, "")}`;
}

function createAnalysisLaunchIdempotencyKey(): string {
  return crypto.randomUUID();
}

function parseStoredMatterScope(
  value: unknown,
): MatterScopePreflightValue | null {
  if (!isRecord(value)) {
    return null;
  }

  const assetTypeHint = value.assetTypeHint;
  const developmentStage = value.developmentStage;
  const intendedActions = Array.isArray(value.intendedActions)
    ? value.intendedActions.filter(
        (action): action is IntendedAction =>
          typeof action === "string" &&
          INTENDED_ACTIONS.has(action as IntendedAction),
      )
    : [];

  if (
    typeof assetTypeHint !== "string" ||
    typeof developmentStage !== "string" ||
    !ASSET_TYPE_HINTS.has(assetTypeHint as AssetTypeHint) ||
    !DEVELOPMENT_STAGES.has(developmentStage as DevelopmentStage) ||
    intendedActions.length === 0
  ) {
    return null;
  }

  return {
    assetTypeHint: assetTypeHint as AssetTypeHint,
    developmentStage: developmentStage as DevelopmentStage,
    intendedActions,
  };
}

function parseStoredProductContext(value: unknown): ProductContextValue | null {
  if (!isRecord(value)) {
    return null;
  }

  const context: ProductContextValue = { ...EMPTY_PRODUCT_CONTEXT };

  PRODUCT_CONTEXT_TEXT_FIELDS.forEach((key) => {
    context[key] = normalizeDraftText(value[key]);
  });

  PRODUCT_CONTEXT_LIST_FIELDS.forEach((key) => {
    context[key] = normalizeDraftTextList(value[key]);
  });
  context.accusedActs = Array.isArray(value.accusedActs)
    ? value.accusedActs
        .map((candidate): AccusedActRecordValue | null => {
          if (!isRecord(candidate)) {
            return null;
          }
          const act = normalizeDraftText(candidate.act);
          const status = normalizeDraftText(candidate.status);
          const purpose = normalizeDraftText(candidate.purpose);
          const regulatoryPath = normalizeDraftText(candidate.regulatoryPath);
          const liabilityTheory = normalizeDraftText(candidate.liabilityTheory);
          if (
            ![
              "manufacture",
              "import",
              "offer_for_sale",
              "sale",
              "use",
              "regulatory_submission",
            ].includes(act) ||
            !["planned", "actual", "denied", "hypothetical"].includes(status) ||
            ![
              "commercial",
              "regulatory_approval",
              "clinical_research",
              "experimental",
              "internal_research",
              "other",
              "unknown",
            ].includes(purpose) ||
            ![
              "none",
              "anda",
              "nda_505_b_1",
              "nda_505_b_2",
              "bla_351_a",
              "abla",
              "biosimilar_351_k",
              "unknown",
            ].includes(regulatoryPath) ||
            ![
              "direct",
              "induced",
              "contributory",
              "artificial_infringement",
              "unknown",
            ].includes(liabilityTheory)
          ) {
            return null;
          }
          return {
            act: act as AccusedActRecordValue["act"],
            jurisdiction: normalizeDraftText(candidate.jurisdiction),
            startDate: normalizeDraftText(candidate.startDate),
            endDate: normalizeDraftText(candidate.endDate) || undefined,
            actor: normalizeDraftText(candidate.actor),
            status: status as AccusedActRecordValue["status"],
            purpose: purpose as AccusedActRecordValue["purpose"],
            regulatoryPath:
              regulatoryPath as AccusedActRecordValue["regulatoryPath"],
            instrumentality: normalizeDraftText(candidate.instrumentality),
            liabilityTheory:
              liabilityTheory as AccusedActRecordValue["liabilityTheory"],
            performsAllClaimSteps:
              typeof candidate.performsAllClaimSteps === "boolean"
                ? candidate.performsAllClaimSteps
                : undefined,
            directInfringer:
              normalizeDraftText(candidate.directInfringer) || undefined,
            knowledgeOfPatent:
              typeof candidate.knowledgeOfPatent === "boolean"
                ? candidate.knowledgeOfPatent
                : undefined,
            affirmativeEncouragement:
              typeof candidate.affirmativeEncouragement === "boolean"
                ? candidate.affirmativeEncouragement
                : undefined,
            manufacturingJurisdiction:
              normalizeDraftText(candidate.manufacturingJurisdiction) ||
              undefined,
            processUsed: normalizeDraftText(candidate.processUsed) || undefined,
            processUseVerified:
              typeof candidate.processUseVerified === "boolean"
                ? candidate.processUseVerified
                : undefined,
            materiallyChangedAfterProcess:
              typeof candidate.materiallyChangedAfterProcess === "boolean"
                ? candidate.materiallyChangedAfterProcess
                : undefined,
            trivialComponentAfterProcess:
              typeof candidate.trivialComponentAfterProcess === "boolean"
                ? candidate.trivialComponentAfterProcess
                : undefined,
            targetProductIdentity:
              normalizeDraftText(candidate.targetProductIdentity) || undefined,
            proposedIndication:
              normalizeDraftText(candidate.proposedIndication) || undefined,
            proposedLabelUse:
              normalizeDraftText(candidate.proposedLabelUse) || undefined,
            labelCarveOutState: [
              "none",
              "partial",
              "complete",
              "unknown",
            ].includes(normalizeDraftText(candidate.labelCarveOutState))
              ? (normalizeDraftText(
                  candidate.labelCarveOutState,
                ) as NonNullable<AccusedActRecordValue["labelCarveOutState"]>)
              : undefined,
            claimedUseMatchReceipts: [],
          };
        })
        .filter((record): record is AccusedActRecordValue => record !== null)
    : [];

  return context;
}

function readAnalysisLaunchDraft(
  draftId: string | null,
  authBoundaryKey: string | null,
): AnalysisLaunchDraft | null {
  if (
    !isSafeLaunchDraftId(draftId) ||
    !authBoundaryKey ||
    typeof window === "undefined"
  ) {
    return null;
  }

  try {
    const rawDraft = readLaunchDraftStorageValue(
      `${ANALYSIS_LAUNCH_DRAFT_STORAGE_PREFIX}${draftId}`,
    );
    if (!rawDraft) {
      return null;
    }

    const parsed = JSON.parse(rawDraft) as unknown;
    if (
      !isRecord(parsed) ||
      parsed.version !== LAUNCH_DRAFT_VERSION ||
      parsed.authBoundaryKey !== authBoundaryKey
    ) {
      return null;
    }

    const createdAt = normalizeDraftText(parsed.createdAt);
    const createdAtMs = Date.parse(createdAt);
    if (
      !Number.isFinite(createdAtMs) ||
      Date.now() - createdAtMs > LAUNCH_DRAFT_TTL_MS ||
      createdAtMs - Date.now() > 60_000
    ) {
      clearAnalysisLaunchDraft(draftId, authBoundaryKey);
      return null;
    }

    const matterScope = parseStoredMatterScope(parsed.matterScope);
    const productContext = parseStoredProductContext(parsed.productContext);
    const idempotencyKey = normalizeDraftText(parsed.idempotencyKey);
    if (
      !matterScope ||
      !productContext ||
      !LAUNCH_IDEMPOTENCY_KEY_PATTERN.test(idempotencyKey)
    ) {
      return null;
    }

    const compoundInput = normalizeDraftText(parsed.compoundInput);
    const identityConfirmation = parseStoredIdentityConfirmation(
      parsed.identityConfirmation,
      compoundInput,
    );
    const storedStep = normalizeDraftStep(parsed.step);

    return {
      authBoundaryKey,
      compoundInput,
      createdAt,
      id: draftId,
      idempotencyKey,
      identityConfirmation,
      inputType: detectInputType(compoundInput),
      matterScope,
      productContext,
      step: identityConfirmation ? storedStep : 1,
      version: LAUNCH_DRAFT_VERSION,
    };
  } catch {
    return null;
  }
}

function writeAnalysisLaunchDraft(draft: AnalysisLaunchDraft) {
  if (!isSafeLaunchDraftId(draft.id) || typeof window === "undefined") {
    return;
  }

  writeLaunchDraftStorageValue(
    `${ANALYSIS_LAUNCH_DRAFT_STORAGE_PREFIX}${draft.id}`,
    JSON.stringify(draft),
  );
  writeLaunchDraftStorageValue(
    `${ACTIVE_LAUNCH_DRAFT_STORAGE_PREFIX}${draft.authBoundaryKey}`,
    draft.id,
  );
}

function readActiveAnalysisLaunchDraftId(
  authBoundaryKey: string | null,
): string | null {
  if (!authBoundaryKey || typeof window === "undefined") {
    return null;
  }
  const draftId = readLaunchDraftStorageValue(
    `${ACTIVE_LAUNCH_DRAFT_STORAGE_PREFIX}${authBoundaryKey}`,
  );
  return isSafeLaunchDraftId(draftId) ? draftId : null;
}

function clearAnalysisLaunchDraft(
  draftId: string | null | undefined,
  authBoundaryKey?: string | null,
) {
  if (!isSafeLaunchDraftId(draftId) || typeof window === "undefined") {
    return;
  }

  removeLaunchDraftStorageValue(
    `${ANALYSIS_LAUNCH_DRAFT_STORAGE_PREFIX}${draftId}`,
  );
  if (authBoundaryKey) {
    const activeKey = `${ACTIVE_LAUNCH_DRAFT_STORAGE_PREFIX}${authBoundaryKey}`;
    if (readLaunchDraftStorageValue(activeKey) === draftId) {
      removeLaunchDraftStorageValue(activeKey);
    }
  }
}

function buildLaunchCreditReturnTo(launchDraftId: string) {
  const params = new URLSearchParams({
    resume: "credit_checkout",
    launch_draft_id: launchDraftId,
  });
  return `/analyses/new?${params.toString()}`;
}

function buildLaunchCreditPackHref(pack: string, launchDraftId: string) {
  const params = new URLSearchParams({
    intent: "credits",
    needed_reports: "1",
    pack,
    return_to: buildLaunchCreditReturnTo(launchDraftId),
    source: "launch",
  });
  return `/billing?${params.toString()}`;
}

function getApiErrorStatus(error: unknown) {
  if (error instanceof APIError) {
    return error.status;
  }
  if (isRecord(error) && typeof error.status === "number") {
    return error.status;
  }
  return null;
}

function isAnalysisCapacityError(error: unknown) {
  return (
    error instanceof APIError &&
    error.telemetry.typeUri === ANALYSIS_CAPACITY_ERROR_TYPE
  );
}

function NewAnalysisWorkflow({
  canManageBilling,
  canManagePresets,
  creditCheckoutResumeState,
  initialCompoundInput,
  launchDraft,
  shouldTrackPrefill,
  token,
}: NewAnalysisWorkflowProps) {
  const router = useRouter();
  const createAnalysis = useCreateAnalysis(token);
  const billingStatusQuery = useBillingStatus(token);
  const requestCreditCapacity = useRequestCreditCapacity(token);
  const { data: savedPresets } = useConfigPresets(token);
  const createPreset = useCreatePreset(token);
  const config = useConfigStore();
  const toast = useToastStore();
  const [launchDraftId] = useState(
    () => launchDraft?.id ?? createAnalysisLaunchDraftId(),
  );
  const [launchDraftCreatedAt] = useState(
    () => launchDraft?.createdAt || new Date().toISOString(),
  );
  const [launchIdempotencyKey, setLaunchIdempotencyKey] = useState(
    () => launchDraft?.idempotencyKey ?? createAnalysisLaunchIdempotencyKey(),
  );
  const [step, setStep] = useState(() => launchDraft?.step ?? 1);
  const stepContentRef = useRef<HTMLDivElement>(null);
  const previousStepRef = useRef(step);
  const [compoundInput, setCompoundInput] = useState(
    launchDraft?.compoundInput ?? initialCompoundInput,
  );
  const [submittedIdentityConfirmation, setSubmittedIdentityConfirmation] =
    useState<SubmittedIdentityConfirmation | null>(
      () => launchDraft?.identityConfirmation ?? null,
    );
  // Seed the detected type for restored or query-prefilled input so the
  // identity decision sheet and later review share one classification before
  // the user generates an input event.
  const [inputType, setInputType] = useState<string | null>(() =>
    launchDraft
      ? launchDraft.inputType
      : initialCompoundInput
        ? detectInputType(initialCompoundInput)
        : null,
  );
  const [showSavePreset, setShowSavePreset] = useState(false);
  const [presetName, setPresetName] = useState("");
  const [presetDescription, setPresetDescription] = useState("");
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [launchErrorAction, setLaunchErrorAction] =
    useState<LaunchErrorAction | null>(null);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [productContext, setProductContext] = useState<ProductContextValue>(
    launchDraft?.productContext ?? { ...EMPTY_PRODUCT_CONTEXT },
  );
  const [matterScope, setMatterScope] = useState<MatterScopePreflightValue>(
    () =>
      launchDraft?.matterScope ??
      (initialCompoundInput
        ? getMatterScopeSuggestion({
            compoundInput: initialCompoundInput,
            inputType: detectInputType(initialCompoundInput),
          })
        : DEFAULT_MATTER_SCOPE),
  );

  useEffect(() => {
    if (previousStepRef.current === step) {
      return undefined;
    }

    previousStepRef.current = step;
    const frame = window.requestAnimationFrame(() => {
      stepContentRef.current?.scrollIntoView?.({ block: "start" });
    });

    return () => window.cancelAnimationFrame(frame);
  }, [step]);
  const scopeSuggestion = useMemo(
    () => getMatterScopeSuggestion({ compoundInput, inputType }),
    [compoundInput, inputType],
  );
  const previousScopeSuggestionRef = useRef<MatterScopePreflightValue>(
    launchDraft
      ? getMatterScopeSuggestion({
          compoundInput: launchDraft.compoundInput,
          inputType: launchDraft.inputType,
        })
      : matterScope,
  );
  const trackedPrefillRef = useRef<string | null>(null);
  const launchInFlightRef = useRef(false);
  const sessionReady = DEMO_MODE_ENABLED || Boolean(token);
  const compoundReadiness = useMemo(
    () => getCompoundInputReadiness(compoundInput),
    [compoundInput],
  );
  const identityConfirmed =
    submittedIdentityConfirmation?.value === compoundInput.trim() &&
    submittedIdentityConfirmation.inputType === detectInputType(compoundInput);
  const identityConfirmationBlocker = identityConfirmed
    ? null
    : LAUNCH_IDENTITY_CONFIRMATION_ERROR_MESSAGE;
  const validationIssues = getConfigValidationIssues(config);
  const billingAccessRestricted = isAuthBoundaryError(billingStatusQuery.error);
  const visibleBillingStatus = billingAccessRestricted
    ? undefined
    : billingStatusQuery.data;
  const capacityBlocker = getReportRequestCapacityBlocker(
    visibleBillingStatus,
    billingStatusQuery.isLoading,
    billingAccessRestricted,
    canManageBilling,
  );
  const productContextBlocker = getProductContextLaunchBlocker({
    context: productContext,
    matterScope,
  });
  const launchCapacity = getLaunchCapacitySummary(
    visibleBillingStatus,
    billingStatusQuery.isLoading,
    billingAccessRestricted,
  );
  const launchBlocker = !sessionReady
    ? "Preparing secure session before launch controls are enabled."
    : !compoundReadiness.canProceed
      ? compoundReadiness.detail
      : (identityConfirmationBlocker ??
        validationIssues[0] ??
        productContextBlocker ??
        capacityBlocker);
  const enabledSources = getEnabledSources(config);
  const launchReadyJurisdictions = getLaunchReadyJurisdictions(
    config.targetJurisdictions,
  );
  const runtimeSearchJurisdictions = getRuntimeSearchJurisdictions({
    jurisdictionBundle: config.jurisdictionBundle,
    searchJurisdictions: config.searchJurisdictions,
    targetJurisdictions: config.targetJurisdictions,
  });
  const reviewPolicyLabel =
    config.hitlEnabled && config.hitlCheckpoints.length > 0
      ? `Identity + ${config.hitlCheckpoints.length} additional gate${
          config.hitlCheckpoints.length === 1 ? "" : "s"
        }`
      : "Resolved identity approval";
  const decisionSupportedLabel =
    matterScope.intendedActions.length > 0
      ? matterScope.intendedActions.map(formatScopeLabel).join(", ")
      : "Diligence screen";
  const capacitySummaryLabel = launchCapacity.isEnterprise
    ? "Enterprise capacity"
    : launchCapacity.isAccessRestricted
      ? "Capacity restricted"
      : launchCapacity.isLoading || launchCapacity.totalRemaining == null
        ? "Capacity checking"
        : `${formatReportRequestCount(launchCapacity.totalRemaining)} available`;
  const launchPillars = [
    {
      icon: FileCheck2,
      label: "Readiness",
      detail: compoundReadiness.canProceed
        ? `Compound accepted as ${compoundReadiness.inputType ?? "identifier"}`
        : compoundReadiness.label,
    },
    {
      icon: Target,
      label: "Scope",
      detail: `${formatScopeLabel(matterScope.assetTypeHint)}; ${formatScopeLabel(
        matterScope.developmentStage,
      )}`,
    },
    {
      icon: CreditCard,
      label: "Capacity",
      detail: capacitySummaryLabel,
    },
    {
      icon: ClipboardCheck,
      label: "Handoff",
      detail: reviewPolicyLabel,
    },
  ];
  const launchEvidenceSummary = [
    {
      label: "Sources",
      value:
        enabledSources.length > 0
          ? `${enabledSources.length} selected`
          : "Needs source",
    },
    {
      label: "Launch lanes",
      value: formatJurisdictionList(
        launchReadyJurisdictions,
        "No launch-ready lanes",
      ),
    },
    {
      label: "Runtime lanes",
      value: formatJurisdictionList(runtimeSearchJurisdictions),
    },
  ];

  const handleCompoundInputChange = (value: string) => {
    setCompoundInput(value);
    const detectedInputType = detectInputType(value);
    if (
      value.trim() !== submittedIdentityConfirmation?.value ||
      detectedInputType !== submittedIdentityConfirmation?.inputType
    ) {
      setSubmittedIdentityConfirmation(null);
    }
  };

  useEffect(() => {
    if (
      !shouldTrackPrefill ||
      !initialCompoundInput ||
      trackedPrefillRef.current === initialCompoundInput
    ) {
      return;
    }

    trackedPrefillRef.current = initialCompoundInput;

    trackMarketingEvent("prefilled_analysis_started", {
      destination: "new_analysis",
      source: "marketing_handoff",
    });
  }, [initialCompoundInput, shouldTrackPrefill]);

  useEffect(() => {
    writeAnalysisLaunchDraft({
      authBoundaryKey: authScopeKey(token),
      compoundInput,
      createdAt: launchDraftCreatedAt,
      id: launchDraftId,
      idempotencyKey: launchIdempotencyKey,
      identityConfirmation: identityConfirmed
        ? submittedIdentityConfirmation
        : null,
      inputType,
      matterScope,
      productContext,
      step,
      version: LAUNCH_DRAFT_VERSION,
    });
  }, [
    compoundInput,
    identityConfirmed,
    inputType,
    launchDraftCreatedAt,
    launchDraftId,
    launchIdempotencyKey,
    matterScope,
    productContext,
    step,
    submittedIdentityConfirmation,
    token,
  ]);

  useEffect(() => {
    if (!compoundInput.trim()) {
      previousScopeSuggestionRef.current = DEFAULT_MATTER_SCOPE;
      return;
    }

    const previousSuggestion = previousScopeSuggestionRef.current;
    previousScopeSuggestionRef.current = scopeSuggestion;

    setMatterScope((currentScope) =>
      matterScopesEqual(currentScope, previousSuggestion)
        ? scopeSuggestion
        : currentScope,
    );
  }, [compoundInput, scopeSuggestion]);

  const handleLoadPreset = (
    presetConfig: Partial<import("@/types/pipeline").PipelineConfig>,
  ) => {
    config.setConfig(pipelineConfigToStore(presetConfig));
  };

  const handleCancelSavePreset = () => {
    setShowSavePreset(false);
    setPresetName("");
    setPresetDescription("");
  };

  const handleSavePreset = async () => {
    if (!canManagePresets || !presetName.trim()) {
      return;
    }
    if (!sessionReady) {
      const message = "Preparing secure session before saving configuration.";
      setSessionError(message);
      toast.addToast(message, "error");
      return;
    }

    const currentConfig = storeToPipelineConfig(useConfigStore.getState());

    try {
      await createPreset.mutateAsync({
        name: presetName.trim(),
        description: presetDescription.trim() || undefined,
        config: currentConfig,
      });
      toast.addToast("Configuration saved", "success");
      handleCancelSavePreset();
      setSessionError(null);
    } catch (error) {
      logError(error, {
        source: "NewAnalysisWorkflow",
        extra: { action: "save_preset" },
      });
      const message = SAVE_CONFIGURATION_ERROR_MESSAGE;
      setSessionError(message);
      toast.addToast(message, "error");
    }
  };

  const requestReportCredits = async (
    requestedReports: number,
    source: CreditCapacityRequestSource,
  ) => {
    try {
      const response = await requestCreditCapacity.mutateAsync({
        requested_reports: requestedReports,
        source,
      });
      toast.addToast(
        `Report Credit request sent to ${response.notified_admins.toLocaleString()} workspace administrator${
          response.notified_admins === 1 ? "" : "s"
        }. Track reference ${response.request_id.slice(0, 8).toUpperCase()} in Billing under Report Credit requests.`,
        "success",
      );
    } catch (error) {
      logError(error, {
        source: "NewAnalysisWorkflow",
        extra: { action: "request_report_credits" },
      });
      toast.addToast(
        error instanceof APIError && error.status === 409
          ? "No active workspace administrator is available. Contact your workspace owner or Praviar support."
          : error instanceof APIError && error.status === 429
            ? "Report Credit requests are limited to three per hour. Wait for the cooldown before sending another request."
            : "Report Credit request was not sent. Retry after checking your connection.",
        "error",
      );
    }
  };

  const submitAnalysisLaunch = async (launchRequest: CreateAnalysis) => {
    if (launchInFlightRef.current) {
      return;
    }
    launchInFlightRef.current = true;
    setLaunchError(null);
    setLaunchErrorAction(null);

    try {
      const newAnalysis = await createAnalysis.mutateAsync({
        ...launchRequest,
        client_idempotency_key: launchIdempotencyKey,
      });
      clearAnalysisLaunchDraft(launchDraftId, authScopeKey(token));
      toast.addToast("Analysis started — tracking progress now", "success");
      router.push(`/analyses/${newAnalysis.id}`);
    } catch (error) {
      logError(error, {
        source: "NewAnalysisWorkflow",
        extra: { action: "start_analysis" },
      });
      const status = getApiErrorStatus(error);
      const capacityWasExhausted =
        status === 429 && isAnalysisCapacityError(error);
      const launchWasRateLimited = status === 429 && !capacityWasExhausted;
      const outcomeIsAmbiguous = status === null || status >= 500;
      const outcomeIsDefinitivelyRejected =
        status !== null && status < 500 && status !== 429;
      const message =
        status === 429
          ? capacityWasExhausted
            ? getStartAnalysisCapacityErrorMessage(canManageBilling)
            : START_ANALYSIS_RATE_LIMIT_MESSAGE
          : status === 409
            ? "This launch key already belongs to a different request. Do not submit another launch until the analysis library has been reconciled."
            : outcomeIsAmbiguous
              ? status === 503
                ? START_ANALYSIS_DISPATCH_ERROR_MESSAGE
                : START_ANALYSIS_ERROR_MESSAGE
              : "Analysis launch was rejected before acceptance. No Report Credit was consumed; review access and the submitted identity before trying again.";
      if (capacityWasExhausted) {
        setLaunchErrorAction({
          href: canManageBilling
            ? buildLaunchCreditPackHref("single_analysis", launchDraftId)
            : undefined,
          label: canManageBilling
            ? "Review Report Credits"
            : "Request Report Credits",
          onClick: canManageBilling
            ? undefined
            : () => {
                void requestReportCredits(1, "launch_retry");
              },
          pending: requestCreditCapacity.isPending,
        });
        void billingStatusQuery.refetch();
      } else if (launchWasRateLimited) {
        setLaunchErrorAction({
          label: "Retry exact launch",
          onClick: () => {
            void submitAnalysisLaunch(launchRequest);
          },
          pending: createAnalysis.isPending,
        });
      } else if (status === 409) {
        setLaunchErrorAction({
          href: "/analyses",
          label: "Open analysis library",
        });
      } else if (outcomeIsAmbiguous) {
        setLaunchErrorAction({
          label: "Reconcile exact launch",
          onClick: () => {
            void submitAnalysisLaunch(launchRequest);
          },
          pending: createAnalysis.isPending,
        });
        void billingStatusQuery.refetch();
      }
      if (outcomeIsDefinitivelyRejected) {
        setLaunchIdempotencyKey(createAnalysisLaunchIdempotencyKey());
      }
      setLaunchError(message);
      toast.addToast(message, "error");
    } finally {
      launchInFlightRef.current = false;
    }
  };

  const handleLaunch = async () => {
    setLaunchErrorAction(null);
    if (!sessionReady) {
      const message = "Preparing secure session before starting analysis.";
      setLaunchError(message);
      toast.addToast(message, "error");
      return;
    }
    if (!compoundReadiness.canProceed) {
      setLaunchError(compoundReadiness.detail);
      toast.addToast(compoundReadiness.detail, "error");
      return;
    }
    if (!identityConfirmed || !submittedIdentityConfirmation) {
      setLaunchError(LAUNCH_IDENTITY_CONFIRMATION_ERROR_MESSAGE);
      toast.addToast(LAUNCH_IDENTITY_CONFIRMATION_ERROR_MESSAGE, "error");
      return;
    }
    if (validationIssues.length > 0) {
      const message = validationIssues[0];
      setLaunchError(message);
      toast.addToast(message, "error");
      return;
    }
    if (productContextBlocker) {
      setLaunchError(productContextBlocker);
      toast.addToast(productContextBlocker, "error");
      return;
    }
    if (capacityBlocker) {
      setLaunchError(capacityBlocker);
      toast.addToast(capacityBlocker, "error");
      return;
    }

    const state = useConfigStore.getState();
    const launchRequest = buildAnalysisLaunchRequest(
      compoundInput,
      state,
      matterScope,
      productContext,
      submittedIdentityConfirmation,
    );
    const validation = createAnalysisSchema.safeParse(launchRequest);
    if (!validation.success) {
      const message = validation.error.issues[0].message;
      setLaunchError(message);
      toast.addToast(message, "error");
      return;
    }
    await submitAnalysisLaunch(validation.data);
  };

  return (
    <div className="mx-auto max-w-6xl space-y-3 animate-fade-up sm:space-y-7">
      <section className="praviar-analysis-launch-field -mx-4 overflow-hidden border-y border-[var(--border-default)] px-4 py-3 sm:mx-0 sm:rounded-lg sm:border sm:px-5 sm:py-5 md:p-6">
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(18rem,0.34fr)] xl:items-stretch">
          <div className="min-w-0">
            <div className="flex min-w-0 items-start gap-2.5 sm:gap-4">
              <PraviarMarkFrame size="hero" className="max-[359px]:hidden" />
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)] sm:text-xs">
                  Compound-first workflow
                </p>
                <h1 className="mt-1 text-2xl font-semibold leading-tight text-[var(--text-primary)] sm:type-heading-xl">
                  New FTO Analysis
                </h1>
                <p className="mt-2 hidden max-w-2xl text-sm leading-6 text-[var(--text-secondary)] sm:block sm:text-base">
                  Start with the molecule, then turn scope, evidence lanes,
                  capacity, and reviewer handoff into one launch-ready packet.
                </p>
              </div>
            </div>
            <div className="mt-4 grid gap-3 rounded-lg border border-brand-primary/15 bg-[color-mix(in_srgb,var(--surface-glass)_84%,transparent)] p-3 shadow-[var(--shadow-xs)] sm:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] sm:p-4">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-primary">
                  Decision supported
                </p>
                <p className="mt-1 text-base font-semibold leading-6 text-[var(--text-primary)] [overflow-wrap:anywhere]">
                  {decisionSupportedLabel}
                </p>
                <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                  Praviar will prepare a source-linked first-pass FTO report
                  request for review, not a legal clearance opinion.
                </p>
              </div>
              <div
                className="hidden min-w-0 gap-2 sm:grid sm:grid-cols-3"
                data-testid="new-analysis-hero-evidence-summary"
              >
                {launchEvidenceSummary.map((item) => (
                  <div
                    key={item.label}
                    className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 py-2"
                  >
                    <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                      {item.label}
                    </p>
                    <p className="mt-1 line-clamp-2 text-xs font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
                      {item.value}
                    </p>
                  </div>
                ))}
              </div>
            </div>
            <div
              className="mt-2 flex flex-wrap gap-1.5 text-xs font-semibold text-[var(--text-secondary)] sm:hidden"
              aria-label="Launch readiness summary"
              data-testid="new-analysis-mobile-readiness"
            >
              <span className="rounded-full border border-brand-primary/15 bg-brand-primary/10 px-2 py-1">
                {enabledSources.length || 0} sources
              </span>
              <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-glass)] px-2 py-1">
                {launchReadyJurisdictions.length || 0} lanes
              </span>
              <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-glass)] px-2 py-1">
                {reviewPolicyLabel}
              </span>
              <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-glass)] px-2 py-1">
                Capacity checked at launch
              </span>
            </div>
            <div
              className="mt-4 hidden gap-2 text-xs text-[var(--text-tertiary)] sm:grid sm:grid-cols-2 xl:grid-cols-4"
              data-testid="new-analysis-launch-signals"
            >
              {launchPillars.map((signal) => {
                const Icon = signal.icon;

                return (
                  <div
                    key={signal.label}
                    className="grid min-w-0 grid-cols-[1.75rem_minmax(0,1fr)] gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-glass)] px-3 py-2"
                  >
                    <span className="flex h-7 w-7 items-center justify-center rounded-md border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
                      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                    </span>
                    <span className="min-w-0">
                      <span className="block font-semibold uppercase tracking-[0.1em]">
                        {signal.label}
                      </span>
                      <span className="mt-1 line-clamp-2 block font-medium normal-case tracking-normal text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                        {signal.detail}
                      </span>
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
          <div className="hidden min-w-0 rounded-lg border border-brand-primary/20 bg-[var(--brand-ink)] p-4 text-[var(--brand-paper)] shadow-[var(--shadow-md)] xl:block">
            <div className="flex items-start gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-brand-accent/30 bg-brand-accent/10 text-brand-accent">
                <Sparkles className="h-4 w-4" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[color-mix(in_srgb,var(--brand-paper)_68%,var(--brand-soft-mint))]">
                  Launch packet
                </p>
                <p className="mt-1 text-base font-semibold">
                  Readiness, Scope, Capacity, Handoff
                </p>
                <p className="mt-2 text-xs leading-5 text-[color-mix(in_srgb,var(--brand-paper)_78%,var(--brand-soft-mint))]">
                  A single run contract keeps the molecule, evidence lanes,
                  Report Credit capacity, and reviewer boundary visible before
                  submission.
                </p>
              </div>
            </div>
            <div className="mt-4 grid gap-2 text-xs">
              {launchPillars.map((item) => {
                const Icon = item.icon;

                return (
                  <div
                    key={item.label}
                    className="grid min-w-0 grid-cols-[1.75rem_minmax(0,1fr)] gap-2 rounded-md border border-[color:color-mix(in_srgb,var(--surface-inverted-fg)_12%,transparent)] bg-[color:color-mix(in_srgb,var(--surface-inverted-fg)_7%,transparent)] px-2.5 py-2"
                  >
                    <Icon
                      className="mt-0.5 h-4 w-4 text-brand-accent"
                      aria-hidden="true"
                    />
                    <span className="min-w-0">
                      <span className="block font-semibold text-[var(--brand-paper)]">
                        {item.label}
                      </span>
                      <span className="mt-0.5 block text-xs leading-4 text-[color-mix(in_srgb,var(--brand-paper)_72%,var(--brand-soft-mint))] [overflow-wrap:anywhere]">
                        {item.detail}
                      </span>
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      {creditCheckoutResumeState?.state === "success" ? (
        <CreditPackCheckoutReconciliation
          capacityRefreshError={Boolean(
            billingStatusQuery.error && !billingAccessRestricted,
          )}
          currentConfirmedBalance={
            visibleBillingStatus?.purchased_credits_balance ?? 0
          }
          draftRestored={creditCheckoutResumeState.draftRestored}
          isCapacityRefreshFetching={billingStatusQuery.isFetching}
          onRefreshCapacity={() => {
            void billingStatusQuery.refetch();
          }}
          sessionId={creditCheckoutResumeState.sessionId}
          surface="analysis"
          token={token}
        />
      ) : (
        <CreditCheckoutResumeNotice state={creditCheckoutResumeState} />
      )}

      <WizardStepper step={step} onStepChange={setStep} />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.38fr)] lg:items-start">
        <div
          ref={stepContentRef}
          className="min-w-0 scroll-mt-24"
          data-testid="new-analysis-step-content"
        >
          {step === 1 ? (
            <CompoundInputStep
              compoundInput={compoundInput}
              identityConfirmed={identityConfirmed}
              saltPolymorphForm={productContext.saltPolymorphForm}
              matterScopeSlot={
                <MatterScopePreflightSlot
                  compoundInput={compoundInput}
                  inputType={inputType}
                  productContext={productContext}
                  value={matterScope}
                  onChange={setMatterScope}
                  onProductContextChange={setProductContext}
                />
              }
              onCompoundInputChange={handleCompoundInputChange}
              onConfirmIdentity={() => {
                const detectedInputType = detectInputType(compoundInput);
                if (detectedInputType) {
                  setSubmittedIdentityConfirmation({
                    inputType: detectedInputType,
                    value: compoundInput.trim(),
                  });
                }
              }}
              onInputTypeChange={setInputType}
              onNext={() => setStep(2)}
            />
          ) : null}

          {step === 2 ? (
            <ConfigurationStep
              canManagePresets={canManagePresets}
              config={config}
              savedPresets={savedPresets}
              showSavePreset={showSavePreset}
              presetName={presetName}
              presetDescription={presetDescription}
              isSavingPreset={createPreset.isPending}
              sessionReady={sessionReady}
              sessionError={sessionError}
              canContinue={validationIssues.length === 0}
              continueBlocker={validationIssues[0] ?? null}
              onLoadPreset={handleLoadPreset}
              onToggleSavePreset={() => setShowSavePreset((value) => !value)}
              onPresetNameChange={setPresetName}
              onPresetDescriptionChange={setPresetDescription}
              onCancelSavePreset={handleCancelSavePreset}
              onSavePreset={handleSavePreset}
              onBack={() => setStep(1)}
              onNext={() => setStep(3)}
            />
          ) : null}

          {step === 3 ? (
            <ReviewLaunchStep
              compoundInput={compoundInput}
              inputType={inputType}
              config={config}
              matterScope={matterScope}
              productContext={productContext}
              launchCapacity={launchCapacity}
              isLaunching={createAnalysis.isPending}
              canLaunch={!launchBlocker}
              launchBlocker={launchBlocker}
              launchError={launchError}
              launchErrorAction={
                launchErrorAction
                  ? {
                      ...launchErrorAction,
                      pending:
                        !launchErrorAction.href &&
                        requestCreditCapacity.isPending,
                    }
                  : null
              }
              onBack={() => setStep(2)}
              onLaunch={handleLaunch}
            />
          ) : null}
        </div>

        <EvidenceLaunchRail
          billingStatus={visibleBillingStatus}
          canManageBilling={canManageBilling}
          compoundInput={compoundInput}
          config={config}
          getCreditPackHref={(pack) =>
            buildLaunchCreditPackHref(pack, launchDraftId)
          }
          isBillingAccessRestricted={billingAccessRestricted}
          isBillingLoading={billingStatusQuery.isLoading}
          matterScope={matterScope}
          onRequestReportCredits={(requestedReports, source) => {
            void requestReportCredits(requestedReports, source);
          }}
          requestReportCreditsPending={requestCreditCapacity.isPending}
          sessionReady={sessionReady}
          step={step}
        />
      </div>
    </div>
  );
}

function MatterScopePreflightSlot({
  compoundInput,
  inputType,
  onChange,
  onProductContextChange,
  productContext,
  value,
}: {
  compoundInput: string;
  inputType: string | null;
  onChange: (value: MatterScopePreflightValue) => void;
  onProductContextChange: (value: ProductContextValue) => void;
  productContext: ProductContextValue;
  value: MatterScopePreflightValue;
}) {
  const suggestion = getMatterScopeSuggestion({ compoundInput, inputType });
  const hasCompound = compoundInput.trim().length > 0;
  const actionSummary =
    value.intendedActions.length === 1
      ? `${formatScopeLabel(value.intendedActions[0])} action`
      : `${value.intendedActions.length} actions`;
  const suggestionSummary = hasCompound
    ? `Suggested: ${formatScopeLabel(
        suggestion.assetTypeHint,
      )}; ${formatScopeLabel(suggestion.developmentStage)}.`
    : "Enter a compound to refine the suggestion.";

  return (
    <div className="space-y-3">
      <details className="group overflow-hidden rounded-lg border border-brand-primary/15 bg-[var(--surface-subtle)]">
        <summary className="grid cursor-pointer list-none gap-3 p-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60 sm:grid-cols-[minmax(0,1fr)_auto] sm:p-4 [&::-webkit-details-marker]:hidden">
          <span className="flex min-w-0 items-start gap-3">
            <span
              className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-brand-primary/20 bg-brand-primary/10 text-brand-primary"
              aria-hidden="true"
            >
              <Lightbulb className="h-4 w-4" />
            </span>
            <span className="min-w-0">
              <span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                Scope brief
              </span>
              <span className="mt-1 block text-sm font-semibold text-[var(--text-primary)]">
                {formatScopeLabel(value.assetTypeHint)};{" "}
                {formatScopeLabel(value.developmentStage)}
              </span>
              <span className="mt-0.5 block text-xs leading-5 text-[var(--text-secondary)]">
                {actionSummary}. {suggestionSummary}
              </span>
            </span>
          </span>
          <span className="inline-flex min-h-10 items-center justify-center gap-2 rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-card)] px-3 text-sm font-semibold text-[var(--text-primary)] shadow-[var(--shadow-xs)] transition-colors group-open:border-brand-primary/30 group-open:text-brand-primary">
            <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
            Edit scope
            <ChevronDown
              className="h-4 w-4 transition-transform group-open:rotate-180"
              aria-hidden="true"
            />
          </span>
        </summary>
        <div className="border-t border-[var(--border-subtle)] p-3 sm:p-4">
          <MatterScopePreflight
            className="border-0 shadow-none"
            compoundInput={compoundInput}
            inputType={inputType}
            value={value}
            onChange={onChange}
          />
        </div>
      </details>
      <ProductContextBrief
        matterScope={value}
        value={productContext}
        onChange={onProductContextChange}
      />
    </div>
  );
}

function getCreditCheckoutResumeState(
  searchParams: URLSearchParams,
  draftRestored: boolean,
): CreditCheckoutResumeState {
  if (
    searchParams.get("resume") !== "credit_checkout" ||
    searchParams.get("intent") !== "credits"
  ) {
    return null;
  }

  const state = searchParams.get("checkout");
  if (state !== "success" && state !== "cancelled") {
    return null;
  }

  return {
    draftRestored,
    sessionId: searchParams.get("checkout_session_id"),
    state,
  };
}

function CreditCheckoutResumeNotice({
  state,
}: {
  state: CreditCheckoutResumeState;
}) {
  if (!state) {
    return null;
  }

  if (state.state === "success") {
    return null;
  }

  return (
    <section
      role="status"
      aria-live="polite"
      className="rounded-lg border border-warning/20 bg-warning/10 px-4 py-3"
    >
      <div className="flex items-start gap-3">
        <TriangleAlert
          className="mt-0.5 h-4 w-4 shrink-0 text-warning"
          aria-hidden="true"
        />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            Report Credits checkout flow cancelled
          </p>
          <p className="mt-0.5 text-sm leading-6 text-[var(--text-secondary)]">
            No Report Credit purchase is assumed from this browser return.
            Authoritative launch capacity remains visible before submission.
          </p>
        </div>
      </div>
    </section>
  );
}

function NewAnalysisContent() {
  const searchParams = useSearchParams();
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const clientReady = useClientReady();
  const marketingPrefillBoundaryKey = token
    ? authScopeKey(token)
    : "demo-session";
  const marketingPrefillBoundaryAttemptRef = useRef<string | null>(null);
  const [marketingCompoundPrefill, setMarketingCompoundPrefill] = useState<{
    authBoundaryKey: string;
    value: string;
  } | null>(null);
  const marketingPrefillReady =
    marketingCompoundPrefill?.authBoundaryKey === marketingPrefillBoundaryKey;

  useEffect(() => {
    if (
      !clientReady ||
      principal.data?.can_create_analysis !== true ||
      marketingPrefillReady ||
      marketingPrefillBoundaryAttemptRef.current === marketingPrefillBoundaryKey
    ) {
      return;
    }

    marketingPrefillBoundaryAttemptRef.current = marketingPrefillBoundaryKey;
    const value = consumeMarketingCompoundHandoff();
    // The session handoff is an external, consume-once browser value. It can
    // only be read after the authenticated capability boundary is known.
    setMarketingCompoundPrefill({
      authBoundaryKey: marketingPrefillBoundaryKey,
      value,
    });
  }, [
    clientReady,
    marketingPrefillBoundaryKey,
    marketingPrefillReady,
    principal.data?.can_create_analysis,
  ]);

  useEffect(() => {
    if (clientReady && principal.data?.can_create_analysis === false) {
      clearMarketingCompoundHandoff();
    }
  }, [clientReady, principal.data?.can_create_analysis]);

  if (!clientReady) {
    return <NewAnalysisLoading />;
  }
  if (!principal.data && (principal.isLoading || principal.isFetching)) {
    return <NewAnalysisLoading />;
  }
  if (!principal.data) {
    return (
      <OperationalStatusFrame
        actionLabel="Retry access check"
        contextItems={[
          "No analysis request submitted",
          "No Report Credit consumed",
          "Application authority was not inferred",
        ]}
        dataTestId="analysis-create-access-unavailable"
        description="Praviar could not load the authoritative application-role snapshot, so analysis launch remains closed until the access check succeeds."
        eyebrow="Analysis launch access"
        icon={LockKeyhole}
        isPending={false}
        onRetry={() => {
          void principal.refetch();
        }}
        recoveryBody="Retry the capability check. If it continues to fail, verify the session or ask a workspace administrator to confirm your membership."
        recoveryTitle="Restore the access check"
        title="New analysis access check unavailable"
        titleId="analysis-create-access-unavailable-title"
        tone="warning"
      />
    );
  }
  if (principal.data?.can_create_analysis !== true) {
    return (
      <OperationalStatusFrame
        contextItems={[
          "No analysis request submitted",
          "No Report Credit consumed",
          "Existing packets remain available",
        ]}
        dataTestId="analysis-create-access-restricted"
        description="Your current application role can inspect permitted analysis records but cannot start a new FTO run."
        eyebrow="Analysis launch access"
        icon={LockKeyhole}
        isPending={false}
        onRetry={() => {
          void principal.refetch();
        }}
        recoveryBody="Ask a workspace administrator or counsel owner to update your role, then retry the authorization check."
        recoveryTitle="Request analysis-launch access"
        title="New analysis access restricted"
        titleId="analysis-create-access-restricted-title"
        tone="error"
      />
    );
  }
  if (!marketingPrefillReady || marketingCompoundPrefill === null) {
    return <NewAnalysisLoading />;
  }
  const launchDraftBoundaryKey = token ? authScopeKey(token) : null;
  const explicitLaunchDraftId = searchParams.get("launch_draft_id");
  const activeLaunchDraftId =
    explicitLaunchDraftId ??
    readActiveAnalysisLaunchDraftId(launchDraftBoundaryKey);
  const storedLaunchDraft = readAnalysisLaunchDraft(
    activeLaunchDraftId,
    launchDraftBoundaryKey,
  );
  const launchDraft = storedLaunchDraft;
  const initialCompoundInput =
    launchDraft?.compoundInput ?? marketingCompoundPrefill.value;
  const creditCheckoutResumeState = getCreditCheckoutResumeState(
    searchParams,
    Boolean(launchDraft),
  );
  const workflowKey = launchDraft
    ? `launch-draft:${launchDraft.id}`
    : initialCompoundInput
      ? "marketing-prefill"
      : "manual";

  return (
    <NewAnalysisWorkflow
      key={workflowKey}
      canManageBilling={principal.data.can_manage_billing}
      canManagePresets={principal.data.can_manage_config}
      creditCheckoutResumeState={creditCheckoutResumeState}
      initialCompoundInput={initialCompoundInput}
      launchDraft={launchDraft}
      shouldTrackPrefill={!launchDraft && initialCompoundInput.length > 0}
      token={token}
    />
  );
}

export default function NewAnalysisPage() {
  return (
    <Suspense fallback={<NewAnalysisLoading />}>
      <NewAnalysisContent />
    </Suspense>
  );
}
