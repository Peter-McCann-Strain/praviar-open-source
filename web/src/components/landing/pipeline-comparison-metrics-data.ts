import { BookOpen, FileWarning, Scale, ShieldCheck } from "lucide-react";

export const METRICS = [
  {
    label: "Intake",
    icon: BookOpen,
    value: "Compound, claims, and sources enter one adaptive runtime",
  },
  {
    label: "Evidence Gap",
    icon: FileWarning,
    value: "Missing support is identified before conclusions harden",
  },
  {
    label: "Escalation",
    icon: ShieldCheck,
    value: "Reasons, excerpts, and affected elements are recorded",
  },
  {
    label: "Handoff",
    icon: Scale,
    value: "Citations and open questions are ready for counsel review",
  },
] as const;
