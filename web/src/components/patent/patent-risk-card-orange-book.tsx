"use client";

import type { OrangeBookInfo } from "@praviar/shared-types";

interface PatentRiskCardOrangeBookProps {
  orangeBookInfo: OrangeBookInfo;
}

export function PatentRiskCardOrangeBook({
  orangeBookInfo,
}: PatentRiskCardOrangeBookProps) {
  const productNames = orangeBookInfo.product_names ?? [];
  const activeIngredients = orangeBookInfo.active_ingredients ?? [];
  const ndaNumbers = orangeBookInfo.nda_numbers ?? [];
  const patentUseCodes = orangeBookInfo.patent_use_codes ?? [];
  const hasDescriptiveMetadata =
    productNames.length > 0 ||
    activeIngredients.length > 0 ||
    ndaNumbers.length > 0 ||
    patentUseCodes.length > 0;

  return (
    <div className="rounded-lg border border-warning/20 bg-warning/5 p-3">
      <p className="mb-1 text-xs font-semibold text-warning">
        Orange Book Listed
      </p>
      <div className="space-y-1 text-sm text-[var(--text-primary)]">
        {productNames.length > 0 && <p>Products: {productNames.join(", ")}</p>}
        {activeIngredients.length > 0 && (
          <p>Active Ingredients: {activeIngredients.join(", ")}</p>
        )}
        {ndaNumbers.length > 0 && <p>NDA: {ndaNumbers.join(", ")}</p>}
        {patentUseCodes.length > 0 && (
          <p>Patent use: {patentUseCodes.join(", ")}</p>
        )}
        {!hasDescriptiveMetadata ? (
          <p className="text-[var(--text-secondary)]">
            FDA listing confirmed; descriptive product metadata was not supplied
            with this record.
          </p>
        ) : null}
      </div>
    </div>
  );
}
