import { Atom, Rocket, Settings2, type LucideIcon } from "lucide-react";

interface WizardStep {
  number: number;
  label: string;
  icon: LucideIcon;
}

interface ExampleCompound {
  name: string;
  input: string;
}

export const WIZARD_STEPS: WizardStep[] = [
  { number: 1, label: "Add molecule", icon: Atom },
  { number: 2, label: "Set evidence scope", icon: Settings2 },
  { number: 3, label: "Confirm launch", icon: Rocket },
];

export const EXAMPLE_COMPOUNDS: ExampleCompound[] = [
  { name: "Succinic acid", input: "succinic acid" },
  { name: "Ibuprofen", input: "ibuprofen" },
  { name: "Aspirin", input: "aspirin" },
];
