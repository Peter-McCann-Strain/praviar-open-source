const MARKETING_COMPOUND_HANDOFF_KEY = "praviar:marketing-compound-handoff:v1";
const MARKETING_COMPOUND_HANDOFF_VERSION = 1;
const MARKETING_COMPOUND_HANDOFF_TTL_MS = 15 * 60 * 1000;
export const MARKETING_COMPOUND_HANDOFF_MAX_LENGTH = 5000;

interface MarketingCompoundHandoffEnvelope {
  compoundInput: string;
  createdAt: number;
  version: 1;
}

function getSessionStorage(): Storage | null {
  if (typeof window === "undefined") return null;

  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function storeMarketingCompoundHandoff(
  value: string,
  storage: Storage | null = getSessionStorage(),
  now = Date.now(),
): boolean {
  const compoundInput = value.trim();
  if (
    !storage ||
    !compoundInput ||
    compoundInput.length > MARKETING_COMPOUND_HANDOFF_MAX_LENGTH
  ) {
    return false;
  }

  const envelope: MarketingCompoundHandoffEnvelope = {
    compoundInput,
    createdAt: now,
    version: MARKETING_COMPOUND_HANDOFF_VERSION,
  };

  try {
    storage.setItem(MARKETING_COMPOUND_HANDOFF_KEY, JSON.stringify(envelope));
    return true;
  } catch {
    return false;
  }
}

export function consumeMarketingCompoundHandoff(
  storage: Storage | null = getSessionStorage(),
  now = Date.now(),
): string {
  if (!storage) return "";

  let serialized: string | null = null;
  try {
    serialized = storage.getItem(MARKETING_COMPOUND_HANDOFF_KEY);
    storage.removeItem(MARKETING_COMPOUND_HANDOFF_KEY);
  } catch {
    return "";
  }

  if (!serialized) return "";

  try {
    const candidate = JSON.parse(
      serialized,
    ) as Partial<MarketingCompoundHandoffEnvelope>;
    const compoundInput = candidate.compoundInput?.trim() ?? "";
    const age = now - Number(candidate.createdAt);

    if (
      candidate.version !== MARKETING_COMPOUND_HANDOFF_VERSION ||
      !compoundInput ||
      compoundInput.length > MARKETING_COMPOUND_HANDOFF_MAX_LENGTH ||
      !Number.isFinite(age) ||
      age < 0 ||
      age > MARKETING_COMPOUND_HANDOFF_TTL_MS
    ) {
      return "";
    }

    return compoundInput;
  } catch {
    return "";
  }
}

export function clearMarketingCompoundHandoff(
  storage: Storage | null = getSessionStorage(),
): void {
  if (!storage) return;

  try {
    storage.removeItem(MARKETING_COMPOUND_HANDOFF_KEY);
  } catch {
    // Storage can be unavailable in privacy-restricted browsers. The handoff
    // already fails closed and never falls back to a URL or persistent store.
  }
}
