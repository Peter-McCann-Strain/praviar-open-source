import { describe, expect, it } from "vitest";
import { canonicalPriorArtSourceUrl } from "@/lib/prior-art-source-url";

describe("canonicalPriorArtSourceUrl", () => {
  it.each([
    "https://doi.org/10.1000/xyz",
    "https://patentcenter.uspto.gov/applications/123",
    "https://ppubs.uspto.gov/pubwebapp/",
    "https://register.epo.org/application?number=EP123",
    "https://worldwide.espacenet.com/patent/search?q=US123",
    "https://patentscope.wipo.int/search/en/detail.jsf?docId=WO123",
    "https://patents.google.com/patent/US123",
    "https://pubmed.ncbi.nlm.nih.gov/12345/",
    "https://www.semanticscholar.org/paper/abc",
    "https://openalex.org/W123",
  ])("allows a canonical HTTPS source on a reviewed exact host: %s", (url) => {
    expect(canonicalPriorArtSourceUrl({ url })).toBe(url);
  });

  it("normalizes host casing and removes fragments", () => {
    expect(
      canonicalPriorArtSourceUrl({
        url: "https://PATENTS.GOOGLE.COM/patent/US123#claims",
      }),
    ).toBe("https://patents.google.com/patent/US123");
  });

  it("builds a DOI URL with every path segment encoded", () => {
    expect(
      canonicalPriorArtSourceUrl({
        doi: "10.1234/article?next=evil.example",
      }),
    ).toBe("https://doi.org/10.1234/article%3Fnext%3Devil.example");
  });

  it("does not fall back to DOI when an explicit source URL is unsafe", () => {
    expect(
      canonicalPriorArtSourceUrl({
        doi: "10.1234/safe",
        url: "javascript:alert(1)",
      }),
    ).toBeNull();
  });

  it.each([
    "javascript:alert(1)",
    "data:text/html,hostile",
    "file:///etc/passwd",
    "http://doi.org/10.1000/xyz",
    "https://doi.org.evil.example/10.1000/xyz",
    "https://evil.example/https://doi.org/10.1000/xyz",
    "https://evil.example@doi.org/10.1000/xyz",
    "https://doi.org@evil.example/10.1000/xyz",
    "https://doi.org:8443/10.1000/xyz",
    "//doi.org/10.1000/xyz",
  ])("rejects a hostile source authority: %s", (url) => {
    expect(canonicalPriorArtSourceUrl({ url })).toBeNull();
  });

  it.each([
    "doi:10.1234/article",
    "10.123/article",
    "10.1234",
    "10.1234/",
    "10.1234//evil.example",
    "10.1234/../evil",
  ])("rejects a malformed DOI: %s", (doi) => {
    expect(canonicalPriorArtSourceUrl({ doi })).toBeNull();
  });
});
