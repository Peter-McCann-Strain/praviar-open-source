"use client";

import { useState, useCallback } from "react";
import { ZoomIn, ZoomOut, Maximize2, Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PdfViewerProps {
  /** URL of the PDF to display */
  pdfUrl: string;
  /** Optional title for the viewer header */
  title?: string;
  /** Optional initial zoom level (default: 100) */
  initialZoom?: number;
}

// ---------------------------------------------------------------------------
// Zoom presets
// ---------------------------------------------------------------------------

const ZOOM_LEVELS = [50, 75, 100, 125, 150, 200] as const;
const MIN_ZOOM = ZOOM_LEVELS[0];
const MAX_ZOOM = ZOOM_LEVELS[ZOOM_LEVELS.length - 1];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * In-browser PDF viewer using an iframe with zoom and download controls.
 *
 * Uses the browser's built-in PDF renderer (via iframe) for simplicity
 * and broad compatibility without requiring additional dependencies.
 */
export function PdfViewer({
  pdfUrl,
  title = "PDF Report",
  initialZoom = 100,
}: PdfViewerProps) {
  const [zoom, setZoom] = useState(initialZoom);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const handleZoomIn = useCallback(() => {
    setZoom((prev) => {
      const next = ZOOM_LEVELS.find((z) => z > prev);
      return next ?? MAX_ZOOM;
    });
  }, []);

  const handleZoomOut = useCallback(() => {
    setZoom((prev) => {
      const next = [...ZOOM_LEVELS].reverse().find((z) => z < prev);
      return next ?? MIN_ZOOM;
    });
  }, []);

  const handleFitWidth = useCallback(() => {
    setZoom(100);
  }, []);

  // Guard against unexpected schemes (defense-in-depth; pdfUrl is
  // server-generated, but an explicit check mirrors the Stripe-redirect guard).
  // Blob URLs are used for authenticated export previews.
  const isSafePdfUrl =
    pdfUrl.startsWith("https://") ||
    pdfUrl.startsWith("/") ||
    pdfUrl.startsWith("blob:");

  const handleDownload = useCallback(() => {
    if (!isSafePdfUrl) return;
    const a = document.createElement("a");
    a.href = pdfUrl;
    a.download = title.replace(/\s+/g, "-").toLowerCase() + ".pdf";
    a.click();
  }, [isSafePdfUrl, pdfUrl, title]);

  const handleIframeLoad = useCallback(() => {
    setIsLoading(false);
  }, []);

  const handleIframeError = useCallback(() => {
    setIsLoading(false);
    setError("Failed to load PDF. The file may be unavailable or corrupted.");
  }, []);

  return (
    <div className="praviar-surface-premium flex h-full flex-col overflow-hidden rounded-lg">
      {/* Toolbar */}
      <div className="praviar-glass-strip flex items-center justify-between gap-3 border-b border-[var(--border-default)] px-4 py-2">
        <h3 className="text-sm font-medium text-[var(--text-primary)] truncate">
          {title}
        </h3>

        <div className="flex items-center gap-1">
          {/* Zoom controls */}
          <Button
            variant="ghost"
            size="icon"
            onClick={handleZoomOut}
            disabled={zoom <= MIN_ZOOM}
            title="Zoom out"
            aria-label="Zoom out"
          >
            <ZoomOut className="h-4 w-4" aria-hidden="true" />
          </Button>

          <span className="text-xs text-[var(--text-secondary)] tabular-nums min-w-[3rem] text-center">
            {zoom}%
          </span>

          <Button
            variant="ghost"
            size="icon"
            onClick={handleZoomIn}
            disabled={zoom >= MAX_ZOOM}
            title="Zoom in"
            aria-label="Zoom in"
          >
            <ZoomIn className="h-4 w-4" aria-hidden="true" />
          </Button>

          <Button
            variant="ghost"
            size="icon"
            onClick={handleFitWidth}
            title="Fit to width"
            aria-label="Fit to width"
          >
            <Maximize2 className="h-4 w-4" aria-hidden="true" />
          </Button>

          <div className="w-px h-5 bg-[var(--border-default)] mx-1" />

          {/* Download */}
          <Button
            variant="ghost"
            size="icon"
            onClick={handleDownload}
            title="Download PDF"
            aria-label="Download PDF"
          >
            <Download className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </div>

      {/* PDF content area */}
      <div className="relative flex-1 overflow-auto bg-[var(--bg-base)]">
        {/* Loading state — only while a renderable (safe) URL is loading.
            For an unsafe URL the iframe never mounts, so its onLoad would
            never fire; showing the spinner there would hang forever. */}
        {isSafePdfUrl && isLoading && !error && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 z-10 bg-[var(--bg-base)]">
            <Loader2 className="h-8 w-8 text-brand-primary animate-spin motion-reduce:animate-none" />
            <p className="text-sm text-[var(--text-secondary)]">
              Loading PDF...
            </p>
          </div>
        )}

        {/* Error state — an explicit iframe error, or an unsafe URL we refuse
            to render in the iframe. Either way, offer the download fallback
            instead of stranding the user on an endless spinner. */}
        {(error || !isSafePdfUrl) && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 z-10 bg-[var(--bg-base)]">
            <p className="text-sm text-error">
              {error ?? "This PDF could not be displayed inline."}
            </p>
            {isSafePdfUrl ? (
              <Button variant="outline" size="sm" onClick={handleDownload}>
                <Download className="h-4 w-4 mr-1.5" />
                Download instead
              </Button>
            ) : null}
          </div>
        )}

        {/* iframe PDF renderer */}
        <div
          className="flex justify-center p-4 origin-top-left"
          style={{
            transform: `scale(${zoom / 100})`,
            transformOrigin: "top center",
            width: `${10000 / zoom}%`,
          }}
        >
          {isSafePdfUrl ? (
            <iframe
              src={`${pdfUrl}#toolbar=0&navpanes=0`}
              className="w-full min-h-[calc(100vh-12rem)] rounded-lg border border-[var(--border-subtle)] bg-[var(--brand-paper)]"
              title={title}
              onLoad={handleIframeLoad}
              onError={handleIframeError}
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}
