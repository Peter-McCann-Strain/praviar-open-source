import type { TraceStep } from "@/components/landing/pipeline-comparison-types";

export const ADAPTIVE_TIMELINE_TRACE: TraceStep[] = [
  { type: "input", text: "Compound + patent claims received", delay: 0 },
  {
    type: "step",
    text: "Intake normalized with deterministic claim structure",
    delay: 0.5,
  },
  {
    type: "step",
    text: "Independent and dependent elements decomposed",
    delay: 1.1,
  },
  {
    type: "critique",
    text: "Evidence gap identified: one claim term needs specification support",
    delay: 1.8,
  },
  {
    type: "step",
    text: "Escalation recorded with reason and affected claim element",
    delay: 2.5,
  },
  {
    type: "step",
    text: "Specification excerpts attached to the evidence record",
    delay: 3.2,
  },
  {
    type: "element",
    text: "Element 1a: specification-supported match recorded",
    delay: 3.9,
    status: "met",
  },
  {
    type: "element",
    text: "Element 1b: unresolved limitation preserved for counsel",
    delay: 4.6,
    status: "not_met",
  },
  {
    type: "element",
    text: "Element 1c: specification-supported match recorded",
    delay: 5.3,
    status: "met",
  },
  {
    type: "critique",
    text: "Independent verification checks cited support and open questions",
    delay: 6,
  },
  {
    type: "risk",
    text: "Risk summary reconciled against potential blocker evidence",
    delay: 6.8,
    risk: "medium",
  },
  {
    type: "complete",
    text: "Governed escalation record ready for counsel handoff",
    delay: 7.6,
  },
];

export const MAX_DELAY = Math.max(
  ...ADAPTIVE_TIMELINE_TRACE.map((step) => step.delay),
);
