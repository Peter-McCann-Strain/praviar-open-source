import * as React from "react";
import { cn } from "@/lib/utils";

/** Static card — displays content with premium light depth, no hover interaction. */
const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "praviar-surface-premium rounded-lg border border-[var(--card-border)] transition-colors duration-200",
      className,
    )}
    {...props}
  />
));
Card.displayName = "Card";

/** Interactive card — hover-lift + pointer for clickable cards. */
const CardInteractive = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "praviar-surface-premium cursor-pointer rounded-lg border border-[var(--card-border)] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow-md)]",
      className,
    )}
    {...props}
  />
));
CardInteractive.displayName = "CardInteractive";

const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex flex-col space-y-1.5 p-6", className)}
    {...props}
  />
));
CardHeader.displayName = "CardHeader";

const CardTitle = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(
  (
    { className, role = "heading", "aria-level": ariaLevel = 3, ...props },
    ref,
  ) => (
    <div
      ref={ref}
      role={role}
      aria-level={ariaLevel}
      className={cn("type-heading-md text-[var(--text-primary)]", className)}
      {...props}
    />
  ),
);
CardTitle.displayName = "CardTitle";

const CardDescription = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("text-sm text-[var(--text-secondary)]", className)}
    {...props}
  />
));
CardDescription.displayName = "CardDescription";

const CardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("p-6 pt-0", className)} {...props} />
));
CardContent.displayName = "CardContent";

export {
  Card,
  CardInteractive,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
};
