import { describe, expect, it } from "vitest";

import {
  productContextPayloadToValue,
  serializeProductContext,
} from "@/lib/product-context";
import type { ProductContextValue } from "@/types/pipeline";
import { buildClaimedUseReceipt } from "../fixtures/claimed-use-receipts";

describe("claimed-use product-context serialization", () => {
  it("round-trips the canonical v3 signed payload without field translation", () => {
    const receipt = buildClaimedUseReceipt().receipt;
    const context: ProductContextValue = {
      accusedActs: [
        {
          act: "regulatory_submission",
          jurisdiction: "US",
          startDate: "2027-01-20",
          actor: "Example Pharma Inc.",
          status: "planned",
          purpose: "regulatory_approval",
          regulatoryPath: "anda",
          instrumentality: "Example ANDA",
          liabilityTheory: "artificial_infringement",
          targetProductIdentity: "Example 10 mg tablet",
          proposedIndication: "Treatment of example disease",
          proposedLabelUse: "One tablet once daily.",
          labelCarveOutState: "partial",
          claimedUseMatchReceipts: [receipt],
        },
      ],
    };

    const payload = serializeProductContext(context);
    expect(payload?.accused_acts?.[0].claimed_use_match_receipts).toEqual([
      receipt,
    ]);

    const restored = productContextPayloadToValue(payload);
    expect(restored.accusedActs?.[0].claimedUseMatchReceipts).toEqual([
      receipt,
    ]);
  });
});
