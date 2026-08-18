import { describe, expect, it } from "vitest";

import {
  getChatCitationDisplayIndex,
  mapChatCitationToCitationRef,
} from "@/components/report/chat-citation-mapping";

describe("mapChatCitationToCitationRef", () => {
  it("preserves structured patent, claim, element, and source URL anchors", () => {
    const citation = mapChatCitationToCitationRef({
      cited_text: "Claim 3 element 2 requires a salt form.",
      document_index: 2,
      document_title: "US0000000001A1 claim chart",
      patent_id: "US0000000001A1",
      claim_number: 3,
      element_number: 2,
      source_url: "https://patents.google.com/patent/US0000000001A1",
    });

    expect(citation).toMatchObject({
      index: 3,
      patentId: "US0000000001A1",
      claimNumber: 3,
      elementNumber: 2,
      text: "Claim 3 element 2 requires a salt form.",
      section: "Report chat citation: US0000000001A1 claim chart",
      url: "https://patents.google.com/patent/US0000000001A1",
    });
  });

  it("infers patent and claim anchors from document title when fields are absent", () => {
    const citation = mapChatCitationToCitationRef({
      cited_text: "The cited claim language is material.",
      document_index: 0,
      document_title: "Patent US-9988776-B2 Claim 12",
    });

    expect(citation.patentId).toBe("US9988776B2");
    expect(citation.claimNumber).toBe(12);
  });

  it("keeps section-level citations drawer-safe when no patent anchor exists", () => {
    const citation = mapChatCitationToCitationRef({
      cited_text: "The executive summary notes a jurisdictional caveat.",
      document_index: 0,
      document_title: "Executive summary",
    });

    expect(citation.patentId).toBeUndefined();
    expect(citation.claimNumber).toBeUndefined();
    expect(citation.text).toBe(
      "The executive summary notes a jurisdictional caveat.",
    );
  });

  it("uses a supplied display index when the citation chip already resolved it", () => {
    const citation = mapChatCitationToCitationRef(
      {
        cited_text: "The cited claim language is material.",
        document_index: 8,
        document_title: "Patent US-9988776-B2 Claim 12",
      },
      3,
    );

    expect(citation.index).toBe(3);
  });

  it("keeps citation chip numbering aligned to backend document indexes", () => {
    expect(
      getChatCitationDisplayIndex(
        {
          cited_text: "Claim source",
          document_index: 2,
        },
        0,
      ),
    ).toBe(3);
    expect(
      getChatCitationDisplayIndex(
        {
          cited_text: "Fallback source",
          document_index: Number.NaN,
        },
        1,
      ),
    ).toBe(2);
  });
});
