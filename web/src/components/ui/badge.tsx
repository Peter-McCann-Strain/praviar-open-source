import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold shadow-[var(--shadow-xs)] transition-colors",
  {
    variants: {
      variant: {
        default:
          "border-brand-primary/25 bg-brand-primary/10 text-brand-primary",
        secondary:
          "border-[var(--border-default)] bg-[var(--surface-active)] text-[var(--text-secondary)]",
        destructive:
          "border-error/25 bg-error/10 text-[var(--color-error-badge-fg)]",
        warning: "border-warning/25 bg-warning/10 text-warning",
        success: "border-success/25 bg-success/10 text-success",
        outline: "border-[var(--border-emphasis)] text-[var(--text-secondary)]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends
    React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
