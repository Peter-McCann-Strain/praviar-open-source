import { ChevronLeft, ChevronRight, Info } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ConfigurationFooterProps {
  canContinue: boolean;
  continueBlocker: string | null;
  onBack: () => void;
  onNext: () => void;
}

export function ConfigurationFooter({
  canContinue,
  continueBlocker,
  onBack,
  onNext,
}: ConfigurationFooterProps) {
  return (
    <>
      <div className="flex items-start gap-2 rounded-lg bg-[var(--surface-subtle)] p-3">
        <Info className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--text-tertiary)]" />
        <p className="text-xs leading-relaxed text-[var(--text-tertiary)]">
          Tanimoto threshold controls structural similarity matching. Lower
          values cast a wider net but may return less relevant patents. Citation
          traversal follows patent references to discover related prior art.
        </p>
      </div>

      {!canContinue ? (
        <div
          className="rounded-lg border border-warning/25 bg-warning/10 p-3 text-sm text-warning"
          role="status"
          aria-live="polite"
        >
          {continueBlocker ??
            "Resolve configuration checks before reviewing the launch packet."}
        </div>
      ) : null}

      <div className="flex flex-col-reverse justify-between gap-3 sm:flex-row">
        <Button
          variant="outline"
          onClick={onBack}
          className="min-h-11 w-full gap-2 sm:w-auto"
        >
          <ChevronLeft className="h-4 w-4" />
          Back
        </Button>
        <Button
          onClick={onNext}
          disabled={!canContinue}
          className="min-h-11 w-full gap-2 sm:w-auto"
        >
          Next: Review
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </>
  );
}
