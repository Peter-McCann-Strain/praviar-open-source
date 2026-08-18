"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RotateCcw, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { logError } from "@/lib/error-logger";

interface Props {
  children: ReactNode;
  /** Heading shown in the fallback UI. */
  title?: string;
  /** If true, render nothing instead of fallback UI on error (for non-critical components). */
  silent?: boolean;
  /**
   * When any value in this array changes between renders, the boundary clears
   * its error state. Use this to recover automatically when the underlying
   * subject changes (e.g. navigating to a different report id) instead of
   * showing a stale crash from the previous subject.
   */
  resetKeys?: ReadonlyArray<unknown>;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * Reusable error boundary for isolating component crashes.
 *
 * Wrap crash-prone components (RDKit WASM, charts, individual report tabs)
 * so a failure in one doesn't take down the entire page.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    logError(error, {
      source: "ErrorBoundary",
      extra: { hasComponentStack: Boolean(info.componentStack) },
    });
  }

  componentDidUpdate(prevProps: Props) {
    if (!this.state.hasError) return;
    const prevKeys = prevProps.resetKeys;
    const nextKeys = this.props.resetKeys;
    if (!prevKeys || !nextKeys) return;
    const changed =
      prevKeys.length !== nextKeys.length ||
      nextKeys.some((key, index) => !Object.is(key, prevKeys[index]));
    if (changed) {
      this.setState({ hasError: false, error: null });
    }
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.silent) return null;

      return (
        <div
          role="alert"
          data-praviar-app-state="error"
          className="praviar-surface-premium flex min-h-[120px] flex-col items-center justify-center gap-3 rounded-lg p-6 text-center"
        >
          <AlertTriangle
            className="h-6 w-6 text-[var(--color-warning)]"
            aria-hidden="true"
          />
          <p className="text-sm font-medium text-[var(--text-primary)]">
            {this.props.title ?? "This section failed to load"}
          </p>
          <p className="max-w-md text-sm leading-6 text-[var(--text-secondary)]">
            This section hit a recoverable rendering error. The rest of the
            report is still available, and retrying will render this section
            again.
          </p>
          <div className="praviar-glass-chip flex min-w-0 items-center gap-2 rounded-lg px-3 py-2 text-xs text-[var(--text-tertiary)]">
            <ShieldCheck
              className="h-3.5 w-3.5 text-brand-primary"
              aria-hidden="true"
            />
            Full diagnostic details stay in logs, not the workspace UI.
          </div>
          <Button variant="outline" size="sm" onClick={this.handleReset}>
            <RotateCcw className="h-3 w-3" aria-hidden="true" />
            Retry
          </Button>
        </div>
      );
    }

    return this.props.children;
  }
}
