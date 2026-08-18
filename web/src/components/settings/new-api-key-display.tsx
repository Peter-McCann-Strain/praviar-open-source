"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Copy, Shield, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { copyTextToClipboard } from "@/components/report/share-analytics-helpers";

interface NewApiKeyDisplayProps {
  apiKey: string;
  onDismiss: () => void;
}

export function NewApiKeyDisplay({ apiKey, onDismiss }: NewApiKeyDisplayProps) {
  const [copied, setCopied] = useState(false);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (copyTimerRef.current !== null) clearTimeout(copyTimerRef.current);
    },
    [],
  );

  const handleCopy = async () => {
    try {
      // The secret key is shown exactly once, so the copy button must work even
      // in insecure/HTTP contexts where the async Clipboard API is unavailable.
      // copyTextToClipboard falls back to a hidden-textarea execCommand path.
      await copyTextToClipboard(apiKey);
      setCopied(true);
      if (copyTimerRef.current !== null) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      // Last-resort: selection still works via the visible select-all code block.
    }
  };

  return (
    <Card className="overflow-hidden border-warning/30 bg-warning/[0.05]">
      <CardHeader className="border-b border-warning/20">
        <div className="flex items-center justify-between">
          <CardTitle
            className="flex items-center gap-2 text-sm text-[var(--text-primary)]"
            role="heading"
            aria-level={3}
          >
            <Shield className="h-4 w-4 text-warning" aria-hidden="true" />
            API key created
          </CardTitle>
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss new API key panel"
            className="flex h-11 w-11 items-center justify-center rounded-md text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-2 rounded-lg border border-[var(--border-emphasis)] bg-[var(--surface-muted)] p-3">
          <code
            aria-label="New API key secret"
            className="min-w-0 flex-1 select-all overflow-x-auto whitespace-nowrap font-mono text-xs text-[var(--text-primary)] sm:text-sm"
            tabIndex={0}
          >
            {apiKey}
          </code>
          <Button
            variant="ghost"
            size="icon"
            className="min-h-11 min-w-11"
            onClick={handleCopy}
            title="Copy to clipboard"
            aria-label={copied ? "Copied" : "Copy API key to clipboard"}
          >
            {copied ? (
              <Check className="h-4 w-4 text-success" aria-hidden="true" />
            ) : (
              <Copy className="h-4 w-4" aria-hidden="true" />
            )}
          </Button>
        </div>
        <p className="sr-only" aria-live="polite">
          {copied ? "API key copied to clipboard" : ""}
        </p>
        <div className="flex items-start gap-2 rounded-lg border border-warning/20 bg-warning/[0.07] px-3 py-2">
          <Shield className="mt-0.5 h-4 w-4 flex-shrink-0 text-warning" />
          <p className="text-xs text-warning">
            Shown once. Anyone with this key can access organization data within
            its permissions. Store it in a secrets manager; Praviar cannot
            recover it.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
