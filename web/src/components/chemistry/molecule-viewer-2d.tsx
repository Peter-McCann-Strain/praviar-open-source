"use client";

import { memo, useCallback, useEffect, useRef, useState } from "react";
import { Atom, AlertCircle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { logError } from "@/lib/error-logger";

interface MoleculeViewer2DProps {
  smiles: string;
  width?: number;
  height?: number;
  className?: string;
  /** Show loading skeleton while RDKit is loading */
  showSkeleton?: boolean;
  /** Label to display below the structure */
  label?: string;
  /** Callback when structure is rendered */
  onRender?: (success: boolean) => void;
  /**
   * Parse the input as Markush CXSMILES (RDKit ``useCXSmiles`` flag).
   * Required for MarkushGrapher output (``[*:1]Cc1ccc(C(=O)N[*:2])cc1
   * |$R1;;;;;;;;;R2$|``); vanilla SMILES parsers reject the trailing
   * ``|...|`` field. When true, the rendered SVG includes R-group labels
   * at the attachment points.
   */
  isMarkush?: boolean;
}

type LoadingState =
  | "idle"
  | "loading-rdkit"
  | "rendering"
  | "rendered"
  | "error"
  | "invalid-smiles";

const MOLECULE_STROKE_COLOR = "#0B1F24";

function normalizeRdkitSvgPalette(svg: string): string {
  return svg
    .replace(/\bfill\s*:\s*(?:#fff(?:fff)?|white)\b/gi, "fill:transparent")
    .replace(
      /\bfill\s*:\s*(?:#000(?:000)?|black)\b/gi,
      `fill:${MOLECULE_STROKE_COLOR}`,
    )
    .replace(
      /\bstroke\s*:\s*(?:#000(?:000)?|black)\b/gi,
      `stroke:${MOLECULE_STROKE_COLOR}`,
    )
    .replace(
      /\bfill\s*=\s*(['"])(?:#fff(?:fff)?|white)\1/gi,
      (_match, quote: string) => `fill=${quote}transparent${quote}`,
    )
    .replace(
      /\bfill\s*=\s*(['"])(?:#000(?:000)?|black)\1/gi,
      (_match, quote: string) =>
        `fill=${quote}${MOLECULE_STROKE_COLOR}${quote}`,
    )
    .replace(
      /\bstroke\s*=\s*(['"])(?:#000(?:000)?|black)\1/gi,
      (_match, quote: string) =>
        `stroke=${quote}${MOLECULE_STROKE_COLOR}${quote}`,
    );
}

export const MoleculeViewer2D = memo(function MoleculeViewer2D({
  smiles,
  width = 300,
  height = 200,
  className,
  showSkeleton = true,
  label,
  onRender,
  isMarkush = false,
}: MoleculeViewer2DProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<LoadingState>("idle");
  const [svgHtml, setSvgHtml] = useState<string>("");

  const renderMolecule = useCallback(async () => {
    if (!smiles.trim()) {
      setState("idle");
      setSvgHtml("");
      return;
    }

    setState("loading-rdkit");

    try {
      // Dynamically import to avoid SSR issues
      const { smilesToSVG } = await import("@/lib/rdkit-loader");

      setState("rendering");
      const svg = await smilesToSVG(smiles, {
        width,
        height,
        useCXSmiles: isMarkush,
      });

      if (svg) {
        // Normalize RDKit SVG output into the Praviar evidence palette.
        const themedSvg = normalizeRdkitSvgPalette(svg);
        setSvgHtml(themedSvg);
        setState("rendered");
        onRender?.(true);
      } else {
        setState("invalid-smiles");
        onRender?.(false);
      }
    } catch {
      logError(new Error("Structure rendering failed"), {
        source: "MoleculeViewer2D",
        extra: { action: "render_structure", isMarkush },
      });
      setState("error");
      onRender?.(false);
    }
  }, [smiles, width, height, onRender, isMarkush]);

  useEffect(() => {
    renderMolecule();
  }, [renderMolecule]);

  const frameHeight = label ? height + 32 : height;

  return (
    <div
      ref={containerRef}
      className={cn(
        "relative rounded-lg border border-[var(--border-default)] bg-[var(--surface-subtle)] overflow-hidden",
        className,
      )}
      style={{ width: "100%", maxWidth: width, height: frameHeight }}
      aria-busy={state === "loading-rdkit" || state === "rendering"}
    >
      {/* Loading state */}
      {(state === "loading-rdkit" || state === "rendering") && showSkeleton && (
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <Loader2 className="h-6 w-6 text-brand-primary animate-spin motion-reduce:animate-none mb-2" />
          <p className="text-xs font-medium text-[var(--text-secondary)]">
            {state === "loading-rdkit" ? "Loading RDKit..." : "Rendering..."}
          </p>
        </div>
      )}

      {/* Idle state: preserve the molecular identity before client hydration. */}
      {state === "idle" &&
        (smiles.trim() ? (
          <div
            className={cn(
              "absolute inset-0 flex flex-col items-center justify-center px-4 text-center",
              label && "pb-9",
            )}
          >
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              Canonical SMILES
            </p>
            <code className="mt-2 max-w-full break-all rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-3 py-2 font-mono text-xs leading-5 text-[var(--text-primary)]">
              {smiles.trim()}
            </code>
            <p className="mt-3 text-xs leading-5 text-[var(--text-secondary)]">
              Interactive structure renders when the molecular viewer loads.
            </p>
          </div>
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <Atom className="h-10 w-10 text-[var(--text-disabled)]/40 mb-1" />
            <p className="text-xs text-[var(--text-tertiary)]">
              Enter SMILES to preview
            </p>
          </div>
        ))}

      {/* Invalid SMILES */}
      {state === "invalid-smiles" && (
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <AlertCircle className="h-7 w-7 text-warning/60 mb-1" />
          <p className="text-xs text-warning/80">Invalid SMILES</p>
        </div>
      )}

      {/* Error state */}
      {state === "error" && (
        <div className="absolute inset-0 flex flex-col items-center justify-center px-3">
          <AlertCircle className="h-7 w-7 text-error/60 mb-1" />
          <p className="text-xs text-error/80">Structure preview unavailable</p>
          <p className="mt-1 text-center text-xs text-[var(--text-tertiary)]">
            Check the compound format or continue without preview.
          </p>
        </div>
      )}

      {/* Rendered SVG — rendered as <img> with a data URI to sandbox any
          scripts that may be present in the RDKit-generated SVG markup. */}
      {state === "rendered" && svgHtml && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svgHtml)}`}
          alt={
            label
              ? `Molecular structure of ${label}`
              : `Molecular structure: ${smiles}`
          }
          width={width}
          height={height}
          className="h-full w-full object-contain"
          style={label ? { paddingBottom: 32 } : undefined}
        />
      )}

      {/* Optional label */}
      {label && (
        <div className="praviar-glass-strip absolute bottom-0 inset-x-0 px-2 py-1.5 text-center">
          <p className="text-xs text-[var(--text-secondary)] truncate">
            {label}
          </p>
        </div>
      )}
    </div>
  );
});
