"use client";

import { useId, useState, useCallback, useMemo, type Ref } from "react";
import { Atom, Clipboard, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { MoleculeViewer2D } from "./molecule-viewer-2d";
import { cn } from "@/lib/utils";
import { logError } from "@/lib/error-logger";

export type InputType =
  | "SMILES"
  | "InChI"
  | "InChIKey"
  | "CAS Number"
  | "Name"
  | null;

export type CompoundInputReadinessStatus =
  | "empty"
  | "ready"
  | "needs_identifier"
  | "malformed_identifier";

export interface CompoundInputReadiness {
  canProceed: boolean;
  detail: string;
  inputType: InputType;
  label: string;
  status: CompoundInputReadinessStatus;
}

const ORGANIC_ATOMS = new Set(["B", "C", "N", "O", "P", "S", "F", "I"]);
const AROMATIC_ATOMS = new Set(["b", "c", "n", "o", "p", "s"]);
const CAS_NUMBER_PATTERN = /^\d{2,7}-\d{2}-\d$/;
const CAS_PREFIX_PATTERN =
  /^CAS(?:[\u0009-\u000D\u0020\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000\uFEFF]*(?:RN|No\.?|#|:))?[\u0009-\u000D\u0020\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000\uFEFF]*/i;
const ECMASCRIPT_WHITESPACE_PATTERN =
  /[\u0009-\u000D\u0020\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000\uFEFF]/;
const INCHIKEY_PATTERN = /^[A-Z]{14}-[A-Z]{10}-[A-Z]$/i;
const INCHIKEY_NEAR_MISS_PATTERN = /^[A-Z]{8,16}-[A-Z]{6,12}(?:-[A-Z])?$/i;
const MAX_NAME_IDENTIFIER_LENGTH = 180;

function isLikelySmiles(input: string): boolean {
  if (!input || ECMASCRIPT_WHITESPACE_PATTERN.test(input)) {
    return false;
  }

  let atomCount = 0;
  let hasStructureMarker = false;

  for (let index = 0; index < input.length; index += 1) {
    const char = input[index];
    const next = input[index + 1];

    if (char === "[") {
      const closeIndex = input.indexOf("]", index + 1);
      if (closeIndex === -1) {
        return false;
      }
      atomCount += 1;
      hasStructureMarker = true;
      index = closeIndex;
      continue;
    }

    if (char === "C" && next === "l") {
      atomCount += 1;
      index += 1;
      continue;
    }

    if (char === "B" && next === "r") {
      atomCount += 1;
      index += 1;
      continue;
    }

    if (ORGANIC_ATOMS.has(char) || AROMATIC_ATOMS.has(char)) {
      atomCount += 1;
      continue;
    }

    if ("-=#$:/\\.()".includes(char)) {
      hasStructureMarker = true;
      continue;
    }

    if (char === "%") {
      if (!/^\d{2}$/.test(input.slice(index + 1, index + 3))) {
        return false;
      }
      hasStructureMarker = true;
      index += 2;
      continue;
    }

    if (/^[1-9]$/.test(char)) {
      hasStructureMarker = true;
      continue;
    }

    if (char === "*") {
      atomCount += 1;
      hasStructureMarker = true;
      continue;
    }

    return false;
  }

  return atomCount >= 2 || (atomCount === 1 && hasStructureMarker);
}

function normalizeCasInput(input: string): string | null {
  const withoutPrefix = input.trim().replace(CAS_PREFIX_PATTERN, "");

  return CAS_NUMBER_PATTERN.test(withoutPrefix) ? withoutPrefix : null;
}

function hasValidCasChecksum(casNumber: string): boolean {
  const digits = casNumber.replaceAll("-", "");
  const checksum = Number(digits.at(-1));
  const weightedSum = digits
    .slice(0, -1)
    .split("")
    .reverse()
    .reduce((sum, digit, index) => sum + Number(digit) * (index + 1), 0);

  return weightedSum % 10 === checksum;
}

function isLikelyValidInchi(input: string): boolean {
  return /^InChI=1S?\/[A-Za-z0-9]/.test(input.trim());
}

function getSmilesSyntaxIssue(input: string): string | null {
  let branchDepth = 0;
  const ringCounts = new Map<string, number>();

  for (let index = 0; index < input.length; index += 1) {
    const char = input[index];

    if (char === "[") {
      const closeIndex = input.indexOf("]", index + 1);
      if (closeIndex === -1) {
        return "Complete the bracketed atom before continuing.";
      }
      index = closeIndex;
      continue;
    }

    if (char === "(") {
      branchDepth += 1;
      continue;
    }

    if (char === ")") {
      branchDepth -= 1;
      if (branchDepth < 0) {
        return "Check the branch parentheses before continuing.";
      }
      continue;
    }

    if (/^[1-9]$/.test(char)) {
      ringCounts.set(char, (ringCounts.get(char) ?? 0) + 1);
      continue;
    }

    if (char === "%") {
      const ringId = input.slice(index + 1, index + 3);
      if (!/^\d{2}$/.test(ringId)) {
        return "Use two digits after % for SMILES ring closures.";
      }
      ringCounts.set(ringId, (ringCounts.get(ringId) ?? 0) + 1);
      index += 2;
    }
  }

  if (branchDepth !== 0) {
    return "Complete the SMILES branch parentheses before continuing.";
  }

  const hasUnmatchedRing = Array.from(ringCounts.values()).some(
    (count) => count % 2 !== 0,
  );
  if (hasUnmatchedRing) {
    return "Complete each SMILES ring closure before continuing.";
  }

  return null;
}

function getNameIdentifierIssue(input: string): string | null {
  if (!/[A-Za-z0-9]/.test(input)) {
    return "Enter a compound name, code, SMILES, InChI, InChIKey, or CAS number.";
  }

  if (/^\d+$/.test(input)) {
    return "Add a resolvable identifier, such as a CAS number with hyphens or a compound name.";
  }

  if (input.length > MAX_NAME_IDENTIFIER_LENGTH) {
    return "Shorten this to a compound identifier rather than a pasted abstract or notes.";
  }

  if (/[\r\n]/.test(input)) {
    return "Use one compound identifier at a time before launch.";
  }

  if (/(?:https?:\/\/|www\.)/i.test(input)) {
    return "Enter the compound identifier itself rather than a source URL.";
  }

  if (/^\s*[\[{].*[\]}]\s*$/.test(input)) {
    return "Paste a compound identifier rather than JSON or structured notes.";
  }

  if (!/^[A-Za-z0-9\s,.'+\-()/[\]:]+$/.test(input)) {
    return "Remove non-identifier characters before continuing.";
  }

  if (input.trim().split(/\s+/).length > 12) {
    return "Use a concise compound name or project code before launch.";
  }

  return null;
}

interface SmilesInputProps {
  value: string;
  onChange: (value: string) => void;
  onInputTypeChange?: (type: InputType) => void;
  inputRef?: Ref<HTMLInputElement>;
  placeholder?: string;
  className?: string;
  showPreview?: boolean;
}

export function detectInputType(input: string): InputType {
  const normalizedInput = input.trim();
  if (!normalizedInput) return null;
  if (normalizeCasInput(normalizedInput)) return "CAS Number";
  if (/^InChI=/.test(normalizedInput)) return "InChI";
  if (INCHIKEY_PATTERN.test(normalizedInput)) return "InChIKey";
  if (isLikelySmiles(normalizedInput)) return "SMILES";
  return "Name";
}

export function getCompoundInputReadiness(
  input: string,
): CompoundInputReadiness {
  const normalizedInput = input.trim();
  const inputType = detectInputType(normalizedInput);

  if (!normalizedInput) {
    return {
      canProceed: false,
      detail:
        "Enter a compound name, SMILES, InChI, InChIKey, CAS number, or internal project code.",
      inputType,
      label: "Awaiting compound",
      status: "empty",
    };
  }

  const casNumber = normalizeCasInput(normalizedInput);
  if (casNumber) {
    if (!hasValidCasChecksum(casNumber)) {
      return {
        canProceed: false,
        detail:
          "The CAS checksum does not match. Check the digits before using a Report Credit.",
        inputType: "CAS Number",
        label: "CAS checksum needs review",
        status: "malformed_identifier",
      };
    }

    return {
      canProceed: true,
      detail:
        "CAS number format and checksum look valid. Structure resolution is checked before claim search.",
      inputType: "CAS Number",
      label: "CAS number ready",
      status: "ready",
    };
  }

  if (inputType === "InChI") {
    if (!isLikelyValidInchi(normalizedInput)) {
      return {
        canProceed: false,
        detail:
          "This starts like an InChI but is missing the version and formula path.",
        inputType,
        label: "Malformed InChI",
        status: "malformed_identifier",
      };
    }

    return {
      canProceed: true,
      detail:
        "InChI format is present. Structure resolution is checked before claim search.",
      inputType,
      label: "InChI ready",
      status: "ready",
    };
  }

  if (
    inputType !== "InChIKey" &&
    INCHIKEY_NEAR_MISS_PATTERN.test(normalizedInput)
  ) {
    return {
      canProceed: false,
      detail:
        "This looks like an InChIKey but the 14-10-1 character groups are incomplete.",
      inputType: "Name",
      label: "InChIKey needs review",
      status: "malformed_identifier",
    };
  }

  if (inputType === "InChIKey") {
    return {
      canProceed: true,
      detail:
        "InChIKey format looks valid. Structure resolution is checked before claim search.",
      inputType,
      label: "InChIKey ready",
      status: "ready",
    };
  }

  if (inputType === "SMILES") {
    const smilesIssue = getSmilesSyntaxIssue(normalizedInput);
    if (smilesIssue) {
      return {
        canProceed: false,
        detail: smilesIssue,
        inputType,
        label: "SMILES needs review",
        status: "malformed_identifier",
      };
    }

    return {
      canProceed: true,
      detail:
        "SMILES syntax looks complete. Preview confirms rendering when available.",
      inputType,
      label: "SMILES detected",
      status: "ready",
    };
  }

  const nameIssue = getNameIdentifierIssue(normalizedInput);
  if (nameIssue) {
    return {
      canProceed: false,
      detail: nameIssue,
      inputType,
      label: "Needs compound identifier",
      status: "needs_identifier",
    };
  }

  return {
    canProceed: true,
    detail:
      "Name or project code accepted. Structure resolution is checked before claim search.",
    inputType,
    label: "Identifier ready",
    status: "ready",
  };
}

export function SmilesInput({
  value,
  onChange,
  onInputTypeChange,
  inputRef,
  placeholder = "e.g., succinic acid, OC(=O)CCC(O)=O, 110-15-6",
  className,
  showPreview = true,
}: SmilesInputProps) {
  const inputType = useMemo(() => detectInputType(value), [value]);
  const [renderedSmiles, setRenderedSmiles] = useState<string | null>(null);
  const inputId = useId();

  const handleChange = useCallback(
    (newValue: string) => {
      onChange(newValue);
      const type = detectInputType(newValue);
      onInputTypeChange?.(type);
    },
    [onChange, onInputTypeChange],
  );

  const handlePaste = useCallback(async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        handleChange(text.trim());
      }
    } catch (err) {
      logError(err, {
        source: "SmilesInput",
        extra: { action: "read_clipboard" },
      });
    }
  }, [handleChange]);

  const handleClear = useCallback(() => {
    handleChange("");
  }, [handleChange]);

  const isPreviewableSmiles = inputType === "SMILES";
  const isInchiPendingResolution = inputType === "InChI";

  return (
    <div className={cn("space-y-4", className)}>
      {/* Input field with type badge */}
      <div className="relative">
        <label htmlFor={inputId} className="sr-only">
          Compound input
        </label>
        <div className="relative">
          <Atom className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-[var(--text-tertiary)]" />
          <Input
            ref={inputRef}
            id={inputId}
            value={value}
            onChange={(e) => handleChange(e.target.value)}
            placeholder={placeholder}
            autoComplete="off"
            className="h-14 pl-11 pr-4 font-mono text-sm sm:pr-44 sm:text-lg"
          />
        </div>
        <div className="mt-2 flex items-center justify-end gap-1.5 sm:absolute sm:right-2 sm:top-1/2 sm:mt-0 sm:-translate-y-1/2">
          {inputType && (
            <span className="rounded-full bg-brand-primary/20 px-2.5 py-1 text-xs font-medium text-brand-primary">
              {inputType}
            </span>
          )}
          {value && (
            <button
              type="button"
              onClick={handleClear}
              className="flex h-11 w-11 items-center justify-center rounded-md text-[var(--text-tertiary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
              title="Clear"
              aria-label="Clear input"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
          <button
            type="button"
            onClick={handlePaste}
            className="flex h-11 w-11 items-center justify-center rounded-md text-[var(--text-tertiary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-brand-primary"
            title="Paste from clipboard"
            aria-label="Paste from clipboard"
          >
            <Clipboard className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* Live molecule preview */}
      {showPreview && value && isPreviewableSmiles && (
        <div className="flex min-w-0 justify-center">
          <div
            className="min-w-0 w-full max-w-[25rem]"
            data-testid="smiles-preview-frame"
          >
            <MoleculeViewer2D
              smiles={value}
              width={400}
              height={280}
              label={renderedSmiles === value ? value : undefined}
              onRender={(success) => setRenderedSmiles(success ? value : null)}
            />
          </div>
        </div>
      )}
      {showPreview && value && isInchiPendingResolution && (
        <p
          role="status"
          className="rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)] px-3 py-2 text-sm text-[var(--text-secondary)]"
        >
          InChI detected. Structure preview will appear after resolution.
        </p>
      )}
    </div>
  );
}
