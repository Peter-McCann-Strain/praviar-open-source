export interface ReportCreditCapacityInput {
  analyses_limit: number;
  analyses_used: number;
  included_analyses_limit: number;
  plan: string;
  purchased_credits_balance: number;
  purchased_credits_used: number;
}

export interface ReportCreditCapacitySnapshot {
  additionalCapacityRemaining: number;
  consumedCreditBackedRequests: number;
  creditBackedRemaining: number;
  effectiveRemaining: number;
  includedRemaining: number;
  isEnterprise: boolean;
  purchasedCreditsBalance: number;
  totalCreditBackedCapacity: number;
}

export function getReportCreditCapacitySnapshot(
  billingStatus: ReportCreditCapacityInput,
): ReportCreditCapacitySnapshot {
  const isEnterprise = billingStatus.plan === "enterprise";
  const analysesUsed = Math.max(0, billingStatus.analyses_used);
  const effectiveLimit = Math.max(0, billingStatus.analyses_limit);
  const includedLimit = Math.max(0, billingStatus.included_analyses_limit);
  const purchasedCreditsBalance = Math.max(
    0,
    billingStatus.purchased_credits_balance,
  );
  const consumedCreditBackedRequests = Math.min(
    analysesUsed,
    Math.max(0, billingStatus.purchased_credits_used ?? 0),
  );
  const effectiveRemaining = Math.max(0, effectiveLimit - analysesUsed);
  const planAnalysesUsed = Math.max(
    0,
    analysesUsed - consumedCreditBackedRequests,
  );
  const includedRemaining = Math.max(0, includedLimit - planAnalysesUsed);
  const rawCreditBackedRemaining = Math.max(
    0,
    effectiveRemaining - includedRemaining,
  );
  const creditBackedRemaining = Math.min(
    rawCreditBackedRemaining,
    purchasedCreditsBalance,
  );
  const additionalCapacityRemaining = Math.max(
    0,
    effectiveRemaining - includedRemaining - creditBackedRemaining,
  );
  const totalCreditBackedCapacity = Math.max(
    0,
    consumedCreditBackedRequests + purchasedCreditsBalance,
  );

  return {
    additionalCapacityRemaining: isEnterprise ? 0 : additionalCapacityRemaining,
    consumedCreditBackedRequests,
    creditBackedRemaining: isEnterprise ? 0 : creditBackedRemaining,
    effectiveRemaining: isEnterprise ? 0 : effectiveRemaining,
    includedRemaining: isEnterprise ? 0 : includedRemaining,
    isEnterprise,
    purchasedCreditsBalance: isEnterprise ? 0 : purchasedCreditsBalance,
    totalCreditBackedCapacity: isEnterprise ? 0 : totalCreditBackedCapacity,
  };
}

export function formatReportRequestCount(value: number) {
  return `${value.toLocaleString()} report request${value === 1 ? "" : "s"}`;
}

function formatAdditionalWorkspaceCapacity(value: number) {
  return `${value.toLocaleString()} additional workspace report request${
    value === 1 ? "" : "s"
  }`;
}

export function formatReportCreditCapacityBreakdown(
  capacity: Pick<
    ReportCreditCapacitySnapshot,
    | "additionalCapacityRemaining"
    | "creditBackedRemaining"
    | "includedRemaining"
    | "purchasedCreditsBalance"
  >,
) {
  const parts = [
    `${capacity.includedRemaining.toLocaleString()} included`,
    `${capacity.creditBackedRemaining.toLocaleString()} credit-backed remaining`,
  ];

  if (capacity.additionalCapacityRemaining > 0) {
    parts.push(
      formatAdditionalWorkspaceCapacity(capacity.additionalCapacityRemaining),
    );
  }

  return `${parts.join(", ")}; ${capacity.purchasedCreditsBalance.toLocaleString()} unused purchased`;
}
