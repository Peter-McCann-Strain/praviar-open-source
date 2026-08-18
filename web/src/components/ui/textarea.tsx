import * as React from "react";
import { AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  error?: boolean;
  errorMessage?: string;
  errorId?: string;
}

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, error, errorMessage, errorId, ...props }, ref) => {
    return (
      <div className="w-full">
        <textarea
          className={cn(
            "praviar-glass-field flex min-h-[80px] w-full rounded-lg px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-disabled)] transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-[var(--bg-base)] disabled:cursor-not-allowed disabled:opacity-50 resize-y",
            error
              ? "border-error focus:border-error/60 focus:ring-error/70"
              : "border-[var(--border-emphasis)] focus:border-brand-primary/60 focus:ring-brand-primary/70",
            className,
          )}
          ref={ref}
          aria-invalid={error || undefined}
          aria-describedby={error && errorId ? errorId : undefined}
          {...props}
        />
        {error && errorMessage && (
          <p
            id={errorId}
            className="mt-1.5 flex items-center gap-1 text-xs text-error"
            role="alert"
            aria-live="polite"
          >
            <AlertCircle className="h-3 w-3 flex-shrink-0" />
            {errorMessage}
          </p>
        )}
      </div>
    );
  },
);
Textarea.displayName = "Textarea";

export { Textarea };
