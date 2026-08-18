export const WELCOME_MODAL_STORAGE_KEY = "praviar_welcomed";
export const ONBOARDING_TOUR_STORAGE_KEY = "praviar_tour_complete";

export interface OnboardingStorageIdentity {
  userId: string;
  orgId: string;
}

export const DEMO_ONBOARDING_IDENTITY: OnboardingStorageIdentity = {
  userId: "demo-user",
  orgId: "org_demo_001",
};

export const DEV_ONBOARDING_IDENTITY: OnboardingStorageIdentity = {
  userId: "dev-user",
  orgId: "dev-org",
};

export const TEST_ONBOARDING_IDENTITY: OnboardingStorageIdentity = {
  userId: "test-user",
  orgId: "test-org",
};

function normalizeIdentityPart(value: string): string | null {
  const normalized = value.trim();
  return normalized ? encodeURIComponent(normalized) : null;
}

export function onboardingStorageKey(
  baseKey: string,
  identity: OnboardingStorageIdentity | null,
): string | null {
  if (!identity) return null;

  const userId = normalizeIdentityPart(identity.userId);
  const orgId = normalizeIdentityPart(identity.orgId);
  if (!userId || !orgId) return null;

  return `${baseKey}:v2:user=${userId}:org=${orgId}`;
}

export function onboardingStorageKeys(
  identity: OnboardingStorageIdentity | null,
): { welcome: string; tour: string } | null {
  const welcome = onboardingStorageKey(WELCOME_MODAL_STORAGE_KEY, identity);
  const tour = onboardingStorageKey(ONBOARDING_TOUR_STORAGE_KEY, identity);
  return welcome && tour ? { welcome, tour } : null;
}

export function readOnboardingFlag(
  baseKey: string,
  identity: OnboardingStorageIdentity | null,
): boolean {
  const key = onboardingStorageKey(baseKey, identity);
  return key ? localStorage.getItem(key) === "true" : false;
}

export function writeOnboardingFlag(
  baseKey: string,
  identity: OnboardingStorageIdentity | null,
): boolean {
  const key = onboardingStorageKey(baseKey, identity);
  if (!key) return false;
  localStorage.setItem(key, "true");
  return true;
}

export function clearLegacyOnboardingFlags(): void {
  localStorage.removeItem(WELCOME_MODAL_STORAGE_KEY);
  localStorage.removeItem(ONBOARDING_TOUR_STORAGE_KEY);
}

export function nonClerkOnboardingIdentity({
  demoMode,
  devAuthBypass,
  nodeEnv,
}: {
  demoMode: boolean;
  devAuthBypass: boolean;
  nodeEnv: string | undefined;
}): OnboardingStorageIdentity | null {
  if (demoMode) return DEMO_ONBOARDING_IDENTITY;
  if (devAuthBypass) return DEV_ONBOARDING_IDENTITY;
  if (nodeEnv === "test") return TEST_ONBOARDING_IDENTITY;
  return null;
}
