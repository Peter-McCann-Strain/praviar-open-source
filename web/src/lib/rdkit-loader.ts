/**
 * RDKit.js WASM Singleton Loader
 *
 * Loads the ~8MB RDKit WASM module once and caches it.
 * Self-hosted from /public/rdkit/ (v2025.3.4-1.0.0).
 */

/** RDKit.js exposes initRDKitModule on the global window object after script load. */
declare global {
  interface Window {
    initRDKitModule?: (options: {
      locateFile: () => string;
    }) => Promise<RDKitModule>;
  }
}

interface RDKitModule {
  /**
   * Parse a SMILES (or CXSMILES, when ``details`` enables it).
   *
   * RDKit-WASM accepts an optional second JSON-encoded options string. To
   * parse a Markush CXSMILES with R-group placeholders (e.g.
   * ``[*:1]Cc1ccc(C(=O)N[*:2])cc1 |$R1;;;;;;;;;R2$|``) pass
   * ``JSON.stringify({ useCXSmiles: true })`` so the engine treats the
   * trailing ``|...|`` block as a coordinate template + R-group field
   * rather than rejecting it as invalid SMILES.
   */
  get_mol: (smiles: string, details?: string) => RDKitMol | null;
  get_mol_from_molblock: (molblock: string) => RDKitMol | null;
  prefer_coordgen: (prefer: boolean) => void;
  version: () => string;
}

interface RDKitMol {
  get_svg: (width?: number, height?: number) => string;
  get_svg_with_highlights: (details: string) => string;
  get_molblock: () => string;
  get_smiles: () => string;
  get_inchi: () => string;
  get_descriptors: () => string;
  get_morgan_fp: (radius?: number, nBits?: number) => string;
  get_substruct_match: (query: RDKitMol) => string;
  delete: () => void;
  is_valid: () => boolean;
}

export type { RDKitModule, RDKitMol };

// Self-hosted RDKit.js WASM build in /public/rdkit/
// Override via NEXT_PUBLIC_RDKIT_CDN_URL if needed
const RDKIT_JS_URL =
  process.env.NEXT_PUBLIC_RDKIT_CDN_URL ?? "/rdkit/RDKit_minimal.js";
const RDKIT_WASM_URL = "/rdkit/RDKit_minimal.wasm";

let rdkitPromise: Promise<RDKitModule> | null = null;
let rdkitModule: RDKitModule | null = null;

/**
 * Load the RDKit WASM module (singleton — loads only once).
 * Subsequent calls return the cached module immediately.
 */
export function loadRDKit(): Promise<RDKitModule> {
  if (rdkitModule) return Promise.resolve(rdkitModule);

  if (!rdkitPromise) {
    rdkitPromise = new Promise<RDKitModule>((resolve, reject) => {
      const rejectAndAllowRetry = (error: unknown) => {
        rdkitPromise = null;
        reject(error);
      };

      if (typeof window === "undefined") {
        rejectAndAllowRetry(
          new Error("RDKit.js requires a browser environment"),
        );
        return;
      }

      // locateFile ensures the WASM binary is fetched from a fixed absolute
      // path regardless of the current page route (e.g. /analyses/123/report)
      const initOptions = { locateFile: () => RDKIT_WASM_URL };

      // Check if already loaded globally
      if (window.initRDKitModule) {
        window
          .initRDKitModule(initOptions)
          .then((mod: RDKitModule) => {
            rdkitModule = mod;
            mod.prefer_coordgen(true);
            resolve(mod);
          })
          .catch(rejectAndAllowRetry);
        return;
      }

      // Load the RDKit.js script
      const script = document.createElement("script");
      script.src = RDKIT_JS_URL;
      script.async = true;

      script.onload = () => {
        if (!window.initRDKitModule) {
          rejectAndAllowRetry(
            new Error("RDKit.js loaded but initRDKitModule not found"),
          );
          return;
        }
        window
          .initRDKitModule(initOptions)
          .then((mod: RDKitModule) => {
            rdkitModule = mod;
            mod.prefer_coordgen(true);
            resolve(mod);
          })
          .catch(rejectAndAllowRetry);
      };

      script.onerror = () => {
        rejectAndAllowRetry(new Error("Failed to load RDKit.js from CDN"));
      };

      document.head.appendChild(script);
    });
  }

  return rdkitPromise;
}

export interface SmilesToSVGOptions {
  /**
   * Parse the input as CXSMILES (RDKit ``useCXSmiles`` flag). Required for
   * Markush structures emitted by MarkushGrapher — they include a trailing
   * ``|$R1;;;R2$|`` field that vanilla SMILES parsers reject.
   */
  useCXSmiles?: boolean;
  width?: number;
  height?: number;
}

/**
 * Render a SMILES (or CXSMILES) string to an SVG string.
 * Returns null if the input is invalid or RDKit isn't loaded.
 *
 * @example
 *   await smilesToSVG("CCO");                                  // ethanol
 *   await smilesToSVG(markushCxsmiles, { useCXSmiles: true }); // Markush
 */
export async function smilesToSVG(
  smiles: string,
  optionsOrWidth?: SmilesToSVGOptions | number,
  height = 200,
): Promise<string | null> {
  // Backwards compat: legacy callers pass `(smiles, width, height)` as
  // positional numbers. New callers pass a single options object.
  const opts: SmilesToSVGOptions =
    typeof optionsOrWidth === "object" && optionsOrWidth !== null
      ? optionsOrWidth
      : { width: optionsOrWidth, height };
  const w = opts.width ?? 300;
  const h = opts.height ?? height ?? 200;

  const rdkit = await loadRDKit();
  const details = opts.useCXSmiles
    ? JSON.stringify({ useCXSmiles: true })
    : undefined;
  const mol = details ? rdkit.get_mol(smiles, details) : rdkit.get_mol(smiles);
  if (!mol || !mol.is_valid()) {
    mol?.delete();
    return null;
  }

  const svg = mol.get_svg(w, h);
  mol.delete();
  return svg;
}
