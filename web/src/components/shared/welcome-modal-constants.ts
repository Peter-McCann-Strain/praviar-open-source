import type { ComponentType, SVGProps } from "react";
import { Atom, FileText, type LucideIcon } from "lucide-react";
import { PraviarMark } from "@/components/icons/praviar-mark";

export {
  ONBOARDING_TOUR_STORAGE_KEY,
  WELCOME_MODAL_STORAGE_KEY,
} from "@/lib/onboarding-storage";

// Accepts lucide icons plus the canonical Praviar brand mark.
export type StepIcon = LucideIcon | ComponentType<SVGProps<SVGSVGElement>>;

export interface WelcomeStep {
  eyebrow: string;
  icon: StepIcon;
  preview: "packet" | "launch" | "report";
  title: string;
  description: string;
  details: string[];
}

export const WELCOME_STEPS: WelcomeStep[] = [
  {
    eyebrow: "Evidence-first workspace",
    icon: PraviarMark,
    preview: "packet",
    title: "Welcome to Praviar",
    description:
      "Start from a molecule, keep the evidence trail visible, and hand counsel a source-linked first-pass packet.",
    details: [
      "Sources and jurisdictions stay visible",
      "Synthetic samples stay labeled",
      "Coverage gaps stay explicit",
    ],
  },
  {
    eyebrow: "Compound launch path",
    icon: Atom,
    preview: "launch",
    title: "Run Your First Analysis",
    description:
      "Enter a compound name, CAS number, SMILES string, or InChI key. Praviar records the evidence plan before the run begins.",
    details: [
      'Try "Example Molecule Alpha" or paste a fictional structure string',
      "Escalation is handled inside the adaptive pipeline",
      "Review gates remain attached to the launch packet",
    ],
  },
  {
    eyebrow: "Report handoff",
    icon: FileText,
    preview: "report",
    title: "Explore Your Report",
    description:
      "Reports summarize risk while preserving claim evidence, source provenance, design-around hypotheses, and review status.",
    details: [
      "Claim charts keep rationale beside cited patent references",
      "Exports carry caveats and provenance metadata",
      "Reviewer decisions are visible before sharing",
    ],
  },
];
