const PRIOR_ART_SOURCE_HOSTS = new Set([
  "doi.org",
  "openalex.org",
  "patentcenter.uspto.gov",
  "patents.google.com",
  "patentscope.wipo.int",
  "ppubs.uspto.gov",
  "pubmed.ncbi.nlm.nih.gov",
  "register.epo.org",
  "semanticscholar.org",
  "worldwide.espacenet.com",
  "www.semanticscholar.org",
]);

const DOI_SHAPE = /^10\.\d{4,9}\/\S+$/u;

export type PriorArtSource = {
  doi?: string | null;
  url?: string | null;
};

/** Return a canonical HTTPS source URL only for a reviewed evidence host. */
export function canonicalPriorArtSourceUrl(
  reference: PriorArtSource | null | undefined,
): string | null {
  if (!reference) return null;
  const suppliedUrl = reference.url?.trim();
  if (suppliedUrl) return canonicalAllowlistedUrl(suppliedUrl);
  return canonicalDoiUrl(reference.doi);
}

function canonicalAllowlistedUrl(value: string): string | null {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return null;
  }
  if (
    parsed.protocol !== "https:" ||
    parsed.username ||
    parsed.password ||
    parsed.port ||
    !PRIOR_ART_SOURCE_HOSTS.has(parsed.hostname)
  ) {
    return null;
  }
  parsed.hash = "";
  return parsed.href;
}

function canonicalDoiUrl(value: string | null | undefined): string | null {
  const doi = value?.trim();
  if (!doi || !DOI_SHAPE.test(doi)) return null;
  const segments = doi.split("/");
  if (
    segments.length < 2 ||
    segments.some(
      (segment, index) =>
        (index > 0 && segment.length === 0) ||
        segment === "." ||
        segment === "..",
    )
  ) {
    return null;
  }
  const encodedDoi = segments
    .map((segment) => encodeURIComponent(segment))
    .join("/");
  return `https://doi.org/${encodedDoi}`;
}
