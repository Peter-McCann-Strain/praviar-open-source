import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium shadow-[var(--shadow-xs)] transition-all duration-200 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)] disabled:pointer-events-none disabled:opacity-50 cursor-pointer",
  {
    variants: {
      variant: {
        default:
          "bg-brand-primary-dim text-[var(--brand-paper)] hover:bg-brand-primary-hover solid-btn-hover",
        destructive:
          "bg-error-emphasis text-[var(--brand-paper)] solid-btn-hover",
        outline:
          "border border-[var(--border-emphasis)] bg-transparent text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] hover:border-[var(--border-emphasis)]",
        secondary:
          "bg-[var(--surface-active)] text-[var(--text-secondary)] hover:bg-[var(--surface-active)] hover:text-[var(--text-primary)]",
        ghost:
          "text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
        link: "text-brand-primary underline-offset-4 hover:underline hover:text-brand-primary",
      },
      size: {
        default:
          "h-10 px-4 py-2 [@media(pointer:coarse)]:min-h-11 [@media(pointer:coarse)]:min-w-11",
        sm: "h-8 rounded-md px-3 text-xs [@media(pointer:coarse)]:min-h-11 [@media(pointer:coarse)]:min-w-11",
        lg: "h-11 rounded-lg px-6 text-base",
        icon: "h-10 w-10 [@media(pointer:coarse)]:h-11 [@media(pointer:coarse)]:w-11",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends
    React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant,
      size,
      asChild = false,
      loading = false,
      children,
      disabled,
      type = "button",
      ...props
    },
    ref,
  ) => {
    if (asChild) {
      return (
        <Slot
          className={cn(buttonVariants({ variant, size, className }))}
          ref={ref}
          {...props}
        >
          {children}
        </Slot>
      );
    }
    return (
      <button
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        disabled={disabled || loading}
        type={type}
        {...props}
      >
        {loading && (
          <Loader2
            className="h-4 w-4 animate-spin motion-reduce:animate-none"
            aria-hidden="true"
          />
        )}
        {children}
      </button>
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
