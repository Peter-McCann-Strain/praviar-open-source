import {
  CREDIT_PACK_DETAILS,
  REPORT_CREDIT_CONTRACT_COPY,
  formatCreditPackPrice,
  formatReportCreditCount,
  isCreditPackId,
} from "@/components/billing/helpers";

const LOCAL_ORIGIN = "https://praviar.local";

export interface AuthCheckoutIntent {
  kind: "credit_pack";
  returnPath: string;
  packId: keyof typeof CREDIT_PACK_DETAILS;
  packLabel: string;
  packDescription: string;
  reportCredits: string;
  totalPrice: string;
  effectiveRate: string;
  savingsLabel: string;
  contractCopy: string;
}

export function resolveAuthCheckoutIntent(
  returnPath: string,
): AuthCheckoutIntent | null {
  try {
    const url = new URL(returnPath, LOCAL_ORIGIN);

    if (url.origin !== LOCAL_ORIGIN || url.pathname !== "/billing") {
      return null;
    }

    if (url.searchParams.get("intent") !== "credits") {
      return null;
    }

    const packId = url.searchParams.get("pack");

    if (!isCreditPackId(packId)) {
      return null;
    }

    const pack = CREDIT_PACK_DETAILS[packId];
    const effectiveRateCents = Math.round(pack.priceCents / pack.credits);

    return {
      kind: "credit_pack",
      returnPath: `${url.pathname}${url.search}${url.hash}`,
      packId,
      packLabel: pack.shortLabel,
      packDescription: pack.description,
      reportCredits: formatReportCreditCount(pack.credits),
      totalPrice: formatCreditPackPrice(pack.priceCents),
      effectiveRate: `${formatCreditPackPrice(effectiveRateCents)} / request`,
      savingsLabel: pack.savingsLabel ?? "Single prepaid request",
      contractCopy: REPORT_CREDIT_CONTRACT_COPY,
    };
  } catch {
    return null;
  }
}
