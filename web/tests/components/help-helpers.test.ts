import { describe, expect, it } from "vitest";
import {
  DEFAULT_STEP_ICON,
  FAQ,
  GETTING_STARTED_STEPS,
  GLOSSARY,
  SECTION_LINKS,
  STEP_DESCRIPTIONS,
  STEP_ICONS,
  highlightFaqAnswer,
  matchesHelpQuery,
} from "@/components/help/helpers";

describe("help page metadata", () => {
  it("describes every pipeline step with an icon", () => {
    expect(Object.keys(STEP_DESCRIPTIONS)).toEqual([
      "1",
      "2",
      "3",
      "4",
      "5",
      "6",
      "7",
      "8",
    ]);
    for (const step of Object.keys(STEP_DESCRIPTIONS).map(Number)) {
      expect(STEP_DESCRIPTIONS[step]).toContain(" ");
      expect(STEP_ICONS[step]).toBeTruthy();
    }
    expect(DEFAULT_STEP_ICON).toBeTruthy();
  });

  it("keeps quick links, getting started cards, and glossary entries populated", () => {
    expect(SECTION_LINKS.map((link) => link.href)).toEqual([
      "#common-tasks",
      "#getting-started",
      "#pipeline-steps",
      "#faq",
      "#glossary",
      "#risk-levels",
      "#shortcuts",
      "#contact",
    ]);
    expect(GETTING_STARTED_STEPS).toHaveLength(3);
    expect(GETTING_STARTED_STEPS[0]).toMatchObject({
      step: 1,
      title: "Enter a compound",
    });
    expect(GLOSSARY.length).toBeGreaterThan(8);
    expect(GLOSSARY.map((entry) => entry.term)).toContain(
      "FTO (Freedom to Operate)",
    );
  });

  it("highlights FAQ keywords and matches help search queries", () => {
    expect(highlightFaqAnswer("Export to PDF with evidence citations")).toEqual(
      expect.arrayContaining([
        { highlighted: true, text: "PDF" },
        { highlighted: true, text: "evidence citations" },
      ]),
    );
    expect(matchesHelpQuery("", "anything")).toBe(true);
    expect(matchesHelpQuery("claim", "Claim Chart", "Other")).toBe(true);
    expect(matchesHelpQuery("missing", "Claim Chart", "Other")).toBe(false);
  });

  it("keeps the confidentiality FAQ fail-closed for the research preview", () => {
    const confidentialityFaq = FAQ.find(
      (item) => item.q === "Is my data kept confidential?",
    );

    expect(confidentialityFaq?.a).toContain(
      "No confidentiality assurance is made",
    );
    expect(confidentialityFaq?.a).toContain(
      "Do not enter confidential matter data",
    );
    expect(confidentialityFaq?.a).toContain(
      "not evidence of an operated service",
    );
    expect(confidentialityFaq?.a).not.toContain(
      "We do not share your data with third parties or use it for model training.",
    );
  });
});
