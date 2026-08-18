export type PublicMarketingReadiness = "informational_only";

/**
 * Public launch state for marketing surfaces.
 *
 * Keep this fail-closed until the contracting identity, applicable terms,
 * privacy documents, deployment review, and purchasing flow are ready for
 * public use. Marketing routes must not link to signup, billing, or checkout
 * while this value remains `informational_only`.
 */
export const PUBLIC_MARKETING_READINESS: PublicMarketingReadiness =
  "informational_only";

export const PUBLIC_PRIMARY_ACTION = {
  href: "/sample-reports/example-molecule-alpha",
  label: "Open the fictional sample",
} as const;

export const PUBLIC_METHODOLOGY_ACTION = {
  href: "/methodology",
  label: "Review the methodology",
} as const;

export const PUBLIC_CONTACT_ACTION = {
  href: "https://github.com/Peter-McCann-Strain/praviar-open-source",
  label: "View source on GitHub",
} as const;

export const PUBLIC_PURCHASING_NOTICE =
  "This is a research-preview portfolio project. Purchasing, confidential-data use, and production reliance are unavailable.";
